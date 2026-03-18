from __future__ import annotations

from pathlib import Path
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


def load_yaml(path: Path):
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or []


def main() -> int:
    venues = load_yaml(VENUES_PATH)
    instances = load_yaml(INSTANCES_PATH)

    seen_venue_ids = set()
    for venue in venues:
        missing = REQUIRED_VENUE_FIELDS - set(venue.keys())
        if missing:
            print(f"[ERROR] venue {venue.get('id')} missing fields: {sorted(missing)}")
            return 1
        vid = venue["id"]
        if vid in seen_venue_ids:
            print(f"[ERROR] duplicate venue id: {vid}")
            return 1
        seen_venue_ids.add(vid)

    seen_instance_ids = set()
    for inst in instances:
        missing = REQUIRED_INSTANCE_FIELDS - set(inst.keys())
        if missing:
            print(f"[ERROR] instance {inst.get('id')} missing fields: {sorted(missing)}")
            return 1
        iid = inst["id"]
        if iid in seen_instance_ids:
            print(f"[ERROR] duplicate instance id: {iid}")
            return 1
        seen_instance_ids.add(iid)
        if inst["venue_id"] not in seen_venue_ids:
            print(f"[ERROR] instance {iid} references missing venue_id: {inst['venue_id']}")
            return 1

    print(f"[OK] validated {len(venues)} venues and {len(instances)} instances")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
