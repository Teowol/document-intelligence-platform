#!/usr/bin/env bash
# Restore a database dump + media archive (Phase 10).
#
# Usage: ./scripts/restore.sh <backup-dir>/db/document_intelligence_<STAMP>.dump
#
# Restores into the running prod DB. For media, extract the matching tarball
# into src/media/ separately.

set -euo pipefail

DUMP_FILE="${1:?usage: restore.sh <path-to-.dump>}"
DB_CONTAINER="${DB_CONTAINER:-dip-prod-db}"
POSTGRES_DB="${POSTGRES_DB:-document_intelligence}"
POSTGRES_USER="${POSTGRES_USER:-dip_user}"

if [ ! -f "$DUMP_FILE" ]; then
  echo "Dump file not found: $DUMP_FILE"
  exit 1
fi

echo ">> Restoring DB from $DUMP_FILE"
# -C --clean create/clean the target db; terminates active connections first.
docker compose exec -T db dropdb -U "${POSTGRES_USER}" --if-exists "${POSTGRES_DB}"
docker compose exec -T db createdb -U "${POSTGRES_USER}" "${POSTGRES_DB}"
docker compose exec -T db pg_restore -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" \
  -C --no-owner < "$DUMP_FILE"

echo ">> Restored. Restart web + worker so they pick up the fresh DB."
