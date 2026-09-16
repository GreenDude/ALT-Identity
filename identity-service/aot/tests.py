import json
from urllib.parse import parse_qs, urlparse
from urllib.error import HTTPError
from unittest.mock import MagicMock, patch

from django.test import Client, TestCase, override_settings
from django.urls import reverse

from auth_server.models import Client as OidcClient
from aot.views import _generate_pkce_challenge


@override_settings(ALLOWED_HOSTS=["127.0.0.1", "192.168.100.88", "testserver"])
class AotRequestProfileViewTests(TestCase):
    def setUp(self) -> None:
        self.client = Client()
        session = self.client.session
        session["access_token"] = "test-access-token"
        session.save()

    @patch("aot.views.urlopen")
    def test_profile_response_is_rendered_as_html(self, mock_urlopen: MagicMock) -> None:
        mock_response = MagicMock()
        mock_response.__enter__.return_value.status = 200
        mock_response.__enter__.return_value.read.return_value = (
            b'{"user_name": "alice", "learning_goal": "Automate tests"}'
        )
        mock_urlopen.return_value = mock_response

        response = self.client.get(reverse("aot_request_profile"))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "aot/profile.html")
        self.assertContains(response, "Profile Response")
        self.assertContains(response, "alice")
        self.assertContains(response, "Automate tests")
        self.assertContains(response, 'id="profile-json"', html=False)
        self.assertContains(response, 'id="logout-button"', html=False)

    def test_missing_access_token_redirects_to_authorize_with_pkce(self) -> None:
        client = Client()

        response = client.get(reverse("aot_request_profile"))

        self.assertEqual(response.status_code, 302)
        parsed = urlparse(response["Location"])
        query = parse_qs(parsed.query)
        verifier = client.session["pkce_code_verifier"]

        self.assertEqual(parsed.path, "/auth/authorize")
        self.assertEqual(query["scope"], ["openid profile"])
        self.assertIn("state", query)
        self.assertIn("nonce", query)
        self.assertEqual(query["code_challenge_method"], ["S256"])
        self.assertEqual(
            query["code_challenge"],
            [_generate_pkce_challenge(verifier)],
        )

    def test_missing_access_token_keeps_current_host_in_authorize_flow(self) -> None:
        client = Client()

        response = client.get(
            reverse("aot_request_profile"),
            HTTP_HOST="127.0.0.1:8000",
        )

        parsed = urlparse(response["Location"])
        query = parse_qs(parsed.query)

        self.assertEqual(parsed.netloc, "127.0.0.1:8000")
        self.assertEqual(query["redirect_uri"], ["http://127.0.0.1:8000/callback"])

    def test_missing_access_token_registers_current_demo_callback_uri(self) -> None:
        client = Client()
        OidcClient.objects.update_or_create(
            client_id="awesome-service",
            defaults={
                "name": "Bundled Demo Client",
                "redirect_uris": "http://localhost:8000/callback",
                "allowed_scopes": "openid profile",
                "is_confidential": False,
            },
        )

        response = client.get(
            reverse("aot_request_profile"),
            HTTP_HOST="192.168.100.88:8900",
        )

        parsed = urlparse(response["Location"])
        query = parse_qs(parsed.query)
        registered_client = OidcClient.objects.get(client_id="awesome-service")

        self.assertEqual(response.status_code, 302)
        self.assertEqual(parsed.netloc, "192.168.100.88:8900")
        self.assertEqual(query["redirect_uri"], ["http://192.168.100.88:8900/callback"])
        self.assertIn("http://localhost:8000/callback", registered_client.registered_redirect_uris())
        self.assertIn("http://192.168.100.88:8900/callback", registered_client.registered_redirect_uris())

    def test_missing_access_token_creates_demo_client_when_absent(self) -> None:
        client = Client()
        OidcClient.objects.filter(client_id="awesome-service").delete()

        response = client.get(
            reverse("aot_request_profile"),
            HTTP_HOST="192.168.100.88:8900",
        )

        registered_client = OidcClient.objects.get(client_id="awesome-service")

        self.assertEqual(response.status_code, 302)
        self.assertEqual(registered_client.allowed_scopes, "openid profile")
        self.assertEqual(registered_client.redirect_uris, "http://192.168.100.88:8900/callback")

    @patch("aot.views.urlopen")
    def test_profile_forbidden_is_rendered_without_restart_flow(self, mock_urlopen: MagicMock) -> None:
        mock_urlopen.side_effect = HTTPError(
            url="http://localhost:8000/auth/userinfo",
            code=403,
            msg="Forbidden",
            hdrs=None,
            fp=MagicMock(read=MagicMock(return_value=b'{"error": "forbidden"}')),
        )

        response = self.client.get(reverse("aot_request_profile"))

        self.assertEqual(response.status_code, 403)
        self.assertTemplateUsed(response, "aot/profile.html")
        self.assertContains(response, "forbidden", status_code=403)
        self.assertEqual(self.client.session.get("access_token"), "test-access-token")


