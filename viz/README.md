# 8️⃣ Dataviz — o painel comparativo

> ⬅️ Anterior: [integracao/](../integracao/README.md) · [README principal](../README.md)

Este repositório tem **três** camadas de visualização, e cada uma serve a um
propósito diferente.

## 1. Painel Streamlit — a comparação lado a lado

```bash
docker compose --profile viz up -d
# http://localhost:8501
```

A ideia do painel não é ser bonito. É ser **honesto**: cada aba faz uma
pergunta de negócio no banco correspondente, **mostra a consulta usada** e
**cronometra**. Você vê, com número na tela, onde cada paradigma brilha.

| Aba | O que ela prova |
|---|---|
| 📊 Visão geral | KPIs, série temporal e **mapa** dos pedidos (ClickHouse) |
| 📄 Documento | o mesmo campo com chaves diferentes por categoria |
| 🔑 Chave-valor | o estado quente da decisão antifraude, por pessoa |
| 🕸️ Grafo | os anéis de fraude e o score de risco |
| 🏛️ Wide-column | timeline por partition key — e o que ela **não** responde |
| 📈 Colunar | agregação, janela móvel e compressão real em disco |
| ⚖️ Comparativo | **a mesma pergunta nos 5 bancos**, cronometrada |

A última aba é a mais importante. Ela pergunta *"quantos pedidos a pessoa 1
fez?"* nos cinco bancos e mostra resposta, tempo e como cada um chegou lá.

> Repare que o **Redis responde 10**, não o total. Não é erro: ele guarda só
> os últimos 10 pedidos, porque foi modelado para estado quente e não para
> histórico. Cada banco responde o que foi projetado para responder — e
> entender isso é o objetivo da aula inteira.

O painel degrada com elegância: se um banco estiver fora do ar, aquela aba
mostra um aviso e as outras continuam funcionando.

## 2. Neo4j Browser — a visualização nativa do grafo

```bash
# http://localhost:7474   (neo4j / sudoers123)
```

Nenhuma biblioteca de gráfico desenha um anel de fraude melhor que o próprio
banco de grafos. Cole isto e veja a estrela de contas em volta de um único
aparelho:

```cypher
MATCH (d:Dispositivo)<-[:USOU]-(:Pedido)<-[:FEZ]-(p:Pessoa)
WITH d, count(DISTINCT p) AS qtd WHERE qtd > 1
WITH d LIMIT 1
MATCH caminho = (d)<-[:USOU]-(:Pedido)<-[:FEZ]-(:Pessoa)
RETURN caminho
```

## 3. Metabase — BI de verdade, para o aluno montar sozinho

```bash
make bi          # baixa o driver do ClickHouse e sobe o Metabase
# http://localhost:3010
```

No primeiro acesso você cria a conta de admin. Depois adicione as fontes:

| Campo | ClickHouse | MongoDB |
|---|---|---|
| Tipo | ClickHouse | MongoDB |
| Host | `clickhouse` | `mongodb` |
| Porta | `8123` | `27017` |
| Banco | `liga_sudoers` | `liga_sudoers` |
| Usuário / senha | `sudoers` / `sudoers` | `sudoers` / `sudoers` |
| Extra | — | *Authentication database:* `admin` |

### Duas armadilhas que o `make bi` já resolve para você

**1. O driver do ClickHouse não vem na imagem do Metabase.**
O de MongoDB vem; o de ClickHouse não. O alvo `make bi-driver` baixa o jar
para `metabase/plugins/`. Sem ele, o tipo "ClickHouse" simplesmente não
aparece na lista de bancos.

**2. O Metabase precisa de permissão de ESCRITA no diretório de plugins.**
Ele extrai o jar ali. Sem permissão, o log diz:

```
WARN metabase.plugins :: Metabase cannot use the plugins directory /plugins
     ... Falling back to a temporary directory for now.
```

…e o driver não carrega — **sem nenhum erro visível na interface**. O
`make bi-driver` faz o `chmod` necessário.

Confirmando que o driver carregou:

```bash
docker logs sudoers_metabase 2>&1 | grep -i clickhouse
# Registered driver :clickhouse (parents: [:sql-jdbc]) 🚚
```

Primeiro dashboard sugerido: faturamento por dia, taxa de fraude por UF e top
categorias. Tudo sai de `agg_vendas_dia` e `fato_pedidos`.

## Testando o painel sem abrir o navegador

O repositório tem um teste headless que executa o painel inteiro e captura
exceções:

```bash
docker compose run --rm seeder python tests/teste_viz.py
```

Esperado: `exceptions: 0`. Os dois "erros na página" que aparecem são
`st.error()` intencionais — as mensagens didáticas sobre fraude.

---

# ➡️ Continue nos [desafios/](../desafios/desafios.md)
