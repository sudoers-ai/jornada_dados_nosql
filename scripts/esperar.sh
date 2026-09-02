#!/usr/bin/env bash
# Espera os containers que TEM healthcheck ficarem saudaveis.
# O Cassandra e o mais lento (costuma levar ~60s).
set -uo pipefail

ALVOS=(sudoers_mongo sudoers_redis sudoers_neo4j sudoers_cassandra sudoers_clickhouse)
LIMITE=${LIMITE:-300}

for c in "${ALVOS[@]}"; do
  docker ps --format '{{.Names}}' | grep -qx "$c" || continue
  printf "  %-20s " "$c"
  fim=$(( $(date +%s) + LIMITE ))
  while :; do
    st=$(docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}sem-healthcheck{{end}}' "$c" 2>/dev/null || echo ausente)
    case "$st" in
      healthy|sem-healthcheck) echo "✅ $st"; break ;;
      unhealthy)               echo "❌ unhealthy (veja: docker logs $c)"; break ;;
    esac
    [ "$(date +%s)" -ge "$fim" ] && { echo "⏰ timeout em ${LIMITE}s (estado: $st)"; break; }
    sleep 3
  done
done
