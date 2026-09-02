#!/usr/bin/env bash
# ==========================================================================
# Espera os bancos ficarem prontos de verdade.
#
# "Pronto" aqui e mais do que "o container esta rodando":
#   1. o healthcheck passou;
#   2. o container esta ligado a uma rede.
#
# O item 2 parece bobo, mas e o problema mais traicoeiro do projeto: se um
# `docker compose up` falha no meio (porta ocupada, por exemplo), o container
# pode ficar criado e SEM REDE. O `up` seguinte so da start nele, sem
# reparar a rede - e a partir dai tudo falha com "ENOTFOUND", sem explicacao.
# ==========================================================================
set -uo pipefail

V="\033[92m"; A="\033[93m"; R="\033[91m"; C="\033[90m"; F="\033[0m"

ALVOS=(sudoers_mongo sudoers_redis sudoers_neo4j sudoers_cassandra sudoers_clickhouse)
LIMITE=${LIMITE:-360}
problemas=0

for c in "${ALVOS[@]}"; do
  docker ps --format '{{.Names}}' | grep -qx "$c" || continue
  printf "  %-20s " "$c"

  fim=$(( $(date +%s) + LIMITE ))
  estado="desconhecido"
  while :; do
    estado=$(docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}sem-healthcheck{{end}}' "$c" 2>/dev/null || echo ausente)
    case "$estado" in
      healthy|sem-healthcheck) break ;;
      unhealthy)               break ;;
    esac
    [ "$(date +%s)" -ge "$fim" ] && break
    sleep 3
  done

  redes=$(docker inspect -f '{{range $k,$v := .NetworkSettings.Networks}}{{$k}} {{end}}' "$c" 2>/dev/null)

  if [ -z "${redes// }" ]; then
    printf "${R}❌ sem rede${F}\n"
    printf "     ${C}O container subiu, mas nao esta ligado a nenhuma rede Docker.${F}\n"
    printf "     ${C}Isso costuma acontecer quando um 'up' anterior falhou no meio.${F}\n"
    printf "     ${C}Conserto:  make consertar${F}\n"
    problemas=$((problemas+1))
    continue
  fi

  case "$estado" in
    healthy)          printf "${V}✅ pronto${F}\n" ;;
    sem-healthcheck)  printf "${V}✅ no ar${F}\n" ;;
    unhealthy)
      printf "${R}❌ unhealthy${F}\n"
      printf "     ${C}Veja o motivo:  docker logs %s | tail -30${F}\n" "$c"
      printf "     ${C}Causa comum: memoria insuficiente. Suba um profile por vez.${F}\n"
      problemas=$((problemas+1)) ;;
    *)
      printf "${A}⏰ nao ficou pronto em %ss (estado: %s)${F}\n" "$LIMITE" "$estado"
      printf "     ${C}Em maquina lenta o Cassandra demora mais. Tente:${F}\n"
      printf "     ${C}  LIMITE=600 bash scripts/esperar.sh${F}\n"
      printf "     ${C}Ou veja o log:  docker logs %s | tail -30${F}\n" "$c"
      problemas=$((problemas+1)) ;;
  esac
done

if [ "$problemas" -gt 0 ]; then
  echo
  printf "${R}%d banco(s) nao ficaram prontos.${F} " "$problemas"
  printf "${C}O seed foi cancelado para nao gerar erro confuso.${F}\n"
  printf "${C}Rode 'make diagnostico' e mande o resultado ao instrutor se travar.${F}\n\n"
  exit 1
fi
exit 0
