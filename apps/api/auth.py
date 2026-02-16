from django.http import HttpRequest

from apps.api.utils import _get_api_key_from_headers
from apps.core.models import Profile

from agent_commons.utils import get_agent_commons_logger

logger = get_agent_commons_logger(__name__)


def _mask_api_key(key: str | None) -> str:
    if not key:
        return "<missing>"
    if len(key) <= 8:
        return "***"
    return f"{key[:4]}...{key[-4:]}"


class APIKeyAuth:
    param_name = "api_key"

    def authenticate(self, request: HttpRequest) -> Profile | None:
        key = request.GET.get(self.param_name) or _get_api_key_from_headers(request)
        if not key:
            return None

        logger.info(
            "[Django Ninja Auth] API request with API key",
            key_masked=_mask_api_key(key),
        )
        try:
            return Profile.objects.get(key=key)
        except Profile.DoesNotExist:
            logger.warning(
                "[Django Ninja Auth] Invalid API key",
                key_masked=_mask_api_key(key),
            )
            return None

    def __call__(self, request: HttpRequest):
        return self.authenticate(request)


class SessionAuth:
    """Authentication via Django session"""

    def authenticate(self, request: HttpRequest) -> Profile | None:
        if hasattr(request, "user") and request.user.is_authenticated:
            logger.info(
                "[Django Ninja Auth] API Request with authenticated user",
                user_id=request.user.id,
            )
            try:
                return request.user.profile
            except Profile.DoesNotExist:
                logger.warning("[Django Ninja Auth] No profile for user", user_id=request.user.id)
                return None
        return None

    def __call__(self, request: HttpRequest):
        return self.authenticate(request)


class SuperuserAPIKeyAuth:
    param_name = "api_key"

    def authenticate(self, request: HttpRequest) -> Profile | None:
        key = request.GET.get(self.param_name) or _get_api_key_from_headers(request)
        if not key:
            return None

        try:
            profile = Profile.objects.get(key=key)
            if profile.user.is_superuser:
                return profile
            logger.warning(
                "[Django Ninja Auth] Non-superuser attempted admin access",
                profile_id=profile.user.id,
            )
            return None
        except Profile.DoesNotExist:
            logger.warning(
                "[Django Ninja Auth] Profile does not exist",
                key_masked=_mask_api_key(key),
            )
            return None

    def __call__(self, request: HttpRequest):
        return self.authenticate(request)


api_key_auth = APIKeyAuth()
session_auth = SessionAuth()
superuser_api_auth = SuperuserAPIKeyAuth()
