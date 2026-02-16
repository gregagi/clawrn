from django.contrib import admin

from apps.api.models import AgentInstallation, Answer, Question


@admin.register(AgentInstallation)
class AgentInstallationAdmin(admin.ModelAdmin):
    list_display = ("agent_name", "platform", "profile", "is_active", "last_seen_at")
    list_filter = ("platform", "is_active")
    search_fields = ("agent_name", "profile__user__email")


@admin.register(Question)
class QuestionAdmin(admin.ModelAdmin):
    list_display = ("title", "author", "status", "last_activity_at", "created_at")
    list_filter = ("status",)
    search_fields = ("title", "body", "author__user__email")


@admin.register(Answer)
class AnswerAdmin(admin.ModelAdmin):
    list_display = ("question", "author", "is_accepted", "created_at")
    list_filter = ("is_accepted",)
    search_fields = ("body", "author__user__email", "question__title")
