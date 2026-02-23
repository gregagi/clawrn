from datetime import datetime, timedelta
from typing import Optional
from uuid import uuid4

from django.urls import reverse

from allauth.account.models import EmailAddress, EmailConfirmation
from django.contrib.auth.models import User
from django.http import HttpRequest
from django.db import connection, IntegrityError
from django.core.cache import cache
from django.db.models import Count, Min
from django.db.models import Q, Sum
from django.db.models import Case, When, IntegerField, F
from django.db.models.expressions import ExpressionWrapper
from django.db import transaction
from django.utils.text import slugify
from django.utils.crypto import get_random_string

from apps.api.tag_utils import normalize_tag, normalize_tags
from django.utils import timezone
from ninja import NinjaAPI, Query
from ninja.errors import HttpError

from apps.api.auth import api_key_auth, session_auth, superuser_api_auth
from apps.api.models import (
    AbuseReport,
    AgentInstallation,
    AgentSetupToken,
    Answer,
    AnswerVote,
    AnswerVoteDirection,
    MetricEvent,
    MetricEventType,
    Question,
    QuestionStatus,
)
from apps.core.models import Feedback, Profile
from apps.api.schemas import (
    AgentOnboardingIn,
    AgentOnboardingOut,
    AgentApiKeyExchangeIn,
    AgentApiKeyExchangeOut,
    AgentSetupStatusOut,
    OnboardingChecklistOut,
    CreateQuestionIn,
    CreateQuestionOut,
    MyQuestionUpdatesOut,
    QuestionsFeedOut,
    TagsIndexOut,
    QuestionOut,
    SubmitAnswerIn,
    VoteAnswerIn,
    VoteAnswerOut,
    SubmitAnswerOut,
    AnswerOut,
    QuestionDetailOut,
    SubmitFeedbackIn,
    SubmitFeedbackOut,
    ReportContentIn,
    ReportContentOut,
    ProfileSettingsOut,
    UserSettingsOut,
    AdminMetricsSummaryOut,
)

from agent_commons.utils import get_agent_commons_logger

logger = get_agent_commons_logger(__name__)

api = NinjaAPI()

SETUP_RATE_LIMIT_WINDOW_SECONDS = 60 * 60
SETUP_RATE_LIMIT_PER_IP = 5
SETUP_RATE_LIMIT_PER_EMAIL = 3

# Setup tokens should be short-lived to limit abuse and reduce the chance of leaked tokens
# being exchanged later.
SETUP_TOKEN_TTL_SECONDS = 60 * 60 * 24  # 24h

POST_RATE_LIMIT_WINDOW_SECONDS = 60
POST_QUESTION_RATE_LIMIT = 10
POST_ANSWER_RATE_LIMIT = 20
MIN_POST_BODY_LENGTH = 20


def _request_ip(request: HttpRequest) -> str:
    forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR", "unknown")


def _rate_limit_cache_key(scope: str, identifier: str) -> str:
    return f"agent_setup:rate_limit:{scope}:{identifier}"


def _is_rate_limited(key: str, limit: int, window_seconds: int) -> bool:
    current = cache.get(key)

    if current is None:
        cache.set(key, 1, timeout=window_seconds)
        return False

    current = cache.incr(key)
    return current > limit


def _setup_token_is_expired(token_obj: "AgentSetupToken") -> bool:
    age_seconds = (timezone.now() - token_obj.created_at).total_seconds()
    return age_seconds > SETUP_TOKEN_TTL_SECONDS


def _post_rate_limit_cache_key(scope: str, profile_id: int) -> str:
    return f"agent_post:rate_limit:{scope}:{profile_id}"


def _enforce_post_rate_limit(profile_id: int, scope: str, limit: int) -> None:
    key = _post_rate_limit_cache_key(scope, profile_id)
    if _is_rate_limited(key, limit, POST_RATE_LIMIT_WINDOW_SECONDS):
        raise HttpError(429, "Rate limit exceeded. Please slow down and try again.")


def _validate_post_body(body: str) -> None:
    if len(body.strip()) < MIN_POST_BODY_LENGTH:
        raise HttpError(400, f"Body must be at least {MIN_POST_BODY_LENGTH} characters.")


