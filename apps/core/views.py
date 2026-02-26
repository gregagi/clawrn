from urllib.parse import urlencode


from allauth.account.models import EmailAddress, EmailConfirmation
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.core.cache import cache
from django.db import IntegrityError, transaction
from django.http import HttpResponse, HttpResponseBadRequest
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from django.contrib.messages.views import SuccessMessageMixin
from django.shortcuts import get_object_or_404, redirect
from django.conf import settings
from django.contrib import messages
from django.urls import reverse, reverse_lazy
from django.views.generic import TemplateView, UpdateView



from apps.core.forms import ProfileUpdateForm
from apps.core.models import Profile
from apps.core.model_utils import generate_random_key
from apps.api.models import AgentInstallation

from agent_commons.utils import get_agent_commons_logger



logger = get_agent_commons_logger(__name__)


class HomeView(LoginRequiredMixin, TemplateView):
    login_url = "account_login"
    template_name = "pages/home.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        user = self.request.user
        # allauth stores email verification state in EmailAddress
        email_address = EmailAddress.objects.filter(user=user, email=user.email).first()
        context["email_verified"] = email_address.verified if email_address else False
        context["rotate_api_key_url"] = reverse("rotate_api_key")
        context["create_agent_installation_url"] = reverse("create_agent_installation")
        context["agent_installations"] = user.profile.agent_installations.all()

        return context


class UserSettingsView(LoginRequiredMixin, SuccessMessageMixin, UpdateView):
    login_url = "account_login"
    model = Profile
    form_class = ProfileUpdateForm
    success_message = "User Profile Updated"
    success_url = reverse_lazy("settings")
    template_name = "pages/user-settings.html"

    def get_object(self):
        return self.request.user.profile

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user

        email_address = EmailAddress.objects.filter(user=user, email=user.email).first()
        context["email_verified"] = email_address.verified if email_address else False
        context["resend_confirmation_url"] = reverse("resend_confirmation")

        return context

@login_required
@require_POST
def resend_confirmation_email(request):
    user = request.user

    try:
        email_address = EmailAddress.objects.get_for_user(user, user.email)

        if not email_address:
            messages.error(request, "No email address found for your account.")
            logger.warning(
                "[Resend Confirmation] No email address found",
                user_id=user.id,
                user_email=user.email,
            )
            return redirect("settings")

        if email_address.verified:
            messages.info(request, "Your email is already verified.")
            logger.info(
                "[Resend Confirmation] Email already verified",
                user_id=user.id,
                user_email=user.email,
            )
            return redirect("settings")

        # Create or get existing email confirmation
        email_confirmation = EmailConfirmation.create(email_address)
        email_confirmation.send(request, signup=False)

        messages.success(request, "Confirmation email has been sent. Please check your inbox.")
        logger.info(
            "[Resend Confirmation] Email sent successfully",
            user_id=user.id,
            user_email=user.email,
        )

    except Exception as e:
        messages.error(request, "Failed to send confirmation email. Please try again later.")
        logger.error(
            "[Resend Confirmation] Failed to send email",
            user_id=user.id,
            user_email=user.email,
            error=str(e),
            exc_info=True,
        )

    return redirect("settings")



@login_required
@require_POST
def rotate_api_key(request):
    user = request.user

    email_address = EmailAddress.objects.filter(user=user, email=user.email).first()
    if not email_address or not email_address.verified:
        messages.error(request, "Please confirm your email before creating an API key.")
        return redirect("home")

    profile = user.profile
    profile.key = generate_random_key()
    profile.save(update_fields=["key", "updated_at"])

    messages.success(request, "API key created.")
    return redirect("home")


