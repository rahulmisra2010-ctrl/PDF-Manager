#!/usr/bin/env bash
# =============================================================================
# PDF-Manager — Production Deployment Script
# Usage: ./scripts/deploy.sh [--skip-build] [--branch <branch>]
# =============================================================================
set -euo pipefail

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
APP_DIR="${APP_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
COMPOSE_FILE="${APP_DIR}/docker-compose.prod.yml"
ENV_FILE="${APP_DIR}/.env"
IMAGE_NAME="pdfmanager-web"
SKIP_BUILD=false
BRANCH="${BRANCH:-main}"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
log()  { echo "[deploy] $*"; }
die()  { echo "[deploy] ERROR: $*" >&2; exit 1; }

require_cmd() { command -v "$1" >/dev/null 2>&1 || die "'$1' is required but not installed."; }

# ---------------------------------------------------------------------------
# Parse arguments
# ---------------------------------------------------------------------------
while [[ $# -gt 0 ]]; do
    case "$1" in
        --skip-build) SKIP_BUILD=true; shift ;;
        --branch)     BRANCH="$2"; shift 2 ;;
        -h|--help)
            echo "Usage: $0 [--skip-build] [--branch <branch>]"
            exit 0
            ;;
        *) die "Unknown argument: $1" ;;
    esac
done

# ---------------------------------------------------------------------------
# Pre-flight checks
# ---------------------------------------------------------------------------
require_cmd docker
require_cmd git

[[ -f "${ENV_FILE}" ]] || die ".env file not found at ${ENV_FILE}. Copy .env.production → .env and fill in secrets."
[[ -f "${COMPOSE_FILE}" ]] || die "docker-compose.prod.yml not found at ${COMPOSE_FILE}"

# ---------------------------------------------------------------------------
# Pull latest code
# ---------------------------------------------------------------------------
log "Pulling latest code from branch '${BRANCH}'..."
cd "${APP_DIR}"
git fetch --quiet origin
git checkout --quiet "${BRANCH}"
git pull --quiet origin "${BRANCH}"
GIT_SHA=$(git rev-parse --short HEAD)
log "Deploying commit: ${GIT_SHA}"

# ---------------------------------------------------------------------------
# Build Docker image
# ---------------------------------------------------------------------------
if [[ "${SKIP_BUILD}" == false ]]; then
    log "Building production Docker image..."
    docker compose -f "${COMPOSE_FILE}" --env-file "${ENV_FILE}" build --no-cache web
    log "Build complete."
else
    log "Skipping build (--skip-build flag set)."
fi

# ---------------------------------------------------------------------------
# Database backup before upgrade
# ---------------------------------------------------------------------------
log "Taking database backup before deployment..."
"${APP_DIR}/scripts/backup.sh" || log "WARNING: Pre-deploy backup failed — continuing."

# ---------------------------------------------------------------------------
# Rolling update — minimal downtime
# ---------------------------------------------------------------------------
log "Starting rolling update..."
docker compose -f "${COMPOSE_FILE}" --env-file "${ENV_FILE}" up \
    --detach \
    --remove-orphans \
    --wait \
    web

# ---------------------------------------------------------------------------
# Run health check
# ---------------------------------------------------------------------------
log "Running post-deploy health check..."
sleep 5
"${APP_DIR}/scripts/health-check.sh" || die "Health check failed after deployment!"

# ---------------------------------------------------------------------------
# Reload Nginx (picks up any config changes)
# ---------------------------------------------------------------------------
log "Reloading Nginx configuration..."
docker compose -f "${COMPOSE_FILE}" --env-file "${ENV_FILE}" exec nginx nginx -s reload || true

log "Deployment of ${GIT_SHA} complete."
