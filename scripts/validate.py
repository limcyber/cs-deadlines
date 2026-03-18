from __future__ import annotations

from pathlib import Path
import sys

import yaml

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))
from common import confidence_label  # noqa: E402

ROOT = SCRIPT_DIR.parents[0]
VENUES_PATH = ROOT / "data" / "venues.yml"
INSTANCES_PATH = ROOT / "data" / "instances.yml"
OVERRIDES_PATH = ROOT / "data" / "manual_overrides.yml"

REQUIRED_VENUE_FIELDS = {
    "id", "title", "short_name", "domain", "type", "tier", "recurring",
    "active", "website", "cfp_url", "default_timezone", "parser", "scan_enabled", "source_priority"
}
REQUIRED_INSTANCE_FIELDS = {
    "id", "venue_id", "year", "scan_status", "checked_at", "source_url", "confidence",
    "review_required", "scan_preview", "deadlines"
}
ALLOWED_PARSERS = {"manual", "generic_dates", "structured_dates", "openreview", "wikicfp_assist"}
ALLOWED_SCAN_STATUS = {"catalog_seed", "scanned", "confirmed", "scan_failed", "archived"}
ALLOWED_KINDS = {"abstract", "paper", "submission", "notification", "camera_ready", "other"}


def load_yaml(path: Path):
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle) or []


def main() -> int:
    venues = load_yaml(VENUES_PATH)
    instances = load_yaml(INSTANCES_PATH)
    overrides = load_yaml(OVERRIDES_PATH)
    venue_ids = set()
    instance_ids = set()

    for index, venue in enumerate(venues, start=1):
        missing = REQUIRED_VENUE_FIELDS - set(venue)
        if missing:
            raise SystemExit(f"[ERROR] venue #{index} missing fields: {sorted(missing)}")
        if venue["id"] in venue_ids:
            raise SystemExit(f"[ERROR] duplicate venue id: {venue['id']}")
        if venue.get("parser") not in ALLOWED_PARSERS:
            raise SystemExit(f"[ERROR] venue {venue['id']} has invalid parser: {venue.get('parser')}")
        if not isinstance(venue.get("source_priority"), list) or not venue.get("source_priority"):
            raise SystemExit(f"[ERROR] venue {venue['id']} must define non-empty source_priority")
        venue_ids.add(venue["id"])

    for index, instance in enumerate(instances, start=1):
        missing = REQUIRED_INSTANCE_FIELDS - set(instance)
        if missing:
            raise SystemExit(f"[ERROR] instance #{index} missing fields: {sorted(missing)}")
        if instance["id"] in instance_ids:
            raise SystemExit(f"[ERROR] duplicate instance id: {instance['id']}")
        if instance["venue_id"] not in venue_ids:
            raise SystemExit(f"[ERROR] instance {instance['id']} references unknown venue_id: {instance['venue_id']}")
        if instance.get("scan_status") not in ALLOWED_SCAN_STATUS:
            raise SystemExit(f"[ERROR] instance {instance['id']} has invalid scan_status: {instance.get('scan_status')}")
        if confidence_label(instance.get("confidence")) not in {"high", "medium", "low"}:
            raise SystemExit(f"[ERROR] instance {instance['id']} has invalid confidence: {instance.get('confidence')}")
        for deadline in instance.get("deadlines", []) or []:
            for field in ["kind", "value", "timezone", "source", "confirmed", "confidence"]:
                if field not in deadline:
                    raise SystemExit(f"[ERROR] instance {instance['id']} deadline missing field: {field}")
            if deadline.get("kind") not in ALLOWED_KINDS:
                raise SystemExit(f"[ERROR] instance {instance['id']} has invalid deadline kind: {deadline.get('kind')}")
            if confidence_label(deadline.get("confidence")) not in {"high", "medium", "low"}:
                raise SystemExit(f"[ERROR] instance {instance['id']} has invalid deadline confidence: {deadline.get('confidence')}")
        for preview in instance.get("scan_preview", []) or []:
            if not isinstance(preview, dict):
                raise SystemExit(f"[ERROR] instance {instance['id']} scan_preview entries must be dictionaries")
            for field in ["text", "detected_kind", "source", "confidence"]:
                if field not in preview:
                    raise SystemExit(f"[ERROR] instance {instance['id']} scan_preview missing field: {field}")
        instance_ids.add(instance["id"])

    for item in overrides:
        if item.get("id") not in instance_ids:
            raise SystemExit(f"[ERROR] manual override references unknown instance id: {item.get('id')}")

    print(f"[OK] validated {len(venues)} venues, {len(instances)} instances, {len(overrides)} override entries")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
