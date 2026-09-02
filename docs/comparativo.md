# ⚖️ Matriz de decisão — qual banco escolher

> ⬅️ [README principal](../README.md)

## A regra que vale mais que a tabela

> **Nenhum banco NoSQL substitui o relacional.** Eles complementam.
>
> Se o seu problema tem transação com débito e crédito, integridade
> referencial e consulta imprevisível, a resposta é PostgreSQL. Os cinco
> bancos deste repositório entram **em volta** disso, não no lugar.

## Escolha por necessidade

| Você precisa de… | Use | Não use | Por quê |
|---|---|---|---|
| schema que varia por item | **MongoDB** | Cassandra | schema fixo por tabela |
| leitura de página inteira sem `JOIN` | **MongoDB** | Postgres | embedding resolve em 1 leitura |
| estado quente em < 1 ms | **Redis** | ClickHouse | é analítico, não operacional |
| contador atômico sob concorrência | **Redis** | Postgres | `INCR` não precisa de transação |
| dado que expira sozinho | **Redis** ou **Cassandra** | Postgres | TTL nativo x job de limpeza |
| relação entre entidades, N saltos | **Neo4j** | qualquer outro | `JOIN` recursivo não escala |
| caminho mais curto / comunidade | **Neo4j** | — | não tem equivalente prático |
| escrita massiva ordenada por chave | **Cassandra** | MongoDB | append sequencial, sem leitura antes |
| série temporal por entidade | **Cassandra** | ClickHouse | partição por entidade |
| agregação sobre bilhões de linhas | **ClickHouse** | Cassandra | nem tenta |
| `GROUP BY` livre e janelas | **ClickHouse** | Cassandra | não existe lá |
| transação ACID multi-tabela | **PostgreSQL** | todos os cinco | é para isso que ele existe |

## Custo de cada escolha

| Banco | Você ganha | Você perde |
|---|---|---|
| MongoDB | flexibilidade de schema, leitura sem `JOIN` | integridade referencial, `JOIN` eficiente |
| Redis | latência de microssegundos | tudo cabe na RAM; consulta só por chave |
| Neo4j | travessia de relações barata | agregação em massa é lenta; escala horizontal é difícil |
| Cassandra | escrita massiva, alta disponibilidade | sem `JOIN`, sem `GROUP BY` livre, sem consulta ad-hoc |
| ClickHouse | agregação absurdamente rápida, compressão | `UPDATE`/`DELETE` são caros; não é operacional |

## O mesmo dado, os cinco modelos

Um pedido da Liga Sudoers, e como cada banco o representa:

| Banco | Como o pedido existe | Como você acha |
|---|---|---|
| MongoDB | um documento com itens e auditoria dentro | `find({_id: 1})` |
| Redis | não existe inteiro; só o id numa LIST dos últimos 10 | `LRANGE pessoa:ultimos_pedidos:1` |
| Neo4j | um nó `(:Pedido)` ligado a pessoa, produtos, device, local | `MATCH (:Pessoa {id:1})-[:FEZ]->(p)` |
| Cassandra | uma linha em `pedidos_por_pessoa`, itens numa coleção congelada | `WHERE id_pessoa = 1` |
| ClickHouse | uma linha em `fato_pedidos` + N linhas em `fato_itens` | `WHERE id_pedido = 1` |
| PostgreSQL | 3 linhas em 3 tabelas normalizadas | `JOIN` |

> Repare que o Redis é o único que **não** guarda o pedido. Isso é a
> modelagem funcionando: ele foi projetado para estado quente, não para
> histórico. Um banco que guarda tudo não é mais completo — é mal modelado.

## Cassandra x ClickHouse: a confusão do "colunar"

| | Cassandra | ClickHouse |
|---|---|---|
| Categoria correta | *wide-column store* | *colunar analítico* |
| Agrupa em disco | linhas, por partição | colunas |
| Otimizado para | escrita, leitura por chave | agregação |
| `JOIN` | não existe | existe |
| `GROUP BY` livre | não | sim |
| Modelo de consulta | uma tabela por pergunta | SQL livre |
| Escala | horizontal, sem líder | vertical + shards |
| Uso típico | clickstream, IoT, log de eventos | dashboard, BI, analytics |

## Perguntas que ajudam a decidir

Antes de adicionar um banco à sua arquitetura, responda:

1. **Qual pergunta ele responde que nenhum banco que já tenho responde bem?**
   Se não houver resposta clara, não adicione.
2. **Quem opera isso às 3h da manhã?** Cada banco novo é mais um runbook, mais
   um backup, mais um alerta.
3. **Como o dado chega lá e como ele sai?** Um banco sem pipeline de entrada e
   saída vira ilha.
4. **O que acontece se ele cair?** O sistema degrada ou para?
5. **Dá para resolver com o Postgres que eu já tenho?** Muitas vezes dá —
   `JSONB`, índices GIN e extensões cobrem bastante coisa.

> A resposta "porque é moderno" reprova em qualquer entrevista de arquitetura.
