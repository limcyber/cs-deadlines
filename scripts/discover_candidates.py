from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable
from urllib.parse import urljoin, urlparse

import requests
import yaml
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
VENUES_PATH = ROOT / "data" / "venues.yml"
CANDIDATES_PATH = ROOT / "data" / "candidate_venues.json"

HEADERS = {
    "User-Agent": "cs-deadlines-discovery/0.1",
}

YEAR_PATTERN = re.compile(r"\b(20\d{2})\b")
NAME_YEAR_PATTERN = re.compile(r"\b([A-Za-z][A-Za-z0-9+\- ]{2,40}?)\s*(20\d{2})\b")
DATE_HINT_PATTERN = re.compile(
    r"(?:\b(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\b|\b\d{4}-\d{2}-\d{2}\b|\bsubmission due\b|\bdeadline\b)",
    re.IGNORECASE,
)
ACRONYM_HINT_PATTERN = re.compile(r"\b[A-Z][A-Z0-9&/-]{2,}\b")
NOISE_TOKENS = {
    "home",
    "about",
    "login",
    "sign in",
    "register",
    "privacy",
    "terms",
    "cookies",
    "sitemap",
}


@dataclass(frozen=True)
class DiscoverySource:
    # Each source bundles where to crawl, how to parse it, and a prior confidence baseline.
    name: str
    url: str
    parser: str
    base_confidence: float


DISCOVERY_SOURCES: list[DiscoverySource] = [
    DiscoverySource(
        name="ieee-tcsp",
        url="https://www.ieee-security.org/CFP/Cipher-Call-for-Papers.html",
        parser="tcsp_cfp",
        base_confidence=0.58,
    ),
    DiscoverySource(
        name="ieee-sps-conferences",
        url="https://signalprocessingsociety.org/event-categories/conferences-workshops",
        parser="ieee_sps",
        base_confidence=0.57,
    ),
    DiscoverySource(
        name="ieee-procomm",
        url="https://procomm.ieee.org/conference/2026-2/",
        parser="generic_links",
        base_confidence=0.57,
    ),
    DiscoverySource(
        name="usenix-cfp",
        url="https://www.usenix.org/conferences/calls-for-papers",
        parser="usenix_cfp",
        base_confidence=0.64,
    ),
    DiscoverySource(
        name="iacr-events",
        url="https://iacr.org/events/",
        parser="iacr_events",
        base_confidence=0.63,
    ),
    DiscoverySource(
        name="wikicfp-cs",
        url="https://www.wikicfp.com/cfp/call?conference=computer%20science",
        parser="wikicfp",
        base_confidence=0.62,
    ),
    DiscoverySource(
        name="wikicfp-ai",
        url="https://www.wikicfp.com/cfp/call?conference=artificial%20intelligence",
        parser="wikicfp",
        base_confidence=0.60,
    ),
    DiscoverySource(
        name="wikicfp-security",
        url="https://www.wikicfp.com/cfp/call?conference=security",
        parser="wikicfp",
        base_confidence=0.60,
    ),
    DiscoverySource(
        name="aideadlines",
        url="https://aideadlin.es/",
        parser="aideadlines",
        base_confidence=0.50,
    ),
    DiscoverySource(
        name="sec-deadlines",
        url="https://sec-deadlines.github.io/",
        parser="sec_deadlines",
        base_confidence=0.50,
    ),
]

WORKSHOP_TOKENS = (
    "workshop",
    "co-located",
    "colocated",
    "in conjunction with",
    "satellite event",
)

NON_CONFERENCE_TOKENS = (
    "special issue",
    "journal",
    "newsletter",
    "summer school",
    "school",
    "doctoral consortium",
    "tutorial",
    "competition",
    "challenge",
    "hackathon",
    "webinar",
    "track at",
    "track ",
    "days",
)


def load_yaml(path: Path):
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or []


def load_json(path: Path):
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8") as f:
        try:
            return json.load(f) or []
        except json.JSONDecodeError:
            return []


