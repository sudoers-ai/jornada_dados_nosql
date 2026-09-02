# 1️⃣ Gerador — o universo compartilhado

> ⬅️ Voltar ao [README principal](../README.md)

Esta é a peça mais importante do repositório, e a que ninguém repara.

## O problema que ele resolve

Imagine que cada banco fosse populado por um script próprio, com `random`
próprio. O `id 1` do MongoDB seria a Maria; o `id 1` do Neo4j seria o João.
Aí você tenta fazer o exercício "siga a pessoa 1 atravessando a arquitetura"
e descobre que não há pessoa 1 — há cinco pessoas diferentes com o mesmo
número.

O `liga_sudoers_gen.py` resolve isso sendo **determinístico**: mesma semente,
exatamente os mesmos dados, sempre. Todos os *seeds* chamam ele.

```
mesma semente  ──►  mesmo universo  ──►  ids que batem entre os 5 bancos
                                          + o Postgres do jornada_dados
```

## O que ele gera

| Entidade | Padrão | Vai para |
|---|---|---|
| `categorias` | 12 | todos |
| `produtos` | 200, com atributos que **variam por categoria** | todos |
| `pessoas` | 500 | todos |
| `pedidos` | 5.000, com itens e auditoria embutidos | todos |
| `eventos` | clickstream por pessoa | Cassandra, ClickHouse |
| `reviews` | ~30% dos pedidos, texto em português | MongoDB |
| `aneis_fraude` | 6 anéis de 5 pessoas | Neo4j (é o alvo da caça) |

## As três fraudes plantadas

O gerador injeta fraude de propósito, nas mesmas regras do `jornada_dados`:

| Motivo | Como é plantado | Quem detecta bem |
|---|---|---|
| `geolocalizacao` | pedido com geohash fora de SP/MG/RJ | qualquer banco (é regra de linha) |
| `troca_dispositivo` | pedido com aparelho diferente do habitual | Redis (estado quente) |
| `dispositivo_compartilhado` | 5 contas com o **mesmo `device_id`** | **só o grafo** |

### `dispositivo` x `device_id` — a distinção que faz a diferença

* `dispositivo` é o **modelo**: "iPhone 15". Duas pessoas podem ter o mesmo
  modelo sem nenhuma relação entre si.
* `device_id` é o **fingerprint do aparelho físico**: `d-855b6c5b`. O mesmo
  `device_id` em duas contas significa o **mesmo aparelho**.

É por isso que os anéis não são óbvios olhando o modelo do celular. É o
`device_id` que denuncia — e é ele que vira um **nó** no Neo4j.

## Usando

Rodando dentro do container (não precisa de Python na sua máquina):

```bash
# só o resumo do universo
docker compose run --rm seeder python gerador/liga_sudoers_gen.py --resumo

# gerar os arquivos JSON
docker compose run --rm seeder python gerador/liga_sudoers_gen.py \
  --formato json --saida /app/saida

# gerar INSERTs para o Postgres do jornada_dados
docker compose run --rm seeder python gerador/liga_sudoers_gen.py \
  --formato sql --saida /app/saida
```

Saída esperada do `--resumo`:

```json
{
  "semente": 42,
  "pessoas": 500,
  "produtos": 200,
  "pedidos": 5000,
  "pedidos_fraudulentos": 235,
  "taxa_fraude_pct": 4.7,
  "fraude_por_motivo": {
    "dispositivo_compartilhado": 112,
    "troca_dispositivo": 77,
    "geolocalizacao": 46
  },
  "aneis_fraude": 6
}
```

## Provando o determinismo

Este é um bom primeiro exercício. Gere duas vezes e compare:

```bash
docker compose run --rm seeder bash -c "
  python gerador/liga_sudoers_gen.py --saida /tmp/a >/dev/null &&
  python gerador/liga_sudoers_gen.py --saida /tmp/b >/dev/null &&
  diff -r /tmp/a /tmp/b && echo '✅ idêntico' || echo '❌ divergiu'"
```

## Mudando o tamanho do universo

Edite o `.env` na raiz:

```bash
SEMENTE=42
N_PESSOAS=500
N_PRODUTOS=200
N_PEDIDOS=5000
```

> ⚠️ **Mudou qualquer um desses valores? Repopule TODOS os bancos** com
> `make seed`. Se você mudar a semente e repopular só um banco, os ids param
> de bater entre eles e o `make validar` vai acusar.

## Um detalhe fino: o geohash

O gerador implementa o algoritmo de geohash à mão (~25 linhas, sem
dependência externa). E faz uma coisa que parece exagero, mas não é: ele
**sorteia a coordenada de novo** até o prefixo de 3 caracteres bater com o da
capital da UF.

Por quê? Sem isso, ~3% dos pedidos legítimos de São Paulo caíam no prefixo
`6gz` em vez de `6gy`, e seriam classificados como fraude geográfica no outro
repositório. Falso positivo puro, causado pelo gerador e não pelo pipeline —
e o aluno passaria horas caçando um bug que não existe no código dele.

---

# ➡️ Continue no [mongodb/README.md](../mongodb/README.md)
