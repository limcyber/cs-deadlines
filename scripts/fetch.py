from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

import requests
import yaml
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
VENUES_PATH = ROOT / "data" / "venues.yml"
INSTANCES_PATH = ROOT / "data" / "instances.yml"
CANDIDATES_PATH = ROOT / "data" / "candidate_venues.json"

HEADERS = {
    "User-Agent": "cs-deadlines-mvp/0.2 (+https://github.com/your-org/cs-deadlines-mvp)"
}
DATE_PATTERNS = [
    r"(?:deadline|abstract|paper|submission|important dates?)",
    r"(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s+\d{1,2},?\s+20\d{2}",
]


@dataclass
class ScanResult:
    venue_id: str
    ok: bool
    source_url: str
    checked_at: str
    matched_lines: List[str]
    notes: Optional[str] = None


def load_yaml(path: Path):
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or []


def save_yaml(path: Path, data) -> None:
    with path.open("w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, sort_keys=False, allow_unicode=True)


def fetch_text(url: str, timeout: int = 20) -> str:
    resp = requests.get(url, headers=HEADERS, timeout=timeout)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.extract()
    return soup.get_text("\n", strip=True)


def extract_candidate_lines(text: str, max_lines: int = 10) -> List[str]:
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    hits = []
    for line in lines:
        lower = line.lower()
        if any(re.search(pat, lower) for pat in DATE_PATTERNS):
            hits.append(line)
        if len(hits) >= max_lines:
            break
    return hits


def update_instances_with_scan(instances, result: ScanResult, year: int) -> list:
    instance_id = f"{result.venue_id}-{year}"
    existing = next((x for x in instances if x["id"] == instance_id), None)
    payload = {
        "id": instance_id,
        "venue_id": result.venue_id,
        "year": year,
        "status": "scanned" if result.ok else "scan_failed",
        "deadlines": [],
        "venue_date_start": None,
        "venue_date_end": None,
        "location": None,
        "source_url": result.source_url,
        "checked_at": result.checked_at,
        "confidence": 0.2 if result.ok and result.matched_lines else 0.0,
        "scan_preview": result.matched_lines[:5],
        "notes": result.notes,
    }
    if existing:
        existing.update(payload)
    else:
        instances.append(payload)
    return instances


def discover_new_candidates() -> None:
    if not CANDIDATES_PATH.exists():
        CANDIDATES_PATH.write_text("[]\n", encoding="utf-8")


def main() -> int:
    year = datetime.now(timezone.utc).year
    venues = load_yaml(VENUES_PATH)
    instances = load_yaml(INSTANCES_PATH)

    enabled = [v for v in venues if v.get("scan_enabled", False)]
    skipped = len(venues) - len(enabled)

    print(f"[INFO] scanning {len(enabled)} venues (skipping {skipped} catalog-only entries)")
    for venue in enabled:
        target_url = venue.get("cfp_url") or venue.get("website")
        checked_at = datetime.now(timezone.utc).isoformat()
        try:
            text = fetch_text(target_url)
            matched_lines = extract_candidate_lines(text)
            result = ScanResult(
                venue_id=venue["id"],
                ok=True,
                source_url=target_url,
                checked_at=checked_at,
                matched_lines=matched_lines,
                notes="MVP scanner: extracted candidate lines only; manual confirmation is still recommended.",
            )
            print(f"[OK] {venue['short_name']}: {len(matched_lines)} candidate lines")
        except Exception as exc:
            result = ScanResult(
                venue_id=venue["id"],
                ok=False,
                source_url=target_url,
                checked_at=checked_at,
                matched_lines=[],
                notes=f"fetch failed: {exc}",
            )
            print(f"[WARN] {venue['short_name']}: {exc}")

        instances = update_instances_with_scan(instances, result, year)

    save_yaml(INSTANCES_PATH, instances)
    discover_new_candidates()
    print("[DONE] instances.yml updated")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
