#!/usr/bin/env bash
# =============================================================================
# PDF-Manager — Database Restore Script
# Restores a PostgreSQL backup created by scripts/backup.sh.
#
# Usage:
#   ./scripts/restore.sh [/path/to/backup.sql.gz]
#   If no file is provided the script uses /backups/latest.sql.gz.
#
# Environment variables:
#   POSTGRES_HOST   (default: localhost)
#   POSTGRES_PORT   (default: 5432)
#   POSTGRES_DB     (default: pdfmanager)
#   POSTGRES_USER   (default: pdfmanager)
#   PGPASSWORD      — PostgreSQL password
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

log()  { echo "[restore] $*"; }
die()  { echo "[restore] ERROR: $*" >&2; exit 1; }

# ---------------------------------------------------------------------------
# Determine which backup file to use
# ---------------------------------------------------------------------------
BACKUP_FILE="${1:-${BACKUP_DIR}/latest.sql.gz}"

[[ -f "${BACKUP_FILE}" ]] || die "Backup file not found: ${BACKUP_FILE}"

log "Restore source : ${BACKUP_FILE}"
log "Target database: ${POSTGRES_DB} on ${POSTGRES_HOST}:${POSTGRES_PORT}"

# ---------------------------------------------------------------------------
# Confirmation prompt
# ---------------------------------------------------------------------------
read -r -p "[restore] WARNING: This will DROP and recreate '${POSTGRES_DB}'. Continue? [y/N] " CONFIRM
[[ "${CONFIRM,,}" == "y" ]] || { log "Aborted."; exit 0; }

# ---------------------------------------------------------------------------
# Drop and recreate the database
# ---------------------------------------------------------------------------
log "Dropping existing database..."
psql \
    --host="${POSTGRES_HOST}" \
    --port="${POSTGRES_PORT}" \
    --username="${POSTGRES_USER}" \
    --dbname=postgres \
    --no-password \
    -c "DROP DATABASE IF EXISTS ${POSTGRES_DB};"

log "Creating fresh database..."
psql \
    --host="${POSTGRES_HOST}" \
    --port="${POSTGRES_PORT}" \
    --username="${POSTGRES_USER}" \
    --dbname=postgres \
    --no-password \
    -c "CREATE DATABASE ${POSTGRES_DB} OWNER ${POSTGRES_USER};"

# ---------------------------------------------------------------------------
# Restore
# ---------------------------------------------------------------------------
log "Restoring from backup..."
gunzip -c "${BACKUP_FILE}" | psql \
    --host="${POSTGRES_HOST}" \
    --port="${POSTGRES_PORT}" \
    --username="${POSTGRES_USER}" \
    --dbname="${POSTGRES_DB}" \
    --no-password \
    --single-transaction \
    --set ON_ERROR_STOP=1

log "Restore complete."
