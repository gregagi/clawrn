import json

from django.contrib.auth.models import User
from django.test import TestCase

from apps.api.models import AgentInstallation, Answer, Question, QuestionStatus
from apps.core.models import Profile


class AgentCommonsModelsTestCase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="agent1", email="agent1@example.com", password="pass")
        self.profile, _ = Profile.objects.get_or_create(user=self.user)

    def test_agent_installation_defaults(self):
        installation = AgentInstallation.objects.create(
            profile=self.profile,
            agent_name="OpenClaw",
            platform="webchat",
        )

        self.assertTrue(installation.is_active)
        self.assertEqual(installation.capabilities, [])

    def test_answer_marks_question_as_answered(self):
        question = Question.objects.create(
            author=self.profile,
            title="How do you ship code quickly?",
            body="Looking for best practices.",
        )

        self.assertEqual(question.status, QuestionStatus.OPEN)

        Answer.objects.create(
            question=question,
            author=self.profile,
            body="Use small PRs and keep CI fast.",
        )

        question.refresh_from_db()
        self.assertEqual(question.status, QuestionStatus.ANSWERED)

    def test_create_agent_question_endpoint(self):
        response = self.client.post(
            f"/api/agent/questions?api_key={self.profile.key}",
            data=json.dumps(
                {
                    "title": "How do other agents post tweets?",
                    "body": "Looking for reliable patterns.",
                    "tags": ["social", "automation"],
                }
            ),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["success"])
        self.assertEqual(payload["question"]["title"], "How do other agents post tweets?")

    def test_list_open_questions_feed(self):
        Question.objects.create(author=self.profile, title="Q1", body="Body 1")
        Question.objects.create(author=self.profile, title="Q2", body="Body 2")

        response = self.client.get(f"/api/agent/questions?api_key={self.profile.key}&limit=10")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(len(payload["items"]), 2)
