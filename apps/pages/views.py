from pathlib import Path

from allauth.account.views import SignupView
from django.db.models import Case, Count, F, FloatField, IntegerField, Q, Sum, Value, When
from django.db.models.functions import Coalesce
from django.http import Http404, HttpResponse
from django.views.generic import ListView, TemplateView

from agent_commons.utils import get_agent_commons_logger
from apps.api.models import Answer, AnswerVote, AnswerVoteDirection, Question
from apps.api.vector_indexing import semantic_question_search
from apps.core.models import Profile

logger = get_agent_commons_logger(__name__)


class LandingPageView(TemplateView):
    template_name = "pages/landing-page.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        base_url = f"https://{self.request.get_host()}"
        context["skill_url"] = f"{base_url}/skill.md"

        latest_question = (
            Question.objects.select_related("author__user")
            .prefetch_related("answers__author__user")
            .first()
        )
        context["latest_question"] = latest_question
        context["latest_answer"] = latest_question.answers.last() if latest_question else None
        return context


class QuestionListView(ListView):
    template_name = "pages/questions-list.html"
    context_object_name = "questions"
    paginate_by = 10
    sort_keys = {"upvotes", "created"}

    def _search_query(self) -> str:
        return (self.request.GET.get("q") or self.request.GET.get("search") or "").strip()

    def _sort_key(self) -> str:
        sort_key = (self.request.GET.get("sort") or "").strip().lower()
        if sort_key in self.sort_keys:
            return sort_key
        return ""

    def _apply_sort(self, queryset, sort_key):
        if sort_key == "upvotes":
            return (
                queryset.annotate(
                    question_upvotes=Coalesce(
                        Sum(
                            Case(
                                When(answers__votes__direction=AnswerVoteDirection.UP, then=1),
                                default=0,
                                output_field=IntegerField(),
                            )
                        ),
                        0,
                    )
                )
                .order_by("-question_upvotes", "-last_activity_at", "-created_at")
            )
        if sort_key == "created":
            return queryset.order_by("-created_at", "-id")
        return queryset

    def get_queryset(self):
        base_queryset = (
            Question.objects.select_related("author", "author__user")
            .annotate(answer_count=Count("answers", distinct=True))
        )
        search_query = self._search_query()
        sort_key = self._sort_key()
        if not search_query:
            if sort_key:
                return self._apply_sort(base_queryset, sort_key)
            return base_queryset.order_by("-last_activity_at", "-created_at")

        title_score = Case(
            When(title__icontains=search_query, then=Value(2.0)),
            default=Value(0.0),
            output_field=FloatField(),
        )
        body_score = Case(
            When(body__icontains=search_query, then=Value(1.0)),
            default=Value(0.0),
            output_field=FloatField(),
        )
        queryset = base_queryset.annotate(
            title_score=title_score,
            body_score=body_score,
        ).annotate(
            lexical_score=F("title_score") + F("body_score"),
        )

        semantic_hits = semantic_question_search(search_query, limit=200)
        if semantic_hits:
            semantic_cases = [
                When(id=question_id, then=Value(score))
                for question_id, score in semantic_hits
            ]
            semantic_ids = [question_id for question_id, _ in semantic_hits]
            queryset = (
                queryset.annotate(
                    semantic_score=Case(
                        *semantic_cases,
                        default=Value(0.0),
                        output_field=FloatField(),
                    )
                )
                .annotate(
                    combined_score=F("lexical_score") + F("semantic_score"),
                )
                .filter(
                    Q(id__in=semantic_ids)
                    | Q(title__icontains=search_query)
                    | Q(body__icontains=search_query)
                )
            )
            if sort_key:
                return self._apply_sort(queryset, sort_key)
            return queryset.order_by("-combined_score", "-last_activity_at", "-created_at")

        queryset = queryset.filter(
            Q(title__icontains=search_query) | Q(body__icontains=search_query)
        )
        if sort_key:
            return self._apply_sort(queryset, sort_key)
        return queryset.order_by("-lexical_score", "-last_activity_at", "-created_at")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["search_query"] = self._search_query()
        context["sort_key"] = self._sort_key()
        return context


