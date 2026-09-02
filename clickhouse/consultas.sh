#!/bin/bash
# ==========================================================================
# ClickHouse - consultas guiadas da Liga Sudoers
#
#   docker exec -it sudoers_clickhouse bash /scripts/consultas.sh
#
# Interativo:
#   docker exec -it sudoers_clickhouse clickhouse-client -u sudoers --password sudoers
#
# Pela UI (sem instalar nada):  http://localhost:8123/play
# ==========================================================================
CH="clickhouse-client -u sudoers --password sudoers -d liga_sudoers"
Q() { $CH -q "$1"; }
QF() { $CH -q "$1 FORMAT PrettyCompactMonoBlock"; }
titulo() { echo; echo "=== $1 ==="; }

titulo "1. POR QUE COLUNAR E RAPIDO: le so a coluna que voce pediu"
echo "-- lendo 1 coluna de 14.924 linhas:"
$CH --time -q "SELECT sum(valor_total) FROM fato_itens" 2>&1
echo "-- bytes lidos em cada caso (system.query_log):"
Q "SYSTEM FLUSH LOGS"
QF "SELECT
      substring(query, 1, 45) AS consulta,
      read_rows,
      formatReadableSize(read_bytes) AS bytes_lidos
    FROM system.query_log
    WHERE type = 'QueryFinish' AND has(databases, 'liga_sudoers')
      AND query LIKE 'SELECT sum(valor_total) FROM fato_itens%'
    ORDER BY event_time DESC LIMIT 1"
echo ">>> Num banco de LINHAS, essa soma leria as 10 colunas de cada linha."
echo ">>> Aqui leu so a coluna valor_total."

titulo "2. Compressao por coluna (o segredo do espaco)"
# column_data_*  = tamanho DAQUELA coluna.
# data_*         = tamanho do part inteiro (erro comum: da o mesmo valor pra todas).
QF "SELECT column AS coluna, type,
      formatReadableSize(sum(column_data_uncompressed_bytes)) AS cru,
      formatReadableSize(sum(column_data_compressed_bytes)) AS comprimido,
      round(sum(column_data_uncompressed_bytes)/greatest(sum(column_data_compressed_bytes),1),1) AS fator
    FROM system.parts_columns
    WHERE database='liga_sudoers' AND table='fato_pedidos' AND active
    GROUP BY column, type ORDER BY sum(column_data_uncompressed_bytes) DESC LIMIT 10"
echo ">>> Valores parecidos ficam juntos no disco, entao comprimem muito."
echo
echo "-- LowCardinality x String: as duas guardam TEXTO. Compare o tamanho:"
QF "SELECT column AS coluna, type,
      formatReadableSize(sum(column_data_compressed_bytes)) AS em_disco
    FROM system.parts_columns
    WHERE database='liga_sudoers' AND table='fato_pedidos' AND active
      AND column IN ('uf','dispositivo','motivo_fraude','telefone','device_id','geohash')
    GROUP BY column, type ORDER BY sum(column_data_compressed_bytes) DESC"
echo ">>> LowCardinality vira dicionario: guarda um numero pequeno no lugar do"
echo ">>> texto. Use em coluna com poucos valores distintos (UF, status, categoria)."
echo ">>> NAO use em coluna com muitos valores distintos (cpf, email, id): piora."

titulo "3. PARTITION PRUNING: filtrar por data descarta arquivos inteiros"
echo "-- particoes existentes:"
QF "SELECT partition, sum(rows) AS linhas, formatReadableSize(sum(bytes_on_disk)) AS disco
    FROM system.parts WHERE database='liga_sudoers' AND table='fato_pedidos' AND active
    GROUP BY partition ORDER BY partition"
echo "-- consultando UM mes:"
$CH --time -q "SELECT count(), round(sum(valor_total),2) FROM fato_pedidos WHERE dt_venda >= '2026-07-01' AND dt_venda < '2026-08-01'"
Q "SYSTEM FLUSH LOGS"
QF "SELECT read_rows, formatReadableSize(read_bytes) AS lidos
    FROM system.query_log WHERE type='QueryFinish'
      AND query LIKE '%dt_venda >= ''2026-07-01''%' ORDER BY event_time DESC LIMIT 1"
