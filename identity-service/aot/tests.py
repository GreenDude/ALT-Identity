from unittest.mock import MagicMock, patch

from django.test import Client, TestCase
from django.urls import reverse


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
