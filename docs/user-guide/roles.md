# User Roles and Permissions

PDF Manager uses a simple role-based access model managed through Flask-Login.

## Roles

| Role | Description |
|------|-------------|
| **Admin** | Full access: manage users, upload, extract, edit, export, delete documents |
| **User** | Can upload, extract, edit own documents, and export |

## Admin Account

The `admin` account is automatically created on first startup using the `ADMIN_PASSWORD` environment variable. If `ADMIN_PASSWORD` is not set, a random password is generated and printed to the server log.

## Authentication

PDF Manager uses cookie-based session authentication (Flask-Login + Flask-WTF CSRF protection).

| Endpoint | Access |
|----------|--------|
| `/auth/login` | Public |
| `/auth/logout` | Authenticated users |
| `/api/v1/*` | Authenticated users |
| Admin settings | Admin only |

## Managing Users

Admins can manage users via the admin panel at `/admin/users` (if the admin blueprint is enabled).

## Security Notes

- Sessions are signed with `SECRET_KEY` — keep this value secret.
- CSRF tokens protect all state-changing form submissions.
- Passwords are hashed with bcrypt via Flask-Bcrypt.
- Change the default `ADMIN_PASSWORD` immediately in production.

## Production Recommendations

- Enforce HTTPS so session cookies are transmitted securely.
- Set `SESSION_COOKIE_SECURE=True` and `SESSION_COOKIE_HTTPONLY=True` in production.
- Rotate `SECRET_KEY` periodically (this invalidates existing sessions).
