-- ==========================================================================
-- Cassandra - schema da Liga Sudoers
--
-- A REGRA DE OURO DO CASSANDRA:
--   Voce NAO modela os dados. Voce modela as CONSULTAS.
--
-- No Postgres voce normaliza e depois escreve qualquer SELECT que quiser.
-- No Cassandra e o contrario: primeiro voce lista as perguntas que o sistema
-- vai fazer, e cria UMA TABELA PARA CADA PERGUNTA. O mesmo dado e gravado
-- varias vezes, de proposito.
--
-- Isso parece errado para quem vem do relacional. Nao e. A escrita no
-- Cassandra e baratissima; a leitura sem particao definida e que e cara.
--
-- PERGUNTAS QUE ESTE SCHEMA RESPONDE:
--   P1. O que a pessoa X fez, do mais recente para o mais antigo?
--   P2. O que aconteceu no dia D (para o pipeline diario ler)?
--   P3. Quais os pedidos da pessoa X?
--   P4. Quantos eventos de cada tipo aconteceram?
-- ==========================================================================

CREATE KEYSPACE IF NOT EXISTS liga_sudoers
  WITH replication = {'class': 'SimpleStrategy', 'replication_factor': 1};
-- Em producao seria NetworkTopologyStrategy com RF 3. Aqui e 1 no, RF 1.

USE liga_sudoers;

-- --------------------------------------------------------------------------
-- P1: "o que a pessoa X fez?"  -> particiona por pessoa
-- --------------------------------------------------------------------------
-- PARTITION KEY = (id_pessoa)  -> tudo dessa pessoa fica no MESMO no.
-- CLUSTERING    = (ts DESC)    -> ja gravado ordenado. Ler o ultimo e O(1).
DROP TABLE IF EXISTS eventos_por_pessoa;
CREATE TABLE eventos_por_pessoa (
    id_pessoa    int,
    ts           timestamp,
    id_evento    uuid,
    tipo_evento  text,
    id_produto   int,
    categoria    text,
    id_sessao    text,
    dispositivo  text,
    device_id    text,
    geohash      text,
    duracao_ms   int,
    PRIMARY KEY ((id_pessoa), ts, id_evento)
) WITH CLUSTERING ORDER BY (ts DESC, id_evento ASC)
  AND comment = 'P1: timeline de uma pessoa. Particao por pessoa.';

-- --------------------------------------------------------------------------
-- P2: "o que aconteceu no dia D?"  -> MESMO dado, OUTRA particao
-- --------------------------------------------------------------------------
-- Nao da para responder P2 usando a tabela de P1: o dia nao e partition key,
-- e varrer todas as particoes exigiria ALLOW FILTERING (nunca faca isso).
-- Entao gravamos de novo, com outra chave.
--
-- Repare no bucket de hora dentro da partition key: sem ele, um dia inteiro
-- de eventos cairia numa unica particao, que cresceria sem limite. Isso se
-- chama HOT PARTITION e e o erro numero 1 de quem esta comecando.
DROP TABLE IF EXISTS eventos_por_dia;
CREATE TABLE eventos_por_dia (
    dia          date,
    hora_bucket  int,
    ts           timestamp,
    id_evento    uuid,
    id_pessoa    int,
    tipo_evento  text,
    id_produto   int,
    categoria    text,
    device_id    text,
    PRIMARY KEY ((dia, hora_bucket), ts, id_evento)
) WITH CLUSTERING ORDER BY (ts DESC, id_evento ASC)
  AND comment = 'P2: mesmo dado de eventos_por_pessoa, particionado por dia+hora.';

-- --------------------------------------------------------------------------
-- P3: "quais os pedidos da pessoa X?"
-- --------------------------------------------------------------------------
-- itens_pedido e uma COLECAO congelada dentro da linha. No Cassandra nao
-- existe JOIN: ou o dado esta aqui dentro, ou voce faz N leituras.
DROP TABLE IF EXISTS pedidos_por_pessoa;
CREATE TABLE pedidos_por_pessoa (
    id_pessoa     int,
    dt_venda      timestamp,
    id_pedido     int,
    valor_total   decimal,
    fraude        boolean,
    motivo_fraude text,
    uf            text,
    geohash       text,
    device_id     text,
    dispositivo   text,
    qtd_itens     int,
    itens         frozen<list<frozen<tuple<int, int, decimal>>>>,
    PRIMARY KEY ((id_pessoa), dt_venda, id_pedido)
) WITH CLUSTERING ORDER BY (dt_venda DESC, id_pedido ASC)
  AND comment = 'P3: pedidos de uma pessoa, do mais novo para o mais velho.';

-- --------------------------------------------------------------------------
-- P4: contadores. Tipo especial de coluna, so aceita incremento.
-- --------------------------------------------------------------------------
DROP TABLE IF EXISTS contador_eventos;
CREATE TABLE contador_eventos (
    dia          date,
    tipo_evento  text,
    total        counter,
    PRIMARY KEY ((dia), tipo_evento)
) WITH comment = 'P4: contadores. Coluna counter nao aceita INSERT, so UPDATE +=.';

-- --------------------------------------------------------------------------
-- Extra: TTL. Dado quente que se apaga sozinho (igual ao Redis, mas em disco).
-- --------------------------------------------------------------------------
DROP TABLE IF EXISTS sessoes_ativas;
CREATE TABLE sessoes_ativas (
    id_sessao   text,
    ts          timestamp,
    id_pessoa   int,
    device_id   text,
    PRIMARY KEY ((id_sessao), ts)
) WITH CLUSTERING ORDER BY (ts DESC)
  AND default_time_to_live = 604800
  AND comment = 'TTL de 7 dias aplicado na tabela inteira.';
