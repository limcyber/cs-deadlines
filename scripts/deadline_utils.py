from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable

from dateutil import parser as dateparser

MONTH_PATTERN = r"(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*"
DATE_REGEX = re.compile(
    rf"(?P<expr>"
    rf"(?:{MONTH_PATTERN})\s+\d{{1,2}}(?:st|nd|rd|th)?(?:,)?\s+(?:20\d{{2}})"
    rf"|(?:\d{{1,2}}(?:st|nd|rd|th)?\s+(?:{MONTH_PATTERN})(?:,)?\s+(?:20\d{{2}}))"
    rf"|(?:20\d{{2}}[-/]\d{{1,2}}[-/]\d{{1,2}})"
    rf"|(?:\d{{1,2}}[-/]\d{{1,2}}[-/](?:20)?\d{{2}})"
    rf"|(?:\d{{1,2}}\.\d{{1,2}}\.(?:20)?\d{{2}})"
    rf")",
    re.IGNORECASE,
)
YEAR_REGEX = re.compile(r"\b(20\d{2})\b")

POSITIVE_KEYWORDS = {
    "paper submission deadline": 0.20,
    "submission deadline": 0.20,
    "full paper deadline": 0.20,
    "important dates": 0.12,
    "abstract deadline": 0.08,
    "deadline": 0.06,
    "papers due": 0.10,
    "submission": 0.04,
}
NEGATIVE_KEYWORDS = {
    "notification": -0.10,
    "camera ready": -0.10,
    "camera-ready": -0.10,
    "rebuttal": -0.08,
    "poster deadline": -0.10,
    "workshop deadline": -0.10,
    "demo deadline": -0.10,
}
PHASE_THRESHOLDS = {1: 0.90, 2: 0.85, 3: 0.82}
VENUE_TRUST = {
    "thecvf_dates": 0.08,
    "openreview_dates": 0.06,
    "acm_dates": 0.05,
    "acl_dates": 0.06,
    "usenix_dates": 0.06,
    "structured_dates": 0.06,
    "generic_dates": 0.00,
    "manual": -0.05,
}


@dataclass
class ParsedCandidate:
    # Intermediate candidate shape used before writing normalized dicts to YAML/JSON.
    kind: str
    value: str
    raw_text: str
    confidence: float
    source_parser: str


def clamp(v: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, v))