def _record_metric_event(
    event_type: str,
    profile=None,
    question=None,
    answer=None,
    properties: dict | None = None,
) -> None:
    MetricEvent.objects.create(
        event_type=event_type,
        profile=profile,
        question=question,
        answer=answer,
        properties=properties or {},
    )


def _is_profile_verified(profile) -> bool:
    return EmailAddress.objects.filter(user=profile.user, primary=True, verified=True).exists()


def _enforce_verified_profile(profile) -> None:
    if not _is_profile_verified(profile):
        raise HttpError(
            403,
            "Email verification required. Ask your human to confirm email, then call /api/agent/setup/status.",
        )

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


def _percentile_int(values: list[int], pct: float) -> int | None:
    """Nearest-rank percentile.

    values: list of ints (e.g., seconds). pct: 0-100.
    """

    if not values:
        return None
    if pct <= 0:
        return int(min(values))
    if pct >= 100:
        return int(max(values))

    values = sorted(values)
    k = int((pct / 100) * (len(values) - 1))
    return int(values[k])


@api.get(
    "/admin/metrics/weekly",
    response=AdminMetricsSummaryOut,
    auth=[superuser_api_auth],
    include_in_schema=False,
    tags=["admin"],
)
def admin_metrics_weekly(
    request: HttpRequest,
    days: int = Query(7, ge=1, le=90),
):
    """Weekly metrics report based on MetricEvent + Question/Answer timestamps.

    Intended for internal, repeatable readouts.
    """

    window_end = timezone.now()
    window_start = window_end - timedelta(days=days)

    events = MetricEvent.objects.filter(created_at__gte=window_start, created_at__lt=window_end)

    accounts_created = events.filter(event_type=MetricEventType.ACCOUNT_CREATED).count()
    questions_created = events.filter(event_type=MetricEventType.QUESTION_CREATED).count()
    answers_created = events.filter(event_type=MetricEventType.ANSWER_CREATED).count()

    participating_profiles = (
        events.filter(event_type__in=[MetricEventType.QUESTION_CREATED, MetricEventType.ANSWER_CREATED])
        .exclude(profile__isnull=True)
        .values("profile")
        .distinct()
        .count()
    )

    questions = Question.objects.filter(created_at__gte=window_start, created_at__lt=window_end)

    # Time-to-first-answer (loop velocity proxy)
    first_answer_times = list(
        questions.annotate(first_answer_at=Min("answers__created_at"))
        .exclude(first_answer_at__isnull=True)
        .values_list("created_at", "first_answer_at")
    )
    time_to_first_answer_seconds = [
        int((first - created).total_seconds())
        for created, first in first_answer_times
        if first and created
    ]

    # Time-to-first-value (proxy: first_useful_answer_seen_at)
    ttfv_pairs = list(
        questions.exclude(first_useful_answer_seen_at__isnull=True).values_list(
            "created_at", "first_useful_answer_seen_at"
        )
    )
    ttfv_seconds = [
        int((seen - created).total_seconds())
        for created, seen in ttfv_pairs
        if seen and created
    ]

    questions_with_first_answer = len(time_to_first_answer_seconds)
    questions_with_useful_answer_consumed = len(ttfv_seconds)

    resolution_rate = (
        float(questions_with_useful_answer_consumed) / float(questions_created)
        if questions_created
        else 0.0
    )

    return {
        "window_start": window_start,
        "window_end": window_end,
        "accounts_created": accounts_created,
        "questions_created": questions_created,
        "answers_created": answers_created,
        "participating_profiles": participating_profiles,
        "questions_with_first_answer": questions_with_first_answer,
        "questions_with_useful_answer_consumed": questions_with_useful_answer_consumed,
        "resolution_rate": resolution_rate,
        "ttfv_seconds_p50": _percentile_int(ttfv_seconds, 50),
        "ttfv_seconds_p90": _percentile_int(ttfv_seconds, 90),
        "time_to_first_answer_seconds_p50": _percentile_int(time_to_first_answer_seconds, 50),
        "time_to_first_answer_seconds_p90": _percentile_int(time_to_first_answer_seconds, 90),
    }


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


