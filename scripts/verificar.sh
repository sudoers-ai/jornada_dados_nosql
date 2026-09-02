#!/usr/bin/env bash
# ==========================================================================
# Verificacao previa (preflight).
#
# Roda ANTES de subir qualquer coisa. A ideia e simples: e melhor o aluno
# ler "a porta 27017 esta ocupada pelo processo X" do que ver o Docker
# cuspir "Bind for 0.0.0.0:27017 failed" e nao saber o que fazer.
#
#   ./scripts/verificar.sh          # confere tudo
#   ./scripts/verificar.sh rapido   # so o essencial (docker + compose)
# ==========================================================================
set -uo pipefail

V="\033[92m"; A="\033[93m"; R="\033[91m"; C="\033[90m"; N="\033[1m"; F="\033[0m"
erros=0
avisos=0

titulo() { printf "\n${N}%s${F}\n" "$1"; }
ok()     { printf "  ${V}✅${F} %s\n" "$1"; }
aviso()  { printf "  ${A}⚠️ ${F} %s\n" "$1"; avisos=$((avisos+1)); }
falha()  { printf "  ${R}❌${F} %s\n" "$1"; erros=$((erros+1)); }
dica()   { printf "     ${C}%s${F}\n" "$1"; }

MODO="${1:-completo}"

# ---------------------------------------------------------------- Docker
titulo "Docker"

if ! command -v docker >/dev/null 2>&1; then
  falha "Docker nao encontrado."
  dica "Instale: https://docs.docker.com/get-docker/"
  dica "No Windows, use Docker Desktop com WSL2."
  echo; exit 1
fi
ok "docker instalado ($(docker --version | cut -d, -f1))"

if ! docker info >/dev/null 2>&1; then
  falha "O Docker esta instalado mas nao responde."
  dica "Causas comuns:"
  dica "  1. o servico nao esta rodando  ->  sudo systemctl start docker"
  dica "     (no Mac/Windows: abra o Docker Desktop e espere ficar verde)"
  dica "  2. seu usuario nao esta no grupo docker:"
  dica "       sudo usermod -aG docker \$USER   e depois FECHE e ABRA a sessao"
  echo; exit 1
fi
ok "daemon do Docker respondendo"

# Compose v2 e obrigatorio: `profiles` nao existe na v1.
if docker compose version >/dev/null 2>&1; then
  ok "docker compose v2 ($(docker compose version --short 2>/dev/null))"
else
  falha "Voce tem o Docker Compose v1 (docker-compose), nao a v2."
  dica "Este projeto usa PROFILES, que so existem na v2."
  dica "Instale o plugin:  sudo apt install docker-compose-plugin"
  dica "Confira com:       docker compose version"
  echo; exit 1
fi

[ "$MODO" = "rapido" ] && { echo; ok "verificacao rapida OK"; echo; exit 0; }

# ----------------------------------------------------------------- Portas
titulo "Portas"

# le do .env se existir, senao usa o padrao do compose
[ -f .env ] && . ./.env 2>/dev/null

checar_porta() {
  local porta="$1" servico="$2"
  local usada=""
  if command -v ss >/dev/null 2>&1; then
    usada=$(ss -ltnH "sport = :$porta" 2>/dev/null | head -1)
  elif command -v lsof >/dev/null 2>&1; then
    usada=$(lsof -iTCP:"$porta" -sTCP:LISTEN -n -P 2>/dev/null | tail -n +2 | head -1)
  fi
  if [ -n "$usada" ]; then
    # se quem ocupa e um container NOSSO, esta tudo bem
    local dono
    dono=$(docker ps --filter "publish=$porta" --format '{{.Names}}' 2>/dev/null | head -1)
    if [ -n "$dono" ] && echo "$dono" | grep -q "^sudoers_"; then
      ok "$porta ($servico) - ja em uso pelo proprio $dono"
    elif [ -n "$dono" ]; then
      falha "$porta ($servico) ocupada pelo container '$dono'"
      dica "pare esse container, ou mude PORTA_* no arquivo .env"
    else
      falha "$porta ($servico) ocupada por um processo da sua maquina"
      dica "descubra quem e:  sudo lsof -i :$porta"
      dica "ou mude a porta no arquivo .env (ex.: PORTA_MONGO=27018)"
    fi
  else
    ok "$porta ($servico) livre"
  fi
}

