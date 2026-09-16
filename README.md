# ALT-Identity

ALT-Identity is a simple OpenID Connect identity service built with Django. It is
meant for early development, local testing, demos, and browser automation
scenarios where teams need a lightweight identity provider without standing up a
full production auth stack.

This project is intentionally for early development and testing only. It is
designed to help teams move quickly while prototyping auth flows, validating
redirect behavior, and writing automated tests against a predictable local
identity provider.

The repository includes both sides of the flow:

- `auth_server`: a compact identity provider with login, authorization, token,
  logout, discovery, JWKS, and userinfo endpoints.
- `aot`: the bundled demo client that drives the authorization-code flow and
  renders the resulting profile response as a readable HTML page.

## What This Project Is Good For

- Prototyping applications that need a login and token exchange flow.
- Exercising browser redirects and callback handling in local development.
- Writing end-to-end browser automation tests, including Selenium-based tests,
  against a stable, controllable auth flow.
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
- Token endpoint that exchanges codes for bearer-style access and refresh tokens plus an RS256-signed `id_token`.
- OpenID Connect discovery and JWKS publication.
- UserInfo endpoint protected by `Authorization: Bearer ...`.
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
   `/auth/authorize` with `scope=openid profile`, `state`, `nonce`, and PKCE.
3. If the user is not logged in, the auth server stores the pending request in
   session and redirects the browser to `/auth/login`.
4. After login, the auth server returns to `/auth/authorize`, creates an
   authorization code bound to the PKCE challenge, and redirects to the
   configured callback.
5. The callback verifies `state` and exchanges the authorization code at `/auth/token` using the original `code_verifier`.
6. The bundled demo client stores the returned access, refresh, and ID tokens in session and requests `/auth/userinfo` with a bearer token.
7. The userinfo response is rendered as HTML for humans and automation tooling.

More detail is in [docs/architecture.md](docs/architecture.md).

## Quick Start

### Requirements

- Python `3.14`
- Django `6.0.6` or newer

### Install

The identity service logic lives in this repository. There is not a separate
published package to install from PyPI; instead, install this project and its
declared dependencies locally.

```bash
cd /Users/cloudraccoon/PycharmProjects/ALT-Identity
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

### Initialize the database

```bash
cd /Users/cloudraccoon/PycharmProjects/ALT-Identity/identity-service
python3 manage.py migrate
python3 manage.py createsuperuser
```

### Configure OIDC signing keys

ALT-Identity signs `id_token`s with RS256. The token endpoint will return
`{"error": "server_error"}` until a private signing key is configured.

Generate a local development keypair:

```bash
openssl genpkey -algorithm RSA -out /tmp/oidc-private.pem -pkeyopt rsa_keygen_bits:2048
openssl pkey -in /tmp/oidc-private.pem -pubout -out /tmp/oidc-public.pem
```

Set the runtime environment before starting Django:

```bash
export ALT_IDENTITY_ISSUER="http://localhost:8000"
export ALT_IDENTITY_SESSION_COOKIE_NAME="alt_identity_sessionid"
export ALT_IDENTITY_OIDC_PRIVATE_KEY_PEM="$(cat /tmp/oidc-private.pem)"
export ALT_IDENTITY_OIDC_PUBLIC_KEY_PEM="$(cat /tmp/oidc-public.pem)"
export ALT_IDENTITY_OIDC_KEY_ID="dev-rs256-1"
```

If you run ALT-Identity on a different origin, such as `http://127.0.0.1:8900`,
set `ALT_IDENTITY_ISSUER` to that exact origin.

If another Django app is also running on `127.0.0.1`, keep
`ALT_IDENTITY_SESSION_COOKIE_NAME` distinct from that app's session cookie
name. Cookies are shared by host, not port, so using the default Django
`sessionid` value in both apps can break the OIDC state round-trip.

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

### Register a client redirect URI

ALT-Identity validates the exact `redirect_uri` sent to `/auth/authorize` and
`/auth/token`. The bundled demo client automatically registers its current
callback URL before starting the flow, so the profile demo works when you open
the app through `localhost`, `127.0.0.1`, or a LAN address. Other clients still
need exact redirect URI registration. If the callback URL is not registered for
the client, the authorization request fails with `Unregistered redirect_uri.`

You can register client redirect URIs through Django admin or the shell:

```bash
python3 manage.py shell
```

```python
from auth_server.models import Client

client, _ = Client.objects.get_or_create(
    client_id="awesome-service",
    defaults={
        "name": "Bundled Demo Client",
        "redirect_uris": "http://localhost:8000/callback",
        "allowed_scopes": "openid profile",
        "is_confidential": False,
    },
)

uris = set(client.registered_redirect_uris())
uris.add("http://127.0.0.1:8900/callback")
client.redirect_uris = "\n".join(sorted(uris))
client.save()
```

Notes:

- `redirect_uri` matching is exact, so `localhost` and `127.0.0.1` are treated
  as different values.
- The same exact callback URL must be used during both the authorize request
  and the token exchange.
- Multiple redirect URIs are stored as newline-separated values on the client.

### Run the app

```bash
python3 manage.py runserver
```

Open [http://localhost:8000/](http://localhost:8000/).

### Logging

ALT-Identity logs handled requests, returned responses, and the bundled demo client's
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

### Discovery endpoint

- URL: `GET /.well-known/openid-configuration`

### JWKS endpoint

- URL: `GET /.well-known/jwks.json`

### Authorization endpoint

- URL: `GET /auth/authorize`
- Query parameters:
  - `client_id`
  - `redirect_uri`
  - `response_type=code`
  - `scope=openid profile`
  - `state`
  - `nonce`
  - `code_challenge`
  - `code_challenge_method`, supports `plain` and `S256`

Successful requests redirect to:

```text
{redirect_uri}?code={authorization_code}&state={state}
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
  "id_token": "string",
  "token_type": "Bearer",
  "expires_in": 3600,
  "scope": "openid profile"
}
```

### UserInfo endpoint

- URL: `GET /auth/userinfo`
- Header: `Authorization: Bearer {access_token}`

Success response:

```json
{
  "sub": "1",
  "preferred_username": "demo",
  "given_name": "Demo",
  "family_name": "Teacher",
  "name": "Demo Teacher",
  "learning_goal": "Explore local auth flows"
}
```

## Browser Automation Notes

The bundled demo client exposes stable ids for browser automation tools such as
Selenium:

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
