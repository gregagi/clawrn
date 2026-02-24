import json
from datetime import timedelta
from unittest.mock import patch

from allauth.account.models import EmailAddress
from django.contrib.auth.models import User
from django.core.cache import cache
from django.test import TestCase
from django.utils import timezone

from apps.api.models import (
    AbuseReport,
    AgentInstallation,
    AgentSetupToken,
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
        with patch("apps.api.views.index_question_content") as index_question_content:
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
        index_question_content.assert_called_once()

    def test_question_tags_are_normalized_and_deduped(self):
        response = self.client.post(
            f"/api/agent/questions?api_key={self.profile.key}",
            data=json.dumps(
                {
                    "title": "Normalization",
                    "body": "This body is definitely long enough for normalization test.",
                    "tags": ["  DevOps ", "devops", "Hello World", ""],
                }
            ),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        question_id = response.json()["question"]["id"]
        q = Question.objects.get(id=question_id)
        self.assertEqual(q.tags, ["devops", "hello-world"])

    def test_list_questions_can_filter_by_tags(self):
        from django.utils import timezone

        Question.objects.create(
            author=self.profile,
            title="Q deploy",
            body="Body long enough for tag filter test 1.",
            tags=["deploy"],
            last_activity_at=timezone.now(),
        )
        Question.objects.create(
            author=self.profile,
            title="Q onboarding",
            body="Body long enough for tag filter test 2.",
            tags=["onboarding"],
            last_activity_at=timezone.now(),
        )

        response = self.client.get(
            f"/api/agent/questions?api_key={self.profile.key}&limit=10&filter_tags=Deploy"
        )
        self.assertEqual(response.status_code, 200)
        items = response.json()["items"]
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["title"], "Q deploy")

    def test_list_agent_tags_endpoint(self):
        Question.objects.create(
            author=self.profile,
            title="Tag Q1",
            body="Body long enough for list tags.",
            tags=["deploy", "hello-world"],
        )
        Question.objects.create(
            author=self.profile,
            title="Tag Q2",
            body="Body long enough for list tags 2.",
            tags=["deploy"],
        )

        response = self.client.get(f"/api/agent/tags?api_key={self.profile.key}&limit=10")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIn("items", payload)
        tags = {i["tag"]: i["count"] for i in payload["items"]}
        self.assertEqual(tags["deploy"], 2)
        self.assertEqual(tags["hello-world"], 1)

    def test_list_open_questions_feed(self):
        Question.objects.create(author=self.profile, title="Q1", body="Body 1")
        Question.objects.create(author=self.profile, title="Q2", body="Body 2")

        response = self.client.get(f"/api/agent/questions?api_key={self.profile.key}&limit=10")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(len(payload["items"]), 2)

    def test_open_questions_ranking_v1_unanswered_and_recency(self):
        from django.utils import timezone
        from datetime import timedelta

        old_unanswered = Question.objects.create(
            author=self.profile,
            title="Old unanswered",
            body="Body",
            tags=["deploy"],
            last_activity_at=timezone.now() - timedelta(days=7),
        )

        newer_unanswered = Question.objects.create(
            author=self.profile,
            title="Newer unanswered",
            body="Body",
            tags=["onboarding"],
            last_activity_at=timezone.now() - timedelta(hours=1),
        )

        same_age_other_tag = Question.objects.create(
            author=self.profile,
            title="Same age other tag",
            body="Body",
            tags=["payments"],
            last_activity_at=timezone.now() - timedelta(days=6),
        )

        response = self.client.get(f"/api/agent/questions?api_key={self.profile.key}&limit=10")
        self.assertEqual(response.status_code, 200)
        items = response.json()["items"]

        # Among open questions, older last_activity_at should rank higher.
        self.assertEqual(items[0]["id"], old_unanswered.id)
        self.assertEqual(items[1]["id"], same_age_other_tag.id)
        self.assertEqual(items[2]["id"], newer_unanswered.id)

        # Tag boost should elevate matching tags when explicitly requested.
        response_boosted = self.client.get(
            f"/api/agent/questions?api_key={self.profile.key}&limit=10&boost_tags=payments"
        )
        self.assertEqual(response_boosted.status_code, 200)
        boosted_items = response_boosted.json()["items"]
        self.assertEqual(boosted_items[0]["id"], same_age_other_tag.id)

    def test_agent_endpoints_accept_api_key_header(self):
        response = self.client.get(
            "/api/agent/questions?limit=10",
            HTTP_X_API_KEY=self.profile.key,
        )

        self.assertEqual(response.status_code, 200)

    def test_submit_answer_endpoint(self):
        asker_user = User.objects.create_user(
            username="asker2",
            email="asker2@example.com",
            password="pass",
        )
        asker_profile, _ = Profile.objects.get_or_create(user=asker_user)
        self._verify_user(asker_user)

        question = Question.objects.create(author=asker_profile, title="Q", body="Body")

        with patch("apps.api.views.index_answer_content") as index_answer_content:
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
        index_answer_content.assert_called_once()

    def test_submit_answer_rejects_answering_own_question(self):
        question = Question.objects.create(author=self.profile, title="Own question", body="Body")

        response = self.client.post(
            f"/api/agent/answers?api_key={self.profile.key}",
            data=json.dumps(
                {
                    "question_id": question.id,
                    "body": "This should be rejected because I asked this question.",
                }
            ),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 403)
        self.assertIn("own question", response.json()["detail"].lower())
        self.assertEqual(Answer.objects.filter(question=question).count(), 0)
        question.refresh_from_db()
        self.assertEqual(question.status, QuestionStatus.OPEN)

    def test_vote_answer_requires_implemented_attestation(self):
        question = Question.objects.create(author=self.profile, title="Q", body="Body")
        answer = Answer.objects.create(question=question, author=self.profile, body="Answer body")

        response = self.client.post(
            f"/api/agent/answers/vote?api_key={self.profile.key}",
            data=json.dumps({"answer_id": answer.id, "direction": "up", "implemented": False}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)

    def test_vote_answer_create_update_remove(self):
        question = Question.objects.create(author=self.profile, title="Q", body="Body")

        voter_user = User.objects.create_user(username="voter", email="voter@example.com", password="pass")
        voter_profile, _ = Profile.objects.get_or_create(user=voter_user)
        self._verify_user(voter_user)

        answer = Answer.objects.create(question=question, author=self.profile, body="Answer body")

        # create upvote
        response = self.client.post(
            f"/api/agent/answers/vote?api_key={voter_profile.key}",
            data=json.dumps({"answer_id": answer.id, "direction": "up", "implemented": True}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["success"])
        self.assertEqual(payload["status"], "created")
        self.assertEqual(payload["score"], 1)
        self.assertEqual(payload["upvotes"], 1)
        self.assertEqual(payload["downvotes"], 0)

        # change to downvote
        response = self.client.post(
            f"/api/agent/answers/vote?api_key={voter_profile.key}",
            data=json.dumps({"answer_id": answer.id, "direction": "down", "implemented": True}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "updated")
        self.assertEqual(payload["score"], -1)
        self.assertEqual(payload["upvotes"], 0)
        self.assertEqual(payload["downvotes"], 1)

        # same downvote again toggles removal
        response = self.client.post(
            f"/api/agent/answers/vote?api_key={voter_profile.key}",
            data=json.dumps({"answer_id": answer.id, "direction": "down", "implemented": True}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "removed")
        self.assertEqual(payload["score"], 0)
        self.assertEqual(payload["upvotes"], 0)
        self.assertEqual(payload["downvotes"], 0)

    def test_question_detail_sorts_answers_by_score(self):
        question = Question.objects.create(author=self.profile, title="Q", body="Body")

        answer1 = Answer.objects.create(question=question, author=self.profile, body="Answer 1")
        answer2 = Answer.objects.create(question=question, author=self.profile, body="Answer 2")

        voter_user = User.objects.create_user(username="voter2", email="voter2@example.com", password="pass")
        voter_profile, _ = Profile.objects.get_or_create(user=voter_user)
        self._verify_user(voter_user)

        # Give answer2 a higher score.
        vote_response = self.client.post(
            f"/api/agent/answers/vote?api_key={voter_profile.key}",
            data=json.dumps({"answer_id": answer2.id, "direction": "up", "implemented": True}),
            content_type="application/json",
        )
        self.assertEqual(vote_response.status_code, 200)

        detail_response = self.client.get(
            f"/api/agent/questions/{question.id}/detail?api_key={voter_profile.key}"
        )
        self.assertEqual(detail_response.status_code, 200)
        payload = detail_response.json()
        self.assertTrue(payload["success"])
        self.assertEqual(payload["question"]["id"], question.id)
        self.assertEqual([a["id"] for a in payload["answers"]], [answer2.id, answer1.id])
        self.assertEqual(payload["answers"][0]["score"], 1)

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
        installation = AgentInstallation.objects.get(
            profile=created_user.profile,
            agent_name="Forge",
            platform="openclaw",
        )
        self.assertTrue(installation.api_key)
        self.assertTrue(
            MetricEvent.objects.filter(
                event_type=MetricEventType.ACCOUNT_CREATED,
                profile=created_user.profile,
            ).exists()
        )
        self.assertTrue(
            AgentSetupToken.objects.filter(
                token=payload["setup_token"],
                installation=installation,
                profile=created_user.profile,
            ).exists()
        )

    def test_agent_setup_allows_multiple_agents_for_same_owner_email(self):
        first = self.client.post(
            "/api/agent/setup",
            data=json.dumps(
                {
                    "owner_email": self.user.email,
                    "agent_name": "ForgeOne",
                    "platform": "openclaw",
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(first.status_code, 200)

        second = self.client.post(
            "/api/agent/setup",
            data=json.dumps(
                {
                    "owner_email": self.user.email,
                    "agent_name": "ForgeTwo",
                    "platform": "openclaw",
                }
            ),
            content_type="application/json",
        )

        self.assertEqual(second.status_code, 200)
        self.assertEqual(
            AgentInstallation.objects.filter(profile=self.profile, platform="openclaw").count(),
            2,
        )

    def test_agent_setup_rejects_duplicate_agent_name_and_platform_for_same_owner(self):
        first = self.client.post(
            "/api/agent/setup",
            data=json.dumps(
                {
                    "owner_email": self.user.email,
                    "agent_name": "ForgeDup",
                    "platform": "openclaw",
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(first.status_code, 200)

        second = self.client.post(
            "/api/agent/setup",
            data=json.dumps(
                {
                    "owner_email": self.user.email,
                    "agent_name": "ForgeDup",
                    "platform": "openclaw",
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(second.status_code, 409)
        self.assertIn("agent_name and platform", second.json()["detail"])

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

    def test_setup_token_cannot_be_reused_for_api_key_exchange(self):
        setup_response = self.client.post(
            "/api/agent/setup",
            data=json.dumps(
                {
                    "owner_email": "reuse-owner@example.com",
                    "agent_name": "ForgeReuse",
                    "platform": "openclaw",
                }
            ),
            content_type="application/json",
            REMOTE_ADDR="203.0.113.31",
        )
        self.assertEqual(setup_response.status_code, 200)

        setup_token = setup_response.json()["setup_token"]
        created_user = User.objects.get(email="reuse-owner@example.com")
        created_user.emailaddress_set.filter(primary=True).update(verified=True)

        first_exchange = self.client.post(
            "/api/agent/setup/api-key",
            data=json.dumps({"setup_token": setup_token}),
            content_type="application/json",
        )
        self.assertEqual(first_exchange.status_code, 200)
        self.assertTrue(first_exchange.json()["api_key"])

        second_exchange = self.client.post(
            "/api/agent/setup/api-key",
            data=json.dumps({"setup_token": setup_token}),
            content_type="application/json",
        )
        self.assertEqual(second_exchange.status_code, 410)

    def test_api_key_exchange_returns_distinct_agent_keys_and_both_keys_authenticate(self):
        first_setup = self.client.post(
            "/api/agent/setup",
            data=json.dumps(
                {
                    "owner_email": "multi-owner@example.com",
                    "agent_name": "ForgeAlpha",
                    "platform": "openclaw",
                }
            ),
            content_type="application/json",
            REMOTE_ADDR="203.0.113.41",
        )
        self.assertEqual(first_setup.status_code, 200)

        second_setup = self.client.post(
            "/api/agent/setup",
            data=json.dumps(
                {
                    "owner_email": "multi-owner@example.com",
                    "agent_name": "ForgeBeta",
                    "platform": "openclaw",
                }
            ),
            content_type="application/json",
            REMOTE_ADDR="203.0.113.42",
        )
        self.assertEqual(second_setup.status_code, 200)

        owner = User.objects.get(email="multi-owner@example.com")
        owner.emailaddress_set.filter(primary=True).update(verified=True)

        first_key_response = self.client.post(
            "/api/agent/setup/api-key",
            data=json.dumps({"setup_token": first_setup.json()["setup_token"]}),
            content_type="application/json",
        )
        self.assertEqual(first_key_response.status_code, 200)
        first_key = first_key_response.json()["api_key"]

        second_key_response = self.client.post(
            "/api/agent/setup/api-key",
            data=json.dumps({"setup_token": second_setup.json()["setup_token"]}),
            content_type="application/json",
        )
        self.assertEqual(second_key_response.status_code, 200)
        second_key = second_key_response.json()["api_key"]

        self.assertNotEqual(first_key, second_key)

        first_auth_response = self.client.get(f"/api/agent/questions?api_key={first_key}&limit=10")
        self.assertEqual(first_auth_response.status_code, 200)

        second_auth_response = self.client.get(f"/api/agent/questions?api_key={second_key}&limit=10")
        self.assertEqual(second_auth_response.status_code, 200)

    def test_setup_status_rejects_used_setup_token(self):
        setup_response = self.client.post(
            "/api/agent/setup",
            data=json.dumps(
                {
                    "owner_email": "used-status-owner@example.com",
                    "agent_name": "ForgeUsedStatus",
                }
            ),
            content_type="application/json",
            REMOTE_ADDR="203.0.113.32",
        )
        self.assertEqual(setup_response.status_code, 200)

        setup_token = setup_response.json()["setup_token"]
        created_user = User.objects.get(email="used-status-owner@example.com")
        created_user.emailaddress_set.filter(primary=True).update(verified=True)

        exchange = self.client.post(
            "/api/agent/setup/api-key",
            data=json.dumps({"setup_token": setup_token}),
            content_type="application/json",
        )
        self.assertEqual(exchange.status_code, 200)

        status_after_use = self.client.get(f"/api/agent/setup/status?setup_token={setup_token}")
        self.assertEqual(status_after_use.status_code, 410)

    @patch("apps.api.views.SETUP_TOKEN_TTL_SECONDS", 1)
    def test_setup_token_expires(self):
        setup_response = self.client.post(
            "/api/agent/setup",
            data=json.dumps(
                {
                    "owner_email": "expired-owner@example.com",
                    "agent_name": "ForgeExpired",
                }
            ),
            content_type="application/json",
            REMOTE_ADDR="203.0.113.33",
        )
        self.assertEqual(setup_response.status_code, 200)

        setup_token = setup_response.json()["setup_token"]
        token_obj = AgentSetupToken.objects.get(token=setup_token)
        AgentSetupToken.objects.filter(id=token_obj.id).update(created_at=timezone.now() - timedelta(days=2))

        expired_status = self.client.get(f"/api/agent/setup/status?setup_token={setup_token}")
        self.assertEqual(expired_status.status_code, 410)

    def test_admin_weekly_metrics_report(self):
        # Create a superuser profile
        admin_user = User.objects.create_user(
            username="admin",
            email="admin@example.com",
            password="pass",
            is_superuser=True,
            is_staff=True,
        )
        admin_profile, _ = Profile.objects.get_or_create(user=admin_user)
        self._verify_user(admin_user)

        # Seed a simple question -> answer -> useful-consumed flow inside the window
        t0 = timezone.now() - timedelta(days=2)
        question = Question.objects.create(
            author=self.profile,
            title="Metrics Q",
            body="Body long enough for metrics test.",
        )
        Question.objects.filter(id=question.id).update(created_at=t0)
        question.refresh_from_db()

        answer = Answer.objects.create(
            question=question,
            author=self.profile,
            body="Answer body long enough for metrics test.",
        )
        Answer.objects.filter(id=answer.id).update(created_at=t0 + timedelta(hours=1))

        Question.objects.filter(id=question.id).update(first_useful_answer_seen_at=t0 + timedelta(hours=2))

        # MetricEvents (counts)
        MetricEvent.objects.create(event_type=MetricEventType.ACCOUNT_CREATED, profile=self.profile)
        MetricEvent.objects.create(
            event_type=MetricEventType.QUESTION_CREATED,
            profile=self.profile,
            question=question,
        )
        MetricEvent.objects.create(
            event_type=MetricEventType.ANSWER_CREATED,
            profile=self.profile,
            question=question,
            answer=answer,
        )

        resp = self.client.get(f"/api/admin/metrics/weekly?api_key={admin_profile.key}&days=7")
        self.assertEqual(resp.status_code, 200)
        payload = resp.json()

        self.assertEqual(payload["accounts_created"], 1)
        self.assertEqual(payload["questions_created"], 1)
        self.assertEqual(payload["answers_created"], 1)
        self.assertEqual(payload["participating_profiles"], 1)

        self.assertEqual(payload["questions_with_first_answer"], 1)
        self.assertEqual(payload["questions_with_useful_answer_consumed"], 1)
        self.assertAlmostEqual(payload["resolution_rate"], 1.0)

        # p50 should match the single datapoint
        self.assertEqual(payload["time_to_first_answer_seconds_p50"], 60 * 60)
        self.assertEqual(payload["ttfv_seconds_p50"], 2 * 60 * 60)
