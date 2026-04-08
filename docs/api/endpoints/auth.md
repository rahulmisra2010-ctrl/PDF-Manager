# Authentication Endpoints

Base URL: `http://localhost:5000`

These endpoints are **not** under the `/api/v1` prefix — they are served by the `auth` blueprint.

---

## Login

### `POST /auth/login`

Authenticate and start a session.

#### Request

- **Method**: POST
- **Content-Type**: `application/x-www-form-urlencoded`

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `username` | string | ✅ | Account username |
| `password` | string | ✅ | Account password (min 8 chars) |

#### Success Response — `302 Found`

Redirects to the dashboard. Sets `session` cookie.

#### Error Response — `200 OK`

Re-renders the login page with a flash error message.

#### cURL Example

```bash
curl -c cookies.txt \
  -X POST http://localhost:5000/auth/login \
  -d "username=admin&password=yourpassword"
```

#### Python Example

```python
import requests

session = requests.Session()
resp = session.post("http://localhost:5000/auth/login", data={
    "username": "admin",
    "password": "yourpassword"
})
print("Logged in" if resp.ok else "Login failed")
```

---

## Logout

### `GET /auth/logout`

End the current session.

#### Request

- **Method**: GET
- **Authentication**: Required

#### Success Response — `302 Found`

Redirects to the login page. Clears the session cookie.

#### cURL Example

```bash
curl -b cookies.txt http://localhost:5000/auth/logout
```

---

## Notes

- The CSRF token is required for form submissions in browser contexts (managed automatically by Flask-WTF).
- Session expiry is controlled by `PERMANENT_SESSION_LIFETIME` in the Flask config.
- After logout, the session cookie is invalidated server-side.
