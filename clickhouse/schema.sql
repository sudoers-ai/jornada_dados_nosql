-- ==========================================================================
-- ClickHouse - schema da Liga Sudoers (COLUNAR ANALITICO)
--
-- ATENCAO: "colunar" aqui NAO e a mesma coisa que o Cassandra.
--
--   Cassandra  = wide-column store. Guarda LINHAS agrupadas por particao.
--                Otimizado para ESCRITA e leitura por chave.
--   ClickHouse = colunar analitico. Guarda cada COLUNA junta em disco.
--                Otimizado para AGREGACAO sobre bilhoes de linhas.
--
-- Se voce so lembrar de uma coisa desta pasta, lembre disto:
--   somar 1 bilhao de valores no Cassandra e um pesadelo.
--   somar 1 bilhao de valores no ClickHouse leva menos de 1 segundo.
--   E o Cassandra aguenta uma carga de escrita que derruba o ClickHouse.
--
-- POR QUE COLUNAR E RAPIDO EM AGREGACAO?
--   SELECT sum(valor_total) FROM fato_pedidos
--   Num banco de linhas, o disco le a linha INTEIRA (todas as colunas) so
--   para pegar uma. Num colunar, le so o arquivo daquela coluna. E como
--   valores da mesma coluna sao parecidos entre si, comprimem MUITO melhor.
-- ==========================================================================

CREATE DATABASE IF NOT EXISTS liga_sudoers;

-- --------------------------------------------------------------------------
-- Dimensoes
-- --------------------------------------------------------------------------
-- LowCardinality(String) = dicionario interno. Para colunas com poucos
-- valores distintos (UF, categoria, sexo) economiza memoria e acelera GROUP BY.
DROP TABLE IF EXISTS liga_sudoers.dim_pessoas;
CREATE TABLE liga_sudoers.dim_pessoas (
    id_pessoa   UInt32,
    nome        String,
    sexo        LowCardinality(String),
    -- Date32, nao Date: o tipo Date do ClickHouse so vai de 1970 a 2149,
    -- e temos clientes nascidos antes disso. Date32 cobre 1900-2299.
    dt_nasc     Date32,
    cpf         String,
    email       String,
    uf          LowCardinality(String),
    cidade      String,
    device_id   String,
    dispositivo LowCardinality(String)
) ENGINE = MergeTree()
ORDER BY id_pessoa;

DROP TABLE IF EXISTS liga_sudoers.dim_produtos;
CREATE TABLE liga_sudoers.dim_produtos (
    id_produto  UInt32,
    descricao   String,
    categoria   LowCardinality(String),
    valor_unit  Decimal(12, 2),
    estoque     UInt32,
    ativo       UInt8
) ENGINE = MergeTree()
ORDER BY id_produto;

-- --------------------------------------------------------------------------
-- Fato na granularidade de PEDIDO
-- --------------------------------------------------------------------------
-- PARTITION BY  -> arquivos separados por mes. Filtro por data descarta
--                  particoes inteiras sem ler nada (partition pruning).
-- ORDER BY      -> este e o indice primario do ClickHouse. E ESPARSO: guarda
--                  uma marca a cada 8192 linhas, nao uma entrada por linha.
--                  Por isso o indice cabe na memoria mesmo com bilhoes de linhas.
DROP TABLE IF EXISTS liga_sudoers.fato_pedidos;
CREATE TABLE liga_sudoers.fato_pedidos (
    id_pedido     UInt32,
    id_pessoa     UInt32,
    dt_venda      DateTime,
    dia           Date MATERIALIZED toDate(dt_venda),
    valor_total   Decimal(12, 2),
    qtd_itens     UInt16,
    fraude        UInt8,
    motivo_fraude LowCardinality(String),
    uf            LowCardinality(String),
    geohash       String,
    lat           Float64,
    lon           Float64,
    device_id     String,
    dispositivo   LowCardinality(String),
    telefone      String
) ENGINE = MergeTree()
PARTITION BY toYYYYMM(dt_venda)
ORDER BY (dt_venda, id_pessoa)
-- min_bytes_for_wide_part = 0 forca o formato WIDE (um arquivo por coluna).
-- Por padrao, partes pequenas (<10MB) usam o formato COMPACT, que junta todas
-- as colunas num arquivo so - e ai nao da para medir o tamanho de cada coluna
-- separadamente. Como este repo e didatico e o volume e pequeno, forcamos WIDE
-- para voce conseguir VER a compressao coluna a coluna.
-- Em producao, deixe o padrao: COMPACT e mais eficiente para partes pequenas.
SETTINGS index_granularity = 8192, min_bytes_for_wide_part = 0;

-- --------------------------------------------------------------------------
-- Fato na granularidade de ITEM (para analise por produto/categoria)
-- --------------------------------------------------------------------------
DROP TABLE IF EXISTS liga_sudoers.fato_itens;
CREATE TABLE liga_sudoers.fato_itens (
    id_pedido   UInt32,
    id_pessoa   UInt32,
    dt_venda    DateTime,
    id_produto  UInt32,
    categoria   LowCardinality(String),
    qtde        UInt16,
    valor_unit  Decimal(12, 2),
    valor_total Decimal(12, 2),
    fraude      UInt8,
    uf          LowCardinality(String)
) ENGINE = MergeTree()
PARTITION BY toYYYYMM(dt_venda)
ORDER BY (dt_venda, categoria, id_produto);

-- --------------------------------------------------------------------------
-- Clickstream (o mesmo dado que esta no Cassandra - de proposito)
-- --------------------------------------------------------------------------
-- Comparar as duas e um dos exercicios do repo: MESMO dado, dois motores.
DROP TABLE IF EXISTS liga_sudoers.eventos;
CREATE TABLE liga_sudoers.eventos (
    id_pessoa   UInt32,
    ts          DateTime,
    tipo_evento LowCardinality(String),
    id_produto  UInt32,
    categoria   LowCardinality(String),
    id_sessao   String,
    device_id   String,
    geohash     String,
    duracao_ms  UInt32
) ENGINE = MergeTree()
PARTITION BY toYYYYMM(ts)
ORDER BY (ts, id_pessoa);

-- --------------------------------------------------------------------------
-- MATERIALIZED VIEW: agregacao que se atualiza sozinha NA INGESTAO
-- --------------------------------------------------------------------------
-- Diferente de uma view do Postgres (que so guarda a query) e de uma tabela
-- do dbt (que precisa de um job rodando de novo), a MV do ClickHouse e um
-- GATILHO DE INSERCAO: cada linha nova em fato_pedidos ja atualiza o agregado.
-- Latencia zero, sem orquestrador.
DROP TABLE IF EXISTS liga_sudoers.agg_vendas_dia;
CREATE TABLE liga_sudoers.agg_vendas_dia (
    dia         Date,
    uf          LowCardinality(String),
    pedidos     UInt64,
    faturamento Decimal(18, 2),
    fraudes     UInt64
) ENGINE = SummingMergeTree()
ORDER BY (dia, uf);

DROP VIEW IF EXISTS liga_sudoers.mv_vendas_dia;
CREATE MATERIALIZED VIEW liga_sudoers.mv_vendas_dia TO liga_sudoers.agg_vendas_dia AS
SELECT
    toDate(dt_venda) AS dia,
    uf,
    count()          AS pedidos,
    sum(valor_total) AS faturamento,
    sum(fraude)      AS fraudes
FROM liga_sudoers.fato_pedidos
GROUP BY dia, uf;
