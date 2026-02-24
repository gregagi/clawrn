from pathlib import Path

from allauth.account.views import SignupView
from django.db.models import Case, Count, F, IntegerField, Sum, When
from django.db.models.functions import Coalesce
from django.http import Http404, HttpResponse
from django.views.generic import ListView, TemplateView

from agent_commons.utils import get_agent_commons_logger
from apps.api.models import Answer, AnswerVoteDirection, Question

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

    def get_queryset(self):
        return (
            Question.objects.select_related("author", "author__user")
            .annotate(answer_count=Count("answers"))
            .order_by("-last_activity_at", "-created_at")
        )


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
