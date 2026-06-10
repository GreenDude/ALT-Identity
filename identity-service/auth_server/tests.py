from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from auth_server.models import AuthCode
from auth_server.views import _create_pkce_challenge


class LoginTemplateTests(TestCase):
    def test_login_page_contains_stable_automation_ids(self) -> None:
        response = self.client.get(reverse("login"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="username-field"', html=False)
        self.assertContains(response, 'id="password-field"', html=False)
        self.assertContains(response, 'id="login-button"', html=False)


class PkceFlowTests(TestCase):
    def test_authorize_stores_pkce_challenge(self) -> None:
        user = User.objects.create_user(username="demo", password="secret123")
        self.client.force_login(user)

        response = self.client.get(
            reverse("authorize"),
            {
                "client_id": "test-client",
                "redirect_uri": "http://localhost:3000/callback",
                "response_type": "code",
                "scope": "profile.read",
                "code_challenge": "challenge-value",
                "code_challenge_method": "S256",
            },
        )

        self.assertEqual(response.status_code, 302)
        auth_code = AuthCode.objects.get(client_id="test-client")
        self.assertEqual(auth_code.code_challenge, "challenge-value")
        self.assertEqual(auth_code.code_challenge_method, "S256")

    def test_token_requires_matching_pkce_verifier(self) -> None:
        verifier = "verifier-123"
        AuthCode.objects.create(
            auth_code="abc123",
            user_name="demo",
            client_id="test-client",
            redirect_uri="http://localhost:3000/callback",
            scope="profile.read",
            expiry="2099-01-01T00:00:00Z",
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

    def test_token_accepts_matching_pkce_verifier(self) -> None:
        verifier = "verifier-123"
        AuthCode.objects.create(
            auth_code="def456",
            user_name="demo",
            client_id="test-client",
            redirect_uri="http://localhost:3000/callback",
            scope="profile.read",
            expiry="2099-01-01T00:00:00Z",
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
        self.assertIn("access_token", response.json())