@login_required
@require_POST
def create_agent_installation(request):
    user = request.user
    email_address = EmailAddress.objects.filter(user=user, email=user.email).first()
    email_verified = email_address.verified if email_address else False

    if not email_verified:
        messages.error(request, "Please confirm your email before creating an agent installation.")
        return redirect("home")

    agent_name = request.POST.get("agent_name", "").strip()
    platform = request.POST.get("platform", "openclaw").strip() or "openclaw"
    agent_version = request.POST.get("agent_version", "").strip()

    if not agent_name:
        messages.error(request, "Agent name is required.")
        return redirect("home")

    try:
        with transaction.atomic():
            AgentInstallation.objects.create(
                profile=user.profile,
                agent_name=agent_name,
                platform=platform,
                agent_version=agent_version,
            )
    except IntegrityError:
        messages.error(
            request,
            "An agent with this name and platform already exists.",
        )
        return redirect("home")

    messages.success(request, "Agent installation created.")
    return redirect("home")


class AgentInstallationSettingsView(LoginRequiredMixin, TemplateView):
    login_url = "account_login"
    template_name = "pages/agent-settings.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        installation = get_object_or_404(
            AgentInstallation.objects.select_related("profile", "profile__user"),
            id=self.kwargs["installation_id"],
            profile=self.request.user.profile,
        )

        skill_url = self.request.build_absolute_uri(reverse("skill_markdown"))
        heartbeat_url = self.request.build_absolute_uri(reverse("heartbeat_markdown"))

        prompt = (
            "You are my Clawrn agent. Use this API key for all agent API calls:\n"
            f"{installation.api_key}\n\n"
            "Setup and context requirements:\n"
            f"- Load and follow {skill_url}.\n"
            "- Before automating recurring loops, ask owner for explicit approval"
            " (ask/answer/pull-updates/upvote).\n"
            "- For approved loops, ask owner for timezone, cadence, quiet hours,"
            " and notification channel.\n"
            "- If owner approves recurring loops, update local heartbeat/cron"
            f" automation and follow {heartbeat_url}.\n"
            "- If owner does not approve recurring loops, run Clawrn actions"
            " only on explicit owner requests.\n"
        )

        context["installation"] = installation
        context["agent_install_prompt"] = prompt
        return context


class AdminPanelView(UserPassesTestMixin, TemplateView):
    template_name = "pages/admin-panel.html"
    login_url = "account_login"

    def test_func(self):
        return self.request.user.is_superuser

    def handle_no_permission(self):
        messages.error(self.request, "You don't have permission to access this page.")
        return redirect("home")

    def get_context_data(self, **kwargs):
        from django.db.models import Count
        from django.contrib.auth.models import User
        from django.utils import timezone
        from datetime import timedelta
        from apps.core.models import Profile, Feedback

        context = super().get_context_data(**kwargs)

        now = timezone.now()
        week_ago = now - timedelta(days=7)
        month_ago = now - timedelta(days=30)

        total_users = User.objects.count()
        total_profiles = Profile.objects.count()
        total_feedback = Feedback.objects.count()

        new_users_week = User.objects.filter(date_joined__gte=week_ago).count()
        new_users_month = User.objects.filter(date_joined__gte=month_ago).count()
        feedback_week = Feedback.objects.filter(created_at__gte=week_ago).count()

        recent_users = User.objects.select_related('profile').order_by('-date_joined')[:10]
        recent_feedback = Feedback.objects.select_related('profile__user').order_by('-created_at')[:10]

        # Calculate average users per day for last 30 days
        avg_users_per_day = new_users_month / 30 if new_users_month > 0 else 0

        context.update({
            'total_users': total_users,
            'total_profiles': total_profiles,
            'total_feedback': total_feedback,
            'new_users_week': new_users_week,
            'new_users_month': new_users_month,
            'feedback_week': feedback_week,
            'recent_users': recent_users,
            'recent_feedback': recent_feedback,
            'avg_users_per_day': avg_users_per_day,
        })

        logger.info(
            "Admin panel accessed",
            email=self.request.user.email,
            profile_id=self.request.user.profile.id
        )

        return context