def write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")


def fetch_html(url: str, timeout: int = 20, session: requests.Session | None = None) -> str:
    client = session or requests
    resp = client.get(url, headers=HEADERS, timeout=timeout)
    resp.raise_for_status()
    return resp.text


def normalize_space(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip())


def to_abs_url(base_url: str, href: str | None) -> str:
    if not href:
        return ""
    return urljoin(base_url, href.strip())


def short_name_from_title(title: str) -> str:
    title = normalize_space(title)
    if not title:
        return ""
    token = title.split("(", 1)[0].strip()
    words = token.split()
    if len(words) <= 3:
        return token
    upper_tokens = [w for w in words if w.isupper() and 2 <= len(w) <= 10]
    if upper_tokens:
        return upper_tokens[0]
    return " ".join(words[:4])


def normalize_title_key(title: str) -> str:
    value = normalize_space(title).lower()
    value = re.sub(r"\b20\d{2}\b", " ", value)
    value = re.sub(r"'\d{2}\b", " ", value)
    value = re.sub(r"\([^)]*\)", " ", value)
    value = re.sub(r"[^a-z0-9+&/ -]", " ", value)
    return normalize_space(value)


def looks_like_workshop_text(text: str) -> bool:
    lower = normalize_space(text).lower()
    return any(token in lower for token in WORKSHOP_TOKENS)


def looks_like_non_conference_text(text: str) -> bool:
    lower = normalize_space(text).lower()
    return any(token in lower for token in NON_CONFERENCE_TOKENS)


def looks_like_cfp_entry(title: str, url: str, target_year: int) -> bool:
    # Discovery aims for broad recall while still filtering obvious navigation and marketing links.
    t = normalize_space(title).lower()
    if not t or len(t) < 4:
        return False
    if t.startswith("http://") or t.startswith("https://"):
        return False
    if t in NOISE_TOKENS:
        return False
    if any(noise in t for noise in ["privacy", "cookie", "sponsor", "newsletter"]):
        return False
    if looks_like_non_conference_text(t):
        return False

    u = (url or "").lower()
    cfp_signal = any(k in u for k in ["cfp", "call-for-papers", "call_for_papers", "deadline"])
    text_signal = any(k in t for k in ["call for papers", "deadline", "submission"])
    year_signal = str(target_year) in t or str(target_year + 1) in t or bool(YEAR_PATTERN.search(t))
    conference_signal = any(k in t for k in ["conference", "symposium", "workshop", "summit"]) or bool(NAME_YEAR_PATTERN.search(title))

    return (conference_signal and year_signal) or (cfp_signal and year_signal) or (text_signal and year_signal)


def normalize_event_title(title: str) -> str:
    value = normalize_space(title)
    value = re.sub(r"^https?://\S+\s+\(([^)]+)\)$", r"\1", value, flags=re.IGNORECASE)
    value = re.sub(r"\s*[-|]\s*call for papers.*$", "", value, flags=re.IGNORECASE)
    value = re.sub(r"\s*\|\s*.*$", "", value)
    value = value.strip(" -|")
    return value


def infer_year(title: str, target_year: int) -> int:
    match = YEAR_PATTERN.search(title)
    if not match:
        return target_year
    year = int(match.group(1))
    if target_year - 1 <= year <= target_year + 2:
        return year
    return target_year


def extract_item_year(text: str) -> int | None:
    match = YEAR_PATTERN.search(text or "")
    return int(match.group(1)) if match else None


def year_alignment_score(candidate_year: int, target_year: int) -> float:
    if candidate_year == target_year:
        return 0.12
    if candidate_year == target_year + 1:
        return 0.04
    if candidate_year == target_year - 1:
        return -0.03
    return -0.10


def url_evidence_score(url: str) -> float:
    lower = (url or "").lower()
    if any(token in lower for token in ["call-for-papers", "call_for_papers", "/cfp", "cfp.html"]):
        return 0.12
    if "deadline" in lower:
        return 0.08
    if any(token in lower for token in ["/conference/", "/conferences/", "/events/"]):
        return 0.04
    return 0.0


