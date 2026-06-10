from urllib.parse import parse_qs, urlparse
from urllib.error import HTTPError
from unittest.mock import MagicMock, patch

from django.test import Client, TestCase, override_settings
from django.urls import reverse

from aot.views import _generate_pkce_challenge


@override_settings(ALLOWED_HOSTS=["127.0.0.1", "testserver"])
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

    @patch("aot.views.urlopen")
    def test_profile_forbidden_is_rendered_without_restart_flow(self, mock_urlopen: MagicMock) -> None:
        mock_urlopen.side_effect = HTTPError(
            url="http://localhost:8000/auth/profile",
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

        response = self.client.get(reverse("aot_callback"), {"code": "bad-code"})

        self.assertEqual(response.status_code, 400)
        self.assertJSONEqual(response.content, {"error": "invalid_grant"})
        self.assertEqual(self.client.session.get("pkce_code_verifier"), "verifier-123")

    @patch("aot.views.urlopen")
    def test_callback_uses_current_host_for_token_exchange(self, mock_urlopen: MagicMock) -> None:
        mock_response = MagicMock()
        mock_response.__enter__.return_value.status = 200
        mock_response.__enter__.return_value.read.return_value = (
            b'{"access_token": "abc", "refresh_token": "def"}'
        )
        mock_urlopen.return_value = mock_response

        response = self.client.get(
            reverse("aot_callback"),
            {"code": "good-code"},
            HTTP_HOST="127.0.0.1:8000",
        )

        self.assertEqual(response.status_code, 302)
        request_object = mock_urlopen.call_args[0][0]
        posted_data = parse_qs(request_object.data.decode("utf-8"))

        self.assertEqual(request_object.full_url, "http://127.0.0.1:8000/auth/token")
        self.assertEqual(posted_data["redirect_uri"], ["http://127.0.0.1:8000/callback"])
