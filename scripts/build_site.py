from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))
from common import build_search_tokens, confidence_label, map_domains_to_areas, normalize_type, parse_datetime, pick_next_deadline  # noqa: E402

ROOT = SCRIPT_DIR.parents[0]
VENUES_PATH = ROOT / "data" / "venues.yml"
INSTANCES_PATH = ROOT / "data" / "instances.yml"
OVERRIDES_PATH = ROOT / "data" / "manual_overrides.yml"
RUN_SUMMARY_PATH = ROOT / "data" / "scan_run_summary.json"
OUT_PATH = ROOT / "docs" / "assets" / "venues.json"
BUILD_SUMMARY_PATH = ROOT / "docs" / "assets" / "build-summary.json"


def load_yaml(path: Path):
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle) or []


def load_json(path: Path):
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def index_overrides(items: list[dict]) -> dict[str, dict]:
    indexed = {}
    for item in items:
        if item.get("id") and item.get("manual_override"):
            indexed[item["id"]] = item["manual_override"]
    return indexed


def choose_public_deadlines(instance: dict, override: dict | None) -> tuple[list[dict], list[str], bool]:
    reasons: list[str] = []
    review_required = bool(instance.get("review_required"))
    deadlines = list(instance.get("deadlines", []) or [])
    if override and override.get("deadlines"):
        deadlines = override["deadlines"]
        reasons.append("manual override applied")
        review_required = False

    public = []
    for item in deadlines:
        confidence = confidence_label(item.get("confidence") or instance.get("confidence"))
        source = (item.get("source") or "unknown").lower()
        confirmed = bool(item.get("confirmed"))
        if source == "manual_override":
            public.append({**item, "confidence": confidence})
            continue
        if review_required or not confirmed or confidence == "low":
            continue
        if source not in {"official", "openreview", "manual", "manual_override", "secondary"}:
            continue
        public.append({**item, "confidence": confidence})
    public.sort(key=lambda item: ((item.get("value") or ""), item.get("kind") or ""))
    return public, reasons, review_required


def build_record(venue: dict, instance: dict | None, override: dict | None, current_year: int) -> dict:
    instance = instance or {
        "id": f"{venue['id']}-{current_year}",
        "venue_id": venue["id"],
        "year": current_year,
        "scan_status": "catalog_seed",
        "checked_at": None,
        "source_url": venue.get("cfp_url") or venue.get("website"),
        "confidence": "low",
        "review_required": False,
        "conflict_reason": None,
        "scan_preview": [],
        "deadlines": [],
        "venue_date_start": None,
        "venue_date_end": None,
        "location": None,
    }
    areas = map_domains_to_areas(venue.get("domain"))
    public_deadlines, publication_notes, review_required = choose_public_deadlines(instance, override)
    next_deadline = pick_next_deadline(public_deadlines)
    source_display = None
    confidence_display = confidence_label(instance.get("confidence"))
    if public_deadlines:
        primary = next_deadline or public_deadlines[0]
        source_display = primary.get("source")
        confidence_display = confidence_label(primary.get("confidence"))

    record = {
        "id": instance.get("id"),
        "venue_id": venue["id"],
        "title": venue.get("title"),
        "short_name": venue.get("short_name"),
        "aliases": venue.get("aliases", []),
        "domain": venue.get("domain", []),
        "areas": areas,
        "primary_area": areas[0] if areas else "SE+Theory",
        "type": normalize_type(venue.get("type")),
        "original_type": venue.get("type"),
        "tier": venue.get("tier"),
        "website": venue.get("website"),
        "cfp_url": venue.get("cfp_url") or venue.get("website"),
        "year": instance.get("year", current_year),
        "status": instance.get("scan_status", "catalog_seed"),
        "scan_status": instance.get("scan_status", "catalog_seed"),
        "review_required": review_required,
        "conflict_reason": instance.get("conflict_reason"),
        "public_deadlines": public_deadlines,
        "deadlines": instance.get("deadlines", []),
        "next_deadline": None,
        "venue_date_start": instance.get("venue_date_start"),
        "venue_date_end": instance.get("venue_date_end"),
        "location": instance.get("location"),
        "source_url": instance.get("source_url") or venue.get("cfp_url") or venue.get("website"),
        "source_display": source_display,
        "checked_at": instance.get("checked_at"),
        "confidence": confidence_display,
        "scan_preview": instance.get("scan_preview", []),
        "scan_preview_count": len(instance.get("scan_preview", [])),
        "notes": venue.get("notes"),
        "parser": venue.get("parser"),
        "scan_enabled": bool(venue.get("scan_enabled")),
        "active": bool(venue.get("active", True)),
        "source_priority": venue.get("source_priority", ["official", "openreview", "secondary"]),
        "last_seen_year": venue.get("last_seen_year"),
        "publication_notes": publication_notes,
        "manual_override_applied": bool(publication_notes),
        "default_timezone": venue.get("default_timezone"),
    }
    if next_deadline:
        record["next_deadline"] = {
            "kind": next_deadline.get("kind"),
            "value": next_deadline.get("value"),
            "timezone": next_deadline.get("timezone"),
            "source": next_deadline.get("source"),
            "confidence": confidence_label(next_deadline.get("confidence")),
            "extended_from": next_deadline.get("extended_from"),
            "previous_value": next_deadline.get("previous_value"),
            "original_value": next_deadline.get("original_value"),
        }
    record["search_tokens"] = build_search_tokens(record)
    return record


def main() -> int:
    venues = load_yaml(VENUES_PATH)
    instances = load_yaml(INSTANCES_PATH)
    overrides = index_overrides(load_yaml(OVERRIDES_PATH))
    run_summary = load_json(RUN_SUMMARY_PATH)
    current_year = datetime.now(timezone.utc).year

    latest_by_venue: dict[str, dict] = {}
    for instance in instances:
        venue_id = instance.get("venue_id")
        current = latest_by_venue.get(venue_id)
        if current is None or instance.get("year", 0) >= current.get("year", 0):
            latest_by_venue[venue_id] = instance

    records = [
        build_record(venue, latest_by_venue.get(venue["id"]), overrides.get(f"{venue['id']}-{current_year}"), current_year)
        for venue in venues
    ]

    def sort_key(item: dict):
        next_value = item.get("next_deadline", {}).get("value") if item.get("next_deadline") else None
        next_tz = item.get("next_deadline", {}).get("timezone") if item.get("next_deadline") else None
        dt = parse_datetime(next_value, next_tz) if next_value else None
        return (dt is None, dt or datetime.max.replace(tzinfo=timezone.utc), item.get("short_name", "").lower())

    records.sort(key=sort_key)

    build_summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "record_count": len(records),
        "confirmed_public_deadlines": sum(1 for item in records if item.get("next_deadline")),
        "review_required": sum(1 for item in records if item.get("review_required")),
        "catalog_seed": sum(1 for item in records if item.get("scan_status") == "catalog_seed"),
        "scanned": sum(1 for item in records if item.get("scan_status") == "scanned"),
        "confirmed": sum(1 for item in records if item.get("scan_status") == "confirmed"),
        "scan_failed": sum(1 for item in records if item.get("scan_status") == "scan_failed"),
        "run_summary": run_summary,
    }

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
    BUILD_SUMMARY_PATH.write_text(json.dumps(build_summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(build_summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
