from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
import yaml

ROOT = Path(__file__).resolve().parents[1]
VENUES_PATH = ROOT / "data" / "venues.yml"
INSTANCES_PATH = ROOT / "data" / "instances.yml"
OUT_PATH = ROOT / "docs" / "assets" / "venues.json"


def load_yaml(path: Path):
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or []


def main() -> int:
    venues = load_yaml(VENUES_PATH)
    instances = load_yaml(INSTANCES_PATH)
    current_year = datetime.now(timezone.utc).year

    latest_by_venue = {}
    for inst in instances:
        venue_id = inst["venue_id"]
        current = latest_by_venue.get(venue_id)
        if current is None or inst.get("year", 0) >= current.get("year", 0):
            latest_by_venue[venue_id] = inst

    merged = []
    for venue in venues:
        inst = latest_by_venue.get(venue["id"])
        merged.append(
            {
                "id": inst["id"] if inst else f"{venue['id']}-{current_year}",
                "venue_id": venue["id"],
                "title": venue["title"],
                "short_name": venue["short_name"],
                "aliases": venue.get("aliases", []),
                "domain": venue["domain"],
                "type": venue["type"],
                "tier": venue["tier"],
                "website": venue["website"],
                "cfp_url": venue["cfp_url"],
                "year": inst.get("year", current_year) if inst else current_year,
                "status": inst.get("status", "catalog_seed") if inst else "catalog_seed",
                "deadlines": inst.get("deadlines", []) if inst else [],
                "venue_date_start": inst.get("venue_date_start") if inst else None,
                "venue_date_end": inst.get("venue_date_end") if inst else None,
                "location": inst.get("location") if inst else None,
                "source_url": inst.get("source_url") if inst else None,
                "checked_at": inst.get("checked_at") if inst else None,
                "confidence": inst.get("confidence", 0) if inst else 0,
                "scan_preview": inst.get("scan_preview", []) if inst else [],
                "notes": inst.get("notes") if inst and inst.get("notes") else venue.get("notes"),
                "parser": venue.get("parser"),
                "scan_enabled": venue.get("scan_enabled", False),
                "active": venue.get("active", True),
            }
        )

    merged.sort(key=lambda x: (x["short_name"].lower(), x["year"]))

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with OUT_PATH.open("w", encoding="utf-8") as f:
        json.dump(merged, f, ensure_ascii=False, indent=2)

    print(f"[OK] wrote {len(merged)} merged records -> {OUT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
