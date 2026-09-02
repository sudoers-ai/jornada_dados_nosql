# 🗄️ Liga Sudoers — o lado NoSQL

> Repositório-irmão do [`jornada_dados`](../jornada_dados). Lá você constrói a
> trilha **relacional**: OLTP → CDC → Kafka → Spark → Delta Lake → DW.
> Aqui você constrói os **satélites**: os bancos que o mundo real coloca em
> volta desse núcleo, e que servem de **origem** para aquele pipeline.

Bem-vindo à segunda parte do Mapa do Engenheiro de Dados. Se no primeiro
repositório o desafio era mover dado de um lado para o outro, aqui o desafio é
outro e mais difícil: **escolher onde o dado deve morar.**

---

## 🎯 O que você vai aprender aqui

Não é "como usar o MongoDB". É **por que existe um MongoDB**.

Cada um dos cinco bancos deste repositório resolve um problema que o
PostgreSQL do `jornada_dados` resolveria mal — e cada um deles é péssimo em
alguma coisa que o PostgreSQL faz muito bem. Ao final você vai conseguir
defender, numa reunião de arquitetura, por que colocou cada peça no lugar
onde colocou.

### Os cinco paradigmas e o papel de cada um

| Paradigma | Banco | O problema que ele resolve na Liga Sudoers |
|---|---|---|
| 📄 **Documento** | MongoDB | Produto de categoria diferente tem atributo diferente. Livro tem ISBN, eletrônico tem voltagem. Tabela não acomoda isso. |
| 🔑 **Chave-valor** | Redis | Decidir, em menos de 1 ms durante o checkout, se o cliente trocou de aparelho. Ir ao banco transacional é inviável. |
| 🕸️ **Grafo** | Neo4j | Cinco contas diferentes usando o mesmo celular. Nenhuma regra de linha pega isso; a ligação entre elas é que denuncia. |
| 🏛️ **Wide-column** | Cassandra | Clickstream: escrita massiva, contínua, sempre lida por chave e em ordem cronológica. |
| 📈 **Colunar** | ClickHouse | Somar bilhões de linhas em milissegundos para o dashboard. |

> **Atenção a uma confusão muito comum:** Cassandra e ClickHouse são chamados
> de "colunares", mas são coisas diferentes. Cassandra é *wide-column store*
> (agrupa **linhas** por partição, otimizado para escrita). ClickHouse é
> *colunar analítico* (agrupa **colunas** em disco, otimizado para agregação).
> Ter os dois lado a lado, com o mesmo dado, resolve essa dúvida de vez.

---

## 🔗 A ideia central: um universo, cinco bancos

Todos os bancos são populados pelo **mesmo gerador**, com a **mesma semente**.

Isso significa que `pessoa.id = 1` é a **mesma pessoa** no MongoDB, no Redis,
no Neo4j, no Cassandra, no ClickHouse — e também no PostgreSQL do
`jornada_dados`, quando você rodar a carga.

Sem isso, os bancos seriam cinco ilhas e nenhum exercício de cruzamento faria
sentido. Com isso, você consegue seguir a *mesma pessoa* atravessando toda a
arquitetura.

```
                    gerador/liga_sudoers_gen.py
                         (semente = 42)
                               │
      ┌──────────┬─────────────┼─────────────┬──────────┐
      ▼          ▼             ▼             ▼          ▼
  MongoDB     Redis         Neo4j       Cassandra   ClickHouse
 (documento) (chave-valor)  (grafo)   (wide-column)  (colunar)
      │          │             │             │          │
      └──────────┴──────┬──────┴─────────────┴──────────┘
                        │  integracao/
                        ▼
         ┌──────────────────────────────────┐
         │   repo jornada_dados             │
         │   Postgres OLTP → Debezium →     │
         │   Kafka → Spark → Delta → DW     │
         └──────────────────────────────────┘
```

---

## 🕵️ A história que amarra tudo: fraude

O `jornada_dados` detecta fraude com duas regras de linha:

* **Geolocalização** — compra fora de SP, MG ou RJ.
* **Troca de dispositivo** — o cliente mudou de aparelho.

Este repositório acrescenta a terceira, que **nenhuma regra de linha pega**:

* **Anel de fraude** — cinco contas, cinco CPFs, cinco nomes, todas comprando
  de dentro de SP, todas com "seu" celular de sempre. Cada pedido, isolado, é
  perfeitamente normal. O que denuncia o grupo é que o **aparelho físico é o
  mesmo**.

Achar isso em SQL exige *self-join* sobre *self-join*, e piora a cada salto.
Em Cypher é um desenho de uma linha. Esse contraste é o coração do repositório.

