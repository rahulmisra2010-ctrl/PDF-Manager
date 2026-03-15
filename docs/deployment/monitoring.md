# Monitoring and Logging

## Application Logs

Flask logs are written to stdout by default. In production, redirect them:

```bash
gunicorn "app:create_app()" \
  --access-logfile /var/log/pdf-manager/access.log \
  --error-logfile /var/log/pdf-manager/error.log
```

In Docker, use the logging driver:

```yaml
services:
  backend:
    logging:
      driver: "json-file"
      options:
        max-size: "100m"
        max-file: "5"
```

## Health Check Endpoint

PDF Manager exposes `/health`:

```bash
curl http://localhost:5000/health
# → {"status": "ok", "database": "ok"}
```

Configure your load balancer / uptime monitor to check this endpoint every 60 seconds.

## Prometheus Metrics (Optional)

Install `prometheus-flask-exporter` to expose metrics at `/metrics`:

```bash
pip install prometheus-flask-exporter
```

```python
# In app.py
from prometheus_flask_exporter import PrometheusMetrics
metrics = PrometheusMetrics(app)
```

Then scrape with a Prometheus server and visualise in Grafana.

## Docker Compose Health Check

```yaml
services:
  backend:
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:5000/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 40s
```

## Log Aggregation

For centralised logging, ship logs to a log aggregation service:

| Service | How |
|---------|-----|
| AWS CloudWatch | Use the `awslogs` Docker logging driver |
| GCP Cloud Logging | Use the `gcplogs` Docker logging driver |
| Elastic Stack (ELK) | Use Filebeat to tail log files |
| Datadog | Use the Datadog Docker agent |

## Alerting

Set up alerts for:

- HTTP 5xx error rate > 1% (5 minutes)
- Health check failures
- Disk usage > 80%
- Database connection pool exhausted
- OCR extraction duration > 30 seconds

## Performance Metrics to Track

| Metric | Target |
|--------|--------|
| API response time (p95) | < 2 seconds |
| OCR extraction time | < 30 seconds |
| Upload throughput | Limited by disk I/O |
| Database query time (p99) | < 500 ms |