checar_porta "${PORTA_MONGO:-27017}"            "MongoDB"
checar_porta "${PORTA_MONGO_UI:-8091}"          "Mongo Express"
checar_porta "${PORTA_REDIS:-6380}"             "Redis"
checar_porta "${PORTA_NEO4J_HTTP:-7474}"        "Neo4j Browser"
checar_porta "${PORTA_NEO4J_BOLT:-7687}"        "Neo4j Bolt"
checar_porta "${PORTA_CASSANDRA:-9042}"         "Cassandra"
checar_porta "${PORTA_CLICKHOUSE_HTTP:-8123}"   "ClickHouse HTTP"
checar_porta "${PORTA_CLICKHOUSE_NATIVA:-9010}" "ClickHouse nativo"
checar_porta "${PORTA_STREAMLIT:-8501}"         "Streamlit"
checar_porta "${PORTA_METABASE:-3010}"          "Metabase"

# --------------------------------------------------------------- Recursos
titulo "Recursos"

# memoria que o DOCKER enxerga (no Mac/Windows e a da VM, nao a do host)
mem_bytes=$(docker info --format '{{.MemTotal}}' 2>/dev/null || echo 0)
mem_gb=$(( mem_bytes / 1024 / 1024 / 1024 ))
if [ "$mem_gb" -ge 6 ]; then
  ok "memoria disponivel ao Docker: ${mem_gb} GB"
elif [ "$mem_gb" -ge 3 ]; then
  aviso "memoria disponivel ao Docker: ${mem_gb} GB - pouco para a stack inteira"
  dica "suba UM profile por vez em vez de 'make tudo':"
  dica "  docker compose --profile documento up -d"
  dica "no Docker Desktop: Settings > Resources > Memory"
else
  falha "memoria disponivel ao Docker: ${mem_gb} GB - insuficiente"
  dica "aumente em Settings > Resources > Memory (minimo 4 GB)"
  dica "ou suba um profile por vez"
fi

disco_kb=$(df -Pk . 2>/dev/null | awk 'NR==2{print $4}')
disco_gb=$(( ${disco_kb:-0} / 1024 / 1024 ))
if [ "$disco_gb" -ge 8 ]; then
  ok "disco livre: ${disco_gb} GB"
elif [ "$disco_gb" -ge 4 ]; then
  aviso "disco livre: ${disco_gb} GB - as imagens ocupam ~4 GB"
else
  falha "disco livre: ${disco_gb} GB - insuficiente (precisa de ~5 GB)"
  dica "libere espaco:  docker system prune -a"
fi

cpus=$(docker info --format '{{.NCPU}}' 2>/dev/null || echo 0)
if [ "${cpus:-0}" -ge 4 ]; then
  ok "CPUs disponiveis ao Docker: $cpus"
else
  aviso "CPUs disponiveis ao Docker: $cpus - o Cassandra vai demorar mais para subir"
fi

# --------------------------------------------------------------- Resultado
echo
if [ "$erros" -gt 0 ]; then
  printf "${R}%d problema(s) que impedem a stack de subir.${F}\n" "$erros"
  printf "${C}Resolva os itens marcados com ❌ e rode de novo.${F}\n\n"
  exit 1
fi
if [ "$avisos" -gt 0 ]; then
  printf "${A}Tudo certo para subir, com %d aviso(s).${F}\n\n" "$avisos"
  exit 0
fi
printf "${V}Tudo certo. Pode subir.${F}\n\n"
