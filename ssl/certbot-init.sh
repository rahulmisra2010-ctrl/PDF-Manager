#!/usr/bin/env bash
# =============================================================================
# PDF-Manager — Let's Encrypt Certificate Initialization
# Run once to obtain the initial SSL certificate for your domain.
#
# Prerequisites:
#   - Domain DNS already points to this server
#   - Nginx container is NOT yet started (or is serving port 80 only)
#   - DOMAIN_NAME and CERTBOT_EMAIL are set in .env
#
# Usage:
#   ./ssl/certbot-init.sh
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="${SCRIPT_DIR}/../.env"

# Load environment
[[ -f "${ENV_FILE}" ]] && set -a && source "${ENV_FILE}" && set +a

DOMAIN_NAME="${DOMAIN_NAME:?DOMAIN_NAME must be set in .env}"
CERTBOT_EMAIL="${CERTBOT_EMAIL:?CERTBOT_EMAIL must be set in .env}"
WEBROOT="${WEBROOT:-/var/www/certbot}"

log() { echo "[certbot-init] $*"; }
die() { echo "[certbot-init] ERROR: $*" >&2; exit 1; }

command -v docker >/dev/null 2>&1 || die "Docker is required."

log "Obtaining certificate for ${DOMAIN_NAME} (email: ${CERTBOT_EMAIL})..."

# ---------------------------------------------------------------------------
# Create webroot directory for ACME challenge
# ---------------------------------------------------------------------------
mkdir -p "${WEBROOT}"

# ---------------------------------------------------------------------------
# Run certbot in standalone / webroot mode
# ---------------------------------------------------------------------------
docker run --rm \
    -v certificates:/etc/letsencrypt \
    -v "${WEBROOT}:/var/www/certbot" \
    certbot/certbot:latest \
    certonly \
    --webroot \
    --webroot-path=/var/www/certbot \
    --email "${CERTBOT_EMAIL}" \
    --agree-tos \
    --no-eff-email \
    --force-renewal \
    -d "${DOMAIN_NAME}" \
    -d "www.${DOMAIN_NAME}"

log "Certificate obtained successfully."
log "Reload Nginx to activate: docker compose -f docker-compose.prod.yml exec nginx nginx -s reload"

# ---------------------------------------------------------------------------
# Generate Diffie-Hellman parameters (once — takes several minutes)
# ---------------------------------------------------------------------------
DHPARAM_FILE="${SCRIPT_DIR}/../nginx/dhparam/dhparam.pem"
mkdir -p "$(dirname "${DHPARAM_FILE}")"

if [[ ! -f "${DHPARAM_FILE}" ]]; then
    log "Generating 4096-bit DH parameters (this may take a few minutes)..."
    openssl dhparam -out "${DHPARAM_FILE}" 4096
    log "DH parameters generated at ${DHPARAM_FILE}"
else
    log "DH parameters already exist at ${DHPARAM_FILE} — skipping generation."
fi