def title_evidence_score(title: str) -> float:
    score = 0.0
    normalized = normalize_space(title)
    lower = normalized.lower()
    if any(token in lower for token in ["conference", "symposium", "summit", "forum"]):
        score += 0.04
    if "call for papers" in lower:
        score += 0.08
    if "deadline" in lower or "submission" in lower:
        score += 0.06
    if ACRONYM_HINT_PATTERN.search(normalized):
        score += 0.03
    return score


def text_evidence_score(text: str) -> float:
    lower = (text or "").lower()
    score = 0.0
    if "call for papers" in lower:
        score += 0.06
    if "submission due" in lower or "submissions due" in lower or "paper submission" in lower:
        score += 0.05
    if DATE_HINT_PATTERN.search(text or ""):
        score += 0.05
    if any(token in lower for token in ["location:", "venue:", "date:"]):
        score += 0.03
    return score


def score_candidate(
    title: str,
    url: str,
    base: float,
    is_known_domain: bool,
    target_year: int,
    candidate_year: int,
    extra_text: str = "",
) -> float:
    # This score only prioritizes manual review; it is not used for automatic venue creation.
    score = base
    t = (title or "").lower()
    extra = normalize_space(extra_text).lower()

    score += year_alignment_score(candidate_year, target_year)
    score += url_evidence_score(url)
    score += title_evidence_score(title)
    score += text_evidence_score(extra_text)
    if looks_like_workshop_text(extra):
        score -= 0.22
    if looks_like_non_conference_text(extra):
        score -= 0.20
    if looks_like_non_conference_text(t):
        score -= 0.15
    if is_known_domain:
        score -= 0.15

    return max(0.0, min(0.99, round(score, 4)))


def confidence_band(confidence: float) -> str:
    value = float(confidence or 0.0)
    if value <= 0.55:
        return "low"
    if value <= 0.70:
        return "medium"
    if value <= 0.84:
        return "high"
    return "very_high"


def extract_from_wikicfp(html: str, source: DiscoverySource, target_year: int) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    out: list[dict] = []
    seen: set[str] = set()

    for a in soup.find_all("a", href=True):
        href = to_abs_url(source.url, a.get("href"))
        if "event.showcfp" not in href:
            continue
        title = normalize_event_title(a.get_text(" ", strip=True))
        if not looks_like_cfp_entry(title, href, target_year):
            continue
        if href in seen:
            continue
        seen.add(href)
        out.append(
            {
                "title": title,
                "short_name": short_name_from_title(title),
                "website": href,
                "cfp_url": href,
                "year": infer_year(title, target_year),
                "source_name": source.name,
                "source_url": source.url,
                "parser": source.parser,
            }
        )

    return out


def extract_from_generic_links(html: str, source: DiscoverySource, target_year: int) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    out: list[dict] = []
    seen: set[str] = set()

    for a in soup.find_all("a", href=True):
        href = to_abs_url(source.url, a.get("href"))
        if not href.startswith("http"):
            continue
        title = normalize_event_title(a.get_text(" ", strip=True))
        if not looks_like_cfp_entry(title, href, target_year):
            continue
        if href in seen:
            continue
        seen.add(href)
        out.append(
            {
                "title": title,
                "short_name": short_name_from_title(title),
                "website": href,
                "cfp_url": href,
                "year": infer_year(title, target_year),
                "source_name": source.name,
                "source_url": source.url,
                "parser": source.parser,
            }
        )

    return out


