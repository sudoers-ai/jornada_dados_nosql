# ✅ Checklist Imprimível (Aluno) — Jornada NoSQL

> ⬅️ [README principal](../README.md)
>
> Marque cada item **somente após validar a evidência** correspondente.

### 1) Preparação

* [ ] Rodei `make verificar` e ele terminou com "Tudo certo. Pode subir."
* [ ] Docker + Docker Compose v2 instalados (`docker compose version`)
* [ ] ~6 GB de RAM livres (ou vou subir um profile por vez)
* [ ] Portas livres: 27017, 8091, 6380, 7474, 7687, 9042, 8123, 9010, 8501
* [ ] `docker compose config --quiet` roda sem erro
* [ ] Imagem de ferramentas construída (`make ferramentas`)

### 2) Gerador — o universo compartilhado

* [ ] `make ajuda` lista os comandos
* [ ] `docker compose run --rm seeder python gerador/liga_sudoers_gen.py --resumo` funciona
* [ ] Entendi o que é a **semente** e por que ela precisa ser a mesma
* [ ] Entendi que **não preciso editar o `.env`** para seguir a trilha
* [ ] Provei o determinismo (gerei duas vezes e comparei)
* [ ] Sei a diferença entre `dispositivo` (modelo) e `device_id` (aparelho)

### 3) MongoDB — documento

* [ ] `docker compose --profile documento up -d` sem erro
* [ ] `sudoers_mongo` está `healthy`
* [ ] `sudoers_mongo_rs_init` saiu com `Exited (0)` — **é o esperado**
* [ ] Seed rodou: 200 produtos, 500 pessoas, 5000 pedidos
* [ ] Mongo Express abre em http://localhost:8091
* [ ] Vi produtos de categorias diferentes com **chaves diferentes** em `atributos`
* [ ] Vi `IXSCAN` no `explain` do índice esparso
* [ ] O insert inválido foi **rejeitado** pelo `$jsonSchema` (código 121)
* [ ] Abri um Change Stream e vi o evento aparecer

### 4) Redis — chave-valor

* [ ] `docker compose --profile chavevalor up -d` sem erro
* [ ] Seed rodou e `DBSIZE` > 3000
* [ ] `GET device:atual:1` devolve um `device_id`
* [ ] `SMEMBERS device:hist:1` mostra o histórico
* [ ] Vi o `PFCOUNT` e comparei o `MEMORY USAGE` do HyperLogLog
* [ ] Rodei um `GEOSEARCH` e recebi pedidos próximos
* [ ] `XLEN stream:fraude` bate com o total de fraudes
* [ ] Entendi por que **nunca** rodar `KEYS *`

### 5) Neo4j — grafo

* [ ] `docker compose --profile grafo up -d` sem erro
* [ ] Seed reportou `aneis: 6` = `esperado: 6`
* [ ] Neo4j Browser abre em http://localhost:7474
* [ ] Rodei a consulta de anel e vi **6 dispositivos compartilhados**
* [ ] Vi os membros de um anel: CPFs e nomes diferentes, mesmo aparelho
* [ ] Rodei o `shortestPath` e li a rota salto a salto
* [ ] **Desenhei o anel na tela** do Browser
* [ ] Entendi por que `Dispositivo` é nó e não coluna

### 6) Cassandra — wide-column

* [ ] `docker compose --profile widecolumn up -d` (esperei ~60s até `healthy`)
* [ ] Seed rodou: `eventos_por_pessoa` e `eventos_por_dia` com a **mesma contagem**
* [ ] Consulta **com** partition key funcionou
* [ ] Consulta **sem** partition key foi **recusada** (`ALLOW FILTERING`)
* [ ] Rodei com `ALLOW FILTERING` e entendi por que não devo usar
* [ ] Comparei os tempos no `TRACING` (com e sem partition key)
* [ ] `INSERT` na tabela de `counter` foi recusado
* [ ] Entendi o que é **hot partition** e para que serve o `hora_bucket`

### 7) ClickHouse — colunar

* [ ] `docker compose --profile colunar up -d` sem erro
* [ ] Seed rodou e reportou o fator de compressão
* [ ] http://localhost:8123/play abre
* [ ] Vi o `read_rows` de uma consulta com filtro por data (partition pruning)
* [ ] Comparei `LowCardinality` x `String` no tamanho em disco
* [ ] Confirmei que a `MATERIALIZED VIEW` bate com a tabela fato
* [ ] Sei explicar a diferença entre Cassandra e ClickHouse

### 8) Validação geral

* [ ] `make validar` → **32 passaram, 0 falharam**
* [ ] `make status` mostra tudo `healthy`
* [ ] Confirmei que `pessoa 1` é a **mesma** nos cinco bancos

### 9) Integração com o `jornada_dados`

* [ ] O outro repositório está no ar
* [ ] `make lake-conectar` rodou e `docker exec debezium getent hosts mongodb` resolve
* [ ] `make lake-oltp` (sem flag) **recusou** escrever sobre dados existentes
* [ ] `make lake-oltp args=--limpar` carregou 5000 pedidos
* [ ] `pessoa id=1` no Postgres = `pessoa id=1` no gerador
* [ ] `make lake-export` gravou 8 objetos na zona `raw`
* [ ] Li um Parquet de volta (Spark ou o próprio script)
* [ ] Conector Debezium do Mongo `RUNNING` **e** tópicos criados
* [ ] Fiz um insert no Mongo e capturei o evento no Kafka

### 10) Dataviz

* [ ] Painel abre em http://localhost:8501
* [ ] As 7 abas carregam sem erro
* [ ] Vi o mapa dos pedidos com fraude destacada
* [ ] Na aba Comparativo, entendi **por que o Redis responde 10**
* [ ] `docker compose run --rm seeder python tests/teste_viz.py` → `exceptions: 0`
