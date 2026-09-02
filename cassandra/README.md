# 5️⃣ Cassandra — banco **wide-column**

> ⬅️ Anterior: [neo4j/](../neo4j/README.md) · [README principal](../README.md)

## A regra de ouro

> **Você não modela os dados. Você modela as CONSULTAS.**

No Postgres você normaliza e depois escreve qualquer `SELECT` que quiser. No
Cassandra é o contrário: primeiro você lista as perguntas que o sistema vai
fazer, e cria **uma tabela para cada pergunta**. O mesmo dado é gravado várias
vezes, **de propósito**.

Isso parece errado para quem vem do relacional. Não é. A escrita no Cassandra
é baratíssima (append sequencial em disco, sem leitura antes de gravar); a
leitura sem partição definida é que é cara.

## Por que wide-column aqui?

Clickstream. Cada pessoa navegando gera dezenas de eventos por sessão: viu a
home, buscou, abriu o produto, colocou no carrinho, tirou do carrinho.

Esse volume tem três características que quebram um relacional:

1. escrita muito mais frequente que leitura;
2. dado que só faz sentido em ordem cronológica, por chave;
3. crescimento sem fim — você nunca "termina" de gerar clickstream.

## As tabelas deste repositório

| Pergunta | Tabela | Partition key |
|---|---|---|
| P1. O que a pessoa X fez? | `eventos_por_pessoa` | `(id_pessoa)` |
| P2. O que aconteceu no dia D? | `eventos_por_dia` | `(dia, hora_bucket)` |
| P3. Quais os pedidos da pessoa X? | `pedidos_por_pessoa` | `(id_pessoa)` |
| P4. Quantos eventos de cada tipo? | `contador_eventos` | `(dia)` |

**P1 e P2 guardam exatamente o mesmo dado.** Não é bug — é o projeto.

### O `hora_bucket` na chave de P2

Repare que a partition key de `eventos_por_dia` é `(dia, hora_bucket)`, e não
só `(dia)`. Sem o bucket, um dia inteiro de eventos cairia numa **única
partição**, que cresceria sem limite. Isso se chama **hot partition** e é o
erro nº 1 de quem está começando: um nó do cluster fica com uma partição
gigante e vira gargalo.

## Subindo

```bash
docker compose --profile widecolumn up -d
docker compose run --rm seeder python cassandra/seed_cassandra.py
```

> O Cassandra é o container mais lento a subir — costuma levar ~60s até ficar
> `healthy`. Use `make status` para acompanhar. Se rodar o seed antes da hora,
> você recebe `Connection refused` — espere e rode de novo.

## O erro que todo mundo comete

```bash
make q-cassandra
```

O bloco 2 do [`consultas.sh`](./consultas.sh) tenta isto:

```sql
SELECT * FROM eventos_por_pessoa WHERE tipo_evento = 'compra';
```

E recebe:

```
InvalidRequest: Cannot execute this query as it might involve data filtering
and thus may have unpredictable performance. If you want to execute this query
despite the performance unpredictability, use ALLOW FILTERING
```

**Isso é proposital.** Sem a partition key, o Cassandra teria que perguntar
para *todos* os nós do cluster. Ele prefere te barrar a te enganar.

### `ALLOW FILTERING` — a saída que você não deve usar

```sql
SELECT * FROM eventos_por_pessoa WHERE tipo_evento = 'compra' ALLOW FILTERING;
```

Funciona. Em 3 mil linhas é instantâneo. Em 3 bilhões, derruba o cluster.
`ALLOW FILTERING` em produção é incidente.

### A solução certa: outra tabela

```sql
SELECT * FROM eventos_por_dia WHERE dia = '2026-07-13' AND hora_bucket = 6;
```

Mesma informação, outra chave, consulta barata.

## Veja o coordenador trabalhando

O bloco 8 liga o `TRACING` e compara os dois caminhos. Resultado real deste
repositório:

```
com partition key  →  3.463 µs
varrendo tudo      → 46.587 µs      (13x mais lento, com só 3 mil linhas)
```

Agora extrapole para bilhões.

## Outras coisas que valem a parada

**Coleção congelada = o `JOIN` que não existe**

```sql
SELECT dt_venda, id_pedido, itens FROM pedidos_por_pessoa WHERE id_pessoa = 1;
--  [(28, 1, 1696.64), (82, 3, 7282.80), ...]
```

Os itens estão **dentro** da linha. Não existe tabela de itens para juntar.

**`COUNTER` — coluna que só aceita incremento**

```sql
INSERT INTO contador_eventos (dia, tipo_evento, total) VALUES ('2026-01-01','teste',5);
-- InvalidRequest: INSERT statements are not allowed on counter tables, use UPDATE instead
```

**`token()` — como o Cassandra escolhe o nó**

```sql
SELECT id_pessoa, token(id_pessoa) FROM eventos_por_pessoa LIMIT 5;
```

O token é o hash da partition key. Ele define em qual nó o dado mora. É só
isso — e é por isso que a partition key é a decisão mais importante do schema.

**Detectando hot partition**

```bash
docker exec sudoers_cassandra nodetool tablestats liga_sudoers.eventos_por_pessoa \
  | grep -E "Number of partitions|Compacted partition maximum bytes"
```

Partição gigante = nó sobrecarregado.

## Exercícios rápidos

1. Modele uma tabela que responda *"quais pedidos fraudulentos houve no dia
   D?"*. Qual partition key? Precisa de bucket?
2. Rode `TRACING ON` numa consulta com e sem partition key e compare
   `source_elapsed`. Anote os dois números.
3. Explique, em duas frases, por que `eventos_por_pessoa` e `eventos_por_dia`
   guardarem o mesmo dado **não** é desperdício.

---

# ➡️ Continue no [clickhouse/README.md](../clickhouse/README.md)