def extract_from_aideadlines(html: str, source: DiscoverySource, target_year: int) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    out: list[dict] = []
    seen: set[str] = set()

    for card in soup.select(".ConfItem"):
        title_node = card.select_one(".conf-title a")
        if not title_node:
            continue
        title = normalize_event_title(title_node.get_text(" ", strip=True))
        year = extract_item_year(title)
        if year is None:
            continue
        if year < target_year - 1 or year > target_year + 1:
            continue

        website_node = card.select_one(".conf-title-icon a[href]")
        note_links = [to_abs_url(source.url, a.get("href")) for a in card.select(".note a[href]")]
        cfp_url = next((url for url in note_links if url.startswith("http")), "") or (
            to_abs_url(source.url, website_node.get("href")) if website_node else ""
        )
        website = to_abs_url(source.url, website_node.get("href")) if website_node else cfp_url
        if not cfp_url:
            continue

        key = f"{title}|{cfp_url}"
        if key in seen:
            continue
        seen.add(key)
        out.append(
            {
                "title": title,
                "short_name": short_name_from_title(title),
                "website": website,
                "cfp_url": cfp_url,
                "year": year,
                "source_name": source.name,
                "source_url": source.url,
                "parser": source.parser,
                "extra_text": normalize_space(card.get_text(" ", strip=True)),
            }
        )

    return out


def extract_from_sec_deadlines(html: str, source: DiscoverySource, target_year: int) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    out: list[dict] = []
    seen: set[str] = set()

    for card in soup.select(".conf"):
        title_node = card.select_one("h2 a[href]")
        if not title_node:
            continue
        title = normalize_event_title(title_node.get_text(" ", strip=True))
        year = extract_item_year(title)
        if year is None:
            continue
        if year < target_year - 1 or year > target_year + 1:
            continue

        classes = {normalize_space(cls).upper() for cls in (card.get("class") or [])}
        meta_text = normalize_space(card.select_one(".meta").get_text(" ", strip=True) if card.select_one(".meta") else "")
        deadline_meta = normalize_space(card.select_one(".deadline .meta").get_text(" ", strip=True) if card.select_one(".deadline .meta") else "")
        extra_text = normalize_space(f"{meta_text} {deadline_meta}")

        # sec-deadlines labels workshops with SHOP; keep main conferences by default.
        if "SHOP" in classes or looks_like_workshop_text(extra_text):
            continue

        href = to_abs_url(source.url, title_node.get("href"))
        key = f"{title}|{href}"
        if key in seen:
            continue
        seen.add(key)
        out.append(
            {
                "title": title,
                "short_name": short_name_from_title(title),
                "website": href,
                "cfp_url": href,
                "year": year,
                "source_name": source.name,
                "source_url": source.url,
                "parser": source.parser,
                "extra_text": extra_text,
            }
        )

    return out


def extract_from_tcsp_cfp(html: str, source: DiscoverySource, target_year: int) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    out: list[dict] = []
    seen: set[str] = set()

    for paragraph in soup.find_all("p"):
        text = normalize_space(paragraph.get_text(" ", strip=True))
        if not text or not YEAR_PATTERN.search(text):
            continue
        title_anchor = next(
            (
                a
                for a in paragraph.select("a[href]")
                if extract_item_year(a.get_text(" ", strip=True))
            ),
            None,
        )
        if not title_anchor:
            continue

        title = normalize_event_title(title_anchor.get_text(" ", strip=True))
        year = extract_item_year(title)
        if year is None or year < target_year - 1 or year > target_year + 1:
            continue
        if looks_like_workshop_text(text) or looks_like_non_conference_text(text):
            continue

        href = to_abs_url(source.url, title_anchor.get("href"))
        key = f"{title}|{href}"
        if key in seen:
            continue
        seen.add(key)
        out.append(
            {
                "title": title,
                "short_name": short_name_from_title(title),
                "website": href,
                "cfp_url": href,
                "year": year,
                "source_name": source.name,
                "source_url": source.url,
                "parser": source.parser,
                "extra_text": text,
            }
        )

    return out


