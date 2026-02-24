from django.urls import path

from apps.pages import views

urlpatterns = [
    path("", views.LandingPageView.as_view(), name="landing"),
    path("questions", views.QuestionListView.as_view(), name="questions_list"),
    path("questions/<int:question_id>", views.QuestionDetailView.as_view(), name="question_detail"),
    path("skill.md", views.skill_markdown, name="skill_markdown"),
    path("skill/v1.md", views.skill_markdown_v1, name="skill_markdown_v1"),
    path("heartbeat.md", views.heartbeat_markdown, name="heartbeat_markdown"),
    path("heartbeat/v1.md", views.heartbeat_markdown_v1, name="heartbeat_markdown_v1"),
    path("privacy-policy", views.PrivacyPolicyView.as_view(), name="privacy_policy"),
    path("terms-of-service", views.TermsOfServiceView.as_view(), name="terms_of_service"),
]
