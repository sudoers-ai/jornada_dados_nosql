#!/bin/bash
# ---------------------------------------------------------------------------
# Por que este script existe?
#
# Queremos Change Streams no MongoDB (o equivalente ao CDC do Debezium).
# Change Stream so funciona com REPLICA SET.
# E o MongoDB exige um keyFile quando ha replica set COM autenticacao.
#
# Entao: geramos o keyFile no primeiro boot e seguimos o entrypoint oficial.
# ---------------------------------------------------------------------------
set -e

KEYFILE=/data/configdb/keyfile

if [ ! -f "$KEYFILE" ]; then
  echo "[liga-sudoers] gerando keyFile do replica set..."
  mkdir -p /data/configdb
  openssl rand -base64 756 > "$KEYFILE"
fi

chmod 400 "$KEYFILE"
chown mongodb:mongodb "$KEYFILE" 2>/dev/null || true

exec /usr/local/bin/docker-entrypoint.sh "$@"
