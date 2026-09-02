# 🧪 Desafios da Jornada NoSQL

> ⬅️ [README principal](../README.md)

Escolha seu nível. Cada desafio tem **tarefas**, **evidências** (o que
comprova que deu certo) e **entregáveis** (o que você vai postar/commitar).
**Não é necessário alterar nenhum código do projeto.**

- [Nível Júnior](#-nível-júnior) — os cinco paradigmas de pé
- [Nível Pleno](#-nível-pleno) — modelagem, integração e trade-offs
- [Nível Sênior](#-nível-sênior) — arquitetura, custo e decisão

> **Pré-requisito:** conclua o desafio Júnior do repositório `jornada_dados`
> antes. Aqui a gente assume que você já viu o pipeline relacional funcionando.

---

## 🔹 Nível Júnior

**Foco:** subir os cinco bancos, popular e enxergar a diferença entre eles.

### Tarefas

1. Subir cada paradigma **por profile**, um de cada vez, e anotar quanto de
   RAM cada um consome (`docker stats`).
2. Popular os cinco com `make seed` e rodar `make validar` sem nenhuma falha.
3. Rodar os roteiros de consulta de cada pasta (`make q-mongo`, `q-redis`,
   `q-neo4j`, `q-cassandra`, `q-clickhouse`).
4. Responder **a mesma pergunta nos cinco bancos**: *"quais pedidos a pessoa 1
   fez?"*. Anote a consulta de cada um.
5. Achar, no Mongo e no Neo4j, o mesmo anel de fraude. Comparar as duas
   consultas lado a lado.
6. Abrir o painel (http://localhost:8501) e o Neo4j Browser
   (http://localhost:7474) e navegar.

### Evidências mínimas

* Saída completa do `make validar` com **0 falhas**.
* Print do `docker stats` com os cinco containers.
* As cinco consultas da tarefa 4, com a resposta de cada uma.
* Print do grafo desenhado no Neo4j Browser mostrando um anel.
* Print do erro `InvalidRequest ... use ALLOW FILTERING` do Cassandra.

### Entregáveis

* `CHECKLIST_JUNIOR.md` preenchido (modelo em [`../docs/checklist.md`](../docs/checklist.md)).
* Uma tabela sua: *banco × pergunta que ele responde bem × pergunta que ele
  responde mal*.

---

## 🔸 Nível Pleno

**Foco:** modelar de verdade, integrar com o `jornada_dados` e justificar
escolhas.

### Tarefas

1. **Modelagem no Cassandra.** Crie uma tabela que responda *"quais pedidos
   fraudulentos houve no dia D, por UF?"*. Justifique a partition key
   escolhida e explique como você evitou hot partition.
2. **Modelagem no MongoDB.** As `reviews` estão embutidas no produto. Um
   produto campeão de vendas pode ter 50 mil reviews. Explique o problema
   (limite de 16 MB por documento) e **proponha e implemente** um modelo
   alternativo. Meça a diferença.
3. **Grafo além da fraude.** Escreva uma consulta de recomendação
   ("quem comprou X também comprou Y") e explique por que ela é *o mesmo
   padrão* da detecção de anel.
4. **Integração — carga.** Rode `make lake-oltp args=--limpar` e confirme que
   `pessoas.id = 1` é a mesma pessoa nos seis bancos (5 NoSQL + Postgres).
5. **Integração — lake.** Rode `make lake-export`, leia um dos Parquet com o
   Spark do `jornada_dados` e faça um `SELECT` com contagem.
6. **Integração — CDC.** Registre o conector do MongoDB, insira um documento e
   capture o evento no Kafka. Compare com o CDC do Postgres.
7. **ClickHouse.** Crie uma `MATERIALIZED VIEW` nova e prove que ela se
   preenche sozinha na ingestão (insira uma linha e consulte).

### Evidências mínimas

* `DESCRIBE` da sua tabela do Cassandra + a consulta rodando + `TRACING`.
* Comparação antes/depois do modelo de reviews (tamanho do documento, tempo).
* Log do conector Debezium `RUNNING` **e** a lista de tópicos criados.
* Saída do `kafka-console-consumer` com o evento `"op": "c"`.
* Print do Spark lendo `s3a://raw/neo4j/score_risco_pessoa/`.

### Entregáveis

* `RELATORIO_PLENO.md` com:
  * as decisões de modelagem e o porquê de cada uma;
  * evidências (prints e saídas);
  * 3 riscos da arquitetura + mitigação;
  * uma seção **"o que eu faria diferente"**.

---

## 🟣 Nível Sênior

**Foco:** decidir. Arquitetura é escolha sob restrição, não catálogo de
ferramentas.

### Tarefas

1. **Poda da arquitetura.** Escolha **um** dos cinco bancos e defenda, por
   escrito, que ele deveria ser removido: qual outro assumiria sua função,
   quanto se perde, quanto se economiza em operação. Depois defenda o
   contrário. (Sim, os dois lados.)
2. **Consistência.** Os cinco bancos têm garantias diferentes. Descreva o que
   acontece se o Redis cair **entre** a gravação do pedido no Postgres e a
   atualização do `device:atual`. O sistema fica inconsistente? Por quanto
   tempo? Como você detecta? Como reconcilia?
3. **Custo real.** Estime o custo mensal desta arquitetura em nuvem para
   **100x** o volume atual. Qual banco domina o custo? A resposta muda se o
   perfil for mais leitura ou mais escrita?
4. **O grafo em produção.** O `score_risco` é recalculado varrendo o grafo
   inteiro. Isso não escala. Proponha uma estratégia incremental: o que
   dispara o recálculo, de quem, e com qual latência aceitável.
5. **Reprocessamento.** O `make lake-export` sobrescreve a partição do dia.
   Desenhe um plano de reprocessamento idempotente e explique o que acontece
   se ele rodar duas vezes no mesmo dia.
6. **Governança.** Estes bancos guardam CPF, telefone e geolocalização.
   Aponte onde há dado pessoal em cada um, e proponha um plano de
   mascaramento/retenção que respeite a LGPD **sem** quebrar a detecção de
   fraude. (Dica: o anel é detectável com o `device_id` anonimizado?)
7. **Observabilidade.** Defina 5 indicadores e seus alarmes: um por banco.
   Para cada um, diga qual comando/consulta coleta a métrica.

### Evidências mínimas

* Os dois lados do argumento da tarefa 1, com números.
* Diagrama (pode ser ASCII) do fluxo de reconciliação da tarefa 2.
* Planilha ou tabela de custo estimado, com as premissas explícitas.
* Tabela: banco × dado pessoal × tratamento proposto.
* Tabela: indicador × como coletar × limiar de alarme.

### Entregáveis

* `ARQUITETURA_SENIOR.md` com:
  * a decisão de poda e sua justificativa;
  * o modelo de consistência e reconciliação;
  * a estimativa de custo com premissas;
  * o plano de LGPD;
  * os indicadores e alarmes.

---

## 🏁 Desafio final (opcional, vale por todos)

Junte os dois repositórios e responda **uma** pergunta de negócio que exija
os dois lados:

> *"Quais clientes têm alto score de risco no grafo, compraram acima da mediana
> no DW, e ainda estão com carrinho ativo no Redis agora?"*

Essa pergunta não é respondível por nenhum banco sozinho. Ela exige o grafo
(score), o lake/DW (histórico agregado) e o Redis (estado atual). Entregue a
consulta, o resultado e o desenho do fluxo.

Se você conseguir responder isso e explicar cada escolha, você entendeu
persistência poliglota.
