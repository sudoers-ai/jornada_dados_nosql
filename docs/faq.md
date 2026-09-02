# ❓ FAQ de Aula — erros comuns e como resolver

> ⬅️ [README principal](../README.md)
>
> **Antes de qualquer coisa, rode isto:**
>
> ```bash
> make verificar      # confere Docker, portas e memória ANTES de subir
> ```
>
> Ele aponta o problema em português, com o comando para resolver. A maioria
> dos erros desta página nem chega a acontecer se você rodar isso primeiro.

---

## 🚑 Os três comandos de socorro

| Comando | Quando usar |
|---|---|
| `make aula a=<nome>` | máquina modesta — sobe **só** o paradigma do dia |
| `make verificar` | **antes** de subir — porta ocupada, pouca memória, Compose v1 |
| `make consertar` | algo subiu errado — recria os containers **sem apagar seus dados** |
| `make diagnostico` | travou e você não sabe por quê — gera um relatório para o instrutor |

Se nada funcionar: `make limpar` apaga tudo (inclusive os dados) e você
recomeça com `make tudo`. Você não perde nada de importante — os dados são
gerados a partir da semente, sempre iguais.

---

## 1. "port is already allocated" / "address already in use"

```
Error response from daemon: ... failed to bind host port 0.0.0.0:27017/tcp:
address already in use
```

**O que é:** alguma coisa na sua máquina já usa aquela porta. O caso mais
comum é ter um MongoDB, Redis ou Postgres instalado localmente.

**Como resolver — escolha uma:**

```bash
# 1) descubra quem está usando
sudo lsof -i :27017

# 2) OU mude a porta no arquivo .env (mais simples, não mexe na sua máquina)
#    edite .env e troque, por exemplo:
#    PORTA_MONGO=27018
```

Depois: `make consertar`.

> ⚠️ **Importante:** se esse erro aconteceu, é bem provável que o container
> tenha ficado **sem rede**. Sempre rode `make consertar` depois de resolver a
> porta — não basta rodar `make tudo` de novo. Veja o item 2.

---

## 2. Tudo falha com "ENOTFOUND", "Name or service not known", "getaddrinfo"

```
MongoNetworkError: getaddrinfo ENOTFOUND mongodb
```

**O que é:** o container está rodando, mas **não está ligado a nenhuma rede
Docker**. Acontece quando um `docker compose up` falhou no meio (quase sempre
por porta ocupada): o container foi criado, a rede não foi configurada, e o
`up` seguinte apenas dá *start* nele sem reparar nada.

É o erro mais traiçoeiro do projeto porque o container aparece como
`Up (healthy)` — ele parece saudável, só não fala com ninguém.

**Como confirmar:**

```bash
make diagnostico | grep redes
# sudoers_mongo   saude=healthy  redes=[NENHUMA!]
```

**Como resolver:**

```bash
make consertar
```

Isso recria os containers e refaz a rede. **Seus dados ficam nos volumes e
não são perdidos.**

---

## 3. O Cassandra não fica pronto / "Connection refused"

O Cassandra é, de longe, o container mais lento a subir — leva ~60s numa
máquina boa e pode passar de 3 minutos numa mais modesta.

**Se o `make tudo` desistiu de esperar:**

```bash
LIMITE=600 bash scripts/esperar.sh    # espera até 10 minutos
make seed-cassandra
```

**Se ele nunca fica `healthy`:** quase sempre é memória. Veja o item 4.

> Os *seeds* já esperam sozinhos: se você rodar `make seed-cassandra` antes da
> hora, ele mostra `⏳ Cassandra ainda nao esta pronto. Esperando...` e tenta
> por até 5 minutos, em vez de estourar um erro.

---

## 4. Container morre sozinho, reinicia, ou fica "unhealthy"

**Quase sempre é falta de memória.** A stack completa pede ~6 GB.

**No Docker Desktop (Mac/Windows):** Settings → Resources → Memory → suba para
pelo menos 6 GB e aplique.

**Se não der para aumentar, suba um paradigma por vez** — é para isso que os
profiles existem. O jeito mais simples:

