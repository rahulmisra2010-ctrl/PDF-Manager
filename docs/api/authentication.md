# Authentication

PDF Manager uses **cookie-based session authentication** powered by Flask-Login.

## Logging In

### Via the Browser

Navigate to `/auth/login` and enter your credentials.

### Via the API (cURL)

Obtain a session cookie by posting credentials to the login endpoint:

```bash
curl -c cookies.txt -X POST http://localhost:5000/auth/login \
  -d "username=admin&password=<your-password>"
```

The `-c cookies.txt` flag saves the session cookie. Use `-b cookies.txt` in subsequent requests:

```bash
curl -b cookies.txt http://localhost:5000/api/v1/documents
```

### Via Python

```python
import requests

session = requests.Session()
session.post("http://localhost:5000/auth/login", data={
    "username": "admin",
    "password": "your-password"
})

# All subsequent requests use the session cookie automatically
response = session.get("http://localhost:5000/api/v1/documents")
print(response.json())
```

## CSRF Protection

State-changing requests (POST, PUT, DELETE) require a valid CSRF token when called from a browser form. The React frontend handles this automatically. For API clients, the CSRF requirement can be disabled in development by setting `WTF_CSRF_ENABLED=False` in your test configuration.

## Logging Out

```bash
curl -b cookies.txt -X POST http://localhost:5000/auth/logout
```

## Error Responses

| Code | Reason |
|------|--------|
| 401 | Not authenticated – redirect to `/auth/login` |
| 403 | Authenticated but not authorised |

## Security Notes

- Session cookies are `HttpOnly` and should be `Secure` in production (HTTPS only).
- `SECRET_KEY` in `.env` controls session signing; rotate it to invalidate all sessions.
- Always use HTTPS in production to protect session cookies in transit.
