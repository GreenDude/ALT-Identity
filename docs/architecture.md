# Architecture Overview

## Purpose

ALT-Identity provides a compact local identity service that implements a
standards-shaped OpenID Connect authorization-code flow to support early integration work,
test automation, and demos.

## Main Components

### `auth_server`

The identity-provider app. It is responsible for:

- authenticating users with Django's built-in auth system
- publishing OIDC discovery metadata and JWKS
- issuing authorization codes
- storing PKCE challenges on authorization codes
- exchanging authorization codes for access, refresh, and ID tokens
- serving a protected userinfo endpoint
- logging the browser session out

### `aot`

The bundled demo client, acting as a small relying-party application. It is
responsible for:

- starting the authorization flow
- handling the callback
- exchanging the authorization code for tokens
- storing tokens in the browser session
- requesting the protected userinfo endpoint
- rendering the userinfo response as human-readable HTML

### `resource_server`

Currently a placeholder. It exists as the natural home for future protected APIs
if the project grows beyond a single profile endpoint.

## Data Model

### `Client`

Represents a registered relying party, including:

- client id
- allowed redirect URIs
- allowed scopes
- confidentiality mode

### `AuthCode`

Represents a short-lived authorization code bound to:

- a username
- a validated client id
- a redirect URI
- an OIDC state value
- an OIDC nonce value
- an issued scope string
- an expiry timestamp
- a single-use flag

### `Token`

Represents issued token material, including:

- access token
- refresh token
- token type
- user name
- client id
- issued scope
- creation timestamp

### `UserProfile`

Adds simple profile data to Django's built-in `User`. Right now the exposed demo
attribute is `learning_goal`.

## Request Flow

```mermaid
sequenceDiagram
    participant Browser
    participant AOT as AOT Client
    participant Auth as Auth Server

    Browser->>AOT: GET /profile
    AOT-->>Browser: Redirect to /auth/authorize if no token
    Browser->>Auth: GET /auth/authorize with state, nonce, and PKCE
    Auth-->>Browser: Redirect to /auth/login if not authenticated
    Browser->>Auth: POST /auth/login
    Auth-->>Browser: Redirect back to pending /auth/authorize
    Browser->>Auth: GET /auth/authorize
    Auth-->>Browser: Redirect to /callback?code=...&state=...
    Browser->>AOT: GET /callback?code=...&state=...
    AOT->>Auth: POST /auth/token with code_verifier
    Auth-->>AOT: JSON token payload
    AOT->>Auth: GET /auth/userinfo with bearer token
    Auth-->>AOT: JSON userinfo payload
    AOT-->>Browser: Render profile HTML
```

## Session Boundaries

Two different storage mechanisms are used:

- Django browser session:
  - login state for the human user
  - bundled demo client's `access_token`, `refresh_token`, `id_token`, `state`, and `nonce`
- Database models:
  - registered clients
  - issued authorization codes
  - issued tokens
  - user profile data

## Security Posture

This repository is intentionally lightweight. Its architecture is appropriate for
local development and test environments, not for production identity workloads.

Important simplifications:

- no client secret validation
- no refresh-token exchange endpoint
- no consent UI
- limited scope handling beyond `openid` and `profile`

PKCE is supported for authorization-code exchanges and is used by the bundled
demo client with the `S256` method.

## Extension Points

Teams commonly evolve this architecture by:

- separating identity-provider and resource-server concerns
- adding client registration and environment-specific configuration
- enforcing token expiry and revocation
- implementing refresh-token and introspection endpoints
- adding richer claims to `UserProfile`
- replacing local session token storage with a more formal client strategy
