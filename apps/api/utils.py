from django.http import HttpRequest

from agent_commons.utils import get_agent_commons_logger

logger = get_agent_commons_logger(__name__)


def _coerce_header_value(value: object) -> str | None:
    if value is None:
        return None

    if isinstance(value, bytes):
        try:
            value = value.decode("utf-8")
        except UnicodeDecodeError:
            return None

    if not isinstance(value, str):
        return None

    value = value.strip()
    if not value:
        return None

    return value


def _header_get(headers, name: str) -> object:
    value = headers.get(name)
    if value is None:
        value = headers.get(name.lower())
    return value


def _get_api_key_from_headers(request: HttpRequest) -> str | None:
    headers = getattr(request, "headers", None)
    if not headers:
        return None

    key = _coerce_header_value(_header_get(headers, "X-API-Key"))
    if key:
        return key

    auth_header = _coerce_header_value(_header_get(headers, "Authorization"))
    if not auth_header:
        return None

    parts = auth_header.split(None, 1)
    if len(parts) != 2:
        return None

    scheme = parts[0].lower()
    value = _coerce_header_value(parts[1])
    if not value:
        return None

    if scheme in {"api-key", "apikey", "bearer", "token"}:
        return value

    return None
