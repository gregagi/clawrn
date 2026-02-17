from __future__ import annotations

from collections.abc import Iterable

from django.utils.text import slugify


def normalize_tag(tag: str) -> str:
    """Normalize a user-provided tag.

    Goals:
    - stable and comparable (case/whitespace-insensitive)
    - URL-safe-ish (slug)
    - no empty tags

    We intentionally keep this lightweight; synonym mapping can be layered later.
    """

    if tag is None:
        return ""

    normalized = slugify(str(tag).strip().lower())
    return normalized


def normalize_tags(tags: Iterable[str] | None) -> list[str]:
    """Normalize + de-duplicate tags while preserving first-seen order."""

    if not tags:
        return []

    seen: set[str] = set()
    out: list[str] = []

    for raw in tags:
        t = normalize_tag(raw)
        if not t:
            continue
        if t in seen:
            continue
        seen.add(t)
        out.append(t)

    return out
