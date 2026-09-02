# 7️⃣ Integração — virando **origem** do `jornada_dados`

> ⬅️ Anterior: [clickhouse/](../clickhouse/README.md) · [README principal](../README.md)

Até aqui você tem cinco bancos rodando isolados. Esta pasta é o que
transforma este repositório num **fornecedor de dados** para o pipeline do
`jornada_dados`.

## Pré-requisito: os dois repositórios no ar

```bash
cd ../jornada_dados
docker compose up -d           # ou só o que você precisa:
# docker compose up -d postgres-oltp minio zookeeper kafka debezium
```

## As três pontes

```
                      ESTE REPOSITORIO
   MongoDB   Redis   Neo4j   Cassandra   ClickHouse
      │        │       │         │           │
      │        └───────┴────┬────┴───────────┘
      │                     │
      │  ponte 3            │  ponte 2
      │  (streaming)        │  (batch)
      ▼                     ▼
  Debezium ─► Kafka     MinIO / zona raw
                             │
   ponte 1 (carga)           ▼
   Postgres OLTP ──► Debezium ──► Kafka ──► Spark ──► Delta ──► DW
                      REPO jornada_dados
```

---

## 🔌 Ponte 0 — a rede (faça isto primeiro)

Os dois repositórios sobem em redes Docker diferentes. Para conversarem:

```bash
make lake-conectar
# ou: ./integracao/conectar_lake.sh
```

### Por que o `--alias` importa (não é detalhe)

Um container ganha, na rede em que subiu, **dois** nomes: o nome do serviço
no compose (`mongodb`) e o nome do container (`sudoers_mongo`). Mas
`docker network connect` numa rede nova leva **apenas o nome do container**.
O apelido curto some.

Isso quebra o CDC de um jeito traiçoeiro: o replica set do MongoDB anuncia
seus membros como `mongodb:27017`. O Debezium, do outro lado, não resolve
esse nome — e o conector fica **`RUNNING`, sem erro no log, sem criar tópico
nenhum**. Falha silenciosa, das piores de diagnosticar.

Por isso o script conecta com `--alias`, replicando o nome de serviço:

```bash
docker exec debezium getent hosts mongodb
# 172.22.0.4      mongodb          ✅
```

Para desfazer: `make lake-desconectar`.

---

## 🔌 Ponte 1 — carga no Postgres OLTP

Este é o script que **fecha o circuito entre os dois repositórios**.

> O `jornada_dados` cita um `liga_sudoers_historico.py` que popula o Postgres
> transacional — mas esse script nunca foi versionado lá. Aqui ele existe. E
> melhor: usa a **mesma semente** que popula os cinco bancos NoSQL.

```bash
# 1) veja o que aconteceria (não escreve nada)
make lake-oltp

# 2) carregue de verdade (APAGA os dados atuais das 6 tabelas)
make lake-oltp args=--limpar
```

Saída esperada:

```
carregando:
  categorias ..........     12
  produtos ............    200
  pessoas .............    500
  pedidos .............   5000
  itens_pedidos .......  14976
  auditoria_pedidos ...   5000

  pessoa id=1 no Postgres: Thomas Camargo
  pessoa id=1 no gerador : Thomas Camargo
  ^ tem que ser a MESMA pessoa.
```

Sem o `--limpar`, o script **se recusa** a escrever se as tabelas tiverem
dados. É proposital: apagar o OLTP de alguém sem avisar seria péssimo.

A partir daqui, o pipeline do outro repositório roda sozinho:
**Debezium → Kafka → Spark → Delta Lake → DW**.

---

## 🔌 Ponte 2 — export batch para o Data Lake

```bash
make lake-export
# ou só uma origem:
make lake-export args=neo4j
```

O que vai para a zona `raw` do MinIO:

| Origem | Objeto | Formato | Por quê |
|---|---|---|---|
| MongoDB | `produtos` | **JSONL** | preserva o schema variável |
| MongoDB | `pedidos` | Parquet | grão fixo, cabe em tabela |
| Redis | `ranking_produtos` | Parquet | |
| Redis | `alertas_fraude` | Parquet | vem da STREAM |
| Neo4j | `score_risco_pessoa` | Parquet | **só o grafo produz isto** |
| Neo4j | `aneis_fraude` | Parquet | |
| Cassandra | `clickstream` | Parquet | |
| ClickHouse | `agg_vendas_dia` | Parquet | |

### Por que produtos sai em JSON e não em Parquet

Os produtos do Mongo têm `atributos` com chaves diferentes por categoria.
Forçar isso em Parquet exigiria achatar tudo numa super-tabela esparsa e
**perder informação**. A zona `raw` preserva o dado como ele veio; achatar é
decisão da camada `trusted`.

É isso que "raw" significa: o dado **como ele é**, não como você queria.

Layout gravado:

```
s3a://raw/<origem>/<tabela>/dt=AAAA-MM-DD/<tabela>.parquet
```

Conferindo do lado do `jornada_dados`:

```bash
docker exec -it minio sh -c "mc alias set local http://minio:9000 sudoers123 sudoers1234 && mc ls -r local/raw/"
```

E lendo no Spark:

```sql
CREATE TABLE score_risco USING parquet
LOCATION 's3a://raw/neo4j/score_risco_pessoa/';

SELECT * FROM score_risco ORDER BY score_risco DESC LIMIT 10;
```

> **O ciclo fecha aqui.** O lake alimenta o grafo com os pedidos; o grafo
> devolve um `score_risco` que nenhuma regra de linha conseguiria calcular; o
> score volta para a camada gold. É esse vaivém que caracteriza uma
> arquitetura de dados madura.

---

## 🔌 Ponte 3 — CDC do MongoDB (streaming)

O MongoDB deste repositório sobe como **replica set** justamente para isso:
sem replica set não há Change Stream, e sem Change Stream não há CDC.

```bash
# registra o conector no Debezium do jornada_dados
curl -X POST -H "Content-Type: application/json" \
  --data @integracao/debezium-mongodb.json \
  http://localhost:8083/connectors

# confere
curl -s http://localhost:8083/connectors/mongodb-liga-sudoers/status
```

Esperado: `"state": "RUNNING"` no conector **e** na task.

> ⚠️ `RUNNING` **não** garante que está funcionando. Confira sempre se os
> tópicos existem:

```bash
docker exec kafka kafka-topics --bootstrap-server localhost:9092 --list | grep nosql
# nosql.liga_sudoers.pedidos
# nosql.liga_sudoers.produtos
```

Se os tópicos não aparecerem, você esqueceu o `make lake-conectar` (veja a
Ponte 0).

### Provando ponta a ponta

```bash
# insere um pedido no Mongo
docker exec sudoers_mongo mongosh --quiet -u sudoers -p sudoers \
  --authenticationDatabase admin liga_sudoers --eval '
  db.pedidos.insertOne({_id: 999001, id_pessoa: 1, valor_total: 4242.42,
    fraude: true, motivo_fraude: "geolocalizacao"})'

# lê o último evento do tópico
docker exec kafka kafka-console-consumer --bootstrap-server localhost:9092 \
  --topic nosql.liga_sudoers.pedidos --partition 0 --offset 5000 --max-messages 1
```

O evento traz `"op": "c"` (create) e o documento inteiro. Compare com o CDC
do Postgres que você já viu no outro repositório: **mesma ideia, origem
diferente**.

| | Postgres | MongoDB |
|---|---|---|
| Fonte do CDC | WAL (write-ahead log) | oplog do replica set |
| Pré-requisito | `wal_level=logical` | replica set + keyFile |
| Conector | `PostgresConnector` | `MongoDbConnector` |

---

## Ordem recomendada

```bash
make lake-conectar                 # 0. rede (com alias)
make lake-oltp args=--limpar       # 1. Postgres OLTP
make lake-export                   # 2. zona raw do MinIO
curl -X POST ... /connectors       # 3. CDC do Mongo
```

---

# ➡️ Continue no [viz/README.md](../viz/README.md)