---

## ✅ Pré-requisitos

* [ ] **Docker** e **Docker Compose v2** instalados
* [ ] ~6 GB de RAM livres para a stack completa (ou suba um profile por vez)
* [ ] ~4 GB de disco para as imagens
* [ ] `make` (opcional — todo comando tem o equivalente em `docker compose`)

> **Você não precisa instalar Python, nem driver nenhum.** Todos os scripts
> rodam dentro do container `seeder`, que já vem com os cinco drivers.

---

## ▶️ Começando em 5 minutos

### Opção A — a stack inteira

```bash
make tudo
```

Isso sobe os cinco bancos, espera todos ficarem saudáveis e popula todos.

### Opção B — um paradigma por vez (recomendado em máquina modesta)

É aqui que os **profiles** entram. Você sobe só o que vai usar na aula de hoje:

```bash
docker compose --profile documento  up -d   # MongoDB
docker compose --profile chavevalor up -d   # Redis
docker compose --profile grafo      up -d   # Neo4j
docker compose --profile widecolumn up -d   # Cassandra
docker compose --profile colunar    up -d   # ClickHouse
docker compose --profile viz        up -d   # painel Streamlit
docker compose --profile bi         up -d   # Metabase (use `make bi`: baixa o driver)
docker compose --profile tudo       up -d   # tudo junto
```

Depois popule o que subiu:

```bash
docker compose run --rm seeder python mongodb/seed_mongo.py
```

### Conferindo que deu certo

```bash
make status     # todos os containers e o estado de saúde
make validar    # compara os 5 bancos com o gerador, item por item
```

O `make validar` é o seu **guia de evidências**: ele regera o universo em
memória e confere cada contagem. Se algo divergir, ele diz exatamente o quê.

---

## 🚪 Endereços

| Serviço | Endereço | Credenciais |
|---|---|---|
| Mongo Express | http://localhost:8091 | `sudoers` / `sudoers` |
| Neo4j Browser | http://localhost:7474 | `neo4j` / `sudoers123` |
| ClickHouse Play | http://localhost:8123/play | `sudoers` / `sudoers` |
| Painel Streamlit | http://localhost:8501 | — |
| Metabase | http://localhost:3010 | você cria no 1º acesso |
| MongoDB | `localhost:27017` | `sudoers` / `sudoers` |
| Redis | `localhost:6380` | senha `sudoers` |
| Cassandra | `localhost:9042` | sem auth |

> As portas do Redis (6380) e do ClickHouse nativo (9010) foram trocadas de
> propósito: 6379 costuma estar ocupado por um Redis local, e a 9000 é do
> MinIO do `jornada_dados`. Tudo é configurável no arquivo `.env`.

---

## 🗂️ Como este repositório está organizado

Cada pasta é uma **parada da trilha** e tem o seu próprio README, com a teoria
e os comandos daquele paradigma. Siga na ordem:

| # | Pasta | O que você faz lá |
|---|---|---|
| 1 | [`gerador/`](./gerador/README.md) | Entende a semente e o universo compartilhado |
| 2 | [`mongodb/`](./mongodb/README.md) | Documento: schema flexível, embedding, Change Streams |
| 3 | [`redis/`](./redis/README.md) | Chave-valor: 8 estruturas, TTL, Streams |
| 4 | [`neo4j/`](./neo4j/README.md) | Grafo: acha o anel de fraude |
| 5 | [`cassandra/`](./cassandra/README.md) | Wide-column: modelagem por consulta |
| 6 | [`clickhouse/`](./clickhouse/README.md) | Colunar: agregação e compressão |
| 7 | [`integracao/`](./integracao/README.md) | Vira **origem** do `jornada_dados` |
| 8 | [`viz/`](./viz/README.md) | Dataviz: o painel comparativo |
| 9 | [`desafios/`](./desafios/desafios.md) | Desafios Júnior, Pleno e Sênior |

Material de apoio:

* [📐 Guia de modelagem](./docs/modelagem.md) — como o mesmo dado vira cinco modelos
* [⚖️ Matriz de decisão](./docs/comparativo.md) — qual banco escolher e por quê
* [✅ Checklist do aluno](./docs/checklist.md) — para não se perder
* [🔎 Validação por evidências](./docs/validacao_evidencia.md) — como provar que funcionou
* [👩‍💻 Perfis e responsabilidades](./docs/perfis.md) — quem faz o quê no time

---

## 🧹 Encerrando

```bash
make derruba    # para os containers, mantém os dados
make limpar     # para e APAGA os volumes (recomeça do zero)
```

---

# ➡️ Continue no [gerador/README.md](./gerador/README.md)
