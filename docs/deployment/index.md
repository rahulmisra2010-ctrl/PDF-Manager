# Deployment

This page explains how to deploy PDF Manager in various environments.

## Docker Compose (recommended)

### Prerequisites

- Docker ≥ 24
- Docker Compose ≥ 2

### Steps

```bash
# 1. Clone the repo
git clone https://github.com/rahulmisra2010-ctrl/PDF-Manager.git
cd PDF-Manager

# 2. Configure environment variables
cp .env.example .env
# Edit .env with your settings

# 3. Build and start all services
docker compose up --build -d
```

Services started:

| Service | Port | Description |
|---------|------|-------------|
| backend | 5000 | Flask REST API |
| frontend | 3000 | React web UI |

### Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `SECRET_KEY` | Yes | Flask secret key (use a strong random value) |
| `ADMIN_PASSWORD` | Yes | Password for the admin account |
| `DATABASE_URL` | No | SQLite path or PostgreSQL URL (default: SQLite) |
| `DOCKER_HUB_USERNAME` | No | Used by CI/CD to push images |
| `DOCKER_HUB_TOKEN` | No | Docker Hub access token |
| `CODECOV_TOKEN` | No | Codecov upload token |
| `PYPI_API_TOKEN` | No | PyPI token for package publishing |

## Production Considerations

- Mount a persistent volume for `/app/uploads` and `/app/instance`
- Use a reverse proxy (nginx / Traefik) in front of the Flask backend
- Set `FLASK_ENV=production` and a strong `SECRET_KEY`
- Enable HTTPS with a valid TLS certificate

## GitHub Container Registry

Pre-built images are published to GHCR on every push to `main`:

```bash
docker pull ghcr.io/rahulmisra2010-ctrl/pdf-manager:latest
```
