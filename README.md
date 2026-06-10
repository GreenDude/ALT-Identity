# ALT-Identity

ALT-Identity is a simple OIDC-like identity service built with Django. It is
meant for early development, local testing, demos, and browser automation
scenarios where teams need a lightweight identity provider without standing up a
full production auth stack.

This project is intentionally for early development and testing only. It is
designed to help teams move quickly while prototyping auth flows, validating
redirect behavior, and writing automated tests against a predictable local
identity provider.

The repository includes both sides of the flow:

- `auth_server`: a compact identity provider with login, authorization, token,
  logout, and profile endpoints.
- `aot`: a demo relying-party client that drives the authorization-code flow and
  renders the resulting profile response as a readable HTML page.

## What This Project Is Good For

- Prototyping applications that need a login and token exchange flow.
- Exercising browser redirects and callback handling in local development.
- Writing end-to-end or Selenium tests against a stable, controllable auth flow.
- Demonstrating the basics of an OAuth 2.0 / OIDC-style authorization-code flow.

## What This Project Is Not

- Not a production-ready identity provider.
- Not a complete OIDC implementation.
- Not hardened for multi-tenant, internet-facing deployments.
- Not currently validating clients, secrets, consent, refresh flows, or token
  expiry beyond the stored authorization-code window.

## Why Not Production

For production environments, it is usually better to use a dedicated identity
platform such as Keycloak or another managed identity service.

Those systems are built to handle concerns that this project intentionally keeps
out of scope, including:

- stronger security hardening and operational review
- robust client registration and secret management
- production-grade token lifecycle handling
- standards-compliant OIDC and OAuth behavior across more flows
- federation, SSO, user management, and admin tooling
- auditing, monitoring, and policy controls
- operational scalability and high availability

ALT-Identity is valuable because it is small, understandable, and easy to adapt
for local work. That same simplicity is also why it should not be treated as a
drop-in production identity provider.

## Features

- Django session-backed login using the built-in authentication system.
- Authorization endpoint that issues short-lived, single-use auth codes.
- PKCE support for authorization-code clients using `plain` or `S256`.
- Token endpoint that exchanges codes for bearer-style access and refresh tokens.
- Profile endpoint protected by `Authorization: Bearer ...`.
- Demo client page that shows profile data in human-readable HTML and formatted
  JSON.
- Logout button on the demo profile page.
- Stable HTML ids on the login form for browser automation:
  `username-field`, `password-field`, and `login-button`.
- Verbose inbound and outbound HTTP logging, enabled by default for dev and test use.

## Repository Layout

```text
ALT-Identity/
├── README.md
├── docs/
│   ├── architecture.md
│   └── integration-guide.md
└── identity-service/
    ├── manage.py
    ├── config/
    ├── aot/
    ├── auth_server/
    └── resource_server/
```

## Architecture Summary

1. A browser visits the demo client endpoint at `/profile`.
2. If no access token is stored in the browser session, the client redirects to
   `/auth/authorize`.
3. If the user is not logged in, the auth server stores the pending request in
   session and redirects the browser to `/auth/login`.
4. After login, the auth server returns to `/auth/authorize`, creates an
   authorization code bound to the PKCE challenge, and redirects to the
   configured callback.
5. The callback exchanges the authorization code at `/auth/token` using the
   original `code_verifier`.
6. The demo client stores the returned tokens in session and requests
   `/auth/profile` with a bearer token.
7. The profile response is rendered as HTML for humans and automation tooling.

More detail is in [docs/architecture.md](docs/architecture.md).

## Quick Start

### Requirements

- Python `3.14`
- Django `6.0.6` or newer

### Install

```bash
cd /Users/cloudraccoon/PycharmProjects/ALT-Identity
python3 -m venv .venv
source .venv/bin/activate
pip install "django>=6.0.6"
```

### Initialize the database

```bash
cd /Users/cloudraccoon/PycharmProjects/ALT-Identity/identity-service
python3 manage.py migrate
python3 manage.py createsuperuser
```

### Create a demo user profile

Use the Django admin at `/admin/` or a shell session:

```bash
python3 manage.py shell
```

```python
from django.contrib.auth.models import User
from auth_server.models import UserProfile

user = User.objects.create_user(username="demo", password="demo-pass")
UserProfile.objects.create(user=user, learning_goal="Explore local auth flows")
```

### Run the app

```bash
python3 manage.py runserver
```

Open [http://localhost:8000/](http://localhost:8000/).

### Logging

ALT-Identity logs handled requests, returned responses, and the demo client's
outbound HTTP calls by default. This is controlled by the Django setting
`ALT_IDENTITY_VERBOSE_HTTP_LOGGING`, which defaults to `True`.

To disable it:

```python
ALT_IDENTITY_VERBOSE_HTTP_LOGGING = False
```

## Demo Flow

From the landing page:

1. Click `Profile demo`.
2. Log in when redirected to `/auth/login`.
3. Approve the implicit demo flow by continuing through the redirect sequence.
4. Review the resulting profile page, which shows:
   - a readable field list
   - the raw JSON payload
   - a logout button

## Integration Endpoints

### Authorization endpoint

- URL: `GET /auth/authorize`
- Query parameters:
- Query parameters:
  - `client_id`
  - `redirect_uri`
  - `response_type=code`
  - `scope` optional
  - `code_challenge` optional but recommended
  - `code_challenge_method` optional, supports `plain` and `S256`

Successful requests redirect to:

```text
{redirect_uri}?code={authorization_code}
```

### Token endpoint

- URL: `POST /auth/token`
- Form fields:
  - `grant_type=authorization_code`
  - `code`
  - `client_id`
  - `redirect_uri`
  - `code_verifier` required when PKCE was used at authorization time

Success response:

```json
{
  "access_token": "string",
  "refresh_token": "string",
  "token_type": "Bearer",
  "expires_in": 3600,
  "scope": "profile.read"
}
```

### Profile endpoint

- URL: `GET /auth/profile`
- Header: `Authorization: Bearer {access_token}`

Success response:

```json
{
  "user_name": "demo",
  "learning_goal": "Explore local auth flows"
}
```

## Browser Automation Notes

The login page exposes stable ids for Selenium and similar tools:

- `#username-field`
- `#password-field`
- `#login-button`
- `#logout-button`
- `#profile-json`

This makes it straightforward to script the end-to-end demo flow.

## Suggested Selenium Flow

1. Open `http://localhost:8000/profile`.
2. Wait for the login page.
3. Fill `#username-field` and `#password-field`.
4. Click `#login-button`.
5. Wait for the profile page.
6. Assert visible profile content or inspect `#profile-json`.

## Extending the Project

Common next steps if you want to integrate this into a larger local platform:

- Add client registration and client secret validation.
- Add token expiry checks and refresh-token grant support.
- Move protected APIs into `resource_server`.
- Add consent screens and scope filtering.
- Replace SQLite with PostgreSQL for team-shared environments.
- Add API tests for authorization and token edge cases.

## Known Limitations

- `client_id` values are accepted without registration or secret validation.
- Redirect URIs are validated only by equality against the stored auth code.
- Access tokens are stored server-side and not cryptographically signed.
- Token expiry is returned but not actively enforced in the profile endpoint.
- The implementation is intentionally small and omits many production concerns.

## Additional Documentation

- [Architecture overview](docs/architecture.md)
- [Integration guide](docs/integration-guide.md)
