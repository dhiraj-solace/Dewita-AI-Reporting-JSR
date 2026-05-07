import hashlib
import json
import logging
import re
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from app.core.config import get_settings

logger = logging.getLogger(__name__)

STOP_WORDS = {
    "a",
    "an",
    "and",
    "are",
    "by",
    "for",
    "from",
    "give",
    "i",
    "in",
    "is",
    "me",
    "of",
    "please",
    "report",
    "show",
    "the",
    "there",
    "to",
    "want",
    "with",
}

SYNONYMS = {
    "amount": "total",
    "amounts": "total",
    "categories": "type",
    "category": "type",
    "counts": "count",
    "each": "group",
    "grouped": "group",
    "groups": "group",
    "how": "",
    "many": "count",
    "number": "count",
    "numbers": "count",
    "projects": "project",
    "sum": "total",
    "totals": "total",
    "types": "type",
}


def normalize_query(query: str) -> str:
    normalized = query.lower()
    normalized = re.sub(r"[^a-z0-9\s:_-]+", " ", normalized)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalized


def generate_cache_key(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def schema_version(schema_snapshot: dict[str, Any]) -> str:
    return generate_cache_key(schema_snapshot or {})[:16]


def build_cache_identity(
    question: str,
    start_date: str | None,
    end_date: str | None,
    limit: int,
    schema_snapshot: dict[str, Any],
) -> dict[str, Any]:
    normalized = normalize_query(question)
    canonical_tokens = _canonical_tokens(normalized)
    base = {
        "start_date": start_date,
        "end_date": end_date,
        "limit": limit,
        "schema_version": schema_version(schema_snapshot),
    }
    return {
        "exact": {
            **base,
            "normalized_query": normalized,
        },
        "intent": {
            **base,
            "canonical_tokens": canonical_tokens,
            "date_tokens": _date_tokens(normalized),
        },
        "normalized_query": normalized,
        "canonical_tokens": canonical_tokens,
    }


def get_cached_sql(
    question: str,
    start_date: str | None,
    end_date: str | None,
    limit: int,
    schema_snapshot: dict[str, Any],
) -> tuple[dict[str, Any] | None, str]:
    if not get_settings().llm_sql_cache_enabled:
        return None, "disabled"

    identity = build_cache_identity(question, start_date, end_date, limit, schema_snapshot)
    cache = _load_cache()
    now = _now()
    exact_key = generate_cache_key(identity["exact"])
    intent_key = generate_cache_key(identity["intent"])

    for match_type, index_key in (("exact", exact_key), ("intent", intent_key)):
        entry_key = cache.get(f"{match_type}_index", {}).get(index_key)
        entry = cache.get("entries", {}).get(entry_key or "")
        if not entry:
            continue
        if _is_expired(entry, now):
            _delete_entry(cache, entry_key)
            _save_cache(cache)
            logger.info("LLM SQL cache expired key=%s match_type=%s", entry_key, match_type)
            return None, "expired"
        entry["stats"]["hit_count"] = int(entry.get("stats", {}).get("hit_count") or 0) + 1
        entry["stats"]["last_hit_at"] = now.isoformat()
        _save_cache(cache)
        logger.info("LLM SQL cache HIT key=%s match_type=%s", entry_key, match_type)
        return entry, match_type

    logger.info("LLM SQL cache MISS exact_key=%s intent_key=%s", exact_key[:12], intent_key[:12])
    return None, "miss"


def set_cached_sql(
    question: str,
    start_date: str | None,
    end_date: str | None,
    limit: int,
    schema_snapshot: dict[str, Any],
    generated: dict[str, Any],
    tags: list[str] | None = None,
) -> dict[str, Any] | None:
    if not get_settings().llm_sql_cache_enabled:
        return None
    sql = str(generated.get("sql") or "").strip()
    if not sql:
        return None

    settings = get_settings()
    identity = build_cache_identity(question, start_date, end_date, limit, schema_snapshot)
    exact_key = generate_cache_key(identity["exact"])
    intent_key = generate_cache_key(identity["intent"])
    entry_key = intent_key
    now = _now()
    expires_at = now + timedelta(days=max(1, min(3, settings.llm_sql_cache_ttl_days)))
    merged_tags = sorted(
        set(tags or [])
        | {f"cache_key:{entry_key}"}
        | set(_tags_from_identity(identity))
        | set(_tags_from_sql(sql))
    )
    entry = {
        "key": entry_key,
        "query": {
            "original": question,
            "normalized": identity["normalized_query"],
        },
        "intent": {
            "canonical_tokens": identity["canonical_tokens"],
            "date_tokens": identity["intent"]["date_tokens"],
            "start_date": start_date,
            "end_date": end_date,
            "limit": limit,
        },
        "response": {
            "title": generated.get("title") or "SQL Report",
            "sql": sql,
            "explanation": generated.get("explanation") or "",
        },
        "sources": {
            "schema_version": identity["intent"]["schema_version"],
        },
        "tags": merged_tags,
        "cache_policy": {
            "ttl_days": settings.llm_sql_cache_ttl_days,
            "created_at": now.isoformat(),
            "expires_at": expires_at.isoformat(),
        },
        "stats": {
            "hit_count": 0,
            "last_hit_at": None,
            "last_invalidated_at": None,
            "invalidated_reason": None,
        },
    }

    cache = _load_cache()
    cache.setdefault("entries", {})[entry_key] = entry
    cache.setdefault("exact_index", {})[exact_key] = entry_key
    cache.setdefault("intent_index", {})[intent_key] = entry_key
    _save_cache(cache)
    logger.info("LLM SQL cache SET key=%s tags=%s", entry_key, ",".join(merged_tags))
    return entry


def invalidate_cache(tags: list[str] | None = None, reason: str = "manual") -> int:
    cache = _load_cache()
    entries = cache.get("entries", {})
    tag_set = set(tags or [])
    keys = [
        key
        for key, entry in entries.items()
        if not tag_set or tag_set.intersection(set(entry.get("tags") or []))
    ]
    for key in keys:
        entry = entries.get(key)
        if entry:
            entry.setdefault("stats", {})["last_invalidated_at"] = _now().isoformat()
            entry.setdefault("stats", {})["invalidated_reason"] = reason
        _delete_entry(cache, key)
    _save_cache(cache)
    logger.info("LLM SQL cache INVALIDATE count=%s tags=%s reason=%s", len(keys), tags or ["*"], reason)
    return len(keys)


def _canonical_tokens(normalized: str) -> list[str]:
    tokens: list[str] = []
    raw_tokens = re.findall(r"[a-z0-9]+", normalized)
    for token in raw_tokens:
        mapped = SYNONYMS.get(token, token)
        if not mapped or mapped in STOP_WORDS:
            continue
        tokens.append(mapped)
    if "project" in tokens and "total" in tokens and not _has_value_metric(raw_tokens):
        tokens.append("count")
        tokens = [token for token in tokens if token != "total"]
    return sorted(set(tokens))


def _has_value_metric(tokens: list[str]) -> bool:
    return bool(
        {
            "amount",
            "amounts",
            "budget",
            "cost",
            "costs",
            "expense",
            "expenses",
            "hours",
            "price",
            "revenue",
            "sales",
            "value",
            "values",
        }.intersection(tokens)
    )


def _date_tokens(normalized: str) -> list[str]:
    return sorted(set(re.findall(r"\b(?:week|month|year|q[1-4]|quarter|today|yesterday|tomorrow|last|next|this|\d{1,4})\b", normalized)))


def _tags_from_identity(identity: dict[str, Any]) -> list[str]:
    tags = [f"token:{token}" for token in identity["canonical_tokens"][:20]]
    if identity["intent"].get("start_date"):
        tags.append(f"start:{identity['intent']['start_date']}")
    if identity["intent"].get("end_date"):
        tags.append(f"end:{identity['intent']['end_date']}")
    return tags


def _tags_from_sql(sql: str) -> list[str]:
    tags = ["llm_sql"]
    for table in re.findall(r"\b(?:from|join)\s+`?([a-zA-Z_][\w]*)`?", sql, re.IGNORECASE):
        tags.append(f"table:{table.lower()}")
    return tags


def _cache_path() -> Path:
    path = Path(get_settings().llm_sql_cache_path)
    if not path.is_absolute():
        path = Path(__file__).resolve().parents[1] / path
    return path


def _load_cache() -> dict[str, Any]:
    path = _cache_path()
    if not path.exists():
        return {"version": 1, "entries": {}, "exact_index": {}, "intent_index": {}}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        logger.warning("LLM SQL cache file is unreadable; starting with an empty cache.")
        return {"version": 1, "entries": {}, "exact_index": {}, "intent_index": {}}
    data.setdefault("version", 1)
    data.setdefault("entries", {})
    data.setdefault("exact_index", {})
    data.setdefault("intent_index", {})
    return data


def _save_cache(cache: dict[str, Any]) -> None:
    path = _cache_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(cache, ensure_ascii=False, indent=2, sort_keys=True, default=str), encoding="utf-8")
    tmp.replace(path)


def _delete_entry(cache: dict[str, Any], entry_key: str | None) -> None:
    if not entry_key:
        return
    cache.get("entries", {}).pop(entry_key, None)
    for index_name in ("exact_index", "intent_index"):
        index = cache.get(index_name, {})
        stale_keys = [key for key, value in index.items() if value == entry_key]
        for key in stale_keys:
            index.pop(key, None)


def _is_expired(entry: dict[str, Any], now: datetime) -> bool:
    expires_at = entry.get("cache_policy", {}).get("expires_at")
    if not expires_at:
        return True
    try:
        return datetime.fromisoformat(expires_at) <= now
    except ValueError:
        return True


def _now() -> datetime:
    return datetime.now(UTC)
