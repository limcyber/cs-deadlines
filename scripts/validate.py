from __future__ import annotations

from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse
import yaml

ROOT = Path(__file__).resolve().parents[1]
VENUES_PATH = ROOT / "data" / "venues.yml"
INSTANCES_PATH = ROOT / "data" / "instances.yml"

REQUIRED_VENUE_FIELDS = {
    "id", "title", "short_name", "domain", "type", "tier", "recurring",
    "active", "website", "cfp_url", "default_timezone", "parser"
}
REQUIRED_INSTANCE_FIELDS = {
    "id", "venue_id", "year", "status", "deadlines", "confidence"
}
VALID_STATUSES = {
    "catalog_seed", "placeholder", "awaiting_cfp", "scanned", "scan_failed",
    "review_required", "confirmed", "auto_confirmed", "rejected", "closed", "conflict"
}


def load_yaml(path: Path):
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or []


def is_http_url(value: str | None) -> bool:
    if not value:
        return False
    try:
        parsed = urlparse(value)
    except ValueError:
        return False
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def is_iso_datetime_like(value: str | None) -> bool:
    if value in (None, ""):
        return False
    text = str(value).strip()
    # Accept date-only and datetime values in ISO form.
    if len(text) == 10:
        try:
            datetime.strptime(text, "%Y-%m-%d")
            return True
        except ValueError:
            return False
    normalized = text.replace("Z", "+00:00")
    try:
        datetime.fromisoformat(normalized)
        return True
    except ValueError:
        return False


def is_number_in_unit_interval(value) -> bool:
    if not isinstance(value, (int, float)):
        return False
    return 0.0 <= float(value) <= 1.0


def main() -> int:
    venues = load_yaml(VENUES_PATH)
    instances = load_yaml(INSTANCES_PATH)
    # Validation is intentionally strict so malformed data fails before build/deploy.
    if not isinstance(venues, list) or not isinstance(instances, list):
        print("[ERROR] venues.yml and instances.yml must contain top-level lists")
        return 1

    seen_venue_ids = set()
    for venue in venues:
        if not isinstance(venue, dict):
            print("[ERROR] each venue entry must be a mapping/object")
            return 1
        missing = REQUIRED_VENUE_FIELDS - set(venue.keys())
        if missing:
            print(f"[ERROR] venue {venue.get('id')} missing fields: {sorted(missing)}")
            return 1
        vid = venue["id"]
        if not isinstance(vid, str) or not vid.strip():
            print(f"[ERROR] venue id must be a non-empty string: {vid}")
            return 1
        if vid in seen_venue_ids:
            print(f"[ERROR] duplicate venue id: {vid}")
            return 1
        seen_venue_ids.add(vid)
        if not isinstance(venue.get("title"), str) or not venue.get("title", "").strip():
            print(f"[ERROR] venue {vid} title must be a non-empty string")
            return 1
        if not isinstance(venue.get("short_name"), str) or not venue.get("short_name", "").strip():
            print(f"[ERROR] venue {vid} short_name must be a non-empty string")
            return 1
        if not isinstance(venue.get("domain"), list) or not all(isinstance(d, str) for d in venue.get("domain", [])):
            print(f"[ERROR] venue {vid} domain must be a list of strings")
            return 1
        if not isinstance(venue.get("default_timezone"), str) or not venue.get("default_timezone", "").strip():
            print(f"[ERROR] venue {vid} default_timezone must be a non-empty string")
            return 1
        if not isinstance(venue.get("parser"), str) or not venue.get("parser", "").strip():
            print(f"[ERROR] venue {vid} parser must be a non-empty string")
            return 1
        if not is_http_url(venue.get("website")):
            print(f"[ERROR] venue {vid} website must be a valid http/https URL")
            return 1
        if not is_http_url(venue.get("cfp_url")):
            print(f"[ERROR] venue {vid} cfp_url must be a valid http/https URL")
            return 1

    seen_instance_ids = set()
    for inst in instances:
        if not isinstance(inst, dict):
            print("[ERROR] each instance entry must be a mapping/object")
            return 1
        missing = REQUIRED_INSTANCE_FIELDS - set(inst.keys())
        if missing:
            print(f"[ERROR] instance {inst.get('id')} missing fields: {sorted(missing)}")
            return 1
        iid = inst["id"]
        if not isinstance(iid, str) or not iid.strip():
            print(f"[ERROR] instance id must be a non-empty string: {iid}")
            return 1
        if iid in seen_instance_ids:
            print(f"[ERROR] duplicate instance id: {iid}")
            return 1
        seen_instance_ids.add(iid)
        if inst["venue_id"] not in seen_venue_ids:
            print(f"[ERROR] instance {iid} references missing venue_id: {inst['venue_id']}")
            return 1
        if inst.get("status") not in VALID_STATUSES:
            print(f"[ERROR] instance {iid} has invalid status: {inst.get('status')}")
            return 1
        if not isinstance(inst.get("year"), int):
            print(f"[ERROR] instance {iid} year must be an integer")
            return 1
        expected_suffix = f"-{inst['year']}"
        if not iid.endswith(expected_suffix):
            print(f"[ERROR] instance {iid} id must end with year suffix {expected_suffix}")
            return 1
        if not is_number_in_unit_interval(inst.get("confidence")):
            print(f"[ERROR] instance {iid} confidence must be between 0 and 1")
            return 1
        if not isinstance(inst.get("deadlines"), list):
            print(f"[ERROR] instance {iid} deadlines must be a list")
            return 1
        # Public deadlines must already be normalized because the frontend reads them directly.
        for deadline in inst.get("deadlines", []):
            if not isinstance(deadline, dict):
                print(f"[ERROR] instance {iid} has non-object deadline entry")
                return 1
            if not isinstance(deadline.get("kind"), str) or not deadline.get("kind", "").strip():
                print(f"[ERROR] instance {iid} deadline kind must be a non-empty string")
                return 1
            if not is_iso_datetime_like(deadline.get("value")):
                print(f"[ERROR] instance {iid} deadline value must be ISO date/datetime")
                return 1
        source_url = inst.get("source_url")
        if source_url is not None and not is_http_url(source_url):
            print(f"[ERROR] instance {iid} source_url must be a valid http/https URL when present")
            return 1
        checked_at = inst.get("checked_at")
        if checked_at is not None and not is_iso_datetime_like(checked_at):
            print(f"[ERROR] instance {iid} checked_at must be an ISO date/datetime when present")
            return 1
        auto_review = inst.get("auto_review")
        if auto_review is not None and not isinstance(auto_review, dict):
            print(f"[ERROR] instance {iid} auto_review must be a mapping when present")
            return 1
        parsed_deadlines = inst.get("parsed_deadlines")
        if parsed_deadlines is not None:
            if not isinstance(parsed_deadlines, list):
                print(f"[ERROR] instance {iid} parsed_deadlines must be a list when present")
                return 1
            # Parsed candidates are looser than public deadlines, but still need structural sanity.
            for parsed in parsed_deadlines:
                if not isinstance(parsed, dict):
                    print(f"[ERROR] instance {iid} has non-object parsed_deadline entry")
                    return 1
                if not is_iso_datetime_like(parsed.get("value")):
                    print(f"[ERROR] instance {iid} parsed_deadline value must be ISO date/datetime")
                    return 1
                conf = parsed.get("confidence")
                if conf is not None and not is_number_in_unit_interval(conf):
                    print(f"[ERROR] instance {iid} parsed_deadline confidence must be between 0 and 1")
                    return 1

    print(f"[OK] validated {len(venues)} venues and {len(instances)} instances")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