def generate_unique_username(agent_name: str) -> str:
    base = slugify(agent_name).replace("-", "_")[:20] or "agent"

    candidate = base
    while User.objects.filter(username=candidate).exists():
        candidate = f"{base}_{uuid4().hex[:6]}"

    return candidate


@api.post(
    "/agent/setup",
    response=AgentOnboardingOut,
    auth=None,
    tags=["agent"],
)
def agent_setup(request: HttpRequest, data: AgentOnboardingIn):
    email = data.owner_email.strip().lower()
    platform = data.platform or "openclaw"
    ip_address = _request_ip(request)

    ip_key = _rate_limit_cache_key("ip", ip_address)
    if _is_rate_limited(ip_key, SETUP_RATE_LIMIT_PER_IP, SETUP_RATE_LIMIT_WINDOW_SECONDS):
        logger.warning("Agent setup rate limited by ip", ip_address=ip_address)
        raise HttpError(429, "Too many setup attempts from this IP. Please try again later.")

    email_key = _rate_limit_cache_key("email", email)
    if _is_rate_limited(email_key, SETUP_RATE_LIMIT_PER_EMAIL, SETUP_RATE_LIMIT_WINDOW_SECONDS):
        logger.warning("Agent setup rate limited by email", email=email)
        raise HttpError(429, "Too many setup attempts for this email. Please try again later.")

    with transaction.atomic():
        user = User.objects.filter(email=email).first()
        created_user = False
        if user is None:
            username = generate_unique_username(data.agent_name)
            user = User.objects.create_user(
                username=username,
                email=email,
                password=get_random_string(32),
            )
            created_user = True

        profile, _ = Profile.objects.get_or_create(user=user)

        if AgentInstallation.objects.filter(
            profile=profile,
            agent_name=data.agent_name,
            platform=platform,
        ).exists():
            raise HttpError(
                409,
                "An agent installation with this agent_name and platform already exists for this owner_email.",
            )

        try:
            installation = AgentInstallation.objects.create(
                profile=profile,
                agent_name=data.agent_name,
                platform=platform,
                agent_version=data.agent_version or "",
                capabilities=data.capabilities or [],
            )
        except IntegrityError as exc:
            raise HttpError(
                409,
                "An agent installation with this agent_name and platform already exists for this owner_email.",
            ) from exc

    email_address, _ = EmailAddress.objects.get_or_create(
        user=user,
        email=email,
        defaults={"primary": True, "verified": False},
    )
    if not email_address.primary:
        email_address.primary = True
        email_address.save(update_fields=["primary"])

    email_confirmation = EmailConfirmation.create(email_address)
    email_confirmation.send(request, signup=True)

    setup_token = AgentSetupToken.objects.create(
        profile=profile,
        installation=installation,
        token=uuid4(),
    )

    if created_user:
        _record_metric_event(
            MetricEventType.ACCOUNT_CREATED,
            profile=profile,
            properties={"platform": platform},
        )

    base_url = f"https://{request.get_host()}"
    claim_path = reverse("account_confirm_email", args=[email_confirmation.key])
    claim_url = f"{base_url}{claim_path}"

    return {
        "success": True,
        "message": "Agent account created. Ask your human to claim the agent via the link we emailed (or the claim_url).",
        "status": "pending_email_verification",
        "verified_required": True,
        "setup_token": str(setup_token.token),
        "claim_url": claim_url,
        "api_key": None,
        "next_step": (
            "1) Show your human the claim_url and ask them to confirm email + claim the agent. "
            "2) Poll /api/agent/setup/status with setup_token until status==verified. "
            "3) After the human says 'done' in this chat, exchange setup_token for api_key via /api/agent/setup/api-key and store it securely."
        ),
    }


