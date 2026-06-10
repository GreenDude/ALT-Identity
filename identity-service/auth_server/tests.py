from django.test import TestCase
from django.urls import reverse


class LoginTemplateTests(TestCase):
    def test_login_page_contains_stable_automation_ids(self) -> None:
        response = self.client.get(reverse("login"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="username-field"', html=False)
        self.assertContains(response, 'id="password-field"', html=False)
        self.assertContains(response, 'id="login-button"', html=False)
