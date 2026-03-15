# Docker Installation

Docker is the recommended installation method. It starts the Flask backend, React frontend, and (optionally) PostgreSQL with a single command.

## Prerequisites

- [Docker Desktop](https://docs.docker.com/get-docker/) 24+
- [Docker Compose](https://docs.docker.com/compose/install/) 2.20+
- At least 4 GB of free RAM

## Quick Start

```bash
# 1. Clone the repository
git clone https://github.com/rahulmisra2010-ctrl/PDF-Manager.git
cd PDF-Manager

# 2. Create your environment file
cp .env.example .env
# Edit .env and set SECRET_KEY and ADMIN_PASSWORD

# 3. Build and start all services
docker compose up --build
```

Once the build completes, open:

| Service | URL |
|---------|-----|
| React Frontend | <http://localhost:3000> |
| Flask Backend / API | <http://localhost:5000> |
| Admin Login | <http://localhost:5000/auth/login> |

## Service Overview

The `docker-compose.yml` defines the following services:

```yaml
services:
  backend:   # Flask + OCR libraries  → :5000
  frontend:  # React dev server       → :3000
  db:        # PostgreSQL 15          → :5432 (optional)
```

## Environment Configuration

Edit `.env` before starting. At a minimum, set:

```dotenv
SECRET_KEY=<generated-value>
ADMIN_PASSWORD=<strong-password>
```

To use the bundled PostgreSQL database instead of SQLite:

```dotenv
DATABASE_URL=postgresql://pdfmanager:pdfmanager@db:5432/pdfmanager
```

## Useful Commands

```bash
# Start in the background (detached)
docker compose up -d --build

# View logs
docker compose logs -f backend

# Stop all services
docker compose down

# Stop and remove volumes (resets database)
docker compose down -v

# Rebuild a single service
docker compose up --build backend
```

## First-Time Database Initialisation

If you are using the PostgreSQL service, initialise the schema:

```bash
docker compose exec db psql -U pdfmanager -d pdfmanager -f /docker-entrypoint-initdb.d/init.sql
```

## Health Checks

Verify the backend is running:

```bash
curl http://localhost:5000/health
# → {"status": "ok"}
```

## Troubleshooting

| Problem | Solution |
|---------|---------|
| Port 5000 already in use | Change `PORT=5001` in `.env`, update `docker-compose.yml` |
| Port 3000 already in use | Change the frontend port mapping in `docker-compose.yml` |
| Build fails on OCR packages | Ensure Docker has at least 4 GB of memory allocated |
| `SECRET_KEY` not set | Copy `.env.example` to `.env` and fill in values |
| Database connection refused | Check `DATABASE_URL` and that the `db` service is healthy |

See [Troubleshooting](../troubleshooting/common-issues.md) for more help.