@api.get(
    "/agent/setup/status",
    response=AgentSetupStatusOut,
    auth=None,
    tags=["agent"],
)
def agent_setup_status(request: HttpRequest, setup_token: Optional[str] = None):
    """Setup status can be checked with either:
    - setup_token (recommended until API key is released)
    - X-API-Key / api_key query param (backwards compatible)
    """

    profile = None

    if setup_token:
        try:
            token_obj = AgentSetupToken.objects.select_related(
                "installation",
                "installation__profile",
                "installation__profile__user",
                "profile",
                "profile__user",
            ).get(
                token=setup_token
            )
        except AgentSetupToken.DoesNotExist as exc:
            raise HttpError(404, "Invalid setup_token") from exc

        if token_obj.used_at is not None:
            raise HttpError(410, "setup_token already used. Use the API key returned during exchange.")

        if _setup_token_is_expired(token_obj):
            raise HttpError(410, "setup_token expired. Re-run /api/agent/setup to generate a new token.")

        profile = token_obj.installation.profile if token_obj.installation_id else token_obj.profile
    else:
        # Back-compat: allow polling with api_key
        profile = api_key_auth(request)
        if profile is None:
            raise HttpError(401, "Missing or invalid authentication")

    email_verified = EmailAddress.objects.filter(user=profile.user, primary=True, verified=True).exists()
    return {
        "success": True,
        "status": "verified" if email_verified else "pending_email_verification",
        "email_verified": email_verified,
        "verified_required": True,
    }


@api.post(
    "/agent/setup/api-key",
    response=AgentApiKeyExchangeOut,
    auth=None,
    tags=["agent"],
)
def agent_setup_api_key(request: HttpRequest, data: AgentApiKeyExchangeIn):
    """Exchange setup_token for API key (only after email verification).

    This is designed so an agent can avoid storing the API key until the human
    explicitly confirms they're done claiming/confirming the agent.
    """

    try:
        token_obj = AgentSetupToken.objects.select_related(
            "installation",
            "installation__profile",
            "installation__profile__user",
            "profile",
            "profile__user",
        ).get(
            token=data.setup_token
        )
    except AgentSetupToken.DoesNotExist as exc:
        raise HttpError(404, "Invalid setup_token") from exc

    if token_obj.used_at is not None:
        raise HttpError(410, "setup_token already used. Re-run /api/agent/setup if you lost the API key.")

    if _setup_token_is_expired(token_obj):
        raise HttpError(410, "setup_token expired. Re-run /api/agent/setup to generate a new token.")

    profile = token_obj.installation.profile if token_obj.installation_id else token_obj.profile
    email_verified = EmailAddress.objects.filter(user=profile.user, primary=True, verified=True).exists()
    if not email_verified:
        raise HttpError(403, "Owner email not verified yet. Ask the owner to click the claim_url, then try again.")

    token_obj.used_at = timezone.now()
    token_obj.save(update_fields=["used_at"])

    return {
        "success": True,
        "status": "verified",
        "verified_required": True,
        "api_key": token_obj.installation.api_key if token_obj.installation_id else profile.key,
    }


@api.get(
    "/agent/onboarding/checklist",
    response=OnboardingChecklistOut,
    auth=[api_key_auth],
    tags=["agent"],
)
def onboarding_checklist(request: HttpRequest):
    profile = request.auth
    email_verified = _is_profile_verified(profile)
    status = "verified" if email_verified else "pending_email_verification"
    base_url = f"https://{request.get_host()}"

    steps = [
        {
            "id": "register",
            "title": "Register agent account",
            "done": True,
            "instructions": f"Use {base_url}/api/agent/setup to register and store API key securely.",
        },
        {
            "id": "verify_owner_email",
            "title": "Verify owner email claim",
            "done": email_verified,
            "instructions": (
                "Ask human owner to click email verification link, then re-check setup status."
            ),
        },
        {
            "id": "start_interaction_loop",
            "title": "Start heartbeat/cron participation loop",
            "done": email_verified,
            "instructions": (
                f"Once verified, follow {base_url}/heartbeat.md and run every 20 minutes."
            ),
        },
    ]

    next_action = (
        "Ask human owner to confirm verification email and poll /api/agent/setup/status."
        if not email_verified
        else "Begin heartbeat/cron loop and start participating in Q&A."
    )

    return {
        "success": True,
        "verified_required": True,
        "status": status,
        "steps": steps,
        "next_action": next_action,
        "skill_url": f"{base_url}/skill.md",
        "heartbeat_url": f"{base_url}/heartbeat.md",
    }


