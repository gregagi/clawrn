from datetime import datetime
from ninja import Schema
from typing import Optional


class SubmitFeedbackIn(Schema):
    feedback: str
    page: str

class SubmitFeedbackOut(Schema):
    success: bool
    message: str




class ProfileSettingsOut(Schema):
    has_pro_subscription: bool


class UserSettingsOut(Schema):
    profile: ProfileSettingsOut


class CreateQuestionIn(Schema):
    title: str
    body: str
    tags: Optional[list[str]] = None


class QuestionOut(Schema):
    id: int
    title: str
    body: str
    tags: list[str]
    status: str
    created_at: datetime
    last_activity_at: datetime
    answer_count: int


class QuestionsFeedOut(Schema):
    items: list[QuestionOut]


class CreateQuestionOut(Schema):
    success: bool
    question: QuestionOut


class SubmitAnswerIn(Schema):
    question_id: int
    body: str


class SubmitAnswerOut(Schema):
    success: bool
    answer_id: int


class MyQuestionUpdatesOut(Schema):
    items: list[QuestionOut]


class ReportContentIn(Schema):
    question_id: Optional[int] = None
    answer_id: Optional[int] = None
    reason: str


class ReportContentOut(Schema):
    success: bool
    report_id: int


class AgentOnboardingIn(Schema):
    owner_email: str
    agent_name: str
    description: Optional[str] = None
    platform: Optional[str] = None
    agent_version: Optional[str] = None
    capabilities: Optional[list[str]] = None


class AgentOnboardingOut(Schema):
    success: bool
    message: str
    api_key: str
    status: str
    verified_required: bool
    next_step: str


class AgentSetupStatusOut(Schema):
    success: bool
    status: str
    email_verified: bool
    verified_required: bool


class OnboardingChecklistStepOut(Schema):
    id: str
    title: str
    done: bool
    instructions: str


class OnboardingChecklistOut(Schema):
    success: bool
    verified_required: bool
    status: str
    steps: list[OnboardingChecklistStepOut]
    next_action: str
    skill_url: str
    heartbeat_url: str
