import pytest
from allauth.account.models import EmailAddress
from django.urls import reverse


@pytest.mark.django_db
class TestHomeView:
    def test_home_view_status_code(self, auth_client):
        url = reverse("home")
        response = auth_client.get(url)
        assert response.status_code == 200

    def test_home_view_uses_correct_template(self, auth_client):
        url = reverse("home")
        response = auth_client.get(url)
        assert "pages/home.html" in [t.name for t in response.templates]

    def test_home_view_context_includes_email_verified_and_api_key(self, auth_client, user):
        EmailAddress.objects.create(user=user, email=user.email, verified=False, primary=True)

        url = reverse("home")
        response = auth_client.get(url)

        assert response.context["email_verified"] is False
        assert response.context["api_key"]


@pytest.mark.django_db
class TestApiKeyRotation:
    def test_rotate_api_key_requires_verified_email(self, auth_client, user):
        EmailAddress.objects.create(user=user, email=user.email, verified=False, primary=True)

        old_key = user.profile.key
        url = reverse("rotate_api_key")
        response = auth_client.post(url, follow=True)

        user.profile.refresh_from_db()
        assert user.profile.key == old_key
        assert response.status_code == 200

    def test_rotate_api_key_rotates_key_when_verified(self, auth_client, user):
        EmailAddress.objects.create(user=user, email=user.email, verified=True, primary=True)

        old_key = user.profile.key
        url = reverse("rotate_api_key")
        response = auth_client.post(url, follow=True)

        user.profile.refresh_from_db()
        assert user.profile.key != old_key
        assert response.status_code == 200
