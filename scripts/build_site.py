from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
import yaml

ROOT = Path(__file__).resolve().parents[1]
VENUES_PATH = ROOT / "data" / "venues.yml"
INSTANCES_PATH = ROOT / "data" / "instances.yml"
PUBLIC_OUT_PATH = ROOT / "docs" / "assets" / "venues.json"
ADMIN_OUT_PATH = ROOT / "docs" / "assets" / "admin.json"


def load_yaml(path: Path):
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or []


def normalize_location_text(raw: str) -> str:
    # Normalize scanner text into a compact location string suitable for UI display.
    text = re.sub(r"\s+", " ", str(raw or "")).strip(" .,:;|-")
    text = re.sub(r"^(?:in person in|in person at|in-person in|in-person at|person in|person at)\s+", "", text, flags=re.IGNORECASE)
    for stop in [" from ", " during ", " on ", " with ", " for ", " (" ]:
        idx = text.lower().find(stop)
        if idx > 0:
            text = text[:idx]
    return text.strip(" .,:;|-")


def is_plausible_location(value: str | None) -> bool:
    text = normalize_location_text(value)
    if not text:
        return False
    lower = text.lower()
    if len(text) < 4 or len(text) > 48:
        return False
    if re.search(r"\d", text):
        return False
    if text.count(",") > 2:
        return False
    if any(x in lower for x in ["tbd", "online", "virtual", "conference", "symposium", "heart of"]):
        return False
    if lower in {"person"} or lower.startswith("person "):
        return False
    if lower.startswith("person in ") or lower.startswith("person at "):
        return False
    if re.fullmatch(r"the\s+st\.?", lower):
        return False
    return True


def extract_location_from_text(text: str) -> str | None:
    if not text:
        return None
    patterns = [
        re.compile(r"\b(?:held in|held at|takes place in|will take place in|will be held in|located in)\s+([^.;]{4,90})", re.IGNORECASE),
        re.compile(r"\b(?:location|venue)\s*:\s*([^.;]{4,90})", re.IGNORECASE),
    ]
    for line in text.splitlines():
        for pat in patterns:
            match = pat.search(line)
            if not match:
                continue
            candidate = normalize_location_text(match.group(1))
            if is_plausible_location(candidate):
                return candidate
    return None


def resolve_location(inst: dict | None, venue: dict) -> str | None:
    if inst and is_plausible_location(inst.get("location")):
        return normalize_location_text(inst.get("location"))

    # Fall back to loose text extraction so manual/catalog entries can still surface a venue.
    text_chunks = []
    if inst:
        text_chunks.extend(inst.get("scan_preview") or [])
        if inst.get("notes"):
            text_chunks.append(inst.get("notes"))
    if venue.get("notes"):
        text_chunks.append(venue.get("notes"))

    extracted = extract_location_from_text("\n".join(str(x) for x in text_chunks if x))
    return extracted


def merge_records(venues, instances):
    current_year = datetime.now(timezone.utc).year
    latest_by_venue = {}
    for inst in instances:
        venue_id = inst["venue_id"]
        current = latest_by_venue.get(venue_id)
        if current is None or inst.get("year", 0) >= current.get("year", 0):
            latest_by_venue[venue_id] = inst

    merged = []
    for venue in venues:
        # The site shows one "current" record per venue, using the latest known instance.
        inst = latest_by_venue.get(venue["id"])
        status = inst.get("status") if inst else "catalog_seed"
        if (
            inst
            and not venue.get("scan_enabled", False)
            and status in {"review_required", "scanned", "scan_failed"}
            and not (inst.get("deadlines") or inst.get("parsed_deadlines"))
        ):
            # Catalog/manual venues should not appear as scanner review work items.
            status = "catalog_seed"
        record = {
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
            "status": status,
            "deadlines": inst.get("deadlines", []) if inst else [],
            "venue_date_start": inst.get("venue_date_start") if inst else None,
            "venue_date_end": inst.get("venue_date_end") if inst else None,
            "location": resolve_location(inst, venue),
            "source_url": inst.get("source_url") if inst else None,
            "checked_at": inst.get("checked_at") if inst else None,
            "confidence": inst.get("confidence", 0) if inst else 0,
            "scan_preview": inst.get("scan_preview", []) if inst else [],
            "notes": inst.get("notes") if inst and inst.get("notes") else venue.get("notes"),
            "parser": venue.get("parser"),
            "scan_enabled": venue.get("scan_enabled", False),
            "active": venue.get("active", True),
            "default_timezone": venue.get("default_timezone"),
            "recurring": venue.get("recurring", True),
            "source_type": inst.get("source_type") if inst else None,
            "parsed_deadlines": inst.get("parsed_deadlines", []) if inst else [],
            "year_mentions": inst.get("year_mentions", []) if inst else [],
            "auto_review": inst.get("auto_review") if inst else None,
        }
        merged.append(record)

    merged.sort(key=lambda x: (x["short_name"].lower(), x["year"]))
    return merged


def write_json(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def has_preview_deadline(record: dict) -> bool:
    # Public preview only exposes parsed dates once they clear a minimum confidence floor.
    parsed = record.get("parsed_deadlines") or []
    if not parsed:
        return False
    best_conf = max((float(item.get("confidence", 0) or 0) for item in parsed), default=0.0)
    return best_conf >= 0.35


def main() -> int:
    venues = load_yaml(VENUES_PATH)
    instances = load_yaml(INSTANCES_PATH)
    merged = merge_records(venues, instances)
    # Public JSON stays conservative: confirmed data plus preview-worthy scanner candidates.
    public_records = [
        x
        for x in merged
        if (
            x.get("status") in {"confirmed", "auto_confirmed"}
            or not x.get("scan_enabled", False)
            or (
                x.get("scan_enabled", False)
                and x.get("status") in {"scanned", "review_required"}
                and has_preview_deadline(x)
            )
        )
    ]

    write_json(PUBLIC_OUT_PATH, public_records)
    write_json(ADMIN_OUT_PATH, merged)

    print(f"[OK] wrote {len(public_records)} public records -> {PUBLIC_OUT_PATH}")
    print(f"[OK] wrote {len(merged)} admin records  -> {ADMIN_OUT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
