from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

import requests
import yaml
from bs4 import BeautifulSoup

from deadline_utils import (
    ParsedCandidate,
    classify_deadline_kind,
    extract_dates_from_text,
    extract_year_mentions,
    infer_source_quality,
    keyword_strength,
    normalize_ws,
)

ROOT = Path(__file__).resolve().parents[1]
VENUES_PATH = ROOT / "data" / "venues.yml"
INSTANCES_PATH = ROOT / "data" / "instances.yml"
CANDIDATES_PATH = ROOT / "data" / "candidate_venues.json"

HEADERS = {
    # Use a stable, non-placeholder user-agent for crawler observability.
    "User-Agent": "cs-deadlines-tracker/0.5"
}
KEYWORD_PATTERN = re.compile(
    r"(?:deadline|abstract|paper|submission|important dates?|camera[- ]ready|notification|rebuttal)",
    re.IGNORECASE,
)
SCRIPT_DATE_PATTERN = re.compile(
    r"(?:"
    r"(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\s+\d{1,2}(?:st|nd|rd|th)?(?:,)?\s+(?:20\d{2})"
    r"|(?:\d{1,2}(?:st|nd|rd|th)?\s+(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*(?:,)?\s+(?:20\d{2}))"
    r"|(?:20\d{2}[-/]\d{1,2}[-/]\d{1,2})"
    r"|(?:\d{1,2}[./-]\d{1,2}[./-](?:20)?\d{2})"
    r")",
    re.IGNORECASE,
)
MONTH_DAY_PATTERN = re.compile(
    r"\b(?P<month>jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\s+(?P<day>\d{1,2})(?:st|nd|rd|th)?\b",
    re.IGNORECASE,
)
MONTH_TO_NUM = {
    "jan": 1,
    "feb": 2,
    "mar": 3,
    "apr": 4,
    "may": 5,
    "jun": 6,
    "jul": 7,
    "aug": 8,
    "sep": 9,
    "sept": 9,
    "oct": 10,
    "nov": 11,
    "dec": 12,
}
NETWORK_FAILURE_TOKENS = (
    "nameresolutionerror",
    "failed to resolve",
    "temporary failure in name resolution",
    "max retries exceeded",
    "newconnectionerror",
    "connection refused",
    "network is unreachable",
    "nodename nor servname provided",
)


@dataclass
class ScanResult:
    # Normalized fetch output before it is merged back into instances.yml.
    venue_id: str
    ok: bool
    source_url: str
    checked_at: str
    matched_lines: List[str]
    parsed_deadlines: List[dict]
    source_type: str
    year_mentions: List[int]
    location: Optional[str] = None
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
    # Some conference pages keep deadline text in inline JSON or script blobs.
    script_hints = extract_script_hints(soup)
    for tag in soup(["script", "style", "noscript"]):
        tag.extract()
    base_text = soup.get_text("\n", strip=True)
    if script_hints:
        return f"{base_text}\n" + "\n".join(script_hints)
    return base_text


def decode_script_text(raw: str) -> str:
    text = raw or ""
    text = text.replace("\\/", "/")
    # Decode common escaped HTML entities in JSON blobs.
    text = text.replace("\\u003c", "<").replace("\\u003e", ">").replace("\\u0026", "&")
    return text


def extract_script_hints(soup: BeautifulSoup, max_lines: int = 80) -> list[str]:
    hints: list[str] = []
    seen: set[str] = set()
    split_pattern = re.compile(r"[;\n{}]+")

    # Pull short deadline-like snippets out of scripts so JS-heavy sites stay partially parseable.
    for script in soup.find_all("script"):
        raw = script.get_text("\n", strip=True)
        if not raw:
            continue
        decoded = decode_script_text(raw)
        for chunk in split_pattern.split(decoded):
            candidate = normalize_ws(chunk)
            if not candidate:
                continue
            if candidate in seen:
                continue
            if len(candidate) < 10 or len(candidate) > 240:
                continue
            has_date = bool(SCRIPT_DATE_PATTERN.search(candidate))
            has_keyword = bool(KEYWORD_PATTERN.search(candidate)) or "aoe" in candidate.lower()
            if not has_date or not has_keyword:
                continue
            hints.append(candidate)
            seen.add(candidate)
            if len(hints) >= max_lines:
                return hints
    return hints


