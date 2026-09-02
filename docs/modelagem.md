# 📐 Guia de modelagem — o mesmo dado, cinco modelos

> ⬅️ [README principal](../README.md)

Este documento mostra como **a mesma entidade** vira cinco coisas diferentes,
e qual pergunta cada modelagem otimiza.

## Ponto de partida: o modelo relacional

No `jornada_dados`, um pedido é 3ª forma normal:

```sql
pessoas(id, nome, sexo, dt_nasc)
pedidos(id, id_pessoa, dt_venda, valor_total)
itens_pedidos(id_pedido, id_produto, qtde, valor_total)
produtos(id, id_categoria, descricao, valor_unit)
categorias(id, descricao)
auditoria_pedidos(id_pedido, dispositivo, geohash, telefone)
```

Normalizar é ótimo para **escrever sem duplicar**. E é ruim para ler: mostrar
um pedido na tela exige 4 `JOIN`s.

---

## 📄 Documento (MongoDB) — otimiza a LEITURA DO AGREGADO

```javascript
{
  _id: 1,
  id_pessoa: 1,
  dt_venda: ISODate("2026-03-06"),
  valor_total: 24603.23,
  itens: [                                  // ← embutido
    { id_produto: 82, descricao: "...", qtde: 3, valor_total: 7282.80 }
  ],
  auditoria: {                              // ← embutido
    dispositivo: "iPhone 15", device_id: "d-855b6c5b",
    geohash: "6gybu2x", uf: "SP", telefone: "(11) 9..."
  },
  fraude: false
}
```

**Pergunta otimizada:** *"mostre o pedido 1"* → uma leitura, zero `JOIN`.

**Regra de decisão:** embuta o que é **lido junto e muda junto**. Referencie o
que tem ciclo de vida próprio (`pessoas` continua sendo referência por id).

**O limite:** documento tem teto de 16 MB. Array que cresce sem limite é
antipadrão — por isso as `reviews` embutidas neste repositório têm corte.

---

## 🔑 Chave-valor (Redis) — otimiza a DECISÃO IMEDIATA

```
device:atual:1              → "d-5a856750"          (STRING)
device:hist:1               → {d-5a856750, d-32df8d45}  (SET)
pessoa:ultimos_pedidos:1    → [4794, 3396, 4219, ...]   (LIST, máx 10)
rank:produtos               → {produto:93 → 265, ...}    (ZSET)
```

**Pergunta otimizada:** *"esse cliente trocou de aparelho?"* → O(1).

**Regra de decisão:** o Redis não guarda **o dado**; guarda **a resposta**.
Você não pergunta "quais os pedidos dele" — você pergunta "o que eu preciso
saber agora para decidir".

**O limite:** cabe na RAM. E você só acha por chave — não existe "where".

---

## 🕸️ Grafo (Neo4j) — otimiza a RELAÇÃO

```
(:Pessoa {id:1})-[:FEZ]->(:Pedido {id:1})-[:USOU]->(:Dispositivo {device_id:"d-32df8d45"})
                                                            ▲
(:Pessoa {id:45})-[:FEZ]->(:Pedido {id:1129})-[:USOU]───────┘
```

**Pergunta otimizada:** *"quem mais usou esse aparelho, e quem se conecta a
essas pessoas?"*

**Regra de decisão — a mais importante deste documento:**

> Aquilo que você quer ver **compartilhado** precisa virar **nó**, não coluna.

`dispositivo` como coluna numa tabela é um atributo do pedido.
`(:Dispositivo)` como nó é uma entidade que **vários** pedidos apontam — e é
isso que torna o anel visível.

**O limite:** agregação em massa ("some tudo") é lenta. Grafo é para
travessia, não para somatório.

---

## 🏛️ Wide-column (Cassandra) — otimiza a ESCRITA E A LEITURA POR CHAVE

```sql
CREATE TABLE eventos_por_pessoa (
    id_pessoa int, ts timestamp, id_evento uuid, tipo_evento text, ...
    PRIMARY KEY ((id_pessoa), ts, id_evento)
) WITH CLUSTERING ORDER BY (ts DESC);

-- MESMO dado, outra chave, outra pergunta:
CREATE TABLE eventos_por_dia (
    dia date, hora_bucket int, ts timestamp, ...
    PRIMARY KEY ((dia, hora_bucket), ts, id_evento)
);
```

**Pergunta otimizada:** *"os últimos eventos da pessoa X"* → uma partição, um
nó, já ordenado.

**Regra de decisão:** liste as perguntas **antes** de criar as tabelas. Uma
tabela por pergunta. Duplicar dado é o projeto, não o problema.

**O limite:** sem `JOIN`, sem `GROUP BY` livre, sem consulta ad-hoc. Se a
pergunta muda, você precisa de uma tabela nova.

---

## 📈 Colunar (ClickHouse) — otimiza a AGREGAÇÃO

```sql
CREATE TABLE fato_pedidos (
    id_pedido UInt32, dt_venda DateTime,
    uf LowCardinality(String),            -- ← dicionário
    valor_total Decimal(12,2), fraude UInt8, ...
) ENGINE = MergeTree()
PARTITION BY toYYYYMM(dt_venda)           -- ← descarta arquivos
ORDER BY (dt_venda, id_pessoa);           -- ← índice esparso
```

**Pergunta otimizada:** *"faturamento por UF por mês"* → lê só as colunas
`uf`, `valor_total` e a partição do período.

**Regra de decisão:** o `ORDER BY` **é** o índice. Coloque nele as colunas
pelas quais você mais filtra, da mais seletiva para a menos.

**O limite:** `UPDATE` e `DELETE` são caros (reescrevem partes). Não use como
banco operacional.

---

## Resumo em uma frase cada

| Paradigma | A pergunta que ele otimiza |
|---|---|
| Relacional | "garanta que isso está correto e consistente" |
| Documento | "me devolva esta coisa inteira" |
| Chave-valor | "decida isso agora" |
| Grafo | "como estas coisas se conectam?" |
| Wide-column | "grave muito e me devolva por chave, em ordem" |
| Colunar | "some tudo isso, rápido" |

Se você souber responder qual dessas frases descreve o seu problema, você já
escolheu o banco.
