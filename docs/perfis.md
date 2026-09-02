# 👩‍💻 Perfis e responsabilidades — Jornada NoSQL

> ⬅️ [README principal](../README.md)
>
> Ao longo dos desafios, tente enxergar cada tarefa sob cada um destes
> chapéus. É assim que se ganha visão de arquitetura.

## Data Architect (Arquiteto de Dados)

**A pergunta dele:** *por que este banco, e não o que já temos?*

Neste repositório ele é o dono da [matriz de decisão](./comparativo.md) e do
[guia de modelagem](./modelagem.md). É quem defende que `Dispositivo` deve ser
um **nó** e não uma coluna, e quem diz "não" quando alguém quer adicionar o
sexto banco.

**Entregável típico:** o `ARQUITETURA_SENIOR.md` dos desafios — em especial a
tarefa de **podar** um banco da arquitetura.

## Data Engineer (Engenheiro de Dados)

**A pergunta dele:** *como o dado entra, se transforma e sai daqui?*

É o dono da pasta [`integracao/`](../integracao/README.md): a carga no OLTP, o
export para o lake, o conector de CDC. É quem descobre que o conector está
`RUNNING` mas não produz tópico, e por quê.

**Entregável típico:** as três pontes funcionando e documentadas, com plano de
reprocessamento idempotente.

## Data Modeler / Data Administrator

**A pergunta dele:** *esta chave primária aguenta o volume de daqui a 2 anos?*

É quem escolhe a partition key do Cassandra, quem decide o `ORDER BY` do
ClickHouse, quem percebe que um array embutido sem limite vai estourar os
16 MB do MongoDB.

**Entregável típico:** o desafio Pleno de remodelar as `reviews` e a tabela
nova do Cassandra, com justificativa de hot partition.

## Platform Engineer / DevOps

**A pergunta dele:** *quem acorda às 3h se isso cair?*

É quem cuida dos profiles, dos healthchecks, dos limites de memória, das
portas que não podem colidir. É quem escreve o `scripts/esperar.sh` porque o
Cassandra demora 60s e o seed falha se rodar antes.

**Entregável típico:** os indicadores e alarmes do desafio Sênior — um por
banco, com o comando que coleta cada métrica.

## Data Analyst / Analytics Engineer

**A pergunta dele:** *como eu respondo a pergunta do negócio?*

É o consumidor do ClickHouse e do Metabase. É quem descobre que a
`MATERIALIZED VIEW` responde em 3 ms o que a tabela fato responde em 11 ms — e
quem decide se essa diferença importa.

**Entregável típico:** o dashboard do [`viz/`](../viz/README.md) e a análise de
fraude por UF e categoria.

## Data Scientist

**A pergunta dele:** *quais features eu consigo extrair daqui?*

O `score_risco` que sai do Neo4j é exatamente isso: uma feature que **nenhuma
regra de linha produz**, porque depende da topologia da rede de contas. É a
ponte deste repositório com o modelo antifraude do `jornada_dados`.

**Entregável típico:** o desafio final — a pergunta que exige grafo + DW +
Redis ao mesmo tempo.

---

## Como usar isto nos desafios

Para cada tarefa que você concluir, pergunte-se:

1. Qual desses perfis assinaria essa entrega?
2. O que **outro** perfil reclamaria dela?

A segunda pergunta é a que mais ensina. O modelo que o Data Modeler adora
pode ser o que o DevOps odeia operar — e saber conduzir essa conversa é o que
separa o sênior do pleno.