def extract_candidate_lines(text: str, max_lines: int = 12) -> List[str]:
    # Favor concise lines near explicit dates/keywords to keep later scoring interpretable.
    lines = [normalize_ws(ln) for ln in text.splitlines() if normalize_ws(ln)]
    primary: list[str] = []
    secondary: list[str] = []
    seen: set[str] = set()

    def add_primary(value: str) -> None:
        item = normalize_ws(value)
        if not item or item in seen:
            return
        primary.append(item)
        seen.add(item)

    def add_secondary(value: str) -> None:
        item = normalize_ws(value)
        if not item or item in seen:
            return
        secondary.append(item)
        seen.add(item)

    for idx, line in enumerate(lines):
        lower = line.lower()
        has_date_here = bool(extract_dates_from_text(line)) or bool(MONTH_DAY_PATTERN.search(line))
        keyword_here = bool(KEYWORD_PATTERN.search(lower))
        next_line = lines[idx + 1] if idx + 1 < len(lines) else ""
        has_date_next = bool(next_line) and (bool(extract_dates_from_text(next_line)) or bool(MONTH_DAY_PATTERN.search(next_line)))

        if has_date_here:
            add_primary(line)
            continue

        if keyword_here and has_date_next:
            add_primary(line)
            add_primary(next_line)
            continue

        if keyword_here:
            add_secondary(line)

    return (primary + secondary)[:max_lines]


def parser_name_for(venue: dict) -> str:
    # Auto-upgrade generic parsers for a few domains with reliably structured formats.
    parser_name = (venue.get("parser") or "generic_dates").lower()
    url = (venue.get("cfp_url") or venue.get("website") or "").lower()
    if "thecvf.com" in url and parser_name == "generic_dates":
        return "thecvf_dates"
    if "openreview.net" in url and parser_name == "generic_dates":
        return "openreview_dates"
    return parser_name


def year_fallback_urls(url: str, target_year: int) -> list[str]:
    if not url:
        return []
    # Many venues publish next-year CFPs under last year's URL pattern first.
    prev_year = target_year - 1
    out: list[str] = []
    seen: set[str] = set()
    base = url
    candidates = [base]

    full_cur = str(target_year)
    full_prev = str(prev_year)
    yy_cur = f"{target_year % 100:02d}"
    yy_prev = f"{prev_year % 100:02d}"

    if full_cur in base:
        candidates.append(base.replace(full_cur, full_prev))

    token_patterns = [
        (rf"(?<=\D){yy_cur}(?=\D|$)", yy_prev),
        (rf"(?<=\bsc){yy_cur}(?=\b|\.)", yy_prev),
        (rf"(?<=\bsdm){yy_cur}(?=\b|/)", yy_prev),
    ]
    for pattern, repl in token_patterns:
        try:
            replaced = re.sub(pattern, repl, base, count=1)
        except re.error:
            replaced = base
        if replaced != base:
            candidates.append(replaced)

    for cand in candidates:
        if cand and cand not in seen:
            out.append(cand)
            seen.add(cand)
    return out


def score_raw_candidate(raw_text: str, parser_name: str) -> float:
    # Candidate confidence is intentionally shallow and explainable; final promotion happens later.
    has_full_date = bool(extract_dates_from_text(raw_text))
    has_month_day = bool(MONTH_DAY_PATTERN.search(raw_text or ""))
    score = 0.35 if has_full_date else (0.20 if has_month_day else 0.0)
    kw_score, _ = keyword_strength(raw_text)
    score += max(0.0, kw_score)
    if parser_name in {"thecvf_dates", "openreview_dates", "structured_dates"}:
        score += 0.05
    if "aoe" in raw_text.lower():
        score += 0.05
    return min(score, 0.95)


def looks_like_noise_line(text: str) -> bool:
    lower = (text or "").lower()
    return any(
        token in lower
        for token in [
            "retrieved on",
            "curated by",
            "update ",
            "copyright",
            "all rights reserved",
        ]
    )


def is_plausible_deadline_year(target_year: int, candidate_year: int, month: int) -> bool:
    if candidate_year == target_year:
        return True
    # Many venues announce year N deadlines in late year N-1.
    if candidate_year == target_year - 1 and month >= 8:
        return True
    # Allow very early-year deadlines in year N+1 for shifted schedules.
    if candidate_year == target_year + 1 and month <= 2:
        return True
    return False


def normalize_location_text(raw: str) -> str:
    text = normalize_ws(raw)
    text = re.sub(r"^(?:in person in|in person at|in-person in|in-person at)\s+", "", text, flags=re.IGNORECASE)
    text = re.sub(r"^(?:person in|person at)\s+", "", text, flags=re.IGNORECASE)
    for stop in [" from ", " during ", " on ", " with ", " for ", " (" ]:
        idx = text.lower().find(stop)
        if idx > 0:
            text = text[:idx]
    if " - " in text:
        text = text.split(" - ", 1)[0]
    text = re.sub(r"\s+", " ", text).strip(" .,:;|-")
    return text


