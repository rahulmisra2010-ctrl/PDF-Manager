#!/usr/bin/env bash
# =============================================================================
# PDF-Manager — PostgreSQL Backup Script
# Creates a compressed pg_dump backup and rotates old backups.
#
# Environment variables (override via .env or shell):
#   POSTGRES_HOST     (default: postgres)
#   POSTGRES_PORT     (default: 5432)
#   POSTGRES_DB       (default: pdfmanager)
#   POSTGRES_USER     (default: pdfmanager)
#   PGPASSWORD        — set this to avoid interactive password prompt
#   BACKUP_DIR        (default: /backups)
#   BACKUP_RETENTION_DAYS (default: 30)
# =============================================================================
set -euo pipefail

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
POSTGRES_HOST="${POSTGRES_HOST:-postgres}"
POSTGRES_PORT="${POSTGRES_PORT:-5432}"
POSTGRES_DB="${POSTGRES_DB:-pdfmanager}"
POSTGRES_USER="${POSTGRES_USER:-pdfmanager}"
BACKUP_DIR="${BACKUP_DIR:-/backups}"
RETENTION_DAYS="${BACKUP_RETENTION_DAYS:-30}"

TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
BACKUP_FILE="${BACKUP_DIR}/pdfmanager_${TIMESTAMP}.sql.gz"
LATEST_LINK="${BACKUP_DIR}/latest.sql.gz"

# ---------------------------------------------------------------------------
# Ensure backup directory exists
# ---------------------------------------------------------------------------
mkdir -p "${BACKUP_DIR}"

echo "[backup] Starting PostgreSQL backup → ${BACKUP_FILE}"

# ---------------------------------------------------------------------------
# Create backup
# ---------------------------------------------------------------------------
pg_dump \
    --host="${POSTGRES_HOST}" \
    --port="${POSTGRES_PORT}" \
    --username="${POSTGRES_USER}" \
    --dbname="${POSTGRES_DB}" \
    --format=plain \
    --no-password \
    | gzip -9 > "${BACKUP_FILE}"

echo "[backup] Backup completed: $(du -sh "${BACKUP_FILE}" | cut -f1)"

# ---------------------------------------------------------------------------
# Update 'latest' symlink
# ---------------------------------------------------------------------------
ln -sf "${BACKUP_FILE}" "${LATEST_LINK}"

# ---------------------------------------------------------------------------
# Rotate old backups
# ---------------------------------------------------------------------------
echo "[backup] Removing backups older than ${RETENTION_DAYS} days..."
find "${BACKUP_DIR}" -name "pdfmanager_*.sql.gz" -mtime "+${RETENTION_DAYS}" -delete

echo "[backup] Done. Remaining backups:"
ls -lh "${BACKUP_DIR}"/pdfmanager_*.sql.gz 2>/dev/null || echo "(none)"
