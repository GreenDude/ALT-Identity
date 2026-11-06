"""OIDC helpers for JWT signing, discovery metadata, and JWKS publication."""

from __future__ import annotations

import base64
import json
import subprocess
import tempfile
from pathlib import Path

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured


def get_issuer() -> str:
    return settings.ALT_IDENTITY_ISSUER.rstrip("/")


def get_key_id() -> str:
    return settings.ALT_IDENTITY_OIDC_KEY_ID


def _read_private_key_pem() -> str:
    private_key = settings.ALT_IDENTITY_OIDC_PRIVATE_KEY_PEM
    if not private_key:
        raise ImproperlyConfigured("ALT_IDENTITY_OIDC_PRIVATE_KEY_PEM must be configured for OIDC id_token signing.")
    return private_key


def _run_openssl(args: list[str], input_text: str | None = None) -> bytes:
    process = subprocess.run(
        ["openssl", *args],
        input=input_text.encode("utf-8") if input_text is not None else None,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if process.returncode != 0:
        raise ImproperlyConfigured(process.stderr.decode("utf-8").strip() or "OpenSSL command failed.")
    return process.stdout


def get_public_key_pem() -> str:
    configured_public_key = settings.ALT_IDENTITY_OIDC_PUBLIC_KEY_PEM
    if configured_public_key:
        return configured_public_key

    return _run_openssl(["pkey", "-pubout"], input_text=_read_private_key_pem()).decode("utf-8")


def _write_temp_file(directory: str, name: str, contents: bytes) -> Path:
    path = Path(directory) / name
    path.write_bytes(contents)
    return path


def _b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _int_to_b64url(value: int) -> str:
    width = max(1, (value.bit_length() + 7) // 8)
    return _b64url(value.to_bytes(width, "big"))


def sign_jwt(payload: dict[str, object]) -> str:
    header = {
        "alg": "RS256",
        "kid": get_key_id(),
        "typ": "JWT",
    }
    signing_input = ".".join(
        [
            _b64url(json.dumps(header, separators=(",", ":"), sort_keys=True).encode("utf-8")),
            _b64url(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")),
        ]
    )

    with tempfile.TemporaryDirectory() as temp_dir:
        key_path = _write_temp_file(temp_dir, "oidc-private.pem", _read_private_key_pem().encode("utf-8"))
        payload_path = _write_temp_file(temp_dir, "jwt-payload.txt", signing_input.encode("ascii"))
        signature = subprocess.run(
            ["openssl", "dgst", "-sha256", "-sign", str(key_path), str(payload_path)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        if signature.returncode != 0:
            raise ImproperlyConfigured(signature.stderr.decode("utf-8").strip() or "Unable to sign JWT.")

    return f"{signing_input}.{_b64url(signature.stdout)}"


def build_jwks() -> dict[str, list[dict[str, str]]]:
    public_key_text = _run_openssl(["pkey", "-pubin", "-text", "-noout"], input_text=get_public_key_pem()).decode("utf-8")

    modulus_lines: list[str] = []
    exponent_value: int | None = None
    in_modulus = False
    for line in public_key_text.splitlines():
        stripped = line.strip()
        if stripped == "Modulus:":
            in_modulus = True
            continue
        if stripped.startswith("Exponent:"):
            exponent_value = int(stripped.split()[1])
            in_modulus = False
            continue
        if in_modulus:
            modulus_lines.append(stripped.replace(":", ""))

    if not modulus_lines or exponent_value is None:
        raise ImproperlyConfigured("Unable to parse RSA public key for JWKS publication.")

    modulus_value = int("".join(modulus_lines), 16)
    return {
        "keys": [
            {
                "kty": "RSA",
                "use": "sig",
                "alg": "RS256",
                "kid": get_key_id(),
                "n": _int_to_b64url(modulus_value),
                "e": _int_to_b64url(exponent_value),
            }
        ]
    }
