import base64
import datetime
import json
import subprocess
import tempfile
from pathlib import Path

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from auth_server.models import AuthCode, Client, Token, UserProfile
from auth_server.views import _create_pkce_challenge


def _generate_test_key_pair() -> tuple[str, str]:
    with tempfile.TemporaryDirectory() as temp_dir:
        private_key_path = Path(temp_dir) / "private.pem"
        public_key_path = Path(temp_dir) / "public.pem"
        subprocess.run(
            ["openssl", "genpkey", "-algorithm", "RSA", "-out", str(private_key_path), "-pkeyopt", "rsa_keygen_bits:2048"],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        subprocess.run(
            ["openssl", "pkey", "-in", str(private_key_path), "-pubout", "-out", str(public_key_path)],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        return private_key_path.read_text(), public_key_path.read_text()


TEST_PRIVATE_KEY_PEM, TEST_PUBLIC_KEY_PEM = _generate_test_key_pair()


def _decode_jwt(token: str) -> tuple[dict, dict, bytes]:
    header_b64, payload_b64, signature_b64 = token.split(".")

    def decode(segment: str) -> bytes:
        padding = "=" * (-len(segment) % 4)
        return base64.urlsafe_b64decode(f"{segment}{padding}")

    header = json.loads(decode(header_b64))
    payload = json.loads(decode(payload_b64))
    signature = decode(signature_b64)
    return header, payload, signature


def _verify_jwt_signature(token: str, public_key_pem: str) -> bool:
    signing_input = ".".join(token.split(".")[:2]).encode("ascii")
    signature = _decode_jwt(token)[2]
    with tempfile.TemporaryDirectory() as temp_dir:
        public_key_path = Path(temp_dir) / "public.pem"
        payload_path = Path(temp_dir) / "payload.txt"
        signature_path = Path(temp_dir) / "signature.bin"
        public_key_path.write_text(public_key_pem)
        payload_path.write_bytes(signing_input)
        signature_path.write_bytes(signature)
        result = subprocess.run(
            ["openssl", "dgst", "-sha256", "-verify", str(public_key_path), "-signature", str(signature_path), str(payload_path)],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        return result.returncode == 0


@override_settings(
    ALT_IDENTITY_ISSUER="http://localhost:8000",
    ALT_IDENTITY_OIDC_PRIVATE_KEY_PEM=TEST_PRIVATE_KEY_PEM,
    ALT_IDENTITY_OIDC_PUBLIC_KEY_PEM=TEST_PUBLIC_KEY_PEM,
    ALT_IDENTITY_OIDC_KEY_ID="test-rs256-1",
)
class LoginTemplateTests(TestCase):
    def setUp(self) -> None:
        Client.objects.update_or_create(
            client_id="test-client",
            defaults={
                "name": "Test Client",
                "redirect_uris": "http://localhost:3000/callback",
                "allowed_scopes": "openid profile",
            },
        )

    def test_login_page_contains_stable_automation_ids(self) -> None:
        response = self.client.get(reverse("login"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="username-field"', html=False)
        self.assertContains(response, 'id="password-field"', html=False)
        self.assertContains(response, 'id="login-button"', html=False)


@override_settings(
    ALT_IDENTITY_ISSUER="http://localhost:8000",
    ALT_IDENTITY_OIDC_PRIVATE_KEY_PEM=TEST_PRIVATE_KEY_PEM,
    ALT_IDENTITY_OIDC_PUBLIC_KEY_PEM=TEST_PUBLIC_KEY_PEM,
    ALT_IDENTITY_OIDC_KEY_ID="test-rs256-1",
)
class OidcFlowTests(TestCase):
    def setUp(self) -> None:
        self.user = User.objects.create_user(
            username="demo",
            password="secret123",
            first_name="Demo",
            last_name="Teacher",
        )
        UserProfile.objects.create(user=self.user, learning_goal="Explore local auth flows")
        self.client_record = Client.objects.create(
            client_id="test-client",
            name="Test Client",
            redirect_uris="http://localhost:3000/callback",
            allowed_scopes="openid profile",
        )

    def _authorize_params(self, **overrides):
        params = {
            "client_id": self.client_record.client_id,
            "redirect_uri": "http://localhost:3000/callback",
            "response_type": "code",
            "scope": "openid profile",
            "state": "state-123",
            "nonce": "nonce-123",
            "code_challenge": "challenge-value",
            "code_challenge_method": "S256",
        }
        params.update(overrides)
        return params

    def test_authorize_stores_state_nonce_and_pkce_challenge(self) -> None:
        self.client.force_login(self.user)

        response = self.client.get(reverse("authorize"), self._authorize_params())

        self.assertEqual(response.status_code, 302)
        self.assertIn("state=state-123", response["Location"])
        auth_code = AuthCode.objects.get(client_id="test-client")
        self.assertEqual(auth_code.code_challenge, "challenge-value")
        self.assertEqual(auth_code.code_challenge_method, "S256")
        self.assertEqual(auth_code.state, "state-123")
        self.assertEqual(auth_code.nonce, "nonce-123")

    def test_authorize_rejects_unknown_client(self) -> None:
        self.client.force_login(self.user)

        response = self.client.get(reverse("authorize"), self._authorize_params(client_id="missing-client"))

        self.assertEqual(response.status_code, 400)
        self.assertJSONEqual(response.content, {"error": "invalid_client", "error_description": "Unknown client_id."})

    def test_authorize_rejects_unregistered_redirect_uri(self) -> None:
        self.client.force_login(self.user)

        response = self.client.get(reverse("authorize"), self._authorize_params(redirect_uri="http://localhost:9999/callback"))

        self.assertEqual(response.status_code, 400)
        self.assertJSONEqual(response.content, {"error": "invalid_request", "error_description": "Unregistered redirect_uri."})

    def test_authorize_rejects_missing_state(self) -> None:
        self.client.force_login(self.user)

        response = self.client.get(reverse("authorize"), self._authorize_params(state=""))

        self.assertEqual(response.status_code, 302)
        self.assertIn("error=invalid_request", response["Location"])

    def test_authorize_rejects_missing_nonce_for_openid(self) -> None:
        self.client.force_login(self.user)

        response = self.client.get(reverse("authorize"), self._authorize_params(nonce=""))

        self.assertEqual(response.status_code, 302)
        self.assertIn("error=invalid_request", response["Location"])

    def test_authorize_rejects_unsupported_response_type(self) -> None:
        self.client.force_login(self.user)

        response = self.client.get(reverse("authorize"), self._authorize_params(response_type="token"))

        self.assertEqual(response.status_code, 302)
        self.assertIn("error=unsupported_response_type", response["Location"])

    def test_token_requires_matching_pkce_verifier(self) -> None:
        verifier = "verifier-123"
        AuthCode.objects.create(
            auth_code="abc123",
            user_name="demo",
            client_id="test-client",
            redirect_uri="http://localhost:3000/callback",
            scope="openid profile",
            state="state-123",
            nonce="nonce-123",
            expiry=timezone.now() + datetime.timedelta(days=1),
            code_challenge=_create_pkce_challenge(verifier, "S256"),
            code_challenge_method="S256",
        )

        response = self.client.post(
            reverse("token"),
            {
                "grant_type": "authorization_code",
                "code": "abc123",
                "client_id": "test-client",
                "redirect_uri": "http://localhost:3000/callback",
                "code_verifier": "wrong-verifier",
            },
        )

        self.assertEqual(response.status_code, 400)
        self.assertJSONEqual(response.content, {"error": "invalid_grant"})

    def test_token_returns_id_token_with_expected_claims(self) -> None:
        verifier = "verifier-123"
        AuthCode.objects.create(
            auth_code="def456",
            user_name="demo",
            client_id="test-client",
            redirect_uri="http://localhost:3000/callback",
            scope="openid profile",
            state="state-123",
            nonce="nonce-123",
            expiry=timezone.now() + datetime.timedelta(days=1),
            code_challenge=_create_pkce_challenge(verifier, "S256"),
            code_challenge_method="S256",
        )

        response = self.client.post(
            reverse("token"),
            {
                "grant_type": "authorization_code",
                "code": "def456",
                "client_id": "test-client",
                "redirect_uri": "http://localhost:3000/callback",
                "code_verifier": verifier,
            },
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertIn("access_token", body)
        self.assertIn("refresh_token", body)
        self.assertIn("id_token", body)
        self.assertEqual(body["scope"], "openid profile")

        header, payload, _ = _decode_jwt(body["id_token"])
        self.assertEqual(header["alg"], "RS256")
        self.assertEqual(header["kid"], "test-rs256-1")
        self.assertEqual(payload["iss"], "http://localhost:8000")
        self.assertEqual(payload["aud"], "test-client")
        self.assertEqual(payload["nonce"], "nonce-123")
        self.assertEqual(payload["sub"], str(self.user.pk))
        self.assertIn("iat", payload)
        self.assertIn("exp", payload)
        self.assertTrue(_verify_jwt_signature(body["id_token"], TEST_PUBLIC_KEY_PEM))

    def test_token_rejects_reused_code(self) -> None:
        verifier = "verifier-123"
        AuthCode.objects.create(
            auth_code="ghi789",
            user_name="demo",
            client_id="test-client",
            redirect_uri="http://localhost:3000/callback",
            scope="openid profile",
            state="state-123",
            nonce="nonce-123",
            expiry=timezone.now() + datetime.timedelta(days=1),
            used=True,
            code_challenge=_create_pkce_challenge(verifier, "S256"),
            code_challenge_method="S256",
        )

        response = self.client.post(
            reverse("token"),
            {
                "grant_type": "authorization_code",
                "code": "ghi789",
                "client_id": "test-client",
                "redirect_uri": "http://localhost:3000/callback",
                "code_verifier": verifier,
            },
        )

        self.assertEqual(response.status_code, 400)
        self.assertJSONEqual(response.content, {"error": "invalid_grant"})

    def test_token_rejects_expired_code(self) -> None:
        verifier = "verifier-123"
        AuthCode.objects.create(
            auth_code="xyz123",
            user_name="demo",
            client_id="test-client",
            redirect_uri="http://localhost:3000/callback",
            scope="openid profile",
            state="state-123",
            nonce="nonce-123",
            expiry=timezone.now() - datetime.timedelta(minutes=1),
            code_challenge=_create_pkce_challenge(verifier, "S256"),
            code_challenge_method="S256",
        )

        response = self.client.post(
            reverse("token"),
            {
                "grant_type": "authorization_code",
                "code": "xyz123",
                "client_id": "test-client",
                "redirect_uri": "http://localhost:3000/callback",
                "code_verifier": verifier,
            },
        )

        self.assertEqual(response.status_code, 400)
        self.assertJSONEqual(response.content, {"error": "invalid_grant"})

    def test_openid_configuration_exposes_expected_metadata(self) -> None:
        response = self.client.get(reverse("openid_configuration"))

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["issuer"], "http://localhost:8000")
        self.assertEqual(body["authorization_endpoint"], "http://localhost:8000/auth/authorize")
        self.assertEqual(body["token_endpoint"], "http://localhost:8000/auth/token")
        self.assertEqual(body["userinfo_endpoint"], "http://localhost:8000/auth/userinfo")
        self.assertEqual(body["jwks_uri"], "http://localhost:8000/.well-known/jwks.json")
        self.assertEqual(body["scopes_supported"], ["openid", "profile"])
        self.assertEqual(body["response_types_supported"], ["code"])
        self.assertEqual(body["grant_types_supported"], ["authorization_code"])
        self.assertEqual(body["subject_types_supported"], ["public"])
        self.assertEqual(body["id_token_signing_alg_values_supported"], ["RS256"])
        self.assertEqual(body["code_challenge_methods_supported"], ["plain", "S256"])
        self.assertEqual(
            body["claims_supported"],
            ["sub", "preferred_username", "name", "given_name", "family_name", "learning_goal"],
        )

    def test_jwks_exposes_public_signing_key(self) -> None:
        response = self.client.get(reverse("jwks"))

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(len(body["keys"]), 1)
        self.assertEqual(body["keys"][0]["kid"], "test-rs256-1")
        self.assertEqual(body["keys"][0]["alg"], "RS256")
        self.assertEqual(body["keys"][0]["kty"], "RSA")

    def test_userinfo_returns_scope_gated_claims(self) -> None:
        token = Token.objects.create(
            access_token="access-123",
            refresh_token="refresh-123",
            token_type="Bearer",
            user_name="demo",
            client_id="test-client",
            expires_in=3600,
            scope="openid profile",
        )

        response = self.client.get(
            reverse("userinfo"),
            HTTP_AUTHORIZATION=f"Bearer {token.access_token}",
        )

        self.assertEqual(response.status_code, 200)
        self.assertJSONEqual(
            response.content,
            {
                "sub": str(self.user.pk),
                "preferred_username": "demo",
                "given_name": "Demo",
                "family_name": "Teacher",
                "name": "Demo Teacher",
                "learning_goal": "Explore local auth flows",
            },
        )

    def test_userinfo_does_not_return_profile_claims_without_profile_scope(self) -> None:
        token = Token.objects.create(
            access_token="access-456",
            refresh_token="refresh-456",
            token_type="Bearer",
            user_name="demo",
            client_id="test-client",
            expires_in=3600,
            scope="openid",
        )

        response = self.client.get(
            reverse("userinfo"),
            HTTP_AUTHORIZATION=f"Bearer {token.access_token}",
        )

        self.assertEqual(response.status_code, 200)
        self.assertJSONEqual(
            response.content,
            {
                "sub": str(self.user.pk),
                "preferred_username": "demo",
            },
        )

    def test_demo_profile_flow_redirects_into_oidc_authorize_request(self) -> None:
        response = self.client.get(reverse("aot_request_profile"))

        self.assertEqual(response.status_code, 302)
        self.assertIn("/auth/authorize?", response["Location"])
        self.assertIn("scope=openid+profile", response["Location"])
        self.assertIn("state=", response["Location"])
        self.assertIn("nonce=", response["Location"])