def extract_from_ieee_sps(html: str, source: DiscoverySource, target_year: int) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    out: list[dict] = []
    seen: set[str] = set()

    for article in soup.select("article"):
        title_node = article.select_one(".node__title a")
        if not title_node:
            continue
        title = normalize_event_title(title_node.get_text(" ", strip=True))
        year = extract_item_year(title)
        if year is None or year < target_year - 1 or year > target_year + 1:
            continue

        body_text = normalize_space(article.get_text(" ", strip=True))
        external_links = []
        for anchor in article.select("a[href]"):
            href = to_abs_url(source.url, anchor.get("href"))
            host = normalize_domain(href)
            if not href.startswith("http"):
                continue
            if host in {"signalprocessingsociety.org", "www.signalprocessingsociety.org"}:
                continue
            external_links.append(href)

        website = external_links[0] if external_links else to_abs_url(source.url, title_node.get("href"))
        key = f"{title}|{website}"
        if key in seen:
            continue
        seen.add(key)
        out.append(
            {
                "title": title,
                "short_name": short_name_from_title(title),
                "website": website,
                "cfp_url": website,
                "year": year,
                "source_name": source.name,
                "source_url": source.url,
                "parser": source.parser,
                "extra_text": body_text,
            }
        )

    return out


def extract_from_usenix_cfp(html: str, source: DiscoverySource, target_year: int) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    out: list[dict] = []
    seen: set[str] = set()

    for row in soup.select(".view-content .views-row"):
        row_text = normalize_space(row.get_text(" ", strip=True))
        if not row_text:
            continue
        title_link = row.select_one("strong a[href]")
        cfp_link = next(
            (
                a
                for a in row.select("a[href]")
                if "call-for-papers" in (a.get("href") or "").lower()
            ),
            None,
        )
        if not title_link or not cfp_link:
            continue

        title = normalize_event_title(row.select_one("strong").get_text(" ", strip=True))
        if looks_like_non_conference_text(title) or looks_like_workshop_text(title):
            continue

        year_text = normalize_space(row.select_one(".date-display-start").get_text(" ", strip=True) if row.select_one(".date-display-start") else "")
        year = extract_item_year(year_text) or extract_item_year(row_text)
        if year is None or year < target_year - 1 or year > target_year + 1:
            continue

        href = to_abs_url(source.url, cfp_link.get("href"))
        key = f"{title}|{href}"
        if key in seen:
            continue
        seen.add(key)
        out.append(
            {
                "title": title,
                "short_name": short_name_from_title(title),
                "website": href,
                "cfp_url": href,
                "year": year,
                "source_name": source.name,
                "source_url": source.url,
                "parser": source.parser,
                "extra_text": row_text,
            }
        )

    return out


def extract_from_iacr_events(html: str, source: DiscoverySource, target_year: int) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    out: list[dict] = []
    seen: set[str] = set()

    for anchor in soup.select("main a[href], body a[href]"):
        title = normalize_event_title(anchor.get_text(" ", strip=True))
        if not title:
            continue
        year = extract_item_year(title)
        if year is None or year < target_year - 1 or year > target_year + 1:
            continue
        if looks_like_workshop_text(title) or looks_like_non_conference_text(title):
            continue

        href = to_abs_url(source.url, anchor.get("href"))
        lower_href = href.lower()
        if any(token in lower_href for token in ["/schools/", "/transactions/", "/publications/"]):
            continue

        key = f"{title}|{href}"
        if key in seen:
            continue
        seen.add(key)
        out.append(
            {
                "title": title,
                "short_name": short_name_from_title(title),
                "website": href,
                "cfp_url": href,
                "year": year,
                "source_name": source.name,
                "source_url": source.url,
                "parser": source.parser,
                "extra_text": title,
            }
        )

    return out


def parse_source(html: str, source: DiscoverySource, target_year: int) -> list[dict]:
    if source.parser == "wikicfp":
        return extract_from_wikicfp(html, source, target_year)
    if source.parser == "aideadlines":
        return extract_from_aideadlines(html, source, target_year)
    if source.parser == "sec_deadlines":
        return extract_from_sec_deadlines(html, source, target_year)
    if source.parser == "tcsp_cfp":
        return extract_from_tcsp_cfp(html, source, target_year)
    if source.parser == "ieee_sps":
        return extract_from_ieee_sps(html, source, target_year)
    if source.parser == "usenix_cfp":
        return extract_from_usenix_cfp(html, source, target_year)
    if source.parser == "iacr_events":
        return extract_from_iacr_events(html, source, target_year)
    return extract_from_generic_links(html, source, target_year)


