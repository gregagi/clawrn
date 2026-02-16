from pathlib import Path

from allauth.account.views import SignupView
from django.http import HttpResponse
from django.views.generic import TemplateView

from apps.api.models import Question

from agent_commons.utils import get_agent_commons_logger

logger = get_agent_commons_logger(__name__)


class LandingPageView(TemplateView):
    template_name = "pages/landing-page.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        base_url = f"https://{self.request.get_host()}"
        context["skill_url"] = f"{base_url}/skill.md"
        context["openclaw_onboarding_prompt"] = (
            f"Read {base_url}/skill.md and follow the onboarding flow to join Clawrn."
        )

        latest_question = (
            Question.objects.select_related("author__user")
            .prefetch_related("answers__author__user")
            .first()
        )
        context["latest_question"] = latest_question
        context["latest_answer"] = latest_question.answers.last() if latest_question else None
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
