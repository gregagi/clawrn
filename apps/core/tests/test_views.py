from pathlib import Path

import pytest
from allauth.account.models import EmailAddress
from django.contrib.auth.models import User
from django.test import RequestFactory, override_settings
from django.urls import reverse

from apps.api.models import AgentInstallation
from apps.core.context_processors import analytics_settings


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

    def test_home_view_context_includes_email_verified_without_api_key(self, auth_client, user):
        EmailAddress.objects.create(user=user, email=user.email, verified=False, primary=True)

        url = reverse("home")
        response = auth_client.get(url)

        assert response.context["email_verified"] is False
        assert "api_key" not in response.context

    def test_home_view_does_not_render_api_key_for_verified_user(self, auth_client, user):
        EmailAddress.objects.create(user=user, email=user.email, verified=True, primary=True)

        url = reverse("home")
        response = auth_client.get(url)

        content = response.content.decode("utf-8")
        assert user.profile.key not in content
        assert "api-key-value" not in content

    def test_home_view_context_includes_agent_installations(self, auth_client, user):
        installation = AgentInstallation.objects.create(
            profile=user.profile,
            agent_name="Forge",
            platform="openclaw",
        )

        url = reverse("home")
        response = auth_client.get(url)

        assert "agent_installations" in response.context
        assert installation in response.context["agent_installations"]


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


@pytest.mark.django_db
class TestLoginView:
    def test_login_allows_username_identifier(self, client, user):
        response = client.post(
            reverse("account_login"),
            {"login": user.username, "password": "password123"},
        )

        assert response.status_code == 302
        assert response.url == reverse("home")
        assert client.session.get("_auth_user_id") == str(user.id)

    def test_login_allows_email_identifier(self, client, user):
        response = client.post(
            reverse("account_login"),
            {"login": user.email, "password": "password123"},
        )

        assert response.status_code == 302
        assert response.url == reverse("home")
        assert client.session.get("_auth_user_id") == str(user.id)


class TestAnalyticsScripts:
    @override_settings(POSTHOG_KEY="phc_test_key", POSTHOG_HOST="https://eu.i.posthog.com")
    def test_analytics_context_processor_exposes_posthog_settings(self):
        request = RequestFactory().get("/")

        context = analytics_settings(request)

        assert context["posthog_key"] == "phc_test_key"
        assert context["posthog_host"] == "https://eu.i.posthog.com"

    def test_base_templates_include_posthog_snippet(self):
        templates_root = Path(__file__).resolve().parents[3] / "frontend" / "templates"
        base_landing_template = (templates_root / "base_landing.html").read_text(encoding="utf-8")
        base_app_template = (templates_root / "base_app.html").read_text(encoding="utf-8")

        for template in (base_landing_template, base_app_template):
            assert "{% if posthog_key %}" in template
            assert "posthog.init" in template
            assert "{{ posthog_host|escapejs }}" in template


@pytest.mark.django_db
class TestAgentInstallationDashboard:
    def test_create_agent_installation_succeeds_when_email_verified(self, auth_client, user):
        EmailAddress.objects.create(user=user, email=user.email, verified=True, primary=True)

        response = auth_client.post(
            reverse("create_agent_installation"),
            {
                "agent_name": "Forge",
                "platform": "openclaw",
                "agent_version": "v1",
            },
            follow=True,
        )

        assert response.status_code == 200
        installation = AgentInstallation.objects.get(
            profile=user.profile,
            agent_name="Forge",
            platform="openclaw",
        )
        assert installation.agent_version == "v1"

    def test_create_agent_installation_blocked_when_email_not_verified(self, auth_client, user):
        EmailAddress.objects.create(user=user, email=user.email, verified=False, primary=True)

        response = auth_client.post(
            reverse("create_agent_installation"),
            {"agent_name": "Forge", "platform": "openclaw"},
            follow=True,
        )

        assert response.status_code == 200
        assert not AgentInstallation.objects.filter(profile=user.profile).exists()

    def test_create_agent_installation_rejects_duplicate_name_platform_for_owner(
        self, auth_client, user
    ):
        EmailAddress.objects.create(user=user, email=user.email, verified=True, primary=True)
        AgentInstallation.objects.create(
            profile=user.profile,
            agent_name="Forge",
            platform="openclaw",
        )

        response = auth_client.post(
            reverse("create_agent_installation"),
            {"agent_name": "Forge", "platform": "openclaw"},
            follow=True,
        )

        assert response.status_code == 200
        assert (
            AgentInstallation.objects.filter(
                profile=user.profile,
                agent_name="Forge",
                platform="openclaw",
            ).count()
            == 1
        )


@pytest.mark.django_db
class TestAgentInstallationSettings:
    def test_agent_settings_shows_key_and_prompt_for_owner(self, auth_client, user):
        installation = AgentInstallation.objects.create(
            profile=user.profile,
            agent_name="Forge",
            platform="openclaw",
        )

        response = auth_client.get(
            reverse("agent_installation_settings", kwargs={"installation_id": installation.id})
        )

        assert response.status_code == 200
        assert response.context["installation"] == installation
        assert installation.api_key in response.content.decode()
        assert "/skill.md" in response.content.decode()
        assert "heartbeat" in response.content.decode().lower()

    def test_agent_settings_denies_access_for_non_owner(self, client, user):
        other_user = User.objects.create_user(
            username="otheruser",
            email="other@example.com",
            password="password123",
        )
        client.force_login(other_user)
        installation = AgentInstallation.objects.create(
            profile=user.profile,
            agent_name="Forge",
            platform="openclaw",
        )

        response = client.get(
            reverse("agent_installation_settings", kwargs={"installation_id": installation.id})
        )

        assert response.status_code == 404
