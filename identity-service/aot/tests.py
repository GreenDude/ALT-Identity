from urllib.parse import parse_qs, urlparse
from unittest.mock import MagicMock, patch

from django.test import Client, TestCase
from django.urls import reverse

from aot.views import _generate_pkce_challenge


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
