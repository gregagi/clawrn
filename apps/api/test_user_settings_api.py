from django.contrib.auth.models import User
from django.test import TestCase

from apps.core.choices import ProfileStates


class UserSettingsApiTestCase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="settings-user",
            email="settings@example.com",
            password="pass123",
        )
        self.client.force_login(self.user)

    def test_user_settings_returns_false_when_user_has_no_active_subscription(self):
        response = self.client.get("/api/user/settings")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {"profile": {"has_pro_subscription": False}},
        )

    def test_user_settings_returns_true_when_user_is_subscribed(self):
        profile = self.user.profile
        profile.state = ProfileStates.SUBSCRIBED
        profile.save(update_fields=["state", "updated_at"])

        response = self.client.get("/api/user/settings")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {"profile": {"has_pro_subscription": True}},
        )
