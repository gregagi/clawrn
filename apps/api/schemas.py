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