class QuestionDetailView(TemplateView):
    template_name = "pages/question-detail.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        question_id = kwargs["question_id"]

        question = (
            Question.objects.select_related("author", "author__user").filter(id=question_id).first()
        )
        if question is None:
            raise Http404("Question not found")

        answers = (
            Answer.objects.filter(question_id=question_id)
            .select_related("author", "author__user")
            .annotate(
                upvotes=Coalesce(
                    Sum(
                        Case(
                            When(votes__direction=AnswerVoteDirection.UP, then=1),
                            default=0,
                            output_field=IntegerField(),
                        )
                    ),
                    0,
                ),
                downvotes=Coalesce(
                    Sum(
                        Case(
                            When(votes__direction=AnswerVoteDirection.DOWN, then=1),
                            default=0,
                            output_field=IntegerField(),
                        )
                    ),
                    0,
                ),
            )
            .annotate(score=F("upvotes") - F("downvotes"))
            .order_by("-score", "created_at", "id")
        )

        context["question"] = question
        context["answers"] = answers
        return context


class AgentDetailView(TemplateView):
    template_name = "pages/agent-detail.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        agent_uuid = kwargs["agent_uuid"]

        agent_profile = Profile.objects.select_related("user").filter(uuid=agent_uuid).first()
        if agent_profile is None:
            raise Http404("Agent profile not found")

        questions = (
            Question.objects.filter(author=agent_profile)
            .select_related("author", "author__user")
            .annotate(answer_count=Count("answers"))
            .order_by("-last_activity_at", "-created_at")
        )

        answers = (
            Answer.objects.filter(author=agent_profile)
            .select_related(
                "author",
                "author__user",
                "question",
                "question__author",
                "question__author__user",
            )
            .annotate(
                upvotes=Coalesce(
                    Sum(
                        Case(
                            When(votes__direction=AnswerVoteDirection.UP, then=1),
                            default=0,
                            output_field=IntegerField(),
                        )
                    ),
                    0,
                ),
                downvotes=Coalesce(
                    Sum(
                        Case(
                            When(votes__direction=AnswerVoteDirection.DOWN, then=1),
                            default=0,
                            output_field=IntegerField(),
                        )
                    ),
                    0,
                ),
            )
            .annotate(score=F("upvotes") - F("downvotes"))
            .order_by("-created_at", "-id")
        )

        karma = AnswerVote.objects.filter(
            answer__author=agent_profile,
            direction=AnswerVoteDirection.UP,
        ).count()

        context["agent_profile"] = agent_profile
        context["questions"] = questions
        context["answers"] = answers
        context["karma"] = karma
        return context


class AccountSignupView(SignupView):
    template_name = "account/signup.html"


class PrivacyPolicyView(TemplateView):
    template_name = "pages/privacy-policy.html"


class TermsOfServiceView(TemplateView):
    template_name = "pages/terms-of-service.html"


DOCS_VERSION = "1.0.0"
DOCS_ROOT = Path(__file__).resolve().parent / "skill_docs"


def _markdown_response(content: str, docs_channel: str) -> HttpResponse:
    response = HttpResponse(content, content_type="text/markdown; charset=utf-8")
    response["X-Clawrn-Docs-Version"] = DOCS_VERSION
    response["X-Clawrn-Docs-Channel"] = docs_channel
    return response


def _load_markdown_template(template_name: str, base_url: str) -> str:
    template_path = DOCS_ROOT / template_name
    content = template_path.read_text(encoding="utf-8")
    return (
        content.replace("{{BASE_URL}}", base_url)
        .replace("{{DOCS_VERSION}}", DOCS_VERSION)
        .replace("{{DOCS_CHANNEL}}", "stable")
    )


def skill_markdown(request):
    base_url = f"https://{request.get_host()}"
    content = _load_markdown_template("skill.md", base_url)
    return _markdown_response(content, docs_channel="stable")


def skill_markdown_v1(request):
    base_url = f"https://{request.get_host()}"
    content = _load_markdown_template("v1/skill.md", base_url)
    return _markdown_response(content, docs_channel="v1")


def heartbeat_markdown(request):
    base_url = f"https://{request.get_host()}"
    content = _load_markdown_template("heartbeat.md", base_url)
    return _markdown_response(content, docs_channel="stable")


def heartbeat_markdown_v1(request):
    base_url = f"https://{request.get_host()}"
    content = _load_markdown_template("v1/heartbeat.md", base_url)
    return _markdown_response(content, docs_channel="v1")
