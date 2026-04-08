# Authentication

PDF Manager uses **session-based authentication**. A valid session cookie must accompany every request that targets a protected endpoint.

## Login

### `POST /auth/login`

Authenticate with username and password. On success the server sets a `session` cookie that must be sent with every subsequent request.

#### Request Body — `application/x-www-form-urlencoded` or `multipart/form-data`

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `username` | string | ✅ | Your account username |
| `password` | string | ✅ | Your account password (min 8 characters) |

#### Success Response — `302 Found`

The server redirects the browser to the dashboard and sets the session cookie.

#### Error Response — `200 OK` (re-renders the login form)

The login page is re-rendered with a flash error message when credentials are invalid.

#### cURL Example

```bash
# Log in and save the session cookie to a file
curl -c cookies.txt \
  -X POST http://localhost:5000/auth/login \
  -d "username=admin&password=yourpassword"
```

---

## Logout

### `GET /auth/logout`

Ends the current session and clears the session cookie.

#### cURL Example

```bash
curl -b cookies.txt http://localhost:5000/auth/logout
```

---

## Session Management

Sessions are managed server-side with Flask-Login. The cookie is `HttpOnly` and tied to the server secret key.

- Sessions expire when the browser is closed (session cookies).
- The default `SESSION_COOKIE_SECURE` setting should be enabled in production.
- CSRF protection is provided by Flask-WTF for all form submissions.

### Using the Session Cookie with API Requests

After logging in, pass the saved cookie jar with every API call:

```bash
# Save cookie at login
curl -c cookies.txt -X POST http://localhost:5000/auth/login \
  -d "username=admin&password=yourpassword"

# Use cookie for API calls
curl -b cookies.txt http://localhost:5000/api/v1/documents
```

Python:

```python
import requests

session = requests.Session()
session.post("http://localhost:5000/auth/login", data={
    "username": "admin",
    "password": "yourpassword"
})

# Session cookie is kept automatically
resp = session.get("http://localhost:5000/api/v1/documents")
print(resp.json())
```

JavaScript (browser):

```javascript
// Credentials are sent automatically via the browser session cookie.
// Use fetch with credentials: 'include' for cross-origin calls.
const resp = await fetch('http://localhost:5000/api/v1/documents', {
  credentials: 'include'
});
const data = await resp.json();
```

---

## Password Requirements

- Minimum **8 characters**
- Hashed with Bcrypt before storage — plaintext is never persisted

---

## Role-Based Access Control

Every user has one of three roles. Some API endpoints require elevated privileges.

| Role | Description |
|------|-------------|
| `Admin` | Full access including user management |
| `Verifier` | Can upload, extract, and edit fields |
| `Viewer` | Read-only access to documents and fields |

---

## Two-Factor Authentication

Two-factor authentication is **not currently implemented**. It is planned for a future release.

---

## OAuth / SSO

OAuth and SSO integrations are **not currently implemented**. It is planned for a future release.

---

## Security Best Practices

- Always use HTTPS in production.
- Store session cookies securely — do not log or expose them.
- Rotate the Flask `SECRET_KEY` regularly.
- Set `SESSION_COOKIE_SECURE = True` and `SESSION_COOKIE_HTTPONLY = True` in production config.
- Use environment variables for secrets; never hard-code credentials.
