# Backup and Recovery

## Database Backup (PostgreSQL)

### Manual Backup

```bash
# Dump the database
pg_dump -U pdfmanager -d pdfmanager -F c -f backup_$(date +%Y%m%d_%H%M%S).dump

# Restore from backup
pg_restore -U pdfmanager -d pdfmanager -c backup_20260307_120000.dump
```

### Automated Backups with Cron

```bash
# /etc/cron.d/pdf-manager-backup
0 2 * * * postgres pg_dump -U pdfmanager -d pdfmanager -F c \
  -f /backups/pdf-manager_$(date +\%Y\%m\%d).dump
```

### Docker Compose Backup

```bash
docker compose exec db pg_dump -U pdfmanager pdfmanager \
  > backup_$(date +%Y%m%d_%H%M%S).sql
```

## Uploaded Files Backup

PDF uploads are stored in `UPLOAD_DIR` (default: `uploads/`). Back this directory up alongside the database.

```bash
# Sync to S3
aws s3 sync uploads/ s3://your-bucket/pdf-manager/uploads/

# Local archive
tar -czf uploads_$(date +%Y%m%d).tar.gz uploads/
```

## Recovery Procedure

1. Restore the PostgreSQL database from the latest dump.
2. Restore the `uploads/` directory from backup storage.
3. Restart the application.

```bash
# Restore database
pg_restore -U pdfmanager -d pdfmanager -c /backups/pdf-manager_20260307.dump

# Restore uploads
aws s3 sync s3://your-bucket/pdf-manager/uploads/ uploads/

# Restart
docker compose restart backend
```

## Backup Verification

Test your backups regularly:

```bash
# Restore to a test database
createdb pdfmanager_test
pg_restore -U pdfmanager -d pdfmanager_test /backups/pdf-manager_20260307.dump
psql -U pdfmanager -d pdfmanager_test -c "SELECT COUNT(*) FROM documents;"
```

## Retention Policy

| Backup Type | Retention |
|-------------|-----------|
| Daily database dumps | 30 days |
| Weekly database dumps | 12 weeks |
| Monthly database dumps | 12 months |
| Upload files | Indefinite (until deleted by user) |
