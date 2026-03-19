from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path

import yaml

from deadline_utils import phase_threshold, score_best_candidate

ROOT = Path(__file__).resolve().parents[1]
VENUES_PATH = ROOT / "data" / "venues.yml"
INSTANCES_PATH = ROOT / "data" / "instances.yml"


def load_yaml(path: Path):
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or []


def save_yaml(path: Path, data) -> None:
    with path.open("w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, sort_keys=False, allow_unicode=True)


def choose_public_deadlines(instance: dict, review: dict) -> list[dict]:
    best = review.get("best_deadline")
    if not best:
        return []
    # Publish only the strongest matching kind so auto-confirm stays conservative.
    parsed = instance.get("parsed_deadlines") or []
    same_kind = [d for d in parsed if d.get("kind") == best.get("kind")]
    return same_kind[:1] if same_kind else [
        {
            "kind": best.get("kind") or "deadline",
            "value": best.get("value"),
        }
    ]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run score-based auto review for scanned deadline candidates.")
    parser.add_argument("--phase", type=int, choices=[1, 2, 3], default=3, help="Auto-review phase to apply.")
    parser.add_argument("--dry-run", action="store_true", help="Compute decisions without writing instances.yml.")
    parser.add_argument(
        "--include-auto-confirmed",
        action="store_true",
        help="Re-evaluate already auto_confirmed records. Disabled by default to avoid accidental regressions.",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    phase = args.phase
    venues = load_yaml(VENUES_PATH)
    venue_map = {v["id"]: v for v in venues}
    instances = load_yaml(INSTANCES_PATH)

    counts = {"auto_confirmed": 0, "review_required": 0, "rejected": 0, "skipped": 0}
    now = datetime.now(timezone.utc).isoformat()
    # By default we re-score only non-final states to avoid degrading already published data.
    eligible_statuses = {"scanned", "review_required", "rejected", "scan_failed"}
    if args.include_auto_confirmed:
        eligible_statuses.add("auto_confirmed")

    for instance in instances:
        status = instance.get("status")
        if status not in eligible_statuses:
            counts["skipped"] += 1
            continue

        venue = venue_map.get(instance.get("venue_id"))
        if not venue:
            counts["skipped"] += 1
            continue

        # Historical confirmed records provide the strongest guardrail for current-year scoring.
        history = [
            inst for inst in instances
            if inst.get("venue_id") == instance.get("venue_id")
            and inst.get("id") != instance.get("id")
            and inst.get("status") in {"confirmed", "auto_confirmed"}
            and (inst.get("deadlines") or [])
        ]
        history.sort(key=lambda x: x.get("year", 0), reverse=True)

        review = score_best_candidate(instance, venue, history, phase)
        final_status = review["decision"]
        if final_status == "auto_confirmed":
            instance["deadlines"] = choose_public_deadlines(instance, review)
        elif status not in {"confirmed", "auto_confirmed"}:
            # Preserve confirmed/auto-confirmed public deadlines unless a human changes them.
            instance["deadlines"] = []

        instance["status"] = final_status
        instance["confidence"] = max(float(instance.get("confidence") or 0), float(review["score"]))
        instance["auto_review"] = {
            "phase": phase,
            "threshold": phase_threshold(phase),
            "score": review["score"],
            "decision": final_status,
            "reasons": review["reasons"],
            "hard_blockers": review["hard_blockers"],
            "signals": review["signals"],
            "reviewed_at": now,
            "reviewer": "auto",
        }
        counts[final_status] += 1

    print(f"[INFO] phase={phase} threshold={phase_threshold(phase):.2f}")
    print(f"[INFO] auto_confirmed={counts['auto_confirmed']} review_required={counts['review_required']} rejected={counts['rejected']} skipped={counts['skipped']}")

    if not args.dry_run:
        save_yaml(INSTANCES_PATH, instances)
        print("[DONE] auto-review results saved to instances.yml")
    else:
        print("[DONE] dry run only; no file changes written")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
