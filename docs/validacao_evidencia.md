# 🔎 Guia de Validação por Evidências — Jornada NoSQL

> ⬅️ [README principal](../README.md)
>
> **Regra de ouro:** cada etapa deve deixar um rastro verificável. Não confie
> em "subiu sem erro" — confie em número conferido.

## 0) O atalho: `make validar`

```bash
make validar
```

Este comando regera o universo canônico em memória e compara, item por item,
com o que está gravado em cada banco.

**Evidência:** `32 passaram   0 falharam   0 bancos fora do ar`

Se algum número divergir, ele diz exatamente qual. As causas mais comuns:

| Sintoma | Causa provável |
|---|---|
| um banco "indisponível" | o profile não subiu, ou ainda está `starting` |
| contagens divergentes num banco só | o seed não rodou depois de mudar o `.env` |
| todos divergentes | você mudou a `SEMENTE` e repopulou só parte |

---

## 1) Serviços no ar

* **Comando:** `make status`
* **Evidência:** todos com `Up (healthy)`.
* **Atenção:** `sudoers_mongo_rs_init` aparece como `Exited (0)` — **isso é
  correto**. Ele existe só para iniciar o replica set e morrer.
* **Dica:** se algo reinicia em loop, `make logs s=<serviço>`.

## 2) MongoDB

* **Comando:** `make q-mongo`
* **Evidência A:** produtos de categorias diferentes com chaves diferentes em
  `atributos`.
* **Evidência B:** o `explain` mostra `IXSCAN`, e `totalDocsExamined` é igual
  a `nReturned` (o índice esparso está sendo usado de verdade).
* **Evidência C:** o insert inválido devolve erro **121**.
* **Evidência D:** `rs.status().members[0].stateStr` = `PRIMARY`.

## 3) Redis

* **Comando:** `make q-redis`
* **Evidência A:** `DBSIZE` acima de 3000.
* **Evidência B:** os três contadores de `metrica:fraude_motivo:*` somados
  batem com o total de fraudes do gerador.
* **Evidência C:** `TTL carrinho:<id>` devolve um número positivo e
  **decrescente** entre duas chamadas.
* **Evidência D:** `XLEN stream:fraude` = total de pedidos fraudulentos.

## 4) Neo4j

* **Comando:** `make q-neo4j`
* **Evidência A (a mais importante):** a consulta de anel retorna
  **exatamente 6** dispositivos compartilhados — o mesmo número que o gerador
  plantou.
* **Evidência B:** os membros de um anel têm CPFs, nomes e UFs diferentes.
* **Evidência C:** o `shortestPath` retorna uma rota passando por
  `Dispositivo`, não por `Produto`.
* **Evidência D:** print do grafo desenhado no Browser.

## 5) Cassandra

* **Comando:** `make q-cassandra`
* **Evidência A:** consulta **com** partition key retorna em ordem
  decrescente, sem `ORDER BY`.
* **Evidência B:** consulta **sem** partition key devolve
  `InvalidRequest ... use ALLOW FILTERING`. **O erro é a evidência.**
* **Evidência C:** `TRACING` mostra `source_elapsed` muito menor na consulta
  com partition key.
* **Evidência D:** `eventos_por_pessoa` e `eventos_por_dia` têm a mesma
  contagem (a duplicação intencional está correta).

## 6) ClickHouse

* **Comando:** `make q-clickhouse`
* **Evidência A:** consulta filtrada por mês lê **menos linhas** que o total
  da tabela (partition pruning).
* **Evidência B:** colunas `LowCardinality` ocupam ordens de grandeza menos
  disco que `String` na mesma tabela.
* **Evidência C:** o total da `MATERIALIZED VIEW` é igual ao da tabela fato.
* **Evidência D:** `SELECT count() FROM fato_pedidos WHERE uf NOT IN
  ('SP','MG','RJ') AND fraude = 0` retorna **0**.

## 7) Consistência entre bancos

Esta é a evidência que prova que a semente compartilhada funciona:

```bash
# nome da pessoa 1 no MongoDB
docker exec sudoers_mongo mongosh --quiet -u sudoers -p sudoers \
  --authenticationDatabase admin liga_sudoers --eval 'db.pessoas.findOne({_id:1}).nome'

# device da pessoa 1 no Redis
docker exec sudoers_redis redis-cli -a sudoers --no-auth-warning GET device:atual:1

# pessoa 1 no Neo4j
docker exec sudoers_neo4j cypher-shell -u neo4j -p sudoers123 --format plain \
  "MATCH (p:Pessoa {id:1}) RETURN p.nome;"

# pedidos da pessoa 1 no Cassandra
docker exec sudoers_cassandra cqlsh -k liga_sudoers \
  -e "SELECT id_pedido FROM pedidos_por_pessoa WHERE id_pessoa=1 LIMIT 3;"

# a mesma lista no Redis
docker exec sudoers_redis redis-cli -a sudoers --no-auth-warning \
  LRANGE pessoa:ultimos_pedidos:1 0 2
```

**Evidência:** o nome é o mesmo nos três bancos, e as duas listas de pedidos
coincidem.

## 8) Integração — carga no OLTP

* **Evidência A:** o script **recusa** escrever sem `--limpar` se houver dados.
* **Evidência B:** após `--limpar`, `pessoa id=1 no Postgres` = `pessoa id=1
  no gerador`.
* **Evidência C:** zero órfãos:

```sql
SELECT count(*) FROM itens_pedidos i
  LEFT JOIN pedidos p ON p.id = i.id_pedido WHERE p.id IS NULL;  -- 0
```

## 9) Integração — Data Lake

* **Evidência A:** `mc ls -r local/raw/` lista 8 objetos com a partição `dt=`.
* **Evidência B:** o Parquet é legível de volta e a contagem de linhas bate.
* **Evidência C:** o Spark do `jornada_dados` consegue criar tabela sobre
  `s3a://raw/neo4j/score_risco_pessoa/`.

## 10) Integração — CDC

* **Evidência A:** `curl .../status` mostra `RUNNING` no conector **e** na task.
* **Evidência B (indispensável):** `kafka-topics --list | grep nosql` retorna
  os dois tópicos.

> ⚠️ `RUNNING` **sozinho não prova nada**. Um conector que não resolve o nome
> do host fica `RUNNING` para sempre, sem erro e sem tópico. Sempre confira os
> tópicos.

* **Evidência C:** após um insert no Mongo, o offset do tópico **aumenta em 1**
  e o último evento tem `"op": "c"`.

## 11) Dataviz

* **Comando:** `docker compose run --rm seeder python tests/teste_viz.py`
* **Evidência:** `exceptions: 0` e 7 abas renderizadas.
* **Atenção:** os 2 "erros na página" que o teste reporta são `st.error()`
  intencionais (as mensagens didáticas sobre fraude), não falhas.
