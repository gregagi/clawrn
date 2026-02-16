from django.http import HttpRequest
from django.db import connection
from django.core.cache import cache
from ninja import NinjaAPI
from ninja.errors import HttpError

from apps.api.auth import session_auth, superuser_api_auth
from apps.core.models import Feedback
from apps.api.schemas import (
    SubmitFeedbackIn,
    SubmitFeedbackOut,ProfileSettingsOut,
    UserSettingsOut,
)

from agent_commons.utils import get_agent_commons_logger

logger = get_agent_commons_logger(__name__)

api = NinjaAPI()

@api.get("/healthcheck", auth=None, include_in_schema=False, tags=["private"])
def healthcheck(request: HttpRequest):
    """
    Comprehensive healthcheck endpoint for monitoring and load balancers.
    Checks database and Redis connectivity.
    Returns 200 OK if all services are healthy, 503 if any service is down.
    """
    health_status = {
        "status": "healthy",
        "checks": {
            "database": "unknown",
            "redis": "unknown",
        }
    }

    all_healthy = True

    # Check database connectivity
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
        health_status["checks"]["database"] = "healthy"
    except Exception as e:
        health_status["checks"]["database"] = "unhealthy"
        all_healthy = False
        logger.error(
            "Healthcheck failed: Database connection error",
            error=str(e),
            exc_info=True
        )

    # Check Redis connectivity
    try:
        cache_key = "healthcheck_test"
        cache_value = "ok"
        cache.set(cache_key, cache_value, timeout=10)
        retrieved_value = cache.get(cache_key)

        if retrieved_value == cache_value:
            health_status["checks"]["redis"] = "healthy"
        else:
            health_status["checks"]["redis"] = "unhealthy"
            all_healthy = False
            logger.error(
                "Healthcheck failed: Redis value mismatch",
                expected=cache_value,
                retrieved=retrieved_value
            )
    except Exception as e:
        health_status["checks"]["redis"] = "unhealthy"
        all_healthy = False
        logger.error(
            "Healthcheck failed: Redis connection error",
            error=str(e),
            exc_info=True
        )

    # Update overall status
    if all_healthy:
        health_status["status"] = "healthy"
        logger.info(
            "Healthcheck passed: All services healthy",
            database=health_status["checks"]["database"],
            redis=health_status["checks"]["redis"]
        )
        return health_status
    else:
        health_status["status"] = "unhealthy"
        logger.error(
            "Healthcheck failed: One or more services unhealthy",
            database=health_status["checks"]["database"],
            redis=health_status["checks"]["redis"]
        )
        return 503, health_status


@api.post(
    "/submit-feedback",
    response=SubmitFeedbackOut,
    auth=[session_auth],
    include_in_schema=False,
    tags=["private"],
)
def submit_feedback(request: HttpRequest, data: SubmitFeedbackIn):
    profile = request.auth
    try:
        Feedback.objects.create(profile=profile, feedback=data.feedback, page=data.page)
        return {"status": True, "message": "Feedback submitted successfully"}
    except Exception as e:
        logger.error("Failed to submit feedback", error=str(e), profile_id=profile.id)
        return {"status": False, "message": "Failed to submit feedback. Please try again."}




@api.get(
    "/user/settings",
    response=UserSettingsOut,
    auth=[session_auth],
    include_in_schema=False,
    tags=["private"],
)
def user_settings(request: HttpRequest):
    profile = request.auth
    try:
        profile_data = {
            "has_pro_subscription": profile.has_active_subscription,
        }
        data = {"profile": profile_data}

        return data
    except Exception as e:
        logger.error(
            "Error fetching user settings",
            error=str(e),
            profile_id=profile.id,
            exc_info=True,
        )
        raise HttpError(500, "An unexpected error occurred.")
