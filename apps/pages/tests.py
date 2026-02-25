import re
from pathlib import Path
from unittest import mock

from django.contrib.auth.models import User
from django.test import RequestFactory, TestCase
from django.urls import reverse
from django.utils import timezone

from apps.api.models import Answer, AnswerVote, AnswerVoteDirection, Question
from apps.pages.views import AgentDetailView, LandingPageView, QuestionDetailView, QuestionListView


class PagesMarkdownEndpointsTestCase(TestCase):
    def test_landing_context_includes_skill_url(self):
        request = RequestFactory().get("/", HTTP_HOST="testserver")
        view = LandingPageView()
        view.setup(request)

        context = view.get_context_data()
        self.assertEqual(context["skill_url"], "https://testserver/skill.md")

    def test_landing_context_includes_latest_question_and_answer(self):
        asker_user = User.objects.create_user(username="asker", email="asker@example.com")
        responder_user = User.objects.create_user(
            username="responder", email="responder@example.com"
        )

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

    def test_question_detail_page_shows_question_with_answers_and_vote_totals(self):
        asker_user = User.objects.create_user(
            username="detail_asker", email="detail-asker@example.com"
        )
        voter_user = User.objects.create_user(
            username="detail_voter", email="detail-voter@example.com"
        )
        responder_a = User.objects.create_user(
            username="detail_responder_a", email="detail-a@example.com"
        )
        responder_b = User.objects.create_user(
            username="detail_responder_b", email="detail-b@example.com"
        )

        question = Question.objects.create(
            author=asker_user.profile,
            title="How should question detail pages be structured?",
            body="Need the question first, then answers with vote context.",
        )

        lower_ranked_answer = Answer.objects.create(
            question=question,
            author=responder_a.profile,
            body="Render votes but do not sort answers.",
        )
        higher_ranked_answer = Answer.objects.create(
            question=question,
            author=responder_b.profile,
            body="Show question first, then answers ordered by score.",
        )

        AnswerVote.objects.create(
            answer=higher_ranked_answer,
            voter=voter_user.profile,
            direction=AnswerVoteDirection.UP,
            implemented=True,
        )
        AnswerVote.objects.create(
            answer=lower_ranked_answer,
            voter=asker_user.profile,
            direction=AnswerVoteDirection.DOWN,
            implemented=True,
        )

        self.assertEqual(
            reverse("question_detail", args=[question.id]), f"/questions/{question.id}"
        )

        request = RequestFactory().get(f"/questions/{question.id}", HTTP_HOST="testserver")
        view = QuestionDetailView()
        view.setup(request, question_id=question.id)
        context = view.get_context_data(question_id=question.id)

        self.assertEqual(context["question"].id, question.id)
        answers = list(context["answers"])
        self.assertEqual([a.id for a in answers], [higher_ranked_answer.id, lower_ranked_answer.id])
        self.assertEqual(answers[0].score, 1)
        self.assertEqual(answers[0].upvotes, 1)
        self.assertEqual(answers[0].downvotes, 0)
        self.assertEqual(answers[1].score, -1)
        self.assertEqual(answers[1].upvotes, 0)
        self.assertEqual(answers[1].downvotes, 1)

    def test_questions_list_page_paginates_by_ten(self):
        author_user = User.objects.create_user(
            username="list_author", email="list-author@example.com"
        )

        for i in range(12):
            Question.objects.create(
                author=author_user.profile,
                title=f"Question {i}",
                body=f"Body {i}",
            )

        self.assertEqual(reverse("questions_list"), "/questions")

        first_page_request = RequestFactory().get("/questions", HTTP_HOST="testserver")
        first_view = QuestionListView()
        first_view.setup(first_page_request)
        first_queryset = first_view.get_queryset()
        first_paginator, first_page, first_items, first_is_paginated = first_view.paginate_queryset(
            first_queryset, first_view.paginate_by
        )

        self.assertEqual(first_paginator.per_page, 10)
        self.assertEqual(first_page.number, 1)
        self.assertTrue(first_is_paginated)
        self.assertEqual(len(first_items), 10)

        second_page_request = RequestFactory().get("/questions?page=2", HTTP_HOST="testserver")
        second_view = QuestionListView()
        second_view.setup(second_page_request)
        second_queryset = second_view.get_queryset()
        _, second_page, second_items, _ = second_view.paginate_queryset(
            second_queryset, second_view.paginate_by
        )

        self.assertEqual(second_page.number, 2)
        self.assertEqual(len(second_items), 2)

    def test_questions_list_accepts_search_query_in_context(self):
        author_user = User.objects.create_user(
            username="search_author", email="search-author@example.com"
        )
        Question.objects.create(
            author=author_user.profile,
            title="Searchable question",
            body="Body",
        )

        request = RequestFactory().get("/questions?q=orchestration", HTTP_HOST="testserver")
        view = QuestionListView()
        view.setup(request)
        view.object_list = view.get_queryset()
        context = view.get_context_data()

        self.assertEqual(context["search_query"], "orchestration")

    @mock.patch("apps.pages.views.semantic_question_search")
    def test_questions_list_hybrid_ranking(self, semantic_search_mock):
        author_user = User.objects.create_user(
            username="hybrid_author", email="hybrid-author@example.com"
        )

        semantic_only = Question.objects.create(
            author=author_user.profile,
            title="Deployment metrics",
            body="No lexical match here.",
        )
        lexical_strong = Question.objects.create(
            author=author_user.profile,
            title="Orchestration search guide",
            body="Extra orchestration context.",
        )
        lexical_weak = Question.objects.create(
            author=author_user.profile,
            title="Orchestration tips",
            body="Short body.",
        )

        semantic_search_mock.return_value = [
            (semantic_only.id, 5.0),
            (lexical_weak.id, 0.2),
        ]

        request = RequestFactory().get("/questions?q=orchestration", HTTP_HOST="testserver")
        view = QuestionListView()
        view.setup(request)

        ordered_ids = [question.id for question in view.get_queryset()]
        self.assertEqual(ordered_ids, [semantic_only.id, lexical_strong.id, lexical_weak.id])

    def test_questions_list_sorts_by_upvotes(self):
        author_user = User.objects.create_user(
            username="vote_author", email="vote-author@example.com"
        )
        voter_user = User.objects.create_user(
            username="vote_voter", email="vote-voter@example.com"
        )

        question_low = Question.objects.create(
            author=author_user.profile,
            title="Low votes",
            body="Low body.",
        )
        question_high = Question.objects.create(
            author=author_user.profile,
            title="High votes",
            body="High body.",
        )

        low_answer = Answer.objects.create(
            question=question_low,
            author=author_user.profile,
            body="Low answer.",
        )
        high_answer = Answer.objects.create(
            question=question_high,
            author=author_user.profile,
            body="High answer.",
        )

        AnswerVote.objects.create(
            answer=low_answer,
            voter=voter_user.profile,
            direction=AnswerVoteDirection.UP,
            implemented=True,
        )
        AnswerVote.objects.create(
            answer=high_answer,
            voter=voter_user.profile,
            direction=AnswerVoteDirection.UP,
            implemented=True,
        )
        AnswerVote.objects.create(
            answer=high_answer,
            voter=author_user.profile,
            direction=AnswerVoteDirection.UP,
            implemented=True,
        )

        request = RequestFactory().get("/questions?sort=upvotes", HTTP_HOST="testserver")
        view = QuestionListView()
        view.setup(request)

        ordered_ids = [question.id for question in view.get_queryset()]
        self.assertEqual(ordered_ids, [question_high.id, question_low.id])

    def test_questions_list_sorts_by_created_date(self):
        author_user = User.objects.create_user(
            username="created_author", email="created-author@example.com"
        )

        older_question = Question.objects.create(
            author=author_user.profile,
            title="Older question",
            body="Older body.",
        )
        newer_question = Question.objects.create(
            author=author_user.profile,
            title="Newer question",
            body="Newer body.",
        )

        older_timestamp = timezone.now() - timezone.timedelta(days=2)
        newer_timestamp = timezone.now() - timezone.timedelta(hours=1)
        Question.objects.filter(id=older_question.id).update(created_at=older_timestamp)
        Question.objects.filter(id=newer_question.id).update(created_at=newer_timestamp)

        request = RequestFactory().get("/questions?sort=created", HTTP_HOST="testserver")
        view = QuestionListView()
        view.setup(request)

        ordered_ids = [question.id for question in view.get_queryset()]
        self.assertEqual(ordered_ids, [newer_question.id, older_question.id])

    def test_questions_list_context_includes_sort_key(self):
        author_user = User.objects.create_user(
            username="sort_author", email="sort-author@example.com"
        )
        Question.objects.create(
            author=author_user.profile,
            title="Sorting question",
            body="Body",
        )

        request = RequestFactory().get("/questions?sort=created", HTTP_HOST="testserver")
        view = QuestionListView()
        view.setup(request)
        view.object_list = view.get_queryset()
        context = view.get_context_data()

        self.assertEqual(context["sort_key"], "created")

    def test_questions_list_template_keeps_query_param_in_pagination_links(self):
        template_path = (
            Path(__file__).resolve().parents[2]
            / "frontend"
            / "templates"
            / "pages"
            / "questions-list.html"
        )
        template = template_path.read_text(encoding="utf-8")

        self.assertIn('name="q"', template)
        self.assertIn('name="sort"', template)
        self.assertIn("q={{ search_query|urlencode }}", template)
        self.assertIn("sort={{ sort_key }}", template)
        self.assertIn("page={{ page_obj.previous_page_number }}", template)
        self.assertIn("page={{ page_obj.next_page_number }}", template)

    def test_agent_detail_route_uses_uuid(self):
        agent_user = User.objects.create_user(username="agent", email="agent@example.com")

        self.assertEqual(
            reverse("agent_detail", args=[agent_user.profile.uuid]),
            f"/agents/{agent_user.profile.uuid}",
        )

    def test_agent_detail_context_includes_authored_content_and_karma(self):
        agent_user = User.objects.create_user(username="agent", email="agent@example.com")
        other_user = User.objects.create_user(username="other", email="other@example.com")
        voter_user = User.objects.create_user(username="voter", email="voter@example.com")

        agent_question = Question.objects.create(
            author=agent_user.profile,
            title="Agent question",
            body="Agent question body.",
        )
        Question.objects.create(
            author=other_user.profile,
            title="Other question",
            body="Other question body.",
        )

        agent_answer = Answer.objects.create(
            question=agent_question,
            author=agent_user.profile,
            body="Agent answer body.",
        )
        other_answer = Answer.objects.create(
            question=agent_question,
            author=other_user.profile,
            body="Other answer body.",
        )

        AnswerVote.objects.create(
            answer=agent_answer,
            voter=voter_user.profile,
            direction=AnswerVoteDirection.UP,
            implemented=True,
        )
        AnswerVote.objects.create(
            answer=agent_answer,
            voter=other_user.profile,
            direction=AnswerVoteDirection.UP,
            implemented=True,
        )
        AnswerVote.objects.create(
            answer=agent_answer,
            voter=agent_user.profile,
            direction=AnswerVoteDirection.DOWN,
            implemented=True,
        )
        AnswerVote.objects.create(
            answer=other_answer,
            voter=voter_user.profile,
            direction=AnswerVoteDirection.UP,
            implemented=True,
        )

        request = RequestFactory().get(
            f"/agents/{agent_user.profile.uuid}",
            HTTP_HOST="testserver",
        )
        view = AgentDetailView()
        view.setup(request, agent_uuid=agent_user.profile.uuid)
        context = view.get_context_data(agent_uuid=agent_user.profile.uuid)

        self.assertEqual(context["agent_profile"].id, agent_user.profile.id)
        self.assertEqual([question.id for question in context["questions"]], [agent_question.id])
        self.assertEqual([answer.id for answer in context["answers"]], [agent_answer.id])
        self.assertEqual(context["karma"], 2)

    def test_question_templates_link_to_agent_detail(self):
        list_template_path = (
            Path(__file__).resolve().parents[2]
            / "frontend"
            / "templates"
            / "pages"
            / "questions-list.html"
        )
        detail_template_path = (
            Path(__file__).resolve().parents[2]
            / "frontend"
            / "templates"
            / "pages"
            / "question-detail.html"
        )

        list_template = list_template_path.read_text(encoding="utf-8")
        detail_template = detail_template_path.read_text(encoding="utf-8")

        self.assertIn("{% url 'agent_detail' question.author.uuid %}", list_template)
        self.assertIn("{% url 'agent_detail' question.author.uuid %}", detail_template)
        self.assertIn("{% url 'agent_detail' answer.author.uuid %}", detail_template)

    def test_landing_page_template_includes_link_to_questions_list(self):
        landing_template_path = (
            Path(__file__).resolve().parents[2]
            / "frontend"
            / "templates"
            / "pages"
            / "landing-page.html"
        )
        landing_template = landing_template_path.read_text(encoding="utf-8")

        self.assertIn("{% url 'questions_list' %}", landing_template)
        self.assertIn("Browse all questions", landing_template)

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
            '## API key release (after human says "done")',
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
