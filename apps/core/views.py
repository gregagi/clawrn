from urllib.parse import urlencode


from allauth.account.models import EmailAddress, EmailConfirmation
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.core.cache import cache
from django.http import HttpResponse, HttpResponseBadRequest
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django.contrib.messages.views import SuccessMessageMixin
from django.shortcuts import redirect
from django.conf import settings
from django.contrib import messages
from django.urls import reverse, reverse_lazy
from django.views.generic import TemplateView, UpdateView



from apps.core.forms import ProfileUpdateForm
from apps.core.models import Profile

from agent_commons.utils import get_agent_commons_logger



logger = get_agent_commons_logger(__name__)


class HomeView(LoginRequiredMixin, TemplateView):
    login_url = "account_login"
    template_name = "pages/home.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        

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

        email_address = EmailAddress.objects.get_for_user(user, user.email)
        context["email_verified"] = email_address.verified
        context["resend_confirmation_url"] = reverse("resend_confirmation")
        
        context["api_key"] = user.profile.key


        return context

@login_required
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


