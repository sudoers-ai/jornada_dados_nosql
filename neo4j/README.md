# 4️⃣ Neo4j — banco de **grafos**

> ⬅️ Anterior: [redis/](../redis/README.md) · [README principal](../README.md)

> **Esta é a parada mais importante do repositório.** É aqui que fica claro
> que existe uma classe de pergunta que os outros bancos simplesmente não
> respondem bem.

## O problema

O `jornada_dados` pega fraude com regras de linha: *"este pedido saiu de fora
de SP/MG/RJ"*, *"esta pessoa trocou de celular"*. Regras que olham **um
registro por vez**.

Agora considere o seguinte cenário:

> Cinco contas. Cinco CPFs válidos e diferentes. Cinco nomes diferentes.
> Todas comprando de dentro de São Paulo. Todas usando "o seu" celular de
> sempre. Cada pedido, isolado, é **perfeitamente normal**.
>
> O que elas têm em comum: é o **mesmo aparelho físico** e o **mesmo
> telefone**.

Nenhuma regra de linha pega isso, porque a informação não está **numa** linha
— está na **ligação entre** as linhas.

## A modelagem que torna isso visível

A decisão inteira está em uma frase: **`Dispositivo`, `Telefone` e `Local`
viram NÓS, não colunas.**

Como nó, eles podem ser *compartilhados* — e o compartilhamento é exatamente
o que queremos enxergar.

```
(:Pessoa)-[:FEZ]->(:Pedido)-[:CONTEM]->(:Produto)-[:PERTENCE_A]->(:Categoria)
                      │
                      ├──[:USOU]────────►(:Dispositivo)
                      ├──[:VIA_TELEFONE]►(:Telefone)
                      └──[:ORIGINADO_EM]►(:Local)

(:Pessoa)-[:DISPOSITIVO_PADRAO]->(:Dispositivo)
(:Pessoa)-[:TEM_TELEFONE]------->(:Telefone)
```

## Subindo

```bash
docker compose --profile grafo up -d
docker compose run --rm seeder python neo4j/seed_neo4j.py
```

O seed já confere sozinho se achou os 6 anéis que o gerador plantou:

```
  dispositivos compartilhados (aneis): 6
  esperado pelo gerador .............. 6
```

## A consulta que justifica o banco existir

```cypher
MATCH (d:Dispositivo)<-[:USOU]-(:Pedido)<-[:FEZ]-(p:Pessoa)
WITH d, collect(DISTINCT p.id) AS pessoas, count(DISTINCT p) AS qtd
WHERE qtd > 1
RETURN d.device_id, d.modelo, qtd, pessoas ORDER BY qtd DESC;
```

Leia o `MATCH` como um **desenho**: *uma Pessoa fez um Pedido que USOU um
Dispositivo… que foi usado por Pedido de OUTRA Pessoa.*

Resultado:

```
"d-32df8d45", "Motorola Edge 40", 5, [1, 45, 81, 123, 336]
"d-855b6c5b", "iPad Air",         5, [19, 87, 185, 315, 346]
...
```

Agora veja quem são:

```
dispositivo   | nome                   | cpf              | uf
d-32df8d45    | Davi Miguel Teixeira   | 701.829.453-32   | RJ
d-32df8d45    | Dra. Alexia Porto      | 604.782.135-90   | SP
d-32df8d45    | Ravi Rocha             | 064.891.537-93   | MG
d-32df8d45    | Thomas Camargo         | 934.058.627-10   | SP
d-32df8d45    | Srta. Luana Viana      | 952.078.364-47   | SP
```

CPFs diferentes. Nomes diferentes. UFs todas válidas. Nenhuma linha, sozinha,
levanta suspeita.

## O caminho mais curto: a consulta impossível em SQL

```cypher
MATCH caminho = shortestPath((a)-[:FEZ|USOU|VIA_TELEFONE*..6]-(b))
RETURN length(caminho), [n IN nodes(caminho) | labels(n)[0] + ": " + coalesce(n.nome, n.device_id, n.numero, toString(n.id))]
```

```
4 saltos:
  Pessoa: Thomas Camargo
    → Pedido: 3587
      → Dispositivo: d-32df8d45
        → Pedido: 1129
          → Pessoa: Srta. Luana Viana
```

Em SQL isso seria **seis self-joins encadeados**, um por salto possível — e
você precisaria saber *antes* quantos saltos procurar. Aqui você diz `*..6` e
o banco encontra.

> Repare no `[:FEZ|USOU|VIA_TELEFONE*..6]`: filtramos os **tipos** de aresta
> de propósito. Sem isso, o caminho mais curto poderia passar por um produto
> que as duas compraram por coincidência — verdade, mas não é o que estamos
> investigando.

## Veja o grafo desenhado

Abra **http://localhost:7474** (usuário `neo4j`, senha `sudoers123`) e cole:

```cypher
MATCH (d:Dispositivo)<-[:USOU]-(:Pedido)<-[:FEZ]-(p:Pessoa)
WITH d, count(DISTINCT p) AS qtd WHERE qtd > 1
WITH d LIMIT 1
MATCH caminho = (d)<-[:USOU]-(:Pedido)<-[:FEZ]-(:Pessoa)
RETURN caminho
```

É o "aha" da aula: a estrela de contas em volta de um único aparelho, na tela.

## O grafo também devolve valor para o outro repositório

A consulta 6 do [`consultas.cypher`](./consultas.cypher) calcula um
**score de risco** por pessoa, combinando três sinais que só o grafo conhece:

* proporção de pedidos fraudulentos,
* quantos aparelhos distintos a pessoa usou,
* **quantas outras contas se conectam a ela** por aparelho compartilhado.

Esse score é exportado para o Data Lake e volta para a camada gold do
`jornada_dados`. O ciclo fecha: o lake alimenta o grafo, o grafo devolve
inteligência ao lake.

## Rodando tudo

```bash
make q-neo4j

# ou interativo
docker exec -it sudoers_neo4j cypher-shell -u neo4j -p sudoers123
```

## Exercícios rápidos

1. Ache os telefones compartilhados por mais de uma conta. Eles são os mesmos
   anéis dos dispositivos? Por quê?
2. Escreva a consulta "produtos comprados junto com o produto 42". Note que é
   **o mesmo padrão** da detecção de fraude: dois nós ligados por um terceiro.
   Fraude e recomendação são o mesmo problema de grafo.
3. Tente escrever, em SQL, a consulta de anel de fraude contra o Postgres do
   `jornada_dados`. Cronometre quanto tempo você leva só para escrever.

---

# ➡️ Continue no [cassandra/README.md](../cassandra/README.md)
