from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests
import yaml
from bs4 import BeautifulSoup

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))
from common import has_extension_language, infer_kind, parse_datetime  # noqa: E402

ROOT = SCRIPT_DIR.parents[0]
VENUES_PATH = ROOT / "data" / "venues.yml"
INSTANCES_PATH = ROOT / "data" / "instances.yml"
FAILURES_PATH = ROOT / "data" / "scan_failures.json"
SUMMARY_PATH = ROOT / "data" / "scan_run_summary.json"
SUMMARY_MD_PATH = ROOT / "data" / "last_run_summary.md"

HEADERS = {
    "User-Agent": "cs-deadlines-final/1.0 (+https://github.com/your-org/cs-deadlines)"
}
DATE_REGEX = re.compile(
    r"((?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s+\d{1,2},?\s+20\d{2}(?:[^\n]{0,40}?)(?:\d{1,2}:\d{2})?(?:\s*(?:am|pm))?(?:\s*(?:AoE|UTC|PDT|PST|CET|CEST|EST|EDT))?)",
    re.IGNORECASE,
)


@dataclass
class Candidate:
    text: str
    detected_kind: str
    detected_value: str | None
    source: str
    confidence: str
    extension_detected: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "text": self.text,
            "detected_kind": self.detected_kind,
            "detected_value": self.detected_value,
            "source": self.source,
            "confidence": self.confidence,
            "extension_detected": self.extension_detected,
        }


def load_yaml(path: Path):
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle) or []


def save_yaml(path: Path, data) -> None:
    with path.open("w", encoding="utf-8") as handle:
        yaml.safe_dump(data, handle, sort_keys=False, allow_unicode=True)


def fetch_html(url: str, timeout: int = 20) -> tuple[str, BeautifulSoup]:
    response = requests.get(url, headers=HEADERS, timeout=timeout)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")
    return response.text, soup


def clean_soup_text(soup: BeautifulSoup) -> str:
    cloned = BeautifulSoup(str(soup), "html.parser")
    for tag in cloned(["script", "style", "noscript"]):
        tag.extract()
    return cloned.get_text("\n", strip=True)


def parse_candidate_line(line: str, parser_type: str) -> Candidate | None:
    match = DATE_REGEX.search(line)
    if not match:
        return None
    date_text = match.group(1).strip()
    dt = parse_datetime(date_text)
    detected_value = dt.isoformat() if dt else None
    detected_kind = infer_kind(line)
    extension_detected = has_extension_language(line)
    confidence = "high" if parser_type == "structured_dates" and detected_value else "medium" if detected_value else "low"
    return Candidate(
        text=line.strip(),
        detected_kind=detected_kind,
        detected_value=detected_value,
        source="official",
        confidence=confidence,
        extension_detected=extension_detected,
    )


def generic_candidates(text: str, parser_type: str) -> list[Candidate]:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    results: list[Candidate] = []
    for line in lines:
        lowered = line.lower()
        if not any(token in lowered for token in ["deadline", "abstract", "paper", "submission", "notification", "camera", "important date"]):
            continue
        candidate = parse_candidate_line(line, parser_type)
        if candidate:
            results.append(candidate)
        if len(results) >= 8:
            break
    return results


def structured_candidates(soup: BeautifulSoup, parser_type: str) -> list[Candidate]:
    results: list[Candidate] = []
    for block in soup.find_all(["table", "section", "div"]):
        text = block.get_text(" ", strip=True)
        lowered = text.lower()
        if not text or len(text) < 20:
            continue
        if "important dates" not in lowered and "deadline" not in lowered:
            continue
        for segment in re.split(r"(?<=[.;])\s+|\n", text):
            candidate = parse_candidate_line(segment, parser_type)
            if candidate:
                results.append(candidate)
        if results:
            break
    return results[:8]


def existing_confirmed_by_kind(instance: dict) -> dict[str, str]:
    mapping = {}
    for item in instance.get("deadlines", []) or []:
        if item.get("confirmed"):
            mapping[item.get("kind")] = item.get("value")
    return mapping