def extract_location_hint(text: str) -> str | None:
    lines = [normalize_ws(line) for line in (text or "").splitlines() if normalize_ws(line)]
    patterns = [
        re.compile(
            r"\b(?:held in|held at|takes place in|will take place in|will be held in|located in)\s+([^.;]{4,90})",
            re.IGNORECASE,
        ),
        re.compile(
            r"\b(?:location|venue)\s*:\s*([^.;]{4,90})",
            re.IGNORECASE,
        ),
    ]
    bad_tokens = {
        "online",
        "virtual",
        "tbd",
        "to be announced",
        "n/a",
        "conference",
        "workshop",
        "symposium",
        "heart of",
    }

    for line in lines:
        for pat in patterns:
            match = pat.search(line)
            if not match:
                continue
            candidate = normalize_location_text(match.group(1))
            lower = candidate.lower()
            if len(candidate) < 4:
                continue
            if any(token in lower for token in bad_tokens):
                continue
            if any(ch.isdigit() for ch in candidate):
                continue
            if len(candidate) > 48:
                continue
            if candidate.count(",") > 2:
                continue
            if re.fullmatch(r"(?i)the\s+st\.?", candidate):
                continue
            if "," not in candidate and len(candidate.split()) < 2:
                continue
            return candidate
    return None


def parse_deadlines_from_lines(lines: list[str], venue: dict, target_year: int, allow_prev_year_fallback: bool = False) -> list[dict]:
    parser_name = parser_name_for(venue)
    parsed: list[ParsedCandidate] = []
    for line in lines:
        if looks_like_noise_line(line):
            continue
        dates = extract_dates_from_text(line)
        if not dates:
            dates = extract_month_day_without_year(line, target_year)
        if not dates:
            continue
        kind = classify_deadline_kind(line)
        for dt in dates[:2]:
            plausible = is_plausible_deadline_year(target_year, dt.year, dt.month)
            if not plausible and allow_prev_year_fallback and dt.year == target_year - 1:
                plausible = True
            if not plausible:
                continue
            parsed.append(
                ParsedCandidate(
                    kind=kind,
                    value=dt.date().isoformat(),
                    raw_text=line,
                    confidence=score_raw_candidate(line, parser_name),
                    source_parser=parser_name,
                )
            )
    unique = {}
    for item in parsed:
        key = (item.kind, item.value, item.raw_text)
        if key not in unique or unique[key].confidence < item.confidence:
            unique[key] = item
    return [
        {
            "kind": item.kind,
            "value": item.value,
            "raw_text": item.raw_text,
            "confidence": round(item.confidence, 4),
            "source_parser": item.source_parser,
            "year_fallback": bool(allow_prev_year_fallback),
        }
        for item in sorted(unique.values(), key=lambda x: (-x.confidence, x.value))
    ]


def infer_year_for_month_day(target_year: int, month: int) -> int:
    # CFP deadlines for year N are frequently in late year N-1.
    return target_year - 1 if month >= 8 else target_year


def extract_month_day_without_year(text: str, target_year: int) -> list[datetime]:
    out: list[datetime] = []
    seen: set[str] = set()
    for match in MONTH_DAY_PATTERN.finditer(text or ""):
        month_key = (match.group("month") or "").lower()
        day_raw = match.group("day")
        if month_key not in MONTH_TO_NUM or not day_raw:
            continue
        month = MONTH_TO_NUM[month_key]
        day = int(day_raw)
        year = infer_year_for_month_day(target_year, month)
        try:
            dt = datetime(year, month, day, tzinfo=timezone.utc)
        except ValueError:
            continue
        key = dt.date().isoformat()
        if key in seen:
            continue
        seen.add(key)
        out.append(dt)
    return out


def update_instances_with_scan(instances, result: ScanResult, year: int) -> list:
    instance_id = f"{result.venue_id}-{year}"
    existing = next((x for x in instances if x["id"] == instance_id), None)
    existing_status = existing.get("status") if existing else None
    preserve_confirmed = existing_status in {"confirmed", "auto_confirmed"}
    if not result.ok and existing:
        keep_existing_payload = preserve_confirmed or bool(existing.get("deadlines") or existing.get("parsed_deadlines"))
        # Keep good existing data on fetch errors, but mark empty records as scan_failed.
        existing["source_url"] = result.source_url
        existing["source_type"] = result.source_type
        existing["checked_at"] = result.checked_at
        if result.location:
            existing["location"] = result.location
        existing["notes"] = result.notes
        if not keep_existing_payload:
            existing["status"] = "scan_failed"
            existing["confidence"] = 0.0
            existing["scan_preview"] = []
        return instances

    computed_status = "scan_failed"
    if result.ok:
        if result.parsed_deadlines:
            computed_status = "scanned"
        else:
            # Distinguish "page exists but no clear deadline" from a hard fetch/parser failure.
            merged_preview = "\n".join(result.matched_lines or [])
            has_concrete_date = bool(extract_dates_from_text(merged_preview) or MONTH_DAY_PATTERN.search(merged_preview))
            computed_status = "review_required" if has_concrete_date else "awaiting_cfp"

    payload = {
        "id": instance_id,
        "venue_id": result.venue_id,
        "year": year,
        "status": existing_status if preserve_confirmed else computed_status,
        "deadlines": existing.get("deadlines", []) if existing and preserve_confirmed else [],
        "parsed_deadlines": result.parsed_deadlines,
        "venue_date_start": existing.get("venue_date_start") if existing else None,
        "venue_date_end": existing.get("venue_date_end") if existing else None,
        "location": result.location if result.location else (existing.get("location") if existing else None),
        "source_url": result.source_url,
        "source_type": result.source_type,
        "checked_at": result.checked_at,
        "confidence": max([p.get("confidence", 0) for p in result.parsed_deadlines], default=(0.2 if result.ok and result.matched_lines else 0.0)),
        "scan_preview": result.matched_lines[:6],
        "year_mentions": result.year_mentions,
        "notes": result.notes,
    }
    if existing:
        existing.update(payload)
    else:
        instances.append(payload)
    return instances


