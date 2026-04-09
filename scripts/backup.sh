#!/usr/bin/env bash
# =============================================================================
# PDF-Manager — Database Backup Script
# Creates a compressed PostgreSQL dump and rotates old backups.
#
# Environment variables (can also be set in .env):
#   POSTGRES_HOST             (default: localhost)
#   POSTGRES_PORT             (default: 5432)
#   POSTGRES_DB               (default: pdfmanager)
#   POSTGRES_USER             (default: pdfmanager)
#   PGPASSWORD                — PostgreSQL password (used by pg_dump)
#   BACKUP_DIR                (default: /backups)
#   BACKUP_RETENTION_DAYS     (default: 30)
#   S3_BUCKET                 — optional; upload to S3 when set
# =============================================================================
set -euo pipefail

# ---------------------------------------------------------------------------
# Load .env if present
# ---------------------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="${SCRIPT_DIR}/../.env"
[[ -f "${ENV_FILE}" ]] && set -a && source "${ENV_FILE}" && set +a

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
POSTGRES_HOST="${POSTGRES_HOST:-localhost}"
POSTGRES_PORT="${POSTGRES_PORT:-5432}"
POSTGRES_DB="${POSTGRES_DB:-pdfmanager}"
POSTGRES_USER="${POSTGRES_USER:-pdfmanager}"
BACKUP_DIR="${BACKUP_DIR:-/backups}"
RETENTION_DAYS="${BACKUP_RETENTION_DAYS:-30}"
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
BACKUP_FILE="${BACKUP_DIR}/pdfmanager_${TIMESTAMP}.sql.gz"
LATEST_LINK="${BACKUP_DIR}/latest.sql.gz"

log() { echo "[backup] $*"; }

# ---------------------------------------------------------------------------
# Ensure backup directory exists
# ---------------------------------------------------------------------------
mkdir -p "${BACKUP_DIR}"

log "Starting backup → ${BACKUP_FILE}"

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

SIZE=$(du -sh "${BACKUP_FILE}" | cut -f1)
log "Backup complete: ${BACKUP_FILE} (${SIZE})"

# ---------------------------------------------------------------------------
# Update 'latest' symlink
# ---------------------------------------------------------------------------
ln -sf "${BACKUP_FILE}" "${LATEST_LINK}"

# ---------------------------------------------------------------------------
# Upload to S3 (optional)
# ---------------------------------------------------------------------------
if [[ -n "${S3_BUCKET:-}" ]]; then
    log "Uploading backup to s3://${S3_BUCKET}/backups/..."
    aws s3 cp "${BACKUP_FILE}" "s3://${S3_BUCKET}/backups/$(basename "${BACKUP_FILE}")" \
        --storage-class STANDARD_IA
    log "S3 upload complete."
fi

# ---------------------------------------------------------------------------
# Rotate old local backups
# ---------------------------------------------------------------------------
log "Removing backups older than ${RETENTION_DAYS} days..."
find "${BACKUP_DIR}" -name "pdfmanager_*.sql.gz" -mtime "+${RETENTION_DAYS}" -delete

log "Remaining backups:"
ls -lh "${BACKUP_DIR}"/pdfmanager_*.sql.gz 2>/dev/null | tail -5 || log "(none)"
