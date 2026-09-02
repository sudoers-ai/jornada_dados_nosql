# 3️⃣ Redis — banco **chave-valor**

> ⬅️ Anterior: [mongodb/](../mongodb/README.md) · [README principal](../README.md)

## Por que chave-valor?

A regra antifraude do `jornada_dados` diz: *"se o cliente mudou de
dispositivo, marque como suspeito"*.

Para aplicar essa regra **no momento do checkout**, você precisa saber, em
menos de 1 milissegundo, qual era o dispositivo anterior daquele cliente. Ir
ao Postgres, ao Data Lake ou ao DW é inviável — o cliente está olhando a tela
de pagamento esperando.

Esse **estado quente** vive no Redis:

```bash
GET device:atual:1
# "d-5a856750"
```

O(1). Microssegundos. É isso.

## O erro mais comum: achar que Redis é "só cache"

Aqui você usa **oito estruturas de dados** diferentes, cada uma resolvendo um
problema que seria caro em qualquer outro banco:

| Estrutura | Chave neste repo | O que resolve |
|---|---|---|
| `STRING` | `metrica:pedidos:2026-08-01` | contador atômico, sem *race condition* |
| `HASH` | `pessoa:1`, `carrinho:314` | ler/escrever **um campo** sem desserializar o objeto |
| `LIST` | `pessoa:ultimos_pedidos:1` | fila de tamanho fixo (`LPUSH` + `LTRIM`) |
| `SET` | `device:hist:1` | histórico com deduplicação automática |
| `ZSET` | `rank:produtos` | ranking sempre ordenado, leitura O(log N) |
| `HYPERLOGLOG` | `hll:visitantes:2026-08-01` | visitantes únicos em **12 KB fixos** |
| `GEO` | `geo:pedidos` | busca por proximidade (usa geohash por dentro) |
| `STREAM` | `stream:fraude` | fila durável de alertas — a ponte para o Kafka |

## Subindo

```bash
docker compose --profile chavevalor up -d
docker compose run --rm seeder python redis/seed_redis.py
```

> A porta no host é **6380**, não 6379. Muita gente tem um Redis local
> ocupando a 6379. Mude no `.env` se quiser.

## Explorando

```bash
make q-redis

# ou interativo
docker exec -it sudoers_redis redis-cli -a sudoers
```

O [`consultas.sh`](./consultas.sh) tem 12 blocos comentados. Os destaques:

**A regra antifraude, em dois comandos:**

```bash
GET device:atual:1        # aparelho de hoje
SMEMBERS device:hist:1    # todos os que já usou
```

Se o histórico tem mais de um item, o cliente trocou de aparelho em algum
momento. Compare com a decisão do `jornada_dados`.

**HyperLogLog — contar sem guardar:**

```bash
PFCOUNT hll:visitantes:2026-08-01
MEMORY USAGE hll:visitantes:2026-08-01
```

Um `SET` com os mesmos ids gastaria muito mais memória. O HLL sempre gasta
~12 KB, independente de ter 100 ou 100 milhões de itens. O preço é ~0,81% de
erro na contagem. Para "quantos visitantes únicos hoje?", esse erro não
importa. Para "quantos reais faturamos hoje?", importa muito — e aí você
**não** usa HLL.

**GEO — o Redis fala geohash nativamente:**

```bash
GEOSEARCH geo:pedidos FROMLONLAT -46.6333 -23.5505 BYRADIUS 50 km COUNT 5 ASC
GEOHASH geo:pedidos ped:1
```

**TTL — o dado que morre sozinho:**

```bash
TTL carrinho:314
# 3556
```

Carrinho abandonado não precisa de job de limpeza. Ele expira. Compare com o
esforço de fazer isso no Postgres (job noturno, `DELETE` em massa, vacuum...).

**O perigo — nunca rode `KEYS *`:**

```bash
KEYS *                          # ❌ bloqueia o Redis inteiro
SCAN 0 MATCH 'device:atual:*'   # ✅ pagina com cursor
```

O Redis é *single-threaded*. Um `KEYS *` numa base grande trava **todos** os
outros clientes enquanto varre. É um dos incidentes mais clássicos da área.

## Persistência: Redis não é volátil por obrigação

Este container sobe com `--appendonly yes`. Ou seja, ele grava em disco e
sobrevive a um restart. Teste:

```bash
docker compose --profile chavevalor restart redis
docker exec sudoers_redis redis-cli -a sudoers --no-auth-warning DBSIZE
```

As chaves continuam lá (menos as que expiraram por TTL). "Redis perde dados"
é uma escolha de configuração, não uma característica do banco.

## O `stream:fraude` e o `jornada_dados`

Cada pedido fraudulento vira um evento numa STREAM:

```bash
XLEN stream:fraude
XRANGE stream:fraude - + COUNT 2
```

Uma STREAM é uma fila **durável e com consumer groups** — o mesmo modelo do
Kafka, em escala menor. É daqui que sai a ponte para o pipeline do outro
repositório. Veja [`integracao/`](../integracao/README.md).

## Exercícios rápidos

1. Descubra quantas pessoas usaram mais de um `device_id` (dica: `SCAN` +
   `SCARD`). Compare com o total de fraudes por troca de dispositivo.
2. Simule um checkout: leia `device:atual:X`, compare com um device diferente
   e escreva um alerta no `stream:fraude` com `XADD`.
3. Compare `MEMORY USAGE` de um HyperLogLog com o de um SET que tenha os
   mesmos ids. Quantas vezes maior?

---

# ➡️ Continue no [neo4j/README.md](../neo4j/README.md)
