"""
PDF-Manager — Gunicorn Production Configuration
Reference: https://docs.gunicorn.org/en/stable/settings.html
"""
import multiprocessing
import os

# ---------------------------------------------------------------------------
# Server socket
# ---------------------------------------------------------------------------
bind = f"0.0.0.0:{os.environ.get('PORT', '5000')}"
backlog = 2048

# ---------------------------------------------------------------------------
# Workers
# ---------------------------------------------------------------------------
# Formula: (number of CPU cores × 2) + 1
workers = int(os.environ.get("GUNICORN_WORKERS", multiprocessing.cpu_count() * 2 + 1))
worker_class = "sync"       # use "gevent" or "eventlet" for async workloads
threads = int(os.environ.get("GUNICORN_THREADS", 4))
worker_connections = 1000

# ---------------------------------------------------------------------------
# Timeouts
# ---------------------------------------------------------------------------
timeout = int(os.environ.get("GUNICORN_TIMEOUT", 120))
keepalive = 5
graceful_timeout = 30

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
log_dir = os.environ.get("LOG_DIR", "/app/logs")
accesslog = f"{log_dir}/gunicorn_access.log"
errorlog = f"{log_dir}/gunicorn_error.log"
loglevel = "warning"
access_log_format = (
    '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s" %(D)sµs'
)

# ---------------------------------------------------------------------------
# Process naming
# ---------------------------------------------------------------------------
proc_name = "pdfmanager"

# ---------------------------------------------------------------------------
# Server mechanics
# ---------------------------------------------------------------------------
daemon = False              # Docker manages the process
preload_app = True          # load the app before forking (saves memory)
reuse_port = True

# ---------------------------------------------------------------------------
# Security
# ---------------------------------------------------------------------------
limit_request_line = 4094
limit_request_fields = 100
limit_request_field_size = 8190

# ---------------------------------------------------------------------------
# Hooks
# ---------------------------------------------------------------------------
def on_starting(server):
    server.log.info("PDF-Manager Gunicorn starting up")


def on_exit(server):
    server.log.info("PDF-Manager Gunicorn shutting down")


def worker_exit(server, worker):
    server.log.info("Worker %s exited (pid=%d)", worker, worker.pid)
