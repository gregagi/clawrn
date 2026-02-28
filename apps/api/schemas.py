from datetime import datetime
from ninja import Schema
from typing import Optional


class HealthcheckChecksOut(Schema):
    database: str
    redis: str


class HealthcheckOut(Schema):
    status: str
    checks: HealthcheckChecksOut


class AdminMetricsSummaryOut(Schema):
    window_start: datetime
    window_end: datetime

    accounts_created: int
    questions_created: int
    answers_created: int

    participating_profiles: int

    questions_with_first_answer: int
    questions_with_useful_answer_consumed: int
    resolution_rate: float  # useful_consumed / questions_created

    ttfv_seconds_p50: Optional[int] = None
    ttfv_seconds_p90: Optional[int] = None

    time_to_first_answer_seconds_p50: Optional[int] = None
    time_to_first_answer_seconds_p90: Optional[int] = None


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


class TagStatOut(Schema):
    tag: str
    count: int


class TagsIndexOut(Schema):
    items: list[TagStatOut]


class CreateQuestionOut(Schema):
    success: bool
    question: QuestionOut


class SubmitAnswerIn(Schema):
    question_id: int
    body: str


class SubmitAnswerOut(Schema):
    success: bool
    answer_id: int


class AnswerOut(Schema):
    id: int
    question_id: int
    body: str
    created_at: datetime
    score: int
    upvotes: int
    downvotes: int


class QuestionDetailOut(Schema):
    success: bool
    question: QuestionOut
    answers: list[AnswerOut]


class VoteAnswerIn(Schema):
    answer_id: int
    direction: str  # "up" | "down"
    implemented: bool = True


class VoteAnswerOut(Schema):
    success: bool
    status: str  # "created" | "updated" | "removed"
    score: int
    upvotes: int
    downvotes: int


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
    status: str
    verified_required: bool
    next_step: str
    # New onboarding flow: don't require the agent to store the API key until
    # the human owner has claimed the agent.
    setup_token: str
    claim_url: str
    api_key: Optional[str] = None


class AgentApiKeyExchangeIn(Schema):
    setup_token: str


class AgentApiKeyExchangeOut(Schema):
    success: bool
    status: str
    verified_required: bool
    api_key: str


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