def safe_date(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        # Preserve date-only values in UTC so downstream comparisons stay consistent.
        if len(value) == 10 and re.match(r"\d{4}-\d{2}-\d{2}$", value):
            return datetime.fromisoformat(value).replace(tzinfo=timezone.utc)
        dt = dateparser.parse(value)
        if dt is None:
            return None
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None


def iso_date(value: datetime) -> str:
    return value.date().isoformat()


def normalize_ws(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def classify_deadline_kind(text: str) -> str:
    # Collapse many deadline label variants into a smaller set used by the UI and scoring.
    t = normalize_ws(text).lower()
    if "abstract" in t:
        return "abstract"
    if "full paper" in t or "technical paper" in t or "research paper" in t or "paper submission" in t:
        return "paper"
    if "submission" in t or "papers due" in t:
        return "paper"
    if "rebuttal" in t or "response" in t:
        return "rebuttal"
    if "notification" in t:
        return "notification"
    if "camera-ready" in t or "camera ready" in t:
        return "camera_ready"
    if "workshop" in t:
        return "workshop"
    return "deadline"


def extract_year_mentions(text: str) -> list[int]:
    return [int(m.group(1)) for m in YEAR_REGEX.finditer(text or "")]


def extract_dates_from_text(text: str) -> list[datetime]:
    results: list[datetime] = []
    for match in DATE_REGEX.finditer(text or ""):
        expr = match.group("expr")
        try:
            use_dayfirst = bool(re.match(r"^\d{1,2}\.\d{1,2}\.(?:20)?\d{2}$", expr.strip()))
            parsed = dateparser.parse(expr, fuzzy=True, dayfirst=use_dayfirst)
        except Exception:
            parsed = None
        if parsed is None:
            continue
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        results.append(parsed)
    # Dedupe by calendar day while keeping the first-seen ordering from source text.
    seen = set()
    unique: list[datetime] = []
    for item in results:
        key = item.date().isoformat()
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)
    return unique


def keyword_strength(text: str) -> tuple[float, list[str]]:
    lower = normalize_ws(text).lower()
    score = 0.0
    reasons: list[str] = []
    for key, value in POSITIVE_KEYWORDS.items():
        if key in lower:
            score += value
            reasons.append(f"keyword:{key}")
    for key, value in NEGATIVE_KEYWORDS.items():
        if key in lower:
            score += value
            reasons.append(f"keyword:{key}")
    return score, reasons


def detect_timezone_bonus(text: str) -> float:
    lower = (text or "").lower()
    if "aoe" in lower or "utc" in lower or "anywhere on earth" in lower:
        return 0.05
    return 0.0


def infer_source_quality(url: str | None) -> str:
    lower = (url or "").lower()
    if not lower:
        return "unknown"
    if any(x in lower for x in ["call-for-papers", "important-dates", "cfp", "submission"]):
        return "official_cfp"
    if any(x in lower for x in ["thecvf.com", "openreview.net", "researchr.org", "acm.org", "usenix.org", "aclweb.org"]):
        return "official"
    if any(x in lower for x in ["blog", "medium.com", "reddit.com"]):
        return "unofficial"
    return "general"


def source_quality_bonus(url: str | None) -> float:
    quality = infer_source_quality(url)
    return {
        "official_cfp": 0.10,
        "official": 0.05,
        "general": 0.00,
        "unofficial": -0.25,
        "unknown": 0.00,
    }[quality]


def candidate_count_bonus(count: int) -> float:
    if count <= 3:
        return 0.08
    if count >= 9:
        return -0.12
    return 0.0


def proximity_bonus(text: str) -> float:
    lower = normalize_ws(text).lower()
    if "deadline" in lower and extract_dates_from_text(text):
        return 0.10
    return 0.0


def best_deadline(parsed_deadlines: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not parsed_deadlines:
        return None
    return sorted(parsed_deadlines, key=lambda d: (-float(d.get("confidence", 0)), d.get("value", "")))[0]


def phase_threshold(phase: int) -> float:
    return PHASE_THRESHOLDS.get(phase, PHASE_THRESHOLDS[3])


def parser_trust_bonus(parser_name: str | None, phase: int) -> float:
    # Early phases avoid trust bonuses to keep auto-confirm behavior intentionally conservative.
    base = VENUE_TRUST.get((parser_name or "generic_dates").lower(), 0.0)
    if phase <= 1:
        return 0.0
    if phase == 2:
        return max(0.0, base)
    return base


def find_reference_history(instances: list[dict[str, Any]], venue_id: str, current_id: str) -> list[dict[str, Any]]:
    history = [
        inst for inst in instances
        if inst.get("venue_id") == venue_id
        and inst.get("id") != current_id
        and (inst.get("status") in {"confirmed", "auto_confirmed"})
        and inst.get("deadlines")
    ]
    history.sort(key=lambda x: x.get("year", 0), reverse=True)
    return history


def nearest_historical_deadline(history: list[dict[str, Any]], kind: str | None = None) -> tuple[dict[str, Any] | None, int | None]:
    for inst in history:
        deadlines = inst.get("deadlines") or []
        if kind:
            candidates = [d for d in deadlines if d.get("kind") == kind]
            if candidates:
                return candidates[0], inst.get("year")
        if deadlines:
            return deadlines[0], inst.get("year")
    return None, None


def _align_reference_year(reference: datetime, target_year: int) -> datetime:
    try:
        return reference.replace(year=target_year)
    except ValueError:
        # Handle leap-day style edge cases conservatively.
        return reference.replace(year=target_year, day=min(reference.day, 28))


def date_diff_days(a: str | None, b: str | None, align_reference_to_candidate_year: bool = False) -> int | None:
    da = safe_date(a)
    db = safe_date(b)
    if not da or not db:
        return None
    if align_reference_to_candidate_year:
        db = _align_reference_year(db, da.year)
    return abs((da.date() - db.date()).days)


def predict_from_history(history: list[dict[str, Any]], kind: str | None = None) -> dict[str, Any] | None:
    # Use simple year-over-year drift instead of heavy forecasting so results stay debuggable.
    points: list[tuple[int, datetime]] = []
    for inst in sorted(history, key=lambda x: x.get("year", 0)):
        year = inst.get("year")
        deadlines = inst.get("deadlines") or []
        candidate = None
        if kind:
            candidate = next((d for d in deadlines if d.get("kind") == kind), None)
        if candidate is None and deadlines:
            candidate = deadlines[0]
        if year and candidate:
            d = safe_date(candidate.get("value"))
            if d:
                points.append((int(year), d))
    if len(points) < 2:
        return None
    delta_days = []
    for idx in range(1, len(points)):
        delta_days.append((points[idx][1].date() - points[idx - 1][1].date()).days)
    avg_delta = round(sum(delta_days) / len(delta_days)) if delta_days else 365
    predicted_dt = points[-1][1] + timedelta(days=avg_delta)
    return {
        "based_on_years": [p[0] for p in points[-3:]],
        "predicted_value": predicted_dt.date().isoformat(),
        "avg_delta_days": avg_delta,
    }


def score_best_candidate(
    instance: dict[str, Any],
    venue: dict[str, Any],
    history: list[dict[str, Any]],
    phase: int,
) -> dict[str, Any]:
    # The scoring model favors interpretable signals over ML so reviewers can audit decisions.
    parsed_deadlines = instance.get("parsed_deadlines") or []
    best = best_deadline(parsed_deadlines)
    score = 0.0
    reasons: list[str] = []
    hard_blockers: list[str] = []
    signals: dict[str, Any] = {
        "phase": phase,
        "parsed_date_count": len(parsed_deadlines),
        "candidate_line_count": len(instance.get("scan_preview") or []),
        "venue_has_history": bool(history),
    }

    if len(parsed_deadlines) == 1:
        score += 0.25
        reasons.append("parsed_single_date")
    elif len(parsed_deadlines) == 2:
        score += 0.10
        reasons.append("parsed_two_dates")
    elif len(parsed_deadlines) == 0:
        score -= 0.40
        hard_blockers.append("parse_failed")
    elif len(parsed_deadlines) >= 3:
        hard_blockers.append("too_many_dates")
        score -= 0.20

    quality = infer_source_quality(instance.get("source_url") or venue.get("cfp_url") or venue.get("website"))
    signals["source_quality"] = quality
    score += source_quality_bonus(instance.get("source_url") or venue.get("cfp_url") or venue.get("website"))
    reasons.append(f"source:{quality}")
    if quality == "unofficial":
        hard_blockers.append("unofficial_source")

    score += candidate_count_bonus(len(instance.get("scan_preview") or []))
    if len(instance.get("scan_preview") or []) <= 3:
        reasons.append("compact_candidate_set")

    score += parser_trust_bonus(venue.get("parser"), phase)
    if parser_trust_bonus(venue.get("parser"), phase) > 0:
        reasons.append(f"parser_trust:{venue.get('parser')}")

    if best:
        signals["best_kind"] = best.get("kind")
        signals["best_value"] = best.get("value")
        best_text = best.get("raw_text") or ""
        kw_score, kw_reasons = keyword_strength(best_text)
        score += kw_score
        reasons.extend(kw_reasons)
        score += proximity_bonus(best_text)
        if proximity_bonus(best_text) > 0:
            reasons.append("keyword_date_proximity")
        tz_bonus = detect_timezone_bonus(best_text)
        score += tz_bonus
        if tz_bonus > 0:
            reasons.append("timezone_present")

        parsed_dt = safe_date(best.get("value"))
        if parsed_dt:
            target_year = int(instance.get("year") or datetime.now(timezone.utc).year)
            if parsed_dt.year == target_year:
                score += 0.20
                reasons.append("year_match")
                signals["year_match"] = True
            elif parsed_dt.year in {target_year - 1, target_year + 1}:
                score += 0.05
                reasons.append("adjacent_year")
                signals["year_match"] = "adjacent"
            else:
                score -= 0.35
                hard_blockers.append("year_mismatch")
                signals["year_match"] = False

            ref_deadline, ref_year = nearest_historical_deadline(history, best.get("kind"))
            if ref_deadline:
                diff_days = date_diff_days(best.get("value"), ref_deadline.get("value"), align_reference_to_candidate_year=True)
                signals["reference_year"] = ref_year
                signals["date_diff_days_from_reference"] = diff_days
                if diff_days == 0:
                    score += 0.25
                    reasons.append("matches_existing_confirmed")
                elif phase >= 2 and diff_days is not None and diff_days <= 2:
                    score += 0.10
                    reasons.append("within_two_days_of_reference")
                elif diff_days is not None and diff_days >= 8:
                    score -= 0.35
                    hard_blockers.append("large_date_shift")
                elif diff_days is not None and 3 <= diff_days <= 7:
                    score -= 0.10
                    reasons.append("moderate_date_shift")

            if phase >= 3:
                prediction = predict_from_history(history, best.get("kind"))
                if prediction:
                    signals["prediction"] = prediction
                    predicted_diff = date_diff_days(best.get("value"), prediction["predicted_value"], align_reference_to_candidate_year=True)
                    signals["predicted_diff_days"] = predicted_diff
                    if predicted_diff is not None and predicted_diff <= 14:
                        score += 0.08
                        reasons.append("history_prediction_alignment")
    else:
        hard_blockers.append("no_best_candidate")

    score = clamp(score)

    decision = "review_required"
    if phase == 1 and not history:
        hard_blockers.append("no_confirmed_history")

    if hard_blockers:
        decision = "review_required" if any(x in hard_blockers for x in ["no_confirmed_history", "parse_failed", "too_many_dates", "year_mismatch", "large_date_shift", "unofficial_source", "no_best_candidate"]) else "rejected"
    elif score >= phase_threshold(phase):
        decision = "auto_confirmed"
    elif score >= 0.55:
        decision = "review_required"
    else:
        decision = "rejected"

    return {
        "score": round(score, 4),
        "decision": decision,
        "reasons": sorted(set(reasons)),
        "hard_blockers": sorted(set(hard_blockers)),
        "signals": signals,
        "best_deadline": best,
    }


def summarize_kinds(deadlines: Iterable[dict[str, Any]]) -> dict[str, int]:
    counter = Counter(d.get("kind") or "deadline" for d in deadlines)
    return dict(counter)