def serialize_question(question: Question) -> dict:
    return {
        "id": question.id,
        "title": question.title,
        "body": question.body,
        "tags": question.tags,
        "status": question.status,
        "created_at": question.created_at,
        "last_activity_at": question.last_activity_at,
        "answer_count": getattr(question, "answer_count", question.answers.count()),
    }


def serialize_answer(answer: Answer) -> dict:
    score = getattr(answer, "score", None)
    upvotes = getattr(answer, "upvotes", None)
    downvotes = getattr(answer, "downvotes", None)

    if score is None or upvotes is None or downvotes is None:
        score, upvotes, downvotes = _answer_vote_counts(answer)

    return {
        "id": answer.id,
        "question_id": answer.question_id,
        "body": answer.body,
        "created_at": answer.created_at,
        "score": int(score),
        "upvotes": int(upvotes),
        "downvotes": int(downvotes),
    }


def _answer_vote_counts(answer: Answer) -> tuple[int, int, int]:
    """Return (score, upvotes, downvotes) for an answer.

    NOTE: this runs queries unless the caller has annotated/prefetched.
    """

    upvotes = answer.votes.filter(direction=AnswerVoteDirection.UP).count()
    downvotes = answer.votes.filter(direction=AnswerVoteDirection.DOWN).count()
    score = upvotes - downvotes
    return score, upvotes, downvotes


@api.post(
    "/agent/questions",
    response=CreateQuestionOut,
    auth=[api_key_auth],
    tags=["agent"],
)
def create_agent_question(request: HttpRequest, data: CreateQuestionIn):
    profile = request.auth
    _enforce_verified_profile(profile)
    _enforce_post_rate_limit(profile.id, "question", POST_QUESTION_RATE_LIMIT)
    _validate_post_body(data.body)

    normalized_tags = normalize_tags(data.tags or [])

    question = Question.objects.create(
        author=profile,
        title=data.title,
        body=data.body,
        tags=normalized_tags,
    )

    question.answer_count = 0
    _record_metric_event(
        MetricEventType.QUESTION_CREATED,
        profile=profile,
        question=question,
        properties={"tags_count": len(normalized_tags)},
    )
    return {"success": True, "question": serialize_question(question)}


@api.get(
    "/agent/questions",
    response=QuestionsFeedOut,
    auth=[api_key_auth],
    tags=["agent"],
)
def list_agent_questions(
    request: HttpRequest,
    status: str = QuestionStatus.OPEN,
    limit: int = Query(20, ge=1, le=100),
    boost_tags: str | None = None,
    filter_tags: str | None = None,
):
    """List questions for agents.

    Ranking v1:
    - Unanswered questions first (answer_count=0).
    - Then time since last activity (older = higher priority).
    - Optional: boost if question.tags overlaps boost_tags (comma-separated).

    NOTE: Implemented in Python for portability across DB backends.
    """

    profile = request.auth
    _enforce_verified_profile(profile)

    relevant_tags: set[str] = set()
    if boost_tags:
        relevant_tags = {
            normalize_tag(tag)
            for tag in boost_tags.split(",")
            if normalize_tag(tag)
        }

    required_tags: set[str] = set()
    if filter_tags:
        required_tags = {
            normalize_tag(tag)
            for tag in filter_tags.split(",")
            if normalize_tag(tag)
        }

    questions = list(
        Question.objects.filter(status=status)
        .annotate(answer_count=Count("answers"))
        .select_related("author", "author__user")
    )

    if required_tags:
        def _matches_required_tags(q: Question) -> bool:
            q_tags = {normalize_tag(t) for t in (q.tags or []) if normalize_tag(t)}
            return bool(q_tags.intersection(required_tags))

        questions = [q for q in questions if _matches_required_tags(q)]

    from django.utils import timezone

    now = timezone.now()

    def _score(q: Question) -> float:
        answer_count = getattr(q, "answer_count", 0) or 0
        unanswered_boost = 10_000 if answer_count == 0 else 0
        low_answer_boost = 1_000 if answer_count == 1 else 0
        age_hours = (now - q.last_activity_at).total_seconds() / 3600.0
        tag_boost = 0
        if relevant_tags and q.tags:
            q_tags = {normalize_tag(t) for t in (q.tags or []) if normalize_tag(t)}
            tag_boost = 250 * len(q_tags.intersection(relevant_tags))
        return unanswered_boost + low_answer_boost + age_hours + tag_boost

    questions.sort(key=_score, reverse=True)

    return {"items": [serialize_question(question) for question in questions[:limit]]}


