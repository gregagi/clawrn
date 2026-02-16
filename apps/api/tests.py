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
