#!/usr/bin/env bash
# ==========================================================================
# Prepara UMA aula: sobe so o profile do dia, popula e imprime o roteiro.
#
#   make aula a=grafo
#
# Existe para turma com maquina modesta. Em vez de subir 6 GB de stack para
# usar um banco so, o aluno sobe o do dia, faz a aula, e derruba no fim.
# ==========================================================================
set -uo pipefail

V="\033[92m"; A="\033[93m"; N="\033[1m"; C="\033[90m"; F="\033[0m"

AULA="${1:-}"

# aula -> profile | container | seed | consultas | README | titulo
declare -A PROFILE=(
  [documento]=documento  [chavevalor]=chavevalor  [grafo]=grafo
  [widecolumn]=widecolumn [colunar]=colunar
)
declare -A SEED=(
  [documento]="mongodb/seed_mongo.py"       [chavevalor]="redis/seed_redis.py"
  [grafo]="neo4j/seed_neo4j.py"             [widecolumn]="cassandra/seed_cassandra.py"
  [colunar]="clickhouse/seed_clickhouse.py"
)
declare -A ALVO_Q=(
  [documento]=q-mongo   [chavevalor]=q-redis  [grafo]=q-neo4j
  [widecolumn]=q-cassandra [colunar]=q-clickhouse
)
declare -A PASTA=(
  [documento]=mongodb   [chavevalor]=redis    [grafo]=neo4j
  [widecolumn]=cassandra [colunar]=clickhouse
)
declare -A TITULO=(
  [documento]="📄 Documento — MongoDB"
  [chavevalor]="🔑 Chave-valor — Redis"
  [grafo]="🕸️  Grafo — Neo4j"
  [widecolumn]="🏛️  Wide-column — Cassandra"
  [colunar]="📈 Colunar — ClickHouse"
)
declare -A IDEIA=(
  [documento]="Atributos que variam por categoria de produto. Um livro tem ISBN;
     um eletrônico tem voltagem. Nenhuma tabela acomoda isso bem."
  [chavevalor]="O estado quente da decisão antifraude. Saber, em menos de 1 ms
     durante o checkout, se o cliente trocou de aparelho."
  [grafo]="O anel de fraude. Cinco contas, cinco CPFs, o mesmo aparelho físico.
     Nenhuma regra de linha pega — a informação está na LIGAÇÃO."
  [widecolumn]="Modelagem por consulta. Você não modela os dados, modela as
     perguntas: uma tabela para cada uma."
  [colunar]="Agregação sobre tudo, em milissegundos. E por que 'colunar' aqui
     não é a mesma coisa que o Cassandra."
)
declare -A UI=(
  [documento]="Mongo Express: http://localhost:8091  (sudoers / sudoers)"
  [chavevalor]="Sem UI — a aula é no redis-cli, e é melhor assim."
  [grafo]="Neo4j Browser: http://localhost:7474  (neo4j / sudoers123)  <- o 'aha' da aula"
  [widecolumn]="Sem UI — a aula é no cqlsh."
  [colunar]="ClickHouse Play: http://localhost:8123/play  (sudoers / sudoers)"
)

if [ -z "$AULA" ] || [ -z "${PROFILE[$AULA]:-}" ]; then
  echo
  echo "  Uso:  make aula a=<nome>"
  echo
  echo "  Aulas disponíveis:"
  for k in documento chavevalor grafo widecolumn colunar; do
    printf "    %-12s %s\n" "$k" "${TITULO[$k]}"
  done
  echo
  echo "  Exemplo:  make aula a=grafo"
  echo
  [ -n "$AULA" ] && { echo "  (aula '$AULA' não existe)"; echo; exit 1; }
  exit 0
fi

echo
printf "${N}═══ AULA: %s ═══${F}\n" "${TITULO[$AULA]}"
echo
printf "${C}  A ideia do dia:${F}\n"
printf "     %s\n" "${IDEIA[$AULA]}"
echo

# ---------------------------------------------------------------- preparar
printf "${N}1. Verificando o ambiente${F}\n"
bash scripts/verificar.sh rapido >/dev/null 2>&1 \
  && printf "   ${V}✅${F} Docker e Compose ok\n" \
  || { bash scripts/verificar.sh rapido; exit 1; }

printf "${N}2. Subindo só o profile '%s'${F}\n" "${PROFILE[$AULA]}"
docker compose --profile "${PROFILE[$AULA]}" up -d 2>&1 | grep -E "Creat|Start|Error" | sed 's/^/   /'

printf "${N}3. Esperando ficar pronto${F}\n"
bash scripts/esperar.sh || exit 1

printf "${N}4. Populando${F}\n"
docker compose run --rm seeder python "${SEED[$AULA]}" 2>&1 | grep -E "✅|❌|\.\.\.\.|⏳" | sed 's/^/   /'

# ----------------------------------------------------------------- roteiro
echo
printf "${N}═══ ROTEIRO DA AULA ═══${F}\n"
echo
printf "  ${N}Leitura${F} (comece por aqui)\n"
printf "     %s/README.md\n" "${PASTA[$AULA]}"
echo
printf "  ${N}Consultas guiadas${F}\n"
printf "     make %s\n" "${ALVO_Q[$AULA]}"
echo
printf "  ${N}Interface${F}\n"
printf "     %s\n" "${UI[$AULA]}"
echo
printf "  ${N}Conferir que deu certo${F}\n"
printf "     make validar   ${C}(os outros bancos aparecem como 'indisponível' — é esperado)${F}\n"
echo
printf "  ${N}No fim da aula${F}\n"
printf "     docker compose --profile %s down   ${C}(libera a memória; os dados ficam)${F}\n" "${PROFILE[$AULA]}"
echo
printf "  ${C}Travou?  make diagnostico   |   Erro conhecido?  docs/faq.md${F}\n"
echo