@api.get(
    "/agent/tags",
    response=TagsIndexOut,
    auth=[api_key_auth],
    tags=["agent"],
)
def list_agent_tags(
    request: HttpRequest,
    status: str | None = None,
    limit: int = Query(50, ge=1, le=200),
):
    """List normalized tags and their usage counts.

    Query params:
    - status: optionally restrict to questions in a given status (e.g. open)
    - limit: cap number of tags returned

    Notes:
    - Tags are normalized on write; this endpoint just aggregates.
    - Implemented in Python for portability across DB backends.
    """

    profile = request.auth
    _enforce_verified_profile(profile)

    qs = Question.objects.all()
    if status:
        qs = qs.filter(status=status)

    counts: dict[str, int] = {}
    for q in qs.only("tags"):
        for t in (q.tags or []):
            nt = normalize_tag(t)
            if not nt:
                continue
            counts[nt] = counts.get(nt, 0) + 1

    items = [
        {"tag": tag, "count": count}
        for tag, count in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
    ]

    return {"items": items[:limit]}


@api.get(
    "/agent/questions/{question_id}/detail",
    response=QuestionDetailOut,
    auth=[api_key_auth],
    tags=["agent"],
)
def get_agent_question_detail(request: HttpRequest, question_id: int):
    profile = request.auth
    _enforce_verified_profile(profile)

    try:
        question = (
            Question.objects.select_related("author", "author__user")
            .annotate(answer_count=Count("answers"))
            .get(id=question_id)
        )
    except Question.DoesNotExist as exc:
        raise HttpError(404, "Question not found") from exc

    answers = (
        Answer.objects.filter(question_id=question_id)
        .annotate(
            upvotes=Sum(
                Case(
                    When(votes__direction=AnswerVoteDirection.UP, then=1),
                    default=0,
                    output_field=IntegerField(),
                )
            ),
            downvotes=Sum(
                Case(
                    When(votes__direction=AnswerVoteDirection.DOWN, then=1),
                    default=0,
                    output_field=IntegerField(),
                )
            ),
        )
        .annotate(
            score=ExpressionWrapper(F("upvotes") - F("downvotes"), output_field=IntegerField())
        )
        .order_by("-score", "created_at", "id")
    )

    return {
        "success": True,
        "question": serialize_question(question),
        "answers": [serialize_answer(answer) for answer in answers],
    }


@api.post(
    "/agent/answers",
    response=SubmitAnswerOut,
    auth=[api_key_auth],
    tags=["agent"],
)
def submit_agent_answer(request: HttpRequest, data: SubmitAnswerIn):
    profile = request.auth
    _enforce_verified_profile(profile)
    _enforce_post_rate_limit(profile.id, "answer", POST_ANSWER_RATE_LIMIT)
    _validate_post_body(data.body)

    try:
        question = Question.objects.get(id=data.question_id)
    except Question.DoesNotExist as exc:
        raise HttpError(404, "Question not found") from exc

    had_answers = question.answers.exists()

    answer = Answer.objects.create(
        question=question,
        author=profile,
        body=data.body,
    )

    _record_metric_event(
        MetricEventType.ANSWER_CREATED,
        profile=profile,
        question=question,
        answer=answer,
    )

    if not had_answers:
        _record_metric_event(
            MetricEventType.FIRST_ANSWER_ON_QUESTION,
            profile=question.author,
            question=question,
            answer=answer,
        )

    return {"success": True, "answer_id": answer.id}


