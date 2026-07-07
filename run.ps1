$ErrorActionPreference = "Stop"

$privateKeyPath = Join-Path $env:TEMP "oidc-private.pem"
$publicKeyPath = Join-Path $env:TEMP "oidc-public.pem"

openssl genpkey -algorithm RSA -out $privateKeyPath -pkeyopt rsa_keygen_bits:2048
openssl pkey -in $privateKeyPath -pubout -out $publicKeyPath

$env:ALT_IDENTITY_ISSUER = "http://localhost:8900"
$env:ALT_IDENTITY_SESSION_COOKIE_NAME = "alt_identity_sessionid"
$env:ALT_IDENTITY_OIDC_PRIVATE_KEY_PEM = Get-Content -Raw $privateKeyPath
$env:ALT_IDENTITY_OIDC_PUBLIC_KEY_PEM = Get-Content -Raw $publicKeyPath
$env:ALT_IDENTITY_OIDC_KEY_ID = "dev-rs256-1"

uv run python identity-service/manage.py runserver localhost:8900