def update_instance(instances: list[dict], venue: dict, candidates: list[Candidate], checked_at: str, source_url: str, fetch_error: str | None = None):
    year = datetime.now(timezone.utc).year
    instance_id = f"{venue['id']}-{year}"
    existing = next((item for item in instances if item.get("id") == instance_id), None)
    if existing is None:
        existing = {
            "id": instance_id,
            "venue_id": venue["id"],
            "year": year,
            "scan_status": "catalog_seed",
            "checked_at": None,
            "source_url": source_url,
            "confidence": "low",
            "review_required": False,
            "conflict_reason": None,
            "scan_preview": [],
            "deadlines": [],
            "venue_date_start": None,
            "venue_date_end": None,
            "location": None,
        }
        instances.append(existing)

    existing_confirmed = existing_confirmed_by_kind(existing)
    preview = [candidate.to_dict() for candidate in candidates]
    review_required = False
    conflict_reason = None
    auto_promoted = []

    for candidate in candidates:
        if candidate.detected_kind in existing_confirmed and candidate.detected_value and existing_confirmed[candidate.detected_kind] != candidate.detected_value:
            review_required = True
            conflict_reason = f"Detected {candidate.detected_kind} deadline differs from the previously confirmed value."
        if candidate.extension_detected:
            review_required = True
            conflict_reason = conflict_reason or "Possible extension language detected."
        if (
            not existing_confirmed.get(candidate.detected_kind)
            and candidate.detected_value
            and venue.get("parser") == "structured_dates"
            and candidate.confidence == "high"
            and not candidate.extension_detected
        ):
            auto_promoted.append(
                {
                    "kind": candidate.detected_kind,
                    "value": candidate.detected_value,
                    "timezone": venue.get("default_timezone") or "UTC",
                    "source": "official",
                    "confirmed": True,
                    "confidence": "high",
                }
            )

    existing["checked_at"] = checked_at
    existing["source_url"] = source_url
    existing["scan_preview"] = preview
    existing["review_required"] = review_required
    existing["conflict_reason"] = conflict_reason if review_required else None
    if fetch_error:
        existing["scan_status"] = "scan_failed"
        existing["confidence"] = "low"
        existing["notes"] = fetch_error
    else:
        existing["scan_status"] = "confirmed" if existing.get("deadlines") else "scanned"
        existing["confidence"] = max([candidate.confidence for candidate in candidates], key=lambda x: {"low": 0, "medium": 1, "high": 2}[x], default="low")
        if auto_promoted:
            existing["deadlines"] = existing.get("deadlines", []) + auto_promoted
            existing["scan_status"] = "confirmed"
    return existing


def main() -> int:
    venues = load_yaml(VENUES_PATH)
    instances = load_yaml(INSTANCES_PATH)
    failures: list[dict[str, Any]] = []
    counts = {"scanned": 0, "failed": 0, "review_required": 0, "auto_promoted": 0, "skipped": 0}

    enabled = [venue for venue in venues if venue.get("scan_enabled")]
    for venue in enabled:
        parser_type = venue.get("parser", "generic_dates")
        checked_at = datetime.now(timezone.utc).isoformat()
        source_url = venue.get("cfp_url") or venue.get("website")
        if parser_type == "manual":
            counts["skipped"] += 1
            continue
        try:
            _, soup = fetch_html(source_url)
            text = clean_soup_text(soup)
            if parser_type == "structured_dates":
                candidates = structured_candidates(soup, parser_type) or generic_candidates(text, parser_type)
            else:
                candidates = generic_candidates(text, parser_type)
            before = next((item for item in instances if item.get("id") == f"{venue['id']}-{datetime.now(timezone.utc).year}"), None)
            before_deadlines = len(before.get("deadlines", [])) if before else 0
            updated = update_instance(instances, venue, candidates, checked_at, source_url)
            counts["scanned"] += 1
            counts["review_required"] += 1 if updated.get("review_required") else 0
            counts["auto_promoted"] += max(0, len(updated.get("deadlines", [])) - before_deadlines)
        except Exception as exc:
            failures.append(
                {
                    "venue_id": venue.get("id"),
                    "short_name": venue.get("short_name"),
                    "timestamp": checked_at,
                    "source_url": source_url,
                    "parser": parser_type,
                    "failure_type": type(exc).__name__,
                    "error_message": str(exc)[:300],
                }
            )
            update_instance(instances, venue, [], checked_at, source_url, fetch_error=str(exc))
            counts["failed"] += 1

    save_yaml(INSTANCES_PATH, instances)
    FAILURES_PATH.write_text(json.dumps(failures, indent=2), encoding="utf-8")
    summary = {"generated_at": datetime.now(timezone.utc).isoformat(), "counts": counts, "failures": failures[:20]}
    SUMMARY_PATH.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    SUMMARY_MD_PATH.write_text(
        "\n".join(
            [
                "# Scan Run Summary",
                f"- Generated at: {summary['generated_at']}",
                f"- Scanned venues: {counts['scanned']}",
                f"- Failed scans: {counts['failed']}",
                f"- Review required: {counts['review_required']}",
                f"- Auto-promoted deadlines: {counts['auto_promoted']}",
                f"- Skipped manual venues: {counts['skipped']}",
            ]
        ),
        encoding="utf-8",
    )
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