@override_settings(ALLOWED_HOSTS=["127.0.0.1", "testserver"])
class AotCallbackTests(TestCase):
    def setUp(self) -> None:
        self.client = Client()
        session = self.client.session
        session["pkce_code_verifier"] = "verifier-123"
        session["oidc_state"] = "state-123"
        session.save()

    @patch("aot.views.urlopen")
    def test_token_exchange_failure_returns_error_json(self, mock_urlopen: MagicMock) -> None:
        mock_urlopen.side_effect = HTTPError(
            url="http://localhost:8000/auth/token",
            code=400,
            msg="Bad Request",
            hdrs=None,
            fp=MagicMock(read=MagicMock(return_value=b'{"error": "invalid_grant"}')),
        )

        response = self.client.get(reverse("aot_callback"), {"code": "bad-code", "state": "state-123"})

        self.assertEqual(response.status_code, 400)
        self.assertJSONEqual(response.content, {"error": "invalid_grant"})
        self.assertEqual(self.client.session.get("pkce_code_verifier"), "verifier-123")

    @patch("aot.views.urlopen")
    def test_callback_uses_current_host_for_token_exchange(self, mock_urlopen: MagicMock) -> None:
        mock_response = MagicMock()
        mock_response.__enter__.return_value.status = 200
        mock_response.__enter__.return_value.read.return_value = (
            b'{"access_token": "abc", "refresh_token": "def", "id_token": "ghi"}'
        )
        mock_urlopen.return_value = mock_response

        response = self.client.get(
            reverse("aot_callback"),
            {"code": "good-code", "state": "state-123"},
            HTTP_HOST="127.0.0.1:8000",
        )

        self.assertEqual(response.status_code, 302)
        request_object = mock_urlopen.call_args[0][0]
        posted_data = parse_qs(request_object.data.decode("utf-8"))

        self.assertEqual(request_object.full_url, "http://127.0.0.1:8000/auth/token")
        self.assertEqual(posted_data["redirect_uri"], ["http://127.0.0.1:8000/callback"])
        self.assertEqual(self.client.session.get("id_token"), "ghi")

    def test_invalid_state_logs_callback_debug_context(self) -> None:
        with self.assertLogs("alt_identity.http", level="WARNING") as logs:
            response = self.client.get(
                reverse("aot_callback"),
                {"code": "good-code", "state": "wrong-state"},
            )

        self.assertEqual(response.status_code, 400)
        self.assertIn("Invalid OIDC state on callback", logs.output[0])

        payload = json.loads(logs.output[0].split("Invalid OIDC state on callback: ", 1)[1])
        self.assertEqual(payload["kind"], "oidc_state_verification_failed")
        self.assertEqual(payload["returned_state"], "wrong-state")
        self.assertEqual(payload["expected_state"], "state-123")
        self.assertTrue(payload["auth_code_present"])
        self.assertTrue(payload["session_has_pkce_verifier"])
        self.assertTrue(payload["session_cookie_present"])
