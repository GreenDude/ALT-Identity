# Integration Guide

## When To Use ALT-Identity

ALT-Identity is a good fit when your application needs to integrate with an
identity provider during the early stages of development, but you do not yet
want the cost or complexity of wiring a full external IdP into every local and
CI workflow.

## Core Integration Contract

Your client application needs to support the OpenID Connect authorization-code pattern:

1. redirect users to the authorization endpoint
2. receive an authorization code on a callback URL
3. exchange the code for tokens
4. call protected endpoints with the access token

## Default Demo Configuration

The bundled demo client uses these values:

- `client_id`: `awesome-service`
- `redirect_uri`: `http://localhost:8000/callback`
- `scope`: `openid profile`
- `code_challenge_method`: `S256`

If you are integrating another local application, keep your callback handling
compatible with the server's current expectations.

## Endpoint Reference

### `GET /.well-known/openid-configuration`

Publishes the OpenID Connect discovery metadata.

### `GET /.well-known/jwks.json`

Publishes the RSA public signing key for `id_token` verification.

### `GET /auth/authorize`

Starts the authorization-code flow.

Query parameters:

- `client_id`: identifier for the client application
- `redirect_uri`: where the auth code should be returned
- `response_type`: must be `code`
- `scope`: should include `openid`, and may include `profile`
- `state`: required anti-forgery value echoed on the callback
- `nonce`: required value that will be bound into the resulting `id_token`
- `code_challenge`: PKCE code challenge for the request
- `code_challenge_method`: `plain` or `S256`

Behavior:

- if the browser is not logged in, the user is redirected to `/auth/login`
- if the browser is logged in and the request is valid, the server redirects to
  the callback URL with `?code=...`

### `POST /auth/token`

Exchanges a code for token data.

Form payload:

```text
grant_type=authorization_code
code=<authorization_code>
client_id=<client_id>
redirect_uri=<redirect_uri>
code_verifier=<original_verifier>
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

Failure response:

```json
{
  "error": "invalid_grant"
}
```

### `GET /auth/userinfo`

Returns a basic profile document.

Required header:

```text
Authorization: Bearer <access_token>
```

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

Common error responses:

```json
{"error": "missing_authorization_header"}
{"error": "invalid_authorization_header"}
{"error": "invalid_token"}
{"error": "user_not_found"}
{"error": "profile_not_found"}
```

## Example Client Flow

### Step 1: Redirect to authorize

```text
http://localhost:8000/auth/authorize?client_id=my-client&redirect_uri=http://localhost:3000/callback&response_type=code&scope=openid%20profile&state=STATE_VALUE&nonce=NONCE_VALUE&code_challenge=PKCE_CHALLENGE&code_challenge_method=S256
```

### Step 2: Receive callback

Your application should read the `code` query parameter from the callback URL.

### Step 3: Exchange the code

Example using `curl`:

```bash
curl -X POST http://localhost:8000/auth/token \
  -d "grant_type=authorization_code" \
  -d "code=AUTH_CODE_HERE" \
  -d "client_id=my-client" \
  -d "redirect_uri=http://localhost:3000/callback" \
  -d "code_verifier=ORIGINAL_PKCE_VERIFIER"
```

### Step 4: Call the userinfo endpoint

```bash
curl http://localhost:8000/auth/userinfo \
  -H "Authorization: Bearer ACCESS_TOKEN_HERE"
```

## Browser Automation Testing

The bundled demo client login page is instrumented for browser automation,
including Selenium, with stable ids:

- `username-field`
- `password-field`
- `login-button`

The rendered demo profile page exposes:

- `logout-button`
- `profile-json`

That means a simple browser test can assert both login behavior and the final
profile payload without brittle CSS selectors.

## Integration Checklist

- Create at least one Django `User`.
- Create a matching `UserProfile`.
- Ensure your `redirect_uri` is the same value used in the code exchange.
- Ensure the same PKCE verifier is retained from authorization through token exchange.
- Persist the access token on the client side for subsequent API calls.
- Handle `401` responses by restarting the authorization flow.

## Recommended Next Improvements

If you plan to integrate this more deeply into another project, these upgrades
will usually pay off first:

- add a client model and validate registered redirect URIs
- enforce token lifetime on protected endpoints
- add a refresh-token grant endpoint
- move API resources into `resource_server`
- add structured configuration through environment variables