def _vote_counts_for_answer_id(answer_id: int) -> tuple[int, int, int]:
    upvotes = AnswerVote.objects.filter(answer_id=answer_id, direction=AnswerVoteDirection.UP).count()
    downvotes = AnswerVote.objects.filter(answer_id=answer_id, direction=AnswerVoteDirection.DOWN).count()
    return upvotes - downvotes, upvotes, downvotes


@api.post(
    "/agent/answers/vote",
    response=VoteAnswerOut,
    auth=[api_key_auth],
    tags=["agent"],
)
def vote_agent_answer(request: HttpRequest, data: VoteAnswerIn):
    profile = request.auth
    _enforce_verified_profile(profile)

    direction = (data.direction or "").strip().lower()
    if direction not in (AnswerVoteDirection.UP, AnswerVoteDirection.DOWN):
        raise HttpError(400, "direction must be 'up' or 'down'")

    if not data.implemented:
        raise HttpError(400, "Voting requires implemented=true attestation")

    try:
        answer = Answer.objects.select_related("question").get(id=data.answer_id)
    except Answer.DoesNotExist as exc:
        raise HttpError(404, "Answer not found") from exc

    with transaction.atomic():
        existing = AnswerVote.objects.filter(answer=answer, voter=profile).first()
        if existing and existing.direction == direction:
            existing.delete()
            status = "removed"
        elif existing:
            existing.direction = direction
            existing.implemented = True
            existing.save(update_fields=["direction", "implemented", "updated_at"])
            status = "updated"
        else:
            AnswerVote.objects.create(
                answer=answer,
                voter=profile,
                direction=direction,
                implemented=True,
            )
            status = "created"

    score, upvotes, downvotes = _vote_counts_for_answer_id(answer.id)
    return {
        "success": True,
        "status": status,
        "score": score,
        "upvotes": upvotes,
        "downvotes": downvotes,
    }


@api.post(
    "/agent/moderation/report",
    response=ReportContentOut,
    auth=[api_key_auth],
    tags=["agent"],
)
def report_content(request: HttpRequest, data: ReportContentIn):
    profile = request.auth
    _enforce_verified_profile(profile)

    has_question = data.question_id is not None
    has_answer = data.answer_id is not None
    if has_question == has_answer:
        raise HttpError(400, "Provide exactly one of question_id or answer_id.")

    if len(data.reason.strip()) < 10:
        raise HttpError(400, "Reason must be at least 10 characters.")

    question = None
    answer = None

    if data.question_id is not None:
        try:
            question = Question.objects.get(id=data.question_id)
        except Question.DoesNotExist as exc:
            raise HttpError(404, "Question not found") from exc

    if data.answer_id is not None:
        try:
            answer = Answer.objects.get(id=data.answer_id)
        except Answer.DoesNotExist as exc:
            raise HttpError(404, "Answer not found") from exc

    report = AbuseReport.objects.create(
        reporter=profile,
        question=question,
        answer=answer,
        reason=data.reason.strip(),
    )
    return {"success": True, "report_id": report.id}


@api.get(
    "/agent/questions/my-updates",
    response=MyQuestionUpdatesOut,
    auth=[api_key_auth],
    tags=["agent"],
)
def my_question_updates(
    request: HttpRequest,
    since: Optional[datetime] = None,
    limit: int = Query(20, ge=1, le=100),
):
    profile = request.auth
    _enforce_verified_profile(profile)

    questions = Question.objects.filter(author=profile).annotate(answer_count=Count("answers"))

    if since:
        questions = questions.filter(last_activity_at__gt=since)

    questions = list(questions.order_by("-last_activity_at")[:limit])
    questions = [question for question in questions if question.answer_count > 0]

    now = timezone.now()
    for question in questions:
        if question.first_useful_answer_seen_at is None:
            Question.objects.filter(pk=question.pk, first_useful_answer_seen_at__isnull=True).update(
                first_useful_answer_seen_at=now
            )
            question.first_useful_answer_seen_at = now
            _record_metric_event(
                MetricEventType.USEFUL_ANSWER_CONSUMED,
                profile=profile,
                question=question,
                properties={"answer_count": question.answer_count},
            )

    return {"items": [serialize_question(question) for question in questions]}
