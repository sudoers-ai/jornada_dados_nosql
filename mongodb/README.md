# 2️⃣ MongoDB — banco de **documentos**

> ⬅️ Anterior: [gerador/](../gerador/README.md) · [README principal](../README.md)

## Por que documento?

Olhe estes três produtos da Liga Sudoers:

```json
{ "categoria": "Eletronicos", "atributos": { "voltagem": "Bivolt", "garantia_meses": 3, "potencia_w": 800 } }
{ "categoria": "Livros",      "atributos": { "autor": "...", "paginas": 320, "isbn": "...", "editora": "..." } }
{ "categoria": "Pet",         "atributos": { "porte_animal": "medio", "peso_g": 500, "sabor": "salmao" } }
```

Nenhum campo de `atributos` se repete entre eles. Como você põe isso numa
tabela? Três saídas, todas ruins:

1. **Uma coluna por atributo de cada categoria** → tabela com 60 colunas, 58
   delas `NULL` em cada linha.
2. **Tabela EAV** (entidade-atributo-valor) → um `JOIN` por atributo, e
   qualquer consulta vira ilegível.
3. **Um blob JSON numa coluna** → você acabou de fazer um banco de documentos
   mal-feito dentro do relacional.

O MongoDB guarda cada produto com exatamente os campos que fazem sentido para
ele — e ainda consegue **indexar e consultar dentro** desses campos.

## As decisões de modelagem deste repositório

| Dado | Decisão | Motivo |
|---|---|---|
| `reviews` | **embutidas** no produto | a página do produto é uma leitura só, sem `JOIN` |
| `itens` | **embutidos** no pedido | o pedido é um agregado; ninguém lê "meio pedido" |
| `pessoas` | **referenciadas** por id | mudam sozinhas, em outro ritmo |
| `sessoes_checkout` | com **TTL de 7 dias** | dado de vida curta; some sozinho |

> **A regra prática:** embuta o que é lido junto e muda junto. Referencie o
> que tem ciclo de vida próprio. Se você precisa de `$lookup` toda hora, o
> modelo de documentos está errado.

## Subindo

```bash
docker compose --profile documento up -d
docker compose run --rm seeder python mongodb/seed_mongo.py
```

Isso sobe **dois** containers: o `mongodb` e o `mongo-express` (interface web
em http://localhost:8091, usuário `sudoers`, senha `sudoers`).

Você vai ver também um `sudoers_mongo_rs_init` que sobe e morre com
`Exited (0)`. **Isso é o esperado**: ele existe só para iniciar o replica set.

### Por que replica set num banco de um nó só?

Porque **Change Stream** — o CDC nativo do MongoDB — só funciona com replica
set. E como este container tem autenticação ligada, o MongoDB exige um
`keyFile`. O script `entrypoint-rs.sh` gera esse keyfile no primeiro boot.

Sem isso você veria este erro, que é comum e confuso:

```
BadValue: security.keyFile is required when authorization is enabled with replica sets
```

## Explorando

```bash
# roda o roteiro completo de consultas comentadas
make q-mongo

# ou entre no shell e explore
docker exec -it sudoers_mongo mongosh -u sudoers -p sudoers \
  --authenticationDatabase admin liga_sudoers
```

O arquivo [`consultas.js`](./consultas.js) tem 11 consultas guiadas. Os
destaques:

**Consulta 3 — o índice esparso está sendo usado?**

```javascript
db.produtos.find({ "atributos.voltagem": "220V" }).explain("executionStats")
```

Procure por `IXSCAN` (usou índice) ou `COLLSCAN` (varreu tudo). Um índice
**esparso** só indexa os documentos que *têm* aquele campo — perfeito para
atributos que só existem em algumas categorias.

**Consulta 8 — dá para achar o anel de fraude aqui?**

Dá. Mas repare no esforço: é preciso agrupar todos os pedidos, montar um
conjunto de pessoas por dispositivo e filtrar. E isso é só o **primeiro
salto**. Perguntar "e quem mais se conecta a essas pessoas?" vira um pesadelo.

Guarde essa dor. No Neo4j isso é uma linha.

**Consulta 10 — "NoSQL não tem schema" é mito**

```javascript
db.pedidos.insertOne({ _id: 999999, id_pessoa: 1 })   // faltam campos obrigatórios
// MongoServerError: Document failed validation (code 121)
```

A coleção `pedidos` tem um validador `$jsonSchema`. Você **escolhe** onde
colocar o schema: no banco, na aplicação, ou em lugar nenhum. NoSQL te dá a
escolha — não te tira o schema.

## Change Streams: o CDC nativo

```bash
# terminal 1 — fica escutando
docker exec -it sudoers_mongo mongosh --quiet -u sudoers -p sudoers \
  --authenticationDatabase admin liga_sudoers \
  --eval 'db.pedidos.watch().forEach(e => printjson({op: e.operationType, id: e.documentKey._id}))'

# terminal 2 — provoca uma mudança
docker exec -it sudoers_mongo mongosh --quiet -u sudoers -p sudoers \
  --authenticationDatabase admin liga_sudoers \
  --eval 'db.pedidos.updateOne({_id: 1}, {$set: {valor_total: 99999}})'
```

O terminal 1 imprime o evento na hora. É exatamente disso que o Debezium se
alimenta — veja em [`integracao/`](../integracao/README.md).

## Exercícios rápidos

1. Crie um índice em `atributos.paginas` e compare o `explain` antes e depois.
2. Descubra qual categoria tem a melhor nota média (dica: `$group` + `$avg`).
3. Insira um produto de uma categoria nova, com atributos que não existem em
   nenhum outro. Confirme que o banco aceita sem reclamar. Depois pense: isso
   é uma vantagem ou um risco?

---

# ➡️ Continue no [redis/README.md](../redis/README.md)
