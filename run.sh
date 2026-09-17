#!/usr/bin/env sh

set -eu

detect_lan_ip() {
    if command -v ip >/dev/null 2>&1; then
        ip route get 1.1.1.1 2>/dev/null \
            | awk '{ for (i = 1; i <= NF; i++) if ($i == "src") { print $(i + 1); exit } }'
        return
    fi

    if command -v route >/dev/null 2>&1 && command -v ipconfig >/dev/null 2>&1; then
        interface=$(route -n get default 2>/dev/null | awk '/interface:/{print $2; exit}')
        if [ -n "${interface:-}" ]; then
            ipconfig getifaddr "$interface" 2>/dev/null || true
        fi
    fi
}

ALT_IDENTITY_HOST=${ALT_IDENTITY_HOST:-$(detect_lan_ip)}

if [ -z "$ALT_IDENTITY_HOST" ]; then
    echo "Unable to detect a LAN IPv4 address." >&2
    echo "Set ALT_IDENTITY_HOST explicitly, for example:" >&2
    echo "  ALT_IDENTITY_HOST=192.168.100.54 ./run.sh" >&2
    exit 1
fi

openssl genpkey -algorithm RSA -out /tmp/oidc-private.pem -pkeyopt rsa_keygen_bits:2048
openssl pkey -in /tmp/oidc-private.pem -pubout -out /tmp/oidc-public.pem

export ALT_IDENTITY_ISSUER=${ALT_IDENTITY_ISSUER:-"http://$ALT_IDENTITY_HOST:8900"}
export ALT_IDENTITY_ALLOWED_HOSTS=${ALT_IDENTITY_ALLOWED_HOSTS:-"$ALT_IDENTITY_HOST,localhost,127.0.0.1"}
export ALT_IDENTITY_SESSION_COOKIE_NAME="alt_identity_sessionid"
export ALT_IDENTITY_OIDC_PRIVATE_KEY_PEM="$(cat /tmp/oidc-private.pem)"
export ALT_IDENTITY_OIDC_PUBLIC_KEY_PEM="$(cat /tmp/oidc-public.pem)"
export ALT_IDENTITY_OIDC_KEY_ID="dev-rs256-1"

echo "Starting ALT-Identity at $ALT_IDENTITY_ISSUER"
uv run ~/infra/ALT-Identity/identity-service/manage.py runserver 0.0.0.0:8900


