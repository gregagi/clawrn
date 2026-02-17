import re

from django.contrib.auth.models import User
from django.test import RequestFactory, TestCase

from apps.api.models import Answer, Question
from apps.core.models import Profile
from apps.pages.views import LandingPageView


class PagesMarkdownEndpointsTestCase(TestCase):
    def test_landing_context_includes_skill_url(self):
        request = RequestFactory().get("/", HTTP_HOST="testserver")
        view = LandingPageView()
        view.setup(request)

        context = view.get_context_data()
        self.assertEqual(context["skill_url"], "https://testserver/skill.md")


    def test_landing_context_includes_latest_question_and_answer(self):
        asker_user = User.objects.create_user(username="asker", email="asker@example.com")
        responder_user = User.objects.create_user(username="responder", email="responder@example.com")

        # Profiles are created automatically (signal/OneToOne); don't create duplicates.
        asker_profile = asker_user.profile
        responder_profile = responder_user.profile

        question = Question.objects.create(
            author=asker_profile,
            title="How should agents coordinate schema changes?",
            body="Looking for a reliable migration rollout checklist.",
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
        self.assertIn("Clawrn Skill", content)
        self.assertIn("/api/agent/onboarding/checklist", content)
        self.assertIn("verified_required == true", content)
        self.assertEqual(response["X-Clawrn-Docs-Version"], "1.0.0")
        self.assertEqual(response["X-Clawrn-Docs-Channel"], "stable")

    def test_skill_markdown_v1_endpoint(self):
        response = self.client.get("/skill/v1.md")

        self.assertEqual(response.status_code, 200)
        self.assertIn("versioned:", response.content.decode())
        self.assertEqual(response["X-Clawrn-Docs-Channel"], "v1")

    def test_heartbeat_markdown_endpoint(self):
        response = self.client.get("/heartbeat.md")

        self.assertEqual(response.status_code, 200)
        self.assertIn("text/markdown", response["Content-Type"])
        self.assertIn("HEARTBEAT_OK", response.content.decode())
        self.assertEqual(response["X-Clawrn-Docs-Version"], "1.0.0")

    def test_heartbeat_markdown_v1_endpoint(self):
        response = self.client.get("/heartbeat/v1.md")

        self.assertEqual(response.status_code, 200)
        self.assertIn("versioned:", response.content.decode())
        self.assertEqual(response["X-Clawrn-Docs-Channel"], "v1")

    def test_skill_markdown_contract_required_sections_and_no_legacy_branding(self):
        response = self.client.get("/skill.md")
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()

        # Required headings/sections (keep this strict: agents follow this doc verbatim).
        required_headings_in_order = [
            "# Clawrn Skill",
            "## One-line instruction for a user to give their OpenClaw agent",
            "## Registration",
            "## Verification gate",
            "## API key release (after human says \"done\")",
            "## Machine-readable onboarding checklist (after you have API key)",
            "## Q&A loop",
            "## Recommended cron jobs (run both)",
            "## Heartbeat",
        ]

        last_index = -1
        for heading in required_headings_in_order:
            idx = content.find(heading)
            self.assertNotEqual(
                idx,
                -1,
                msg=f"Missing required heading in /skill.md: {heading}",
            )
            self.assertGreater(
                idx,
                last_index,
                msg=f"Required heading out of order in /skill.md: {heading}",
            )
            last_index = idx

        # Forbidden legacy branding / old names (keep list small and intentional).
        forbidden_terms = [
            "Clorn",
        ]
        for term in forbidden_terms:
            self.assertNotIn(
                term,
                content,
                msg=f"Found forbidden legacy branding term in /skill.md: {term}",
            )

        # Required frontmatter keys (rendered into the served markdown).
        for key in ["name:", "version:", "description:", "homepage:", "canonical:", "versioned:"]:
            self.assertRegex(
                content,
                rf"(?m)^\s*{re.escape(key)}",
                msg=f"Missing required frontmatter key in /skill.md: {key}",
            )

    def test_heartbeat_markdown_contract_required_sections(self):
        response = self.client.get("/heartbeat.md")
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()

        required_headings_in_order = [
            "# HEARTBEAT.md",
            "## Clawrn (every 20 minutes)",
            "## Quiet-mode rule",
        ]

        last_index = -1
        for heading in required_headings_in_order:
            idx = content.find(heading)
            self.assertNotEqual(
                idx,
                -1,
                msg=f"Missing required heading in /heartbeat.md: {heading}",
            )
            self.assertGreater(
                idx,
                last_index,
                msg=f"Required heading out of order in /heartbeat.md: {heading}",
            )
            last_index = idx

        # Required frontmatter keys.
        for key in ["version:", "canonical:", "versioned:"]:
            self.assertRegex(
                content,
                rf"(?m)^\s*{re.escape(key)}",
                msg=f"Missing required frontmatter key in /heartbeat.md: {key}",
            )
