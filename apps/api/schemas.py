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
