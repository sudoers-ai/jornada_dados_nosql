#!/usr/bin/env bash
# ==========================================================================
# Liga os containers NoSQL a rede do repo jornada_dados (e vice-versa).
#
#   ./integracao/conectar_lake.sh          # conecta
#   ./integracao/conectar_lake.sh desfazer # desconecta
#
# POR QUE O --alias E OBRIGATORIO AQUI (nao e detalhe):
#
#   Um container ganha, na rede em que subiu, dois nomes: o nome do servico
#   no compose (`mongodb`) e o nome do container (`sudoers_mongo`).
#   Mas `docker network connect` numa rede NOVA leva apenas o nome do
#   container. O apelido curto some.
#
#   Isso quebra o CDC de um jeito traicoeiro: o replica set do MongoDB
#   anuncia seus membros como `mongodb:27017`. O Debezium, do outro lado,
#   nao consegue resolver esse nome - e o conector fica RUNNING, sem erro
#   no log, sem criar topico nenhum. Falha silenciosa.
#
#   Por isso conectamos com --alias, replicando o nome de servico.
# ==========================================================================
set -uo pipefail

REDE_LAKE="jornada_dados_app_network"
ACAO="${1:-conectar}"

# container:apelido-que-o-outro-repo-espera
MAPA=(
  "sudoers_mongo:mongodb"
  "sudoers_redis:redis"
  "sudoers_neo4j:neo4j"
  "sudoers_cassandra:cassandra"
  "sudoers_clickhouse:clickhouse"
)

if ! docker network inspect "$REDE_LAKE" >/dev/null 2>&1; then
  echo "❌ A rede '$REDE_LAKE' nao existe."
  echo "   Suba o repo jornada_dados primeiro:"
  echo "     cd ../jornada_dados && docker compose up -d"
  exit 1
fi

for par in "${MAPA[@]}"; do
  cont="${par%%:*}"
  apelido="${par##*:}"

  if ! docker ps --format '{{.Names}}' | grep -qx "$cont"; then
    echo "   (pulando $cont - nao esta rodando)"
    continue
  fi

  if [ "$ACAO" = "desfazer" ]; then
    docker network disconnect "$REDE_LAKE" "$cont" 2>/dev/null \
      && echo "   desconectado: $cont" || echo "   (ja estava fora: $cont)"
    continue
  fi

  # reconecta sempre, para garantir que o alias exista mesmo que o container
  # ja tivesse sido conectado antes sem ele
  docker network disconnect "$REDE_LAKE" "$cont" 2>/dev/null || true
  if docker network connect --alias "$apelido" "$REDE_LAKE" "$cont" 2>/dev/null; then
    echo "   conectado: $cont  (tambem atende por '$apelido')"
  else
    echo "   ⚠️  falhou ao conectar $cont"
  fi
done

echo
if [ "$ACAO" != "desfazer" ]; then
  echo "✅ Pronto. Confira do lado do jornada_dados:"
  echo "     docker exec debezium getent hosts mongodb"
fi
