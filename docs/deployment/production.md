# Production Deployment Checklist

Use this checklist before deploying PDF Manager to production.

## Security

- [ ] `SECRET_KEY` is cryptographically random (≥ 32 hex chars)
  ```bash
  python -c "import secrets; print(secrets.token_hex(32))"
  ```
- [ ] `ADMIN_PASSWORD` is strong and unique
- [ ] `DEBUG=false` in `.env`
- [ ] HTTPS is enabled (self-signed or CA-signed certificate)
- [ ] `SESSION_COOKIE_SECURE=True` in production configuration
- [ ] Database password is strong and not the default
- [ ] Firewall rules allow only ports 80/443 (and 22 for SSH)

## Database

- [ ] PostgreSQL is used (not SQLite) for production
- [ ] Database is not exposed to the internet
- [ ] Automated backups are configured (see [Backup & Recovery](backup.md))
- [ ] Schema has been applied: `psql -f database/schema.sql`

## Storage

- [ ] `UPLOAD_DIR` and `EXPORT_DIR` point to persistent volumes (not inside containers)
- [ ] Disk space is monitored; alerts configured for > 80% usage

## Performance

- [ ] Gunicorn (not the Flask dev server) is used to serve the backend
- [ ] nginx is used as a reverse proxy in front of Gunicorn and the React frontend
- [ ] Worker count matches available CPU cores: `--workers $(nproc)`

## Monitoring

- [ ] Application logs are collected (see [Monitoring](monitoring.md))
- [ ] Health check endpoint is reachable: `GET /health`
- [ ] Uptime monitoring is configured

## Quick Production `.env`

```dotenv
DEBUG=false
HOST=127.0.0.1
PORT=5000
SECRET_KEY=<generated-value>
ADMIN_PASSWORD=<strong-password>
DATABASE_URL=postgresql://pdfmanager:<password>@db-host:5432/pdfmanager
UPLOAD_DIR=/data/uploads
EXPORT_DIR=/data/exports
MAX_UPLOAD_SIZE_MB=50
ALLOWED_ORIGINS=["https://your-domain.com"]
```

## Starting Gunicorn

```bash
pip install gunicorn
gunicorn "app:create_app()" \
  --bind 127.0.0.1:5000 \
  --workers 4 \
  --timeout 120 \
  --access-logfile /var/log/pdf-manager/access.log \
  --error-logfile /var/log/pdf-manager/error.log
```
