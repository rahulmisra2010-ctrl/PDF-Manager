# SSL/TLS Setup

HTTPS is required for production. This page covers obtaining and configuring TLS certificates.

## Option 1 – Let's Encrypt with Certbot (nginx)

```bash
# Install certbot
sudo apt-get install certbot python3-certbot-nginx

# Obtain certificate
sudo certbot --nginx -d your-domain.com

# Auto-renewal
sudo systemctl enable certbot.timer
```

Certbot automatically modifies your nginx configuration. Certificates renew automatically every 60–90 days.

## Option 2 – Let's Encrypt with Docker and Certbot

```bash
# Stop nginx to free port 80
docker compose stop nginx

# Obtain certificate
docker run --rm \
  -v $(pwd)/certs:/etc/letsencrypt \
  -p 80:80 \
  certbot/certbot certonly \
  --standalone \
  -d your-domain.com \
  --email your-email@example.com \
  --agree-tos

# Restart
docker compose start nginx
```

## Option 3 – Cloud-Managed TLS

If you are using a cloud load balancer, TLS can be terminated at the load balancer:

| Cloud | Service |
|-------|---------|
| AWS | ACM (AWS Certificate Manager) |
| GCP | Managed SSL certificates |
| Azure | App Gateway / Front Door |

No changes to the Flask application are required; it serves plain HTTP behind the load balancer.

## nginx TLS Configuration

```nginx
server {
    listen 443 ssl http2;
    server_name your-domain.com;

    ssl_certificate     /etc/letsencrypt/live/your-domain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/your-domain.com/privkey.pem;

    # Security headers
    ssl_protocols             TLSv1.2 TLSv1.3;
    ssl_prefer_server_ciphers off;
    ssl_session_timeout       1d;
    ssl_session_cache         shared:SSL:10m;

    add_header Strict-Transport-Security "max-age=63072000" always;
    add_header X-Frame-Options           DENY;
    add_header X-Content-Type-Options    nosniff;
    add_header X-XSS-Protection         "1; mode=block";

    # ... proxy_pass to backend/frontend ...
}

# Redirect HTTP → HTTPS
server {
    listen 80;
    server_name your-domain.com;
    return 301 https://$host$request_uri;
}
```

## Flask Session Cookie Security

In production, add these settings to ensure cookies are only sent over HTTPS:

```python
# In app.py or config.py
app.config["SESSION_COOKIE_SECURE"] = True
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
```

Or set via environment variables if your configuration supports it.
