#!/usr/bin/env bash
# =============================================================================
# PDF-Manager — Health Check Script
# Checks that all production services are running and healthy.
# Exit code: 0 = all healthy, 1 = one or more services unhealthy.
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMPOSE_FILE="${SCRIPT_DIR}/../docker-compose.prod.yml"
ENV_FILE="${SCRIPT_DIR}/../.env"

APP_URL="${APP_URL:-http://localhost}"
API_HEALTH_URL="${APP_URL}/api/v1/health"

PASS=0
FAIL=1
overall=${PASS}

log()  { echo "[health] $*"; }
ok()   { echo "[health] ✓ $*"; }
fail() { echo "[health] ✗ $*" >&2; overall=${FAIL}; }

# ---------------------------------------------------------------------------
# HTTP health endpoint
# ---------------------------------------------------------------------------
check_http() {
    local url="$1"
    local label="${2:-HTTP}"
    local http_code
    http_code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 10 "${url}" 2>/dev/null || echo "000")
    if [[ "${http_code}" =~ ^2 ]]; then
        ok "${label}: HTTP ${http_code}"
    else
        fail "${label}: HTTP ${http_code} (expected 2xx) — ${url}"
    fi
}

# ---------------------------------------------------------------------------
# Docker container status
# ---------------------------------------------------------------------------
check_container() {
    local name="$1"
    local status
    status=$(docker inspect --format='{{.State.Health.Status}}' "${name}" 2>/dev/null || echo "missing")
    case "${status}" in
        healthy)  ok  "Container ${name}: healthy" ;;
        missing)  fail "Container ${name}: not found" ;;
        *)        fail "Container ${name}: ${status}" ;;
    esac
}

# ---------------------------------------------------------------------------
# PostgreSQL
# ---------------------------------------------------------------------------
check_postgres() {
    [[ -f "${ENV_FILE}" ]] && source "${ENV_FILE}" || true
    local host="${POSTGRES_HOST:-localhost}"
    local port="${POSTGRES_PORT:-5432}"
    local user="${POSTGRES_USER:-pdfmanager}"
    local db="${POSTGRES_DB:-pdfmanager}"

    if pg_isready -h "${host}" -p "${port}" -U "${user}" -d "${db}" -q 2>/dev/null; then
        ok "PostgreSQL: accepting connections"
    else
        fail "PostgreSQL: not ready on ${host}:${port}"
    fi
}

# ---------------------------------------------------------------------------
# Redis
# ---------------------------------------------------------------------------
check_redis() {
    [[ -f "${ENV_FILE}" ]] && source "${ENV_FILE}" || true
    local host="${REDIS_HOST:-localhost}"
    local port="${REDIS_PORT:-6379}"
    local pass="${REDIS_PASSWORD:-}"

    if redis-cli -h "${host}" -p "${port}" ${pass:+-a "${pass}"} --no-auth-warning ping 2>/dev/null | grep -q PONG; then
        ok "Redis: PONG received"
    else
        fail "Redis: no PONG from ${host}:${port}"
    fi
}

# ---------------------------------------------------------------------------
# Run checks
# ---------------------------------------------------------------------------
log "Starting health checks..."

# Docker container health
for container in pdfmanager-nginx pdfmanager-web pdfmanager-postgres pdfmanager-redis pdfmanager-pgbouncer; do
    check_container "${container}"
done

# Application HTTP endpoint
check_http "${API_HEALTH_URL}" "Flask API /health"

# Infrastructure connectivity
check_postgres
check_redis

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
echo ""
if [[ "${overall}" -eq ${PASS} ]]; then
    log "All checks passed ✓"
else
    log "One or more checks FAILED ✗"
fi

exit "${overall}"
