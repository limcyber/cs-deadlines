from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path

import yaml

from deadline_utils import best_deadline, infer_source_quality, safe_date

ROOT = Path(__file__).resolve().parents[1]
INSTANCES_PATH = ROOT / "data" / "instances.yml"


def load_yaml(path: Path):
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or []


def save_yaml(path: Path, data) -> None:
    with path.open("w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, sort_keys=False, allow_unicode=True)


def shift_year(value: str, years: int = -1) -> str | None:
    dt = safe_date(value)
    if not dt:
        return None
    target_year = dt.year + years
    try:
        shifted = dt.replace(year=target_year)
    except ValueError:
        shifted = dt.replace(year=target_year, day=min(dt.day, 28))
    return shifted.date().isoformat()


def has_confirmed_history(instances: list[dict], venue_id: str) -> bool:
    for inst in instances:
        if inst.get("venue_id") == venue_id and inst.get("status") in {"confirmed", "auto_confirmed"} and (inst.get("deadlines") or []):
            return True
    return False


def seedable(instance: dict) -> tuple[bool, str]:
    # Keep bootstrap seeds intentionally strict because they influence conservative auto-review.
    parsed = instance.get("parsed_deadlines") or []
    if not parsed:
        return False, "no_parsed_deadlines"
    if len(parsed) > 2:
        return False, "too_many_parsed_deadlines"
    quality = infer_source_quality(instance.get("source_url"))
    if quality not in {"official", "official_cfp"}:
        return False, f"source_{quality}"
    best = best_deadline(parsed)
    if not best:
        return False, "no_best_deadline"
    if float(best.get("confidence") or 0) < 0.45:
        return False, "confidence_too_low"
    shifted = shift_year(best.get("value"), -1)
    if not shifted:
        return False, "unshiftable_date"
    return True, "ok"


def bootstrap_seed(instance: dict) -> dict | None:
    best = best_deadline(instance.get("parsed_deadlines") or [])
    if not best:
        return None
    shifted = shift_year(best.get("value"), -1)
    if not shifted:
        return None
    seed_year = int(instance.get("year") or datetime.now(timezone.utc).year) - 1
    return {
        "id": f"{instance['venue_id']}-{seed_year}",
        "venue_id": instance["venue_id"],
        "year": seed_year,
        "status": "confirmed",
        "deadlines": [{"kind": best.get("kind") or "deadline", "value": shifted}],
        "venue_date_start": None,
        "venue_date_end": None,
        "location": None,
        "source_url": instance.get("source_url"),
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "confidence": 0.99,
        "scan_preview": [best.get("raw_text") or "Seeded from current structured deadline candidate."],
        "notes": "Bootstrap confirmed history seed generated locally to enable conservative Phase 1 auto-review. Replace with true historical confirmed data when available.",
        "seed_meta": {
            # Metadata makes it easy to distinguish generated history from real confirmed archives.
            "seed_type": "bootstrap_confirmed_history",
            "generated_from_instance": instance.get("id"),
            "generated_from_deadline": best.get("value"),
            "generated_at": datetime.now(timezone.utc).isoformat(),
        },
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Create bootstrap confirmed history seeds from current structured deadline candidates.")
    parser.add_argument("--limit", type=int, default=8, help="Maximum number of new history seeds to create.")
    parser.add_argument("--dry-run", action="store_true", help="Preview seeds without writing instances.yml.")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    instances = load_yaml(INSTANCES_PATH)
    created = []
    skipped = []
    existing_ids = {inst.get("id") for inst in instances}

    # Process highest-confidence candidates first so a small seed limit yields the safest history set.
    for inst in sorted(instances, key=lambda x: (-float(x.get("confidence") or 0), x.get("id") or "")):
        if len(created) >= args.limit:
            break
        if inst.get("status") not in {"scanned", "review_required", "rejected", "auto_confirmed"}:
            continue
        venue_id = inst.get("venue_id")
        if not venue_id or has_confirmed_history(instances + created, venue_id):
            continue
        ok, reason = seedable(inst)
        if not ok:
            skipped.append((inst.get("id"), reason))
            continue
        seed = bootstrap_seed(inst)
        if not seed or seed["id"] in existing_ids:
            skipped.append((inst.get("id"), "seed_id_exists_or_invalid"))
            continue
        created.append(seed)
        existing_ids.add(seed["id"])

    print(f"[INFO] seed candidates created={len(created)} skipped={len(skipped)}")
    for seed in created:
        dl = (seed.get("deadlines") or [{}])[0].get("value")
        print(f"[SEED] {seed['id']} -> {dl}")

    if args.dry_run:
        print("[DONE] dry run only; no file changes written")
        return 0

    if created:
        instances.extend(created)
        save_yaml(INSTANCES_PATH, instances)
        print("[DONE] bootstrap history seeds saved to instances.yml")
    else:
        print("[DONE] no new seeds created")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
