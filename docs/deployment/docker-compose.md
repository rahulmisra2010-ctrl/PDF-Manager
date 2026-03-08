# Docker Compose Production Setup

This guide configures Docker Compose for a production environment.

## Production `docker-compose.yml`

```yaml
version: "3.9"

services:
  backend:
    build:
      context: .
      dockerfile: Dockerfile
    restart: unless-stopped
    environment:
      - DEBUG=false
      - SECRET_KEY=${SECRET_KEY}
      - ADMIN_PASSWORD=${ADMIN_PASSWORD}
      - DATABASE_URL=postgresql://pdfmanager:${DB_PASSWORD}@db:5432/pdfmanager
      - UPLOAD_DIR=/data/uploads
      - EXPORT_DIR=/data/exports
    volumes:
      - uploads:/data/uploads
      - exports:/data/exports
    depends_on:
      db:
        condition: service_healthy
    networks:
      - internal

  frontend:
    build:
      context: ./frontend
      dockerfile: Dockerfile
    restart: unless-stopped
    networks:
      - internal

  db:
    image: postgres:15-alpine
    restart: unless-stopped
    environment:
      POSTGRES_USER: pdfmanager
      POSTGRES_PASSWORD: ${DB_PASSWORD}
      POSTGRES_DB: pdfmanager
    volumes:
      - postgres_data:/var/lib/postgresql/data
      - ./database/schema.sql:/docker-entrypoint-initdb.d/01-schema.sql
      - ./database/init.sql:/docker-entrypoint-initdb.d/02-init.sql
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U pdfmanager"]
      interval: 10s
      timeout: 5s
      retries: 5
    networks:
      - internal

  nginx:
    image: nginx:alpine
    restart: unless-stopped
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./nginx.conf:/etc/nginx/conf.d/default.conf:ro
      - ./certs:/etc/nginx/certs:ro
    depends_on:
      - backend
      - frontend
    networks:
      - internal

volumes:
  postgres_data:
  uploads:
  exports:

networks:
  internal:
    driver: bridge
```

## nginx Configuration

Save as `nginx.conf` in the project root:

```nginx
server {
    listen 80;
    server_name your-domain.com;
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl;
    server_name your-domain.com;

    ssl_certificate     /etc/nginx/certs/fullchain.pem;
    ssl_certificate_key /etc/nginx/certs/privkey.pem;
    ssl_protocols       TLSv1.2 TLSv1.3;

    # React frontend
    location / {
        proxy_pass http://frontend:3000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
    }

    # Flask backend / API
    location ~ ^/(api|auth|health) {
        proxy_pass http://backend:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        client_max_body_size 55m;
    }
}
```

## Deployment Steps

```bash
# 1. Create production .env
cp .env.example .env
# Edit .env with production values

# 2. Place TLS certificates
mkdir -p certs
# Copy fullchain.pem and privkey.pem to certs/

# 3. Start services
docker compose -f docker-compose.yml up -d

# 4. Verify
curl https://your-domain.com/health
```

## Updating the Application

```bash
git pull
docker compose build backend frontend
docker compose up -d
```
