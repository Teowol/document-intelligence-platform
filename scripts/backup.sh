#!/usr/bin/env bash
# Backup the DB (pg_dump) + uploaded media (Phase 10).
#
# Usage: ./scripts/backup.sh [backup-dir]
# Default backup dir: ./backups (git-ignored).

set -euo pipefail

BACKUP_DIR="${1:-backups}"
STAMP="$(date +%Y%m%d_%H%M%S)"
mkdir -p "${BACKUP_DIR}/db" "${BACKUP_DIR}/media"

DB_CONTAINER="${DB_CONTAINER:-dip-prod-db}"
POSTGRES_DB="${POSTGRES_DB:-document_intelligence}"
POSTGRES_USER="${POSTGRES_USER:-dip_user}"

echo ">> Backing up database -> ${BACKUP_DIR}/db/${POSTGRES_DB}_${STAMP}.dump"
docker compose exec -T db pg_dump -U "${POSTGRES_USER}" -Fc "${POSTGRES_DB}" \
  > "${BACKUP_DIR}/db/${POSTGRES_DB}_${STAMP}.dump"

echo ">> Backing up media -> ${BACKUP_DIR}/media/"
if [ -d src/media ] && [ -n "$(ls -A src/media 2>/dev/null)" ]; then
  tar -czf "${BACKUP_DIR}/media/media_${STAMP}.tar.gz" -C src media
else
  echo "   (no media files to back up)"
fi

echo ">> Done. Backups stored under ${BACKUP_DIR}/"
