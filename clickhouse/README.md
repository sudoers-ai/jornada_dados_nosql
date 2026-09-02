# 6️⃣ ClickHouse — banco **colunar analítico**

> ⬅️ Anterior: [cassandra/](../cassandra/README.md) · [README principal](../README.md)

## Primeiro, desfaça a confusão

"Colunar" é usado para duas coisas diferentes, e misturar as duas é o
mal-entendido mais comum da área:

| | Cassandra | ClickHouse |
|---|---|---|
| Categoria | *wide-column store* | *colunar analítico* |
| Guarda | **linhas** agrupadas por partição | **colunas** juntas em disco |
| Otimizado para | escrita massiva, leitura por chave | agregação sobre tudo |
| `GROUP BY` livre | não | sim |
| `JOIN` | não existe | existe |
| Somar 1 bilhão de valores | pesadelo | < 1 segundo |
| Aguentar 1 milhão de escritas/s | sim | não |

**Nenhum dos dois é melhor.** Eles resolvem problemas opostos. Ter os dois
com o mesmo clickstream, neste repositório, é o jeito mais rápido de nunca
mais confundir.

## Por que colunar é rápido em agregação

```sql
SELECT sum(valor_total) FROM fato_pedidos;
```

Num banco de **linhas**, o disco lê a linha inteira — todas as 14 colunas —
só para pegar uma. Num **colunar**, lê só o arquivo daquela coluna. E como
valores da mesma coluna são parecidos entre si, comprimem muito melhor.

Prova, medida neste repositório:

```
consulta                              read_rows   bytes_lidos
SELECT sum(valor_total) FROM fato_itens   14.924   116.59 KiB
```

## O papel dele na arquitetura

Os outros quatro bancos são **origens**: atendem a aplicação.

O ClickHouse é o oposto: é o **destino**. É onde a pergunta de negócio é
respondida e é ele que alimenta o dashboard. Na arquitetura do
`jornada_dados` ele ocupa o mesmo lugar do PostgreSQL OLAP (star schema) —
com a diferença de agregar ordens de magnitude mais rápido.

## Subindo

```bash
docker compose --profile colunar up -d
docker compose run --rm seeder python clickhouse/seed_clickhouse.py
```

Interface web pronta, sem instalar nada: **http://localhost:8123/play**
(usuário `sudoers`, senha `sudoers`).

> A porta nativa foi mapeada para **9010**, porque a 9000 no host é do MinIO
> do `jornada_dados`.

## Os conceitos, um por um

```bash
make q-clickhouse
```

### `PARTITION BY` — descartar arquivos inteiros

```sql
PARTITION BY toYYYYMM(dt_venda)
```

Filtrar por data descarta partições inteiras sem abrir nada. Medido aqui:

```
consultando 1 mês de 5.000 pedidos → read_rows: 871, lidos: 10.21 KiB
```

### `ORDER BY` — o índice primário é **esparso**

```sql
ORDER BY (dt_venda, id_pessoa)
SETTINGS index_granularity = 8192
```

O índice guarda **uma marca a cada 8.192 linhas**, não uma entrada por linha.
Por isso ele cabe na memória mesmo com bilhões de linhas:

```
tabela          linhas    índice na RAM
fato_itens      14.924    126 bytes
fato_pedidos     5.000    112 bytes
```

Um B-tree do Postgres indexaria **todas** as linhas.

### `LowCardinality` — dicionário interno

Para colunas com poucos valores distintos (UF, categoria, status). Medido
aqui, na mesma tabela:

| coluna | tipo | em disco |
|---|---|---|
| `telefone` | `String` | 42.49 KiB |
| `device_id` | `String` | 30.48 KiB |
| `dispositivo` | `LowCardinality(String)` | **6.15 KiB** |
| `uf` | `LowCardinality(String)` | **4.05 KiB** |
| `motivo_fraude` | `LowCardinality(String)` | **1.91 KiB** |

> ⚠️ **Não** use `LowCardinality` em coluna com muitos valores distintos
> (`cpf`, `email`, `id`): o dicionário fica maior que o dado e **piora**.

### `MATERIALIZED VIEW` — agregado que se atualiza na ingestão

Diferente de uma view do Postgres (que só guarda a query) e de uma tabela do
dbt (que precisa de um job rodando de novo), a MV do ClickHouse é um
**gatilho de inserção**: cada linha nova em `fato_pedidos` já atualiza o
agregado. Latência zero, sem orquestrador.

```sql
SELECT uf, sum(pedidos), sum(faturamento) FROM agg_vendas_dia GROUP BY uf;  -- 3 ms
SELECT uf, count(),     sum(valor_total)  FROM fato_pedidos  GROUP BY uf;   -- 11 ms
```

Mesmo resultado. Compare com o esforço de manter isso no dbt + Airflow.

### Uma pegadinha honesta: `Date` x `Date32`

O tipo `Date` do ClickHouse só cobre **1970 a 2149**. Como a Liga Sudoers tem
clientes nascidos antes de 1970, `dt_nasc` precisa ser `Date32` (1900–2299).
Sem isso a carga falha com uma mensagem enganosa sobre valores nulos.

### Outra: partes `Compact` x `Wide`

Por padrão, partes pequenas (< 10 MB) usam o formato **Compact**: todas as
colunas num arquivo só. Aí `system.parts_columns` retorna **zero** para o
tamanho de cada coluna, e a demonstração de compressão não funciona.

Por isso `fato_pedidos` sobe com `min_bytes_for_wide_part = 0`, forçando o
formato **Wide** (um arquivo por coluna). É didático. **Em produção, deixe o
padrão.**

## Exercícios rápidos

1. Compare `SELECT count()` com `SELECT count(DISTINCT id_pessoa)` e
   `SELECT uniq(id_pessoa)`. Por que o `uniq` é mais rápido? (Dica: é o mesmo
   truque do `PFCOUNT` do Redis.)
2. Rode o mesmo `GROUP BY tipo_evento` na tabela `eventos` daqui e tente o
   equivalente no Cassandra. O que acontece lá?
3. Crie uma MV nova que agregue por categoria e confirme que ela se preenche
   sozinha ao inserir uma linha em `fato_itens`.

---

# ➡️ Continue no [integracao/README.md](../integracao/README.md)