def normalize_domain(url: str) -> str:
    host = urlparse(url or "").netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    return host


def canonicalize_url(url: str) -> str:
    parsed = urlparse(url or "")
    if not parsed.scheme or not parsed.netloc:
        return ""
    host = normalize_domain(url)
    path = parsed.path.rstrip("/") or "/"
    return f"{parsed.scheme.lower()}://{host}{path}"


def existing_venue_indexes(venues: list[dict]) -> tuple[set[str], set[str], set[str]]:
    # Build lightweight duplicate guards so discovery does not keep re-suggesting tracked venues.
    ids: set[str] = set()
    names: set[str] = set()
    domains: set[str] = set()
    for venue in venues:
        vid = (venue.get("id") or "").strip().lower()
        if vid:
            ids.add(vid)
        for name_key in ["short_name", "title"]:
            name = normalize_space(str(venue.get(name_key) or "")).lower()
            if name:
                names.add(name)
                names.add(normalize_title_key(name))
        for alias in venue.get("aliases", []) or []:
            alias_value = normalize_space(str(alias or "")).lower()
            if alias_value:
                names.add(alias_value)
                names.add(normalize_title_key(alias_value))
        for url_key in ["website", "cfp_url"]:
            d = normalize_domain(str(venue.get(url_key) or ""))
            if d:
                domains.add(d)
    return ids, names, domains


def candidate_key(item: dict) -> str:
    canonical_url = canonicalize_url(item.get("cfp_url") or item.get("website") or "")
    if canonical_url:
        return f"{canonical_url}|{int(item.get('year') or 0)}"
    domain = normalize_domain(item.get("cfp_url") or item.get("website") or "")
    title = normalize_space(item.get("title") or "").lower()
    year = int(item.get("year") or 0)
    return f"{domain}|{title}|{year}"


def merge_candidates(existing: list[dict], discovered: list[dict], now_iso: str) -> list[dict]:
    # Candidate history is append-friendly: repeat sightings raise confidence without losing context.
    merged: dict[str, dict] = {}
    for item in existing:
        key = candidate_key(item)
        if not key:
            continue
        copy = dict(item)
        copy.setdefault("seen_count", 1)
        copy.setdefault("first_seen_at", item.get("discovered_at") or now_iso)
        copy.setdefault("last_seen_at", item.get("discovered_at") or now_iso)
        merged[key] = copy

    for item in discovered:
        key = candidate_key(item)
        if not key:
            continue
        prev = merged.get(key)
        if prev:
            prev["confidence"] = max(float(prev.get("confidence", 0) or 0), float(item.get("confidence", 0) or 0))
            prev["confidence_band"] = confidence_band(prev["confidence"])
            prev["last_seen_at"] = now_iso
            prev["seen_count"] = int(prev.get("seen_count", 1)) + 1
            prev["source_name"] = item.get("source_name") or prev.get("source_name")
            prev["source_url"] = item.get("source_url") or prev.get("source_url")
            prev["notes"] = item.get("notes") or prev.get("notes")
            continue

        copy = dict(item)
        copy["confidence_band"] = confidence_band(copy.get("confidence", 0))
        copy["first_seen_at"] = now_iso
        copy["last_seen_at"] = now_iso
        copy["seen_count"] = 1
        merged[key] = copy

    result = list(merged.values())
    for item in result:
        item["confidence_band"] = confidence_band(item.get("confidence", 0))
    result.sort(key=lambda x: (-float(x.get("confidence", 0) or 0), x.get("year", 0), (x.get("title") or "").lower()))
    return result


