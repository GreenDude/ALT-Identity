# ALT-Identity API Guide for Codex

This guide is for another project that wants to use ALT-Identity as its local
authentication provider.

It is written as a practical Codex handoff: what to configure in
ALT-Identity, what contract the client app should expect, and what another
Codex thread should implement in the consuming project.

## What ALT-Identity Exposes

ALT-Identity currently acts as a lightweight OpenID Connect provider for the
authorization code flow with PKCE.

The important endpoints are:

- Discovery: `GET /.well-known/openid-configuration`
- JWKS: `GET /.well-known/jwks.json`
- Authorization: `GET /auth/authorize`
- Token: `POST /auth/token`
- UserInfo: `GET /auth/userinfo`
- Login UI: `GET /auth/login`

The current implementation issues:

- opaque `access_token`
- opaque `refresh_token`
- RS256-signed `id_token`

The current supported scopes are:

- `openid`
- `profile`

The current flow is:

1. the client redirects the browser to `/auth/authorize`
2. ALT-Identity authenticates the user
3. ALT-Identity redirects back with `code` and `state`
4. the client exchanges `code` at `/auth/token`
5. the client calls `/auth/userinfo` with the `access_token`

## Provider Setup in ALT-Identity

Another project cannot use ALT-Identity until these pieces exist locally.

### 1. Run migrations

```bash
cd /Users/cloudraccoon/PycharmProjects/ALT-Identity/identity-service
python3 manage.py migrate
```

### 2. Configure signing keys

ALT-Identity signs `id_token`s with RS256. The provider needs a private key at
runtime.

Example key generation:

```bash
openssl genpkey -algorithm RSA -out oidc-private.pem -pkeyopt rsa_keygen_bits:2048
openssl pkey -in oidc-private.pem -pubout -out oidc-public.pem
```

Example environment:

```bash
export ALT_IDENTITY_ISSUER="http://localhost:8000"
export ALT_IDENTITY_SESSION_COOKIE_NAME="alt_identity_sessionid"
export ALT_IDENTITY_OIDC_PRIVATE_KEY_PEM="$(cat oidc-private.pem)"
export ALT_IDENTITY_OIDC_PUBLIC_KEY_PEM="$(cat oidc-public.pem)"
export ALT_IDENTITY_OIDC_KEY_ID="dev-rs256-1"
```

If `ALT_IDENTITY_OIDC_PUBLIC_KEY_PEM` is omitted, ALT-Identity derives the
public key from the private key.

If the consuming app is also a Django app on `127.0.0.1`, do not let both apps
share the default `sessionid` cookie name. ALT-Identity should use
`alt_identity_sessionid`, and the consuming app should use its own distinct
value such as `alt_pm_sessionid`.

### 3. Create a user and profile

```bash
python3 manage.py createsuperuser
python3 manage.py shell
```

```python
from django.contrib.auth.models import User
from auth_server.models import UserProfile

user = User.objects.create_user(username="demo", password="demo-pass")
UserProfile.objects.create(user=user, learning_goal="Explore local auth flows")
```

### 4. Register the consuming project as a client

ALT-Identity validates `client_id`, exact `redirect_uri`, and requested
scopes. A consuming app must be registered first.

```bash
python3 manage.py shell
```

```python
from auth_server.models import Client

Client.objects.update_or_create(
    client_id="my-app",
    defaults={
        "name": "My Local App",
        "redirect_uris": "http://localhost:3000/auth/callback",
        "allowed_scopes": "openid profile",
        "is_confidential": False,
    },
)
```

Notes:

- `redirect_uris` is newline-delimited, so multiple callback URLs can be stored
  in one field.
- `redirect_uri` matching is exact.
- Public clients should use PKCE.
- The current token endpoint does not implement client-secret authentication.

### 5. Run ALT-Identity

```bash
python3 manage.py runserver
```

Provider base URL:

```text
http://localhost:8000
```

## What the Consuming Project Should Implement

Another project should treat ALT-Identity like an OIDC provider and integrate
through discovery plus the authorization code flow with PKCE.

### Required client behavior

- fetch discovery metadata from `/.well-known/openid-configuration`
- generate `state`
- generate `nonce`
- generate PKCE `code_verifier`
- derive PKCE `code_challenge` with `S256`
- redirect the browser to `/auth/authorize`
- verify returned `state`
- exchange `code` at `/auth/token`
- store at least `access_token` and `id_token`
- optionally call `/auth/userinfo`
- validate the `id_token` signature against the provider JWKS

### Discovery document example

