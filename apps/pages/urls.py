from django.urls import path

from apps.pages import views

urlpatterns = [
    path("", views.LandingPageView.as_view(), name="landing"),
    path("skill.md", views.skill_markdown, name="skill_markdown"),
    path("heartbeat.md", views.heartbeat_markdown, name="heartbeat_markdown"),
    path("privacy-policy", views.PrivacyPolicyView.as_view(), name="privacy_policy"),
    path("terms-of-service", views.TermsOfServiceView.as_view(), name="terms_of_service"),
]