def filter_and_score(candidates: Iterable[dict], known_names: set[str], known_domains: set[str], source: DiscoverySource, target_year: int, min_confidence: float) -> list[dict]:
    out: list[dict] = []
    for raw in candidates:
        title = normalize_event_title(raw.get("title") or "")
        if not title:
            continue

        domain = normalize_domain(raw.get("cfp_url") or raw.get("website") or "")
        short_name = normalize_space(raw.get("short_name") or short_name_from_title(title))
        if not short_name:
            continue

        title_key = normalize_title_key(title)
        short_key = normalize_title_key(short_name)
        lower_names = {title.lower(), short_name.lower(), title_key, short_key}
        if lower_names & known_names:
            continue

        year = int(raw.get("year") or target_year)
        if year < target_year - 1 or year > target_year + 2:
            continue

        extra_text = normalize_space(raw.get("extra_text") or "")
        conf = score_candidate(
            title,
            raw.get("cfp_url") or raw.get("website") or "",
            source.base_confidence,
            domain in known_domains,
            target_year,
            year,
            extra_text=extra_text,
        )
        if conf < min_confidence:
            continue

        out.append(
            {
                "title": title,
                "short_name": short_name,
                "year": year,
                "website": raw.get("website") or raw.get("cfp_url"),
                "cfp_url": raw.get("cfp_url") or raw.get("website"),
                "source_name": raw.get("source_name") or source.name,
                "source_url": raw.get("source_url") or source.url,
                "source_type": "aggregator",
                "confidence": conf,
                "confidence_band": confidence_band(conf),
                "notes": "Discovered from CS conference feed; needs human verification before adding to venues.yml.",
            }
        )

    dedup: dict[str, dict] = {}
    for item in out:
        key = candidate_key(item)
        prev = dedup.get(key)
        if prev is None or float(item.get("confidence", 0) or 0) > float(prev.get("confidence", 0) or 0):
            dedup[key] = item
    return list(dedup.values())


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Discover candidate CS conference venues from external conference news/CFP feeds.")
    parser.add_argument("--output", default=str(CANDIDATES_PATH), help="Output JSON path (default: data/candidate_venues.json).")
    parser.add_argument("--min-confidence", type=float, default=0.55, help="Minimum confidence required to keep a candidate.")
    parser.add_argument("--limit", type=int, default=250, help="Maximum number of candidates to retain in output.")
    parser.add_argument("--year", type=int, default=datetime.now(timezone.utc).year, help="Target conference year for discovery scoring.")
    parser.add_argument("--timeout", type=int, default=20, help="Per-source HTTP timeout in seconds.")
    parser.add_argument("--reset", action="store_true", help="Ignore existing candidate file and rewrite from current crawl only.")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    output_path = Path(args.output).resolve()
    target_year = int(args.year)
    now_iso = datetime.now(timezone.utc).isoformat()

    venues = load_yaml(VENUES_PATH)
    _, known_names, known_domains = existing_venue_indexes(venues)

    discovered_raw: list[dict] = []
    session = requests.Session()
    # Crawl every source independently so one broken feed does not block the rest.
    for source in DISCOVERY_SOURCES:
        try:
            html = fetch_html(source.url, timeout=args.timeout, session=session)
            extracted = parse_source(html, source, target_year)
            filtered = filter_and_score(extracted, known_names, known_domains, source, target_year, args.min_confidence)
            discovered_raw.extend(filtered)
            print(f"[OK] {source.name}: extracted={len(extracted)}, kept={len(filtered)}")
        except Exception as exc:
            print(f"[WARN] {source.name}: {exc}")

    if args.reset:
        existing = []
    else:
        existing = load_json(output_path)

    merged = merge_candidates(existing, discovered_raw, now_iso)
    if args.limit > 0:
        merged = merged[: args.limit]

    for idx, item in enumerate(merged, 1):
        item.setdefault("id", f"cand-{target_year}-{idx:04d}")
        item["discovered_at"] = item.get("last_seen_at", now_iso)

    write_json(output_path, merged)

    print(f"[DONE] wrote {len(merged)} candidates -> {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
