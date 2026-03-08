#!/usr/bin/env bash
# =============================================================================
# PDF-Manager — SSL Certificate Auto-Renewal Script
# Renews Let's Encrypt certificates and reloads Nginx.
#
# Schedule via cron (run as root or the Docker socket owner):
#   0 3 * * * /path/to/ssl/renew-cert.sh >> /var/log/certbot-renew.log 2>&1
#
# Usage:
#   ./ssl/renew-cert.sh [--force]
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="${SCRIPT_DIR}/../.env"
COMPOSE_FILE="${SCRIPT_DIR}/../docker-compose.prod.yml"
FORCE_RENEWAL=""

[[ -f "${ENV_FILE}" ]] && set -a && source "${ENV_FILE}" && set +a

log() { echo "[renew-cert] $(date -u '+%Y-%m-%dT%H:%M:%SZ') $*"; }

# Parse arguments
for arg in "$@"; do
    [[ "${arg}" == "--force" ]] && FORCE_RENEWAL="--force-renewal"
done

log "Starting certificate renewal check..."

# ---------------------------------------------------------------------------
# Run certbot renew inside a temporary container
# ---------------------------------------------------------------------------
docker run --rm \
    -v certificates:/etc/letsencrypt \
    -v /var/www/certbot:/var/www/certbot \
    certbot/certbot:latest \
    renew \
    --webroot \
    --webroot-path=/var/www/certbot \
    --quiet \
    ${FORCE_RENEWAL}

CERTBOT_EXIT=$?

if [[ "${CERTBOT_EXIT}" -eq 0 ]]; then
    log "Certificate check/renewal succeeded."
else
    log "WARNING: certbot exited with code ${CERTBOT_EXIT}."
fi

# ---------------------------------------------------------------------------
# Reload Nginx to pick up renewed certificates
# ---------------------------------------------------------------------------
log "Reloading Nginx configuration..."
docker compose -f "${COMPOSE_FILE}" exec -T nginx nginx -s reload \
    && log "Nginx reloaded successfully." \
    || log "WARNING: Nginx reload failed — check container status."

log "Done."
exit "${CERTBOT_EXIT}"