```bash
make aula a=documento          # sobe só o MongoDB, popula e mostra o roteiro
docker compose --profile documento down     # ao terminar a aula
```

Ou na mão:

```bash
docker compose --profile documento up -d
docker compose run --rm seeder python mongodb/seed_mongo.py
docker compose --profile documento down
```

Confirme quanto o Docker está enxergando:

```bash
make verificar    # mostra memória, CPU e disco disponíveis
```

---

## 5. "docker: 'compose' is not a docker command" ou o `--profile` não funciona

Você tem o Docker Compose **v1** (`docker-compose`, com hífen). Este projeto
usa **profiles**, que só existem na **v2** (`docker compose`, com espaço).

```bash
sudo apt update
sudo apt install docker-compose-plugin
docker compose version        # tem que mostrar v2.x ou superior
```

---

## 6. "permission denied while trying to connect to the Docker daemon"

Seu usuário não está no grupo `docker`:

```bash
sudo usermod -aG docker $USER
```

Depois **feche e abra a sessão** (logout/login). Só rodar `newgrp docker` na
mesma janela costuma não bastar.

---

## 7. `make: command not found`

**No Windows:** use o **WSL2** (o mesmo requisito do repositório
`jornada_dados`). Não rode pelo PowerShell nem pelo CMD.

**No Linux:** `sudo apt install make`

**Se preferir não usar `make`:** todo comando tem o equivalente direto em
`docker compose`, e ele está escrito no README de cada pasta. Exemplo:

```bash
make seed-mongo
# é a mesma coisa que:
docker compose run --rm seeder python mongodb/seed_mongo.py
```

---

## 8. O `make validar` acusa falhas

```
  28 passaram   4 falharam   0 bancos fora do ar
```

**Causa quase certa:** você mudou algum valor no `.env` (`SEMENTE`,
`N_PESSOAS`, `N_PRODUTOS`, `N_PEDIDOS`) e repopulou só parte dos bancos.

Mudou o `.env`? **Repopule todos**:

```bash
make seed
```

Se um banco aparece como "indisponível" em vez de falhar, é porque o profile
dele não está no ar — suba e rode o seed dele.

---

## 9. O painel (Streamlit) mostra "não está acessível"

Cada aba do painel depende do banco correspondente. Se você subiu só alguns
profiles, as outras abas avisam e seguem funcionando — isso é proposital,
não é erro.

Para ter todas: `make tudo`.

---

## 10. O Metabase não mostra o ClickHouse na lista de bancos

O driver do ClickHouse **não vem** na imagem do Metabase (o do MongoDB vem).

```bash
make bi-driver     # baixa o driver
make bi            # sobe o Metabase já com ele
```

Se você está sem internet, o Metabase sobe mesmo assim — só sem o ClickHouse.
O painel Streamlit não depende disso e continua funcionando normalmente.

---

## 11. Erros na integração com o `jornada_dados`

**"Nao consegui falar com o Postgres em 'postgres-oltp'"**

Duas causas:

1. O outro repositório não está no ar:
   ```bash
   cd ../jornada_dados && docker compose up -d postgres-oltp minio
   ```
2. Você esqueceu o *overlay* de rede. Use sempre os **dois** arquivos:
   ```bash
   docker compose -f docker-compose.yml -f docker-compose.lake.yml \
     run --rm seeder python integracao/carga_oltp.py
   ```
   (ou simplesmente `make lake-oltp`, que já faz isso)

**O conector Debezium está `RUNNING` mas não cria tópico nenhum**

Você esqueceu de rodar `make lake-conectar`. Sem os *aliases* de rede, o
Debezium não resolve o nome `mongodb` e o conector fica parado sem
reclamar. Detalhes em [`integracao/README.md`](../integracao/README.md).

---

## 12. "Nada disso resolveu"

```bash
make diagnostico > diagnostico.txt
```

Mande o arquivo inteiro para o instrutor. Ele traz versões, estado de cada
container, redes, portas e os últimos erros dos logs — que é tudo que
alguém precisa para te ajudar sem adivinhar.
