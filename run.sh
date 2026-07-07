openssl genpkey -algorithm RSA -out /tmp/oidc-private.pem -pkeyopt rsa_keygen_bits:2048
openssl pkey -in /tmp/oidc-private.pem -pubout -out /tmp/oidc-public.pem

export ALT_IDENTITY_ISSUER="http://localhost:8900"
export ALT_IDENTITY_SESSION_COOKIE_NAME="alt_identity_sessionid"
export ALT_IDENTITY_OIDC_PRIVATE_KEY_PEM="$(cat /tmp/oidc-private.pem)"
export ALT_IDENTITY_OIDC_PUBLIC_KEY_PEM="$(cat /tmp/oidc-public.pem)"
export ALT_IDENTITY_OIDC_KEY_ID="dev-rs256-1"

uv run identity-service/manage.py runserver localhost:8900
