from django.db import models
from django.utils import timezone

from apps.core.base_models import BaseModel
from apps.core.models import Profile


class AgentInstallation(BaseModel):
    profile = models.ForeignKey(
        Profile,
        on_delete=models.CASCADE,
        related_name="agent_installations",
    )
    agent_name = models.CharField(max_length=120)
    platform = models.CharField(max_length=120, blank=True)
    agent_version = models.CharField(max_length=64, blank=True)
    capabilities = models.JSONField(default=list, blank=True)
    is_active = models.BooleanField(default=True)
    last_seen_at = models.DateTimeField(default=timezone.now)

    class Meta:
        unique_together = ("profile", "agent_name", "platform")
        ordering = ["-last_seen_at"]

    def __str__(self):
        platform_suffix = f" on {self.platform}" if self.platform else ""
        return f"{self.agent_name}{platform_suffix} ({self.profile.user.email})"


class QuestionStatus(models.TextChoices):
    OPEN = "open", "Open"
    ANSWERED = "answered", "Answered"
    CLOSED = "closed", "Closed"


class Question(BaseModel):
    author = models.ForeignKey(
        Profile,
        on_delete=models.CASCADE,
        related_name="questions",
    )
    title = models.CharField(max_length=200)
    body = models.TextField()
    tags = models.JSONField(default=list, blank=True)
    status = models.CharField(
        max_length=20,
        choices=QuestionStatus.choices,
        default=QuestionStatus.OPEN,
    )
    last_activity_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-last_activity_at", "-created_at"]
        indexes = [
            models.Index(fields=["status", "-last_activity_at"]),
        ]

    def __str__(self):
        return self.title


class Answer(BaseModel):
    question = models.ForeignKey(
        Question,
        on_delete=models.CASCADE,
        related_name="answers",
    )
    author = models.ForeignKey(
        Profile,
        on_delete=models.CASCADE,
        related_name="answers",
    )
    body = models.TextField()
    is_accepted = models.BooleanField(default=False)

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        return f"Answer by {self.author.user.email} on {self.question_id}"

    def save(self, *args, **kwargs):
        is_new = self._state.adding
        super().save(*args, **kwargs)

        if is_new:
            Question.objects.filter(pk=self.question_id).update(
                last_activity_at=timezone.now(),
                status=QuestionStatus.ANSWERED,
            )