echo ">>> Leu so as linhas do mes. As outras particoes nem foram abertas."

titulo "4. MATERIALIZED VIEW: agregado pronto, atualizado na ingestao"
echo "-- lendo da MV (ja agregado):"
$CH --time -q "SELECT uf, sum(pedidos) AS pedidos, round(sum(faturamento),2) AS fat FROM agg_vendas_dia GROUP BY uf ORDER BY fat DESC LIMIT 5"
echo "-- recalculando da tabela fato (mesmo resultado):"
$CH --time -q "SELECT uf, count() AS pedidos, round(sum(valor_total),2) AS fat FROM fato_pedidos GROUP BY uf ORDER BY fat DESC LIMIT 5"
echo ">>> Mesmo numero. A MV foi preenchida no INSERT, sem job, sem Airflow."

titulo "5. A pergunta de negocio: fraude por UF"
QF "SELECT uf, count() AS pedidos, sum(fraude) AS fraudes,
       round(100.0*sum(fraude)/count(), 2) AS pct_fraude,
       round(sum(valor_total * fraude), 2) AS valor_em_risco
    FROM fato_pedidos GROUP BY uf ORDER BY pct_fraude DESC, pedidos DESC"
echo ">>> UFs fora de SP/MG/RJ tem 100% de fraude: e a regra do jornada_dados."

titulo "6. Fraude por motivo e por categoria (cruzando os dois fatos)"
QF "SELECT motivo_fraude, count() AS pedidos, round(sum(valor_total),2) AS valor
    FROM fato_pedidos WHERE fraude = 1 GROUP BY motivo_fraude ORDER BY pedidos DESC"
QF "SELECT categoria, count() AS itens, sum(fraude) AS itens_fraude,
       round(100.0*sum(fraude)/count(),2) AS pct
    FROM fato_itens GROUP BY categoria ORDER BY pct DESC LIMIT 5"

titulo "7. Funcoes analiticas que o ClickHouse tem e o Cassandra nao"
echo "-- media movel de 7 dias do faturamento:"
QF "SELECT dia, round(faturamento,2) AS dia_a_dia,
       round(avg(faturamento) OVER (ORDER BY dia ROWS BETWEEN 6 PRECEDING AND CURRENT ROW), 2) AS media_movel_7d
    FROM (SELECT dia, sum(faturamento) AS faturamento FROM agg_vendas_dia GROUP BY dia ORDER BY dia)
    ORDER BY dia DESC LIMIT 7"
echo "-- quantis de valor de pedido (aproximado, muito rapido):"
QF "SELECT round(quantile(0.50)(valor_total),2) AS p50,
       round(quantile(0.90)(valor_total),2) AS p90,
       round(quantile(0.99)(valor_total),2) AS p99,
       uniq(id_pessoa) AS clientes_unicos_aprox
    FROM fato_pedidos"
echo ">>> uniq() usa HyperLogLog, igual ao PFCOUNT do Redis. Mesma ideia."

titulo "8. O indice primario e ESPARSO (por isso cabe na memoria)"
QF "SELECT table, sum(rows) AS linhas,
       formatReadableSize(sum(primary_key_bytes_in_memory)) AS indice_na_ram
    FROM system.parts WHERE database='liga_sudoers' AND active
    GROUP BY table ORDER BY sum(rows) DESC"
echo ">>> 1 marca a cada 8192 linhas. Um B-tree do Postgres indexaria TODAS."

titulo "9. O MESMO clickstream que esta no Cassandra"
QF "SELECT tipo_evento, count() AS eventos, round(avg(duracao_ms)) AS duracao_media_ms
    FROM eventos GROUP BY tipo_evento ORDER BY eventos DESC"
echo ">>> No Cassandra este GROUP BY exigiria ALLOW FILTERING ou outra tabela."
echo ">>> Aqui e uma linha de SQL. Cada banco no seu lugar."

echo
echo "=== fim ==="
