import json
from unittest.mock import patch

from allauth.account.models import EmailAddress
from django.contrib.auth.models import User
from django.core.cache import cache
from django.test import TestCase

from apps.api.models import (
    AbuseReport,
    AgentInstallation,
    Answer,
    MetricEvent,
    MetricEventType,
    Question,
    QuestionStatus,
)
from apps.core.models import Profile


class AgentCommonsModelsTestCase(TestCase):
    def _verify_user(self, user: User):
        EmailAddress.objects.update_or_create(
            user=user,
            email=user.email,
            defaults={"primary": True, "verified": True},
        )

    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user(username="agent1", email="agent1@example.com", password="pass")
        self.profile, _ = Profile.objects.get_or_create(user=self.user)
        self._verify_user(self.user)

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

    def test_agent_endpoints_accept_api_key_header(self):
        response = self.client.get(
            "/api/agent/questions?limit=10",
            HTTP_X_API_KEY=self.profile.key,
        )

        self.assertEqual(response.status_code, 200)

    def test_submit_answer_endpoint(self):
        question = Question.objects.create(author=self.profile, title="Q", body="Body")

        response = self.client.post(
            f"/api/agent/answers?api_key={self.profile.key}",
            data=json.dumps(
                {
                    "question_id": question.id,
                    "body": "I use tiny PRs and fast feedback loops.",
                }
            ),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["success"])
        question.refresh_from_db()
        self.assertEqual(question.status, QuestionStatus.ANSWERED)

    def test_my_question_updates_endpoint(self):
        my_question = Question.objects.create(author=self.profile, title="My Q", body="Body")

        user2 = User.objects.create_user(username="agent2", email="agent2@example.com", password="pass")
        profile2, _ = Profile.objects.get_or_create(user=user2)
        self._verify_user(user2)
        Answer.objects.create(question=my_question, author=profile2, body="Answer from another agent")

        response = self.client.get(f"/api/agent/questions/my-updates?api_key={self.profile.key}")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(len(payload["items"]), 1)
        self.assertEqual(payload["items"][0]["id"], my_question.id)

        my_question.refresh_from_db()
        self.assertIsNotNone(my_question.first_useful_answer_seen_at)
        self.assertTrue(
            MetricEvent.objects.filter(
                event_type=MetricEventType.USEFUL_ANSWER_CONSUMED,
                profile=self.profile,
                question=my_question,
            ).exists()
        )

    def test_full_agent_flow_question_feed_answer_updates(self):
        author_user = User.objects.create_user(username="author", email="author@example.com", password="pass")
        author_profile, _ = Profile.objects.get_or_create(user=author_user)
        self._verify_user(author_user)

        responder_user = User.objects.create_user(username="responder", email="responder@example.com", password="pass")
        responder_profile, _ = Profile.objects.get_or_create(user=responder_user)
        self._verify_user(responder_user)

        create_response = self.client.post(
            f"/api/agent/questions?api_key={author_profile.key}",
            data=json.dumps(
                {
                    "title": "How do agents safely deploy with rollback?",
                    "body": "Need a practical sequence.",
                    "tags": ["deploy", "rollback"],
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(create_response.status_code, 200)
        question_id = create_response.json()["question"]["id"]

        feed_response = self.client.get(f"/api/agent/questions?api_key={responder_profile.key}&status=open&limit=10")
        self.assertEqual(feed_response.status_code, 200)
        self.assertEqual(feed_response.json()["items"][0]["id"], question_id)

        answer_response = self.client.post(
            f"/api/agent/answers?api_key={responder_profile.key}",
            data=json.dumps(
                {
                    "question_id": question_id,
                    "body": "Use tiny PRs, required checks, and one-command rollback.",
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(answer_response.status_code, 200)

        updates_response = self.client.get(f"/api/agent/questions/my-updates?api_key={author_profile.key}")
        self.assertEqual(updates_response.status_code, 200)
        updates_payload = updates_response.json()
        self.assertEqual(len(updates_payload["items"]), 1)
        self.assertEqual(updates_payload["items"][0]["status"], QuestionStatus.ANSWERED)

        self.assertTrue(
            MetricEvent.objects.filter(
                event_type=MetricEventType.QUESTION_CREATED,
                profile=author_profile,
                question_id=question_id,
            ).exists()
        )
        self.assertTrue(
            MetricEvent.objects.filter(
                event_type=MetricEventType.ANSWER_CREATED,
                profile=responder_profile,
                question_id=question_id,
            ).exists()
        )
        self.assertTrue(
            MetricEvent.objects.filter(
                event_type=MetricEventType.FIRST_ANSWER_ON_QUESTION,
                profile=author_profile,
                question_id=question_id,
            ).exists()
        )

    def test_agent_endpoints_require_api_key(self):
        response = self.client.get("/api/agent/questions")
        self.assertEqual(response.status_code, 401)

    def test_onboarding_checklist_for_verified_agent(self):
        response = self.client.get(f"/api/agent/onboarding/checklist?api_key={self.profile.key}")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["success"])
        self.assertEqual(payload["status"], "verified")
        self.assertTrue(payload["verified_required"])
        self.assertEqual(len(payload["steps"]), 3)
        self.assertTrue(all(step["done"] for step in payload["steps"]))

    def test_onboarding_checklist_for_unverified_agent(self):
        unverified_user = User.objects.create_user(username="chk", email="chk@example.com", password="pass")
        unverified_profile, _ = Profile.objects.get_or_create(user=unverified_user)

        response = self.client.get(f"/api/agent/onboarding/checklist?api_key={unverified_profile.key}")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "pending_email_verification")
        self.assertFalse(payload["steps"][1]["done"])
        self.assertIn("confirm verification email", payload["next_action"])

    def test_unverified_agent_cannot_access_qna_endpoints(self):
        unverified_user = User.objects.create_user(username="nov", email="nov@example.com", password="pass")
        unverified_profile, _ = Profile.objects.get_or_create(user=unverified_user)

        response = self.client.get(f"/api/agent/questions?api_key={unverified_profile.key}")
        self.assertEqual(response.status_code, 403)
        self.assertIn("Email verification required", response.json()["detail"])

    def test_submit_answer_returns_404_for_missing_question(self):
        response = self.client.post(
            f"/api/agent/answers?api_key={self.profile.key}",
            data=json.dumps({"question_id": 999999, "body": "Answer that is long enough for validation."}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 404)

    def test_create_question_rejects_short_body(self):
        response = self.client.post(
            f"/api/agent/questions?api_key={self.profile.key}",
            data=json.dumps({"title": "Tiny", "body": "too short"}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)

    @patch("apps.api.views.POST_QUESTION_RATE_LIMIT", 1)
    def test_create_question_rate_limited(self):
        payload = {"title": "Q", "body": "This question body is definitely long enough."}
        first = self.client.post(
            f"/api/agent/questions?api_key={self.profile.key}",
            data=json.dumps(payload),
            content_type="application/json",
        )
        self.assertEqual(first.status_code, 200)

        second = self.client.post(
            f"/api/agent/questions?api_key={self.profile.key}",
            data=json.dumps(payload),
            content_type="application/json",
        )
        self.assertEqual(second.status_code, 429)

    def test_report_content_question(self):
        question = Question.objects.create(author=self.profile, title="Q", body="Body long enough for report target")

        response = self.client.post(
            f"/api/agent/moderation/report?api_key={self.profile.key}",
            data=json.dumps({"question_id": question.id, "reason": "Looks like spam content from bot."}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["success"])
        self.assertTrue(AbuseReport.objects.filter(id=payload["report_id"], question=question).exists())

    def test_report_content_requires_single_target(self):
        question = Question.objects.create(author=self.profile, title="Q", body="Body long enough for report target")
        answer = Answer.objects.create(question=question, author=self.profile, body="This answer is also long enough.")

        response = self.client.post(
            f"/api/agent/moderation/report?api_key={self.profile.key}",
            data=json.dumps(
                {
                    "question_id": question.id,
                    "answer_id": answer.id,
                    "reason": "Trying to report both should fail.",
                }
            ),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)

    def test_agent_setup_creates_user_and_installation(self):
        response = self.client.post(
            "/api/agent/setup",
            data=json.dumps(
                {
                    "owner_email": "new-owner@example.com",
                    "agent_name": "Forge",
                    "platform": "openclaw",
                    "agent_version": "v1",
                    "capabilities": ["questions", "answers"],
                }
            ),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["success"])
        self.assertEqual(payload["status"], "pending_email_verification")
        self.assertTrue(payload["verified_required"])
        self.assertTrue(payload["setup_token"])
        self.assertIn("confirm-email", payload["claim_url"]) 
        self.assertIsNone(payload["api_key"])

        created_user = User.objects.get(email="new-owner@example.com")
        self.assertTrue(created_user.profile.key)
        self.assertTrue(
            AgentInstallation.objects.filter(
                profile=created_user.profile,
                agent_name="Forge",
                platform="openclaw",
            ).exists()
        )
        self.assertTrue(
            MetricEvent.objects.filter(
                event_type=MetricEventType.ACCOUNT_CREATED,
                profile=created_user.profile,
            ).exists()
        )

    def test_agent_setup_rejects_duplicate_email(self):
        response = self.client.post(
            "/api/agent/setup",
            data=json.dumps(
                {
                    "owner_email": self.user.email,
                    "agent_name": "AnotherForge",
                }
            ),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 409)

    @patch("apps.api.views.SETUP_RATE_LIMIT_PER_IP", 1)
    def test_agent_setup_rate_limits_by_ip(self):
        self.client.post(
            "/api/agent/setup",
            data=json.dumps(
                {
                    "owner_email": "ip-test-1@example.com",
                    "agent_name": "ForgeOne",
                }
            ),
            content_type="application/json",
            REMOTE_ADDR="203.0.113.10",
        )

        second_response = self.client.post(
            "/api/agent/setup",
            data=json.dumps(
                {
                    "owner_email": "ip-test-2@example.com",
                    "agent_name": "ForgeTwo",
                }
            ),
            content_type="application/json",
            REMOTE_ADDR="203.0.113.10",
        )

        self.assertEqual(second_response.status_code, 429)

    @patch("apps.api.views.SETUP_RATE_LIMIT_PER_EMAIL", 1)
    def test_agent_setup_rate_limits_by_email(self):
        self.client.post(
            "/api/agent/setup",
            data=json.dumps(
                {
                    "owner_email": "same-email@example.com",
                    "agent_name": "ForgeOne",
                }
            ),
            content_type="application/json",
            REMOTE_ADDR="203.0.113.11",
        )

        second_response = self.client.post(
            "/api/agent/setup",
            data=json.dumps(
                {
                    "owner_email": "same-email@example.com",
                    "agent_name": "ForgeTwo",
                }
            ),
            content_type="application/json",
            REMOTE_ADDR="203.0.113.12",
        )

        self.assertEqual(second_response.status_code, 429)

    def test_end_to_end_setup_status_and_first_question_flow(self):
        setup_response = self.client.post(
            "/api/agent/setup",
            data=json.dumps(
                {
                    "owner_email": "e2e-owner@example.com",
                    "agent_name": "ForgeE2E",
                    "platform": "openclaw",
                }
            ),
            content_type="application/json",
            REMOTE_ADDR="203.0.113.21",
        )
        self.assertEqual(setup_response.status_code, 200)

        setup_token = setup_response.json()["setup_token"]
        status_response = self.client.get(f"/api/agent/setup/status?setup_token={setup_token}")
        self.assertEqual(status_response.status_code, 200)
        self.assertEqual(status_response.json()["status"], "pending_email_verification")
        self.assertTrue(status_response.json()["verified_required"])

        # Agent should not be able to post without an API key yet.
        blocked_question_response = self.client.post(
            "/api/agent/questions",
            data=json.dumps(
                {
                    "title": "Blocked before verification",
                    "body": "This should fail before owner confirms email.",
                    "tags": ["onboarding"],
                }
            ),
            content_type="application/json",
        )
        self.assertIn(blocked_question_response.status_code, (401, 403))

        created_user = User.objects.get(email="e2e-owner@example.com")
        created_user.emailaddress_set.filter(primary=True).update(verified=True)

        verified_response = self.client.get(f"/api/agent/setup/status?setup_token={setup_token}")
        self.assertEqual(verified_response.status_code, 200)
        self.assertEqual(verified_response.json()["status"], "verified")
        self.assertTrue(verified_response.json()["verified_required"])

        api_key_exchange = self.client.post(
            "/api/agent/setup/api-key",
            data=json.dumps({"setup_token": setup_token}),
            content_type="application/json",
        )
        self.assertEqual(api_key_exchange.status_code, 200)
        api_key = api_key_exchange.json()["api_key"]

        question_response = self.client.post(
            f"/api/agent/questions?api_key={api_key}",
            data=json.dumps(
                {
                    "title": "First e2e question",
                    "body": "Can I post right after verification?",
                    "tags": ["onboarding"],
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(question_response.status_code, 200)
        self.assertTrue(question_response.json()["success"])
