from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any, Iterable

from dateutil import parser as dtparser

AREA_BUCKETS = {
    "AI+Data": {"ai", "ml", "machine-learning", "nlp", "vision", "cv", "robotics", "data", "data-mining", "dm", "ir", "information-retrieval", "database", "databases", "web", "mining"},
    "Systems": {"systems", "os", "operating-systems", "architecture", "cloud", "distributed", "networking", "networks", "storage", "performance", "embedded"},
    "Security": {"security", "privacy", "crypto", "cryptography", "trust", "forensics"},
    "SE+Theory": {"software-engineering", "se", "programming-languages", "pl", "compilers", "verification", "theory", "algorithms", "logic", "hci", "human-computer-interaction"},
}

TYPE_NORMALIZATION = {
    "symposium": "conference",
    "journal-track": "conference",
}

KIND_PRIORITY = {
    "abstract": 0,
    "paper": 1,
    "submission": 2,
    "notification": 3,
    "camera_ready": 4,
    "other": 5,
}

KIND_ALIASES = {
    "abstract": ["abstract"],
    "paper": ["paper", "research paper", "main conference paper", "full paper", "manuscript"],
    "submission": ["submission", "proposal"],
    "notification": ["notification", "decision"],
    "camera_ready": ["camera ready", "camera-ready"],
}

EXTENSION_PATTERNS = [
    r"extended\s+to",
    r"deadline\s+extension",
    r"due\s+date\s+moved",
    r"deadline\s+has\s+been\s+postponed",
    r"submission\s+deadline\s+has\s+been\s+postponed",
]


def normalize_type(value: str | None) -> str:
    if not value:
        return "conference"
    lowered = value.strip().lower()
    return TYPE_NORMALIZATION.get(lowered, lowered)


def map_domains_to_areas(domains: Iterable[str] | None) -> list[str]:
    domains = [str(x).strip().lower() for x in (domains or []) if x]
    matched: list[str] = []
    for area, tokens in AREA_BUCKETS.items():
        if any(domain in tokens for domain in domains):
            matched.append(area)
    if not matched:
        matched.append("SE+Theory")
    return matched


def infer_kind(text: str) -> str:
    lowered = (text or "").lower()
    for kind, aliases in KIND_ALIASES.items():
        if any(alias in lowered for alias in aliases):
            return kind
    return "other"


def has_extension_language(text: str) -> bool:
    lowered = (text or "").lower()
    return any(re.search(pattern, lowered) for pattern in EXTENSION_PATTERNS)


def confidence_rank(label: str | None) -> int:
    return {"low": 0, "medium": 1, "high": 2}.get((label or "").lower(), 0)


def confidence_label(value: Any) -> str:
    if isinstance(value, str):
        lowered = value.lower()
        if lowered in {"high", "medium", "low"}:
            return lowered
    if isinstance(value, (float, int)):
        if value >= 0.9:
            return "high"
        if value >= 0.5:
            return "medium"
    return "low"


def deadline_sort_key(item: dict) -> tuple:
    return (KIND_PRIORITY.get(item.get("kind", "other"), 99), item.get("value") or "")


def parse_datetime(value: str | None, timezone_hint: str | None = None):
    if not value:
        return None
    raw = value.strip()
    label = None
    for suffix in [" AoE", " PDT", " PST", " CET", " CEST", " UTC", " EST", " EDT"]:
        if raw.endswith(suffix):
            label = suffix.strip()
            raw = raw[: -len(suffix)]
            break
    try:
        dt = dtparser.isoparse(raw)
    except Exception:
        try:
            dt = dtparser.parse(raw)
        except Exception:
            return None
    if dt.tzinfo is None:
        label = label or timezone_hint or "UTC"
        offsets = {
            "AoE": "-12:00",
            "PDT": "-07:00",
            "PST": "-08:00",
            "CET": "+01:00",
            "CEST": "+02:00",
            "UTC": "+00:00",
            "EST": "-05:00",
            "EDT": "-04:00",
        }
        dt = dtparser.isoparse(f"{dt.strftime('%Y-%m-%dT%H:%M:%S')}{offsets.get(label, '+00:00')}")
    return dt


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def pick_next_deadline(deadlines: list[dict], now: datetime | None = None):
    now = now or now_utc()
    upcoming = []
    for item in deadlines or []:
        dt = parse_datetime(item.get("value"), item.get("timezone"))
        if dt is None:
            continue
        if dt >= now:
            upcoming.append((dt, deadline_sort_key(item), item))
    if not upcoming:
        return None
    upcoming.sort(key=lambda entry: (entry[0], entry[1]))
    dt, _, item = upcoming[0]
    return {**item, "parsed": dt}


def build_search_tokens(record: dict) -> list[str]:
    tokens = set()
    for value in [record.get("title"), record.get("short_name")]:
        if value:
            tokens.update(re.findall(r"[a-z0-9+.#-]+", str(value).lower()))
    for alias in record.get("aliases", []) or []:
        tokens.update(re.findall(r"[a-z0-9+.#-]+", str(alias).lower()))
    for domain in record.get("domain", []) or []:
        tokens.update(re.findall(r"[a-z0-9+.#-]+", str(domain).lower()))
    for area in record.get("areas", []) or []:
        tokens.update(re.findall(r"[a-z0-9+.#-]+", str(area).lower()))
    return sorted(tokens)
