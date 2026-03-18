from __future__ import annotations

import json
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
    venues = {v["id"]: v for v in load_yaml(VENUES_PATH)}
    instances = load_yaml(INSTANCES_PATH)

    merged = []
    for inst in instances:
        venue = venues.get(inst["venue_id"])
        if not venue:
            continue
        merged.append(
            {
                "id": inst["id"],
                "venue_id": inst["venue_id"],
                "title": venue["title"],
                "short_name": venue["short_name"],
                "domain": venue["domain"],
                "type": venue["type"],
                "tier": venue["tier"],
                "website": venue["website"],
                "cfp_url": venue["cfp_url"],
                "year": inst["year"],
                "status": inst["status"],
                "deadlines": inst.get("deadlines", []),
                "venue_date_start": inst.get("venue_date_start"),
                "venue_date_end": inst.get("venue_date_end"),
                "location": inst.get("location"),
                "source_url": inst.get("source_url"),
                "checked_at": inst.get("checked_at"),
                "confidence": inst.get("confidence", 0),
                "scan_preview": inst.get("scan_preview", []),
                "notes": inst.get("notes"),
            }
        )

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with OUT_PATH.open("w", encoding="utf-8") as f:
        json.dump(merged, f, ensure_ascii=False, indent=2)

    print(f"[OK] wrote {len(merged)} merged records -> {OUT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
