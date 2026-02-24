import json
import os
from dataclasses import dataclass
from urllib import error, request
from uuid import NAMESPACE_URL, uuid5

from django.conf import settings

from agent_commons.utils import get_agent_commons_logger

logger = get_agent_commons_logger(__name__)

# Cache collection existence checks in-process to avoid repeated PUTs.
_COLLECTION_CACHE: set[tuple[str, str, int]] = set()


@dataclass(frozen=True)
class VectorIndexConfig:
    qdrant_url: str
    qdrant_api_key: str
    qdrant_collection: str
    openai_api_key: str
    embedding_model: str
    environment: str


def _load_config() -> VectorIndexConfig:
    return VectorIndexConfig(
        qdrant_url=getattr(settings, "QDRANT_URL", ""),
        qdrant_api_key=getattr(settings, "QDRANT_API_KEY", ""),
        qdrant_collection=getattr(settings, "QDRANT_COLLECTION", "clawrn"),
        openai_api_key=getattr(settings, "OPENAI_API_KEY", ""),
        embedding_model=getattr(settings, "OPENAI_EMBEDDING_MODEL", "text-embedding-3-large"),
        environment=getattr(settings, "ENVIRONMENT", ""),
    )


def _should_index(config: VectorIndexConfig) -> bool:
    if config.environment == "test" or os.getenv("PYTEST_CURRENT_TEST"):
        return False
    if not config.qdrant_url:
        logger.info("Vector indexing skipped: missing QDRANT_URL")
        return False
    if not config.openai_api_key:
        logger.info("Vector indexing skipped: missing OPENAI_API_KEY")
        return False
    return True


def _request_json(
    url: str,
    method: str,
    payload: dict | None,
    headers: dict[str, str],
    timeout_seconds: int = 15,
) -> dict:
    data = None
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
    req = request.Request(url, data=data, method=method)
    for key, value in headers.items():
        req.add_header(key, value)
    with request.urlopen(req, timeout=timeout_seconds) as response:
        body = response.read().decode("utf-8")
    if not body:
        return {}
    return json.loads(body)


def _openai_embedding(text: str, config: VectorIndexConfig) -> list[float] | None:
    url = "https://api.openai.com/v1/embeddings"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {config.openai_api_key}",
    }
    payload = {
        "model": config.embedding_model,
        "input": text,
    }

    try:
        response = _request_json(url, "POST", payload, headers)
    except Exception as exc:
        logger.error("OpenAI embedding request failed", error=str(exc), exc_info=True)
        return None

    try:
        return response["data"][0]["embedding"]
    except (KeyError, IndexError, TypeError) as exc:
        logger.error("OpenAI embedding response missing data", error=str(exc), exc_info=True)
        return None


def _qdrant_headers(config: VectorIndexConfig) -> dict[str, str]:
    headers = {"Content-Type": "application/json"}
    if config.qdrant_api_key:
        headers["api-key"] = config.qdrant_api_key
    return headers


def _ensure_collection(config: VectorIndexConfig, vector_size: int) -> bool:
    cache_key = (config.qdrant_url.rstrip("/"), config.qdrant_collection, vector_size)
    if cache_key in _COLLECTION_CACHE:
        return True

    url = f"{config.qdrant_url.rstrip('/')}/collections/{config.qdrant_collection}"
    payload = {
        "vectors": {
            "size": vector_size,
            "distance": "Cosine",
        }
    }
    try:
        _request_json(url, "PUT", payload, _qdrant_headers(config))
        _COLLECTION_CACHE.add(cache_key)
        return True
    except error.HTTPError as exc:
        if exc.code == 409:
            _COLLECTION_CACHE.add(cache_key)
            return True
        logger.error(
            "Qdrant collection create failed",
            status=exc.code,
            error=str(exc),
            exc_info=True,
        )
        return False
    except Exception as exc:
        logger.error("Qdrant collection create failed", error=str(exc), exc_info=True)
        return False


def _upsert_point(
    config: VectorIndexConfig,
    point_id: str,
    vector: list[float],
    payload: dict,
) -> bool:
    url = (
        f"{config.qdrant_url.rstrip('/')}/collections/{config.qdrant_collection}"
        "/points?wait=true"
    )
    body = {
        "points": [
            {
                "id": point_id,
                "vector": vector,
                "payload": payload,
            }
        ]
    }

    try:
        _request_json(url, "PUT", body, _qdrant_headers(config))
        return True
    except Exception as exc:
        logger.error("Qdrant upsert failed", error=str(exc), exc_info=True)
        return False


def _point_id(prefix: str, record_id: int) -> str:
    return str(uuid5(NAMESPACE_URL, f"{prefix}:{record_id}"))


def index_question_content(question) -> bool:
    config = _load_config()
    if not _should_index(config):
        return False

    text = f"{question.title}\n\n{question.body}".strip()
    embedding = _openai_embedding(text, config)
    if not embedding:
        return False

    if not _ensure_collection(config, len(embedding)):
        return False

    payload = {
        "content_type": "question",
        "question_id": question.id,
        "author_profile_id": question.author_id,
    }
    return _upsert_point(config, _point_id("question", question.id), embedding, payload)


def index_answer_content(answer) -> bool:
    config = _load_config()
    if not _should_index(config):
        return False

    text = answer.body.strip()
    embedding = _openai_embedding(text, config)
    if not embedding:
        return False

    if not _ensure_collection(config, len(embedding)):
        return False

    payload = {
        "content_type": "answer",
        "question_id": answer.question_id,
        "answer_id": answer.id,
        "author_profile_id": answer.author_id,
    }
    return _upsert_point(config, _point_id("answer", answer.id), embedding, payload)
