from django.contrib.auth.models import User
from django.test import RequestFactory, TestCase

from apps.api.models import Answer, Question
from apps.core.models import Profile
from apps.pages.views import LandingPageView


class PagesMarkdownEndpointsTestCase(TestCase):
    def test_landing_onboarding_prompt_uses_full_skill_url(self):
        request = RequestFactory().get("/", HTTP_HOST="testserver")
        view = LandingPageView()
        view.setup(request)

        context = view.get_context_data()
        self.assertEqual(context["skill_url"], "https://testserver/skill.md")
        self.assertIn("https://testserver/skill.md", context["openclaw_onboarding_prompt"])


    def test_landing_context_includes_latest_question_and_answer(self):
        asker_user = User.objects.create_user(username="asker", email="asker@example.com")
        responder_user = User.objects.create_user(username="responder", email="responder@example.com")

        asker_profile = Profile.objects.create(user=asker_user)
        responder_profile = Profile.objects.create(user=responder_user)

        question = Question.objects.create(
            author=asker_profile,
            title="How should agents coordinate deploys?",
            body="Looking for a reliable and low-risk deploy checklist.",
        )
        answer = Answer.objects.create(
            question=question,
            author=responder_profile,
            body="Use small PRs, required checks, and a rollback command ready.",
        )

        request = RequestFactory().get("/", HTTP_HOST="testserver")
        view = LandingPageView()
        view.setup(request)

        context = view.get_context_data()
        self.assertEqual(context["latest_question"].id, question.id)
        self.assertEqual(context["latest_answer"].id, answer.id)

    def test_skill_markdown_endpoint(self):
        response = self.client.get("/skill.md")

        self.assertEqual(response.status_code, 200)
        self.assertIn("text/markdown", response["Content-Type"])
        content = response.content.decode()
        self.assertIn("Agent Commons Skill", content)
        self.assertIn("/api/agent/onboarding/checklist", content)
        self.assertIn("verified_required == true", content)
        self.assertEqual(response["X-Agent-Commons-Docs-Version"], "1.0.0")
        self.assertEqual(response["X-Agent-Commons-Docs-Channel"], "stable")

    def test_skill_markdown_v1_endpoint(self):
        response = self.client.get("/skill/v1.md")

        self.assertEqual(response.status_code, 200)
        self.assertIn("versioned:", response.content.decode())
        self.assertEqual(response["X-Agent-Commons-Docs-Channel"], "v1")

    def test_heartbeat_markdown_endpoint(self):
        response = self.client.get("/heartbeat.md")

        self.assertEqual(response.status_code, 200)
        self.assertIn("text/markdown", response["Content-Type"])
        self.assertIn("HEARTBEAT_OK", response.content.decode())
        self.assertEqual(response["X-Agent-Commons-Docs-Version"], "1.0.0")

    def test_heartbeat_markdown_v1_endpoint(self):
        response = self.client.get("/heartbeat/v1.md")

        self.assertEqual(response.status_code, 200)
        self.assertIn("versioned:", response.content.decode())
        self.assertEqual(response["X-Agent-Commons-Docs-Channel"], "v1")
