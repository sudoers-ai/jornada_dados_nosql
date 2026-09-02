#!/usr/bin/env bash
# ==========================================================================
# Coleta o estado da stack num relatorio unico.
#
#   make diagnostico
#   make diagnostico > diagnostico.txt      (para mandar ao instrutor)
#
# Nao expoe nada sensivel: sao credenciais de laboratorio, publicas no README.
# ==========================================================================
set -uo pipefail

secao() { echo; echo "=============== $1 ==============="; }

echo "RELATORIO DE DIAGNOSTICO - Liga Sudoers NoSQL"
echo "gerado em: $(date '+%Y-%m-%d %H:%M:%S')"

secao "SISTEMA"
uname -a 2>/dev/null
echo "docker : $(docker --version 2>/dev/null || echo AUSENTE)"
echo "compose: $(docker compose version 2>/dev/null || echo 'AUSENTE ou v1')"
echo "make   : $(make --version 2>/dev/null | sed -n 1p)"

secao "RECURSOS DO DOCKER"
docker info --format 'CPUs: {{.NCPU}} | Memoria: {{.MemTotal}} bytes' 2>/dev/null
df -h . 2>/dev/null | head -2

secao "CONTAINERS"
docker ps -a --filter "name=sudoers_" \
  --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}' 2>/dev/null

secao "SAUDE E REDE DE CADA CONTAINER"
for c in sudoers_mongo sudoers_redis sudoers_neo4j sudoers_cassandra sudoers_clickhouse; do
  docker ps -a --format '{{.Names}}' | grep -qx "$c" || { echo "$c: NAO EXISTE"; continue; }
  saude=$(docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}sem-healthcheck{{end}}' "$c" 2>/dev/null)
  redes=$(docker inspect -f '{{range $k,$v := .NetworkSettings.Networks}}{{$k}} {{end}}' "$c" 2>/dev/null)
  reinicios=$(docker inspect -f '{{.RestartCount}}' "$c" 2>/dev/null)
  printf "%-20s saude=%-16s reinicios=%-3s redes=[%s]\n" "$c" "$saude" "$reinicios" "${redes:-NENHUMA!}"
  if [ -z "${redes// }" ]; then
    echo "    ^^^ PROBLEMA: container sem rede. Rode: make consertar"
  fi
done

secao "ULTIMOS ERROS NOS LOGS"
for c in sudoers_mongo sudoers_mongo_rs_init sudoers_redis sudoers_neo4j sudoers_cassandra sudoers_clickhouse; do
  docker ps -a --format '{{.Names}}' | grep -qx "$c" || continue
  saida=$(docker logs --tail 200 "$c" 2>&1 \
          | grep -iE "error|erro|fatal|exception|refused|denied|cannot|failed" \
          | grep -viE "0 error|no error" | tail -3)
  [ -n "$saida" ] && { echo "--- $c ---"; echo "$saida" | cut -c1-200; }
done

secao "PORTAS"
for p in 27017 8091 6380 7474 7687 9042 8123 9010 8501 3010; do
  dono=$(docker ps --filter "publish=$p" --format '{{.Names}}' 2>/dev/null | head -1)
  if [ -n "$dono" ]; then
    echo "$p -> container $dono"
  elif command -v ss >/dev/null 2>&1 && ss -ltnH "sport = :$p" 2>/dev/null | grep -q .; then
    echo "$p -> OCUPADA por processo da maquina (nao e container)"
  else
    echo "$p -> livre"
  fi
done

secao "VOLUMES"
docker volume ls --filter "name=jornada_dados_nosql" --format '{{.Name}}' 2>/dev/null

secao "ARQUIVOS DE CONFIGURACAO"
echo ".env existe? $([ -f .env ] && echo sim || echo 'NAO - sera criado pelo make')"
echo "driver metabase? $([ -f metabase/plugins/clickhouse.metabase-driver.jar ] && echo sim || echo 'nao (rode: make bi-driver)')"

echo
echo "=============== FIM ==============="
echo "Mande este relatorio inteiro para o instrutor."