```json
{
  "issuer": "http://localhost:8000",
  "authorization_endpoint": "http://localhost:8000/auth/authorize",
  "token_endpoint": "http://localhost:8000/auth/token",
  "userinfo_endpoint": "http://localhost:8000/auth/userinfo",
  "jwks_uri": "http://localhost:8000/.well-known/jwks.json",
  "scopes_supported": ["openid", "profile"],
  "response_types_supported": ["code"],
  "grant_types_supported": ["authorization_code"],
  "subject_types_supported": ["public"],
  "id_token_signing_alg_values_supported": ["RS256"],
  "token_endpoint_auth_methods_supported": ["none"],
  "code_challenge_methods_supported": ["plain", "S256"],
  "claims_supported": ["sub", "preferred_username", "learning_goal"]
}
```

### Authorization request contract

Send the browser to:

```text
GET /auth/authorize
```

Query parameters:

- `client_id`: registered client id, for example `my-app`
- `redirect_uri`: exact registered callback URL
- `response_type=code`
- `scope=openid profile`
- `state`: random anti-forgery value
- `nonce`: random OIDC nonce
- `code_challenge`: PKCE challenge
- `code_challenge_method=S256`

Example:

```text
http://localhost:8000/auth/authorize?client_id=my-app&redirect_uri=http%3A%2F%2Flocalhost%3A3000%2Fauth%2Fcallback&response_type=code&scope=openid%20profile&state=STATE_VALUE&nonce=NONCE_VALUE&code_challenge=PKCE_CHALLENGE&code_challenge_method=S256
```

Success callback:

```text
http://localhost:3000/auth/callback?code=AUTH_CODE&state=STATE_VALUE
```

### Token exchange contract

Send:

```text
POST /auth/token
Content-Type: application/x-www-form-urlencoded
```

Form body:

```text
grant_type=authorization_code
code=AUTH_CODE
client_id=my-app
redirect_uri=http://localhost:3000/auth/callback
code_verifier=ORIGINAL_PKCE_VERIFIER
```

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

### UserInfo contract

Send:

```text
GET /auth/userinfo
Authorization: Bearer ACCESS_TOKEN
```

Success response:

```json
{
  "sub": "1",
  "preferred_username": "demo",
  "learning_goal": "Explore local auth flows"
}
```

The current implementation always returns `sub` and `preferred_username`. It
returns `learning_goal` when the token includes the `profile` scope and the
user has a profile row.

## Codex Implementation Brief for the Consumer Project

If you want another Codex thread to wire a separate project to ALT-Identity,
give it instructions like this:

```text
Integrate this app with ALT-Identity as an OpenID Connect provider.

Provider base URL: http://localhost:8000
Discovery URL: http://localhost:8000/.well-known/openid-configuration
Client ID: my-app
Redirect URI: http://localhost:3000/auth/callback
Scopes: openid profile
Flow: authorization code with PKCE

Requirements:
- implement login redirect to the provider
- generate and persist state, nonce, and PKCE verifier
- verify state on callback
- exchange code for tokens at /auth/token
- validate id_token with the provider JWKS
- store access_token and id_token in session
- expose a logout path in the client app
- fetch /auth/userinfo after successful login
```

That prompt is enough for a Codex agent to build a standards-shaped local auth
integration in most web apps.

## Example Consumer Pseudocode

```text
on login:
  discovery = fetch(provider + "/.well-known/openid-configuration")
  state = random()
  nonce = random()
  verifier = pkce_verifier()
  challenge = pkce_s256(verifier)
  save state, nonce, verifier in session
  redirect browser to authorization_endpoint with:
    client_id
    redirect_uri
    response_type=code
    scope=openid profile
    state
    nonce
    code_challenge=challenge
    code_challenge_method=S256

on callback:
  verify callback.state == session.state
  post to token_endpoint with:
    grant_type=authorization_code
    code
    client_id
    redirect_uri
    code_verifier=session.verifier
  validate id_token against jwks_uri
  store access_token, id_token
  fetch userinfo with bearer access_token
```

## Current Constraints You Should Know

This guide should be used with the current repository behavior, not a generic
OIDC assumption.

- ALT-Identity is meant for local development and automated testing.
- Access tokens are opaque, not JWTs.
- `refresh_token` is issued, but a refresh-token grant is not implemented.
- Dynamic client registration is not implemented.
- Client-secret authentication is not implemented.
- Consent screens and advanced scope handling are not implemented.
- Exact `redirect_uri` matching means the consumer project must use the same
  callback URL during authorization and token exchange.

## Best Local Setup Pattern

For a second local project running on `localhost:3000`, the cleanest setup is:

- ALT-Identity on `http://localhost:8000`
- consuming app on `http://localhost:3000`
- registered client id `my-app`
- registered redirect URI `http://localhost:3000/auth/callback`
- scopes `openid profile`
- PKCE `S256`

That is the path this repo currently supports best.