def is_probable_network_failure(exc: Exception) -> bool:
    text = str(exc).lower()
    return any(token in text for token in NETWORK_FAILURE_TOKENS)


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
    network_failures = 0
    successful_fetches = 0
    for venue in enabled:
        target_url = venue.get("cfp_url") or venue.get("website")
        candidate_urls = year_fallback_urls(target_url, year)
        checked_at = datetime.now(timezone.utc).isoformat()
        last_exc: Exception | None = None
        best_result: ScanResult | None = None
        used_fallback_url = False
        try:
            primary_success_result: ScanResult | None = None
            for idx, url in enumerate(candidate_urls):
                use_prev_year = idx > 0
                try:
                    text = fetch_text(url)
                    matched_lines = extract_candidate_lines(text)
                    parsed_deadlines = parse_deadlines_from_lines(
                        matched_lines,
                        venue,
                        year,
                        allow_prev_year_fallback=use_prev_year,
                    )
                    year_mentions = extract_year_mentions("\n".join(matched_lines))
                    location_hint = extract_location_hint(text)
                    notes = "Scanner extracted candidate lines and structured date candidates; auto-review may promote safe updates."
                    if use_prev_year:
                        notes = (
                            "Primary-year source had no structured dates; used current_year-1 URL fallback. "
                            + notes
                        )
                    scan_result = ScanResult(
                        venue_id=venue["id"],
                        ok=True,
                        source_url=url,
                        checked_at=checked_at,
                        matched_lines=matched_lines,
                        parsed_deadlines=parsed_deadlines,
                        source_type=infer_source_quality(url),
                        year_mentions=year_mentions,
                        location=location_hint,
                        notes=notes,
                    )
                    if idx == 0:
                        primary_success_result = scan_result
                        best_result = scan_result
                        # Primary URL already produced structured output.
                        if parsed_deadlines:
                            break
                        continue

                    # For fallback URLs, only promote when we actually find structured dates.
                    if parsed_deadlines:
                        best_result = scan_result
                        used_fallback_url = True
                        break
                except Exception as exc:
                    last_exc = exc
                    if is_probable_network_failure(exc):
                        network_failures += 1
                    continue

            if not best_result and primary_success_result:
                best_result = primary_success_result

            if best_result:
                result = best_result
                successful_fetches += 1
                print(
                    f"[OK] {venue['short_name']}: {len(result.matched_lines)} candidate lines, "
                    f"{len(result.parsed_deadlines)} structured dates"
                    + (" (year-1 fallback)" if used_fallback_url else "")
                    + (f", location={result.location}" if result.location else "")
                )
            else:
                raise last_exc or RuntimeError("fetch failed without candidate result")
        except Exception as exc:
            result = ScanResult(
                venue_id=venue["id"],
                ok=False,
                source_url=target_url,
                checked_at=checked_at,
                matched_lines=[],
                parsed_deadlines=[],
                source_type=infer_source_quality(target_url),
                year_mentions=[],
                location=None,
                notes=f"fetch failed: {exc}",
            )
            print(f"[WARN] {venue['short_name']}: {exc}")

        instances = update_instances_with_scan(instances, result, year)

    if enabled:
        failure_ratio = network_failures / len(enabled)
        large_outage = network_failures >= max(5, int(len(enabled) * 0.4))
        # Stop before writing if a broad network outage is likely.
        if (successful_fetches == 0 and failure_ratio >= 0.6) or (large_outage and failure_ratio >= 0.4):
            print(
                f"[FAIL] probable network outage detected "
                f"(network_failures={network_failures}/{len(enabled)}). "
                "Aborting without writing instances.yml."
            )
            return 2

    save_yaml(INSTANCES_PATH, instances)
    discover_new_candidates()
    print("[DONE] instances.yml updated")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
