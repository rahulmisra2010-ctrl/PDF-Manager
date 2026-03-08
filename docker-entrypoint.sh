#!/usr/bin/env sh
# =============================================================================
# PDF-Manager — Container entrypoint script
# =============================================================================
set -e

# ---------------------------------------------------------------------------
# Wait for PostgreSQL to be ready (when using production database)
# ---------------------------------------------------------------------------
wait_for_postgres() {
    if [ -z "${DATABASE_URL}" ] || echo "${DATABASE_URL}" | grep -q "sqlite"; then
        return 0
    fi

    echo "[entrypoint] Waiting for PostgreSQL..."
    # Extract host and port from DATABASE_URL
    DB_HOST=$(echo "${DATABASE_URL}" | sed -E 's|.*@([^:/]+).*|\1|')
    DB_PORT=$(echo "${DATABASE_URL}" | sed -E 's|.*:([0-9]+)/.*|\1|')
    DB_PORT="${DB_PORT:-5432}"

    attempt=0
    max_attempts=30
    until pg_isready -h "${DB_HOST}" -p "${DB_PORT}" -q 2>/dev/null; do
        attempt=$((attempt + 1))
        if [ "${attempt}" -ge "${max_attempts}" ]; then
            echo "[entrypoint] ERROR: PostgreSQL did not become ready in time." >&2
            exit 1
        fi
        echo "[entrypoint] PostgreSQL not ready (attempt ${attempt}/${max_attempts}), retrying in 2s..."
        sleep 2
    done
    echo "[entrypoint] PostgreSQL is ready."
}

# ---------------------------------------------------------------------------
# Wait for Redis to be ready
# ---------------------------------------------------------------------------
wait_for_redis() {
    if [ -z "${REDIS_URL}" ]; then
        return 0
    fi

    echo "[entrypoint] Waiting for Redis..."
    REDIS_HOST=$(echo "${REDIS_URL}" | sed -E 's|.*@([^:/]+).*|\1|')
    REDIS_PORT=$(echo "${REDIS_URL}" | sed -E 's|.*:([0-9]+)/.*|\1|')
    REDIS_PORT="${REDIS_PORT:-6379}"

    attempt=0
    max_attempts=20
    until redis-cli -h "${REDIS_HOST}" -p "${REDIS_PORT}" ping > /dev/null 2>&1; do
        attempt=$((attempt + 1))
        if [ "${attempt}" -ge "${max_attempts}" ]; then
            echo "[entrypoint] WARNING: Redis not reachable — continuing without it."
            return 0
        fi
        echo "[entrypoint] Redis not ready (attempt ${attempt}/${max_attempts}), retrying in 2s..."
        sleep 2
    done
    echo "[entrypoint] Redis is ready."
}

# ---------------------------------------------------------------------------
# Ensure required directories exist
# ---------------------------------------------------------------------------
ensure_dirs() {
    mkdir -p "${UPLOAD_DIR:-/app/uploads}" \
             "${EXPORT_DIR:-/app/exports}" \
             "${LOG_DIR:-/app/logs}" \
             /app/instance
}

# ---------------------------------------------------------------------------
# Run database migrations / table creation
# ---------------------------------------------------------------------------
run_migrations() {
    echo "[entrypoint] Running database setup..."
    python - <<'PYEOF'
import sys
try:
    from app import create_app
    app = create_app()
    with app.app_context():
        from models import db
        db.create_all()
    print("[entrypoint] Database tables verified/created.")
except Exception as exc:
    print(f"[entrypoint] WARNING: DB setup step failed: {exc}", file=sys.stderr)
PYEOF
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
ensure_dirs
wait_for_postgres
wait_for_redis
run_migrations

echo "[entrypoint] Starting: $*"
exec "$@"
