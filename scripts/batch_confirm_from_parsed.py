from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
INSTANCES_PATH = ROOT / "data" / "instances.yml"
DEFAULT_PATCH_PATH = ROOT / "data" / "review_patch.json"
APPLY_PATCH_SCRIPT = ROOT / "scripts" / "apply_review_patch.py"


def load_yaml(path: Path):
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or []


def best_parsed_deadline(parsed_deadlines: list[dict]) -> dict | None:
    if not parsed_deadlines:
        return None
    return max(parsed_deadlines, key=lambda item: float(item.get("confidence", 0) or 0))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Create and optionally apply a review patch that batch-confirms instances from parsed deadlines."
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=0.35,
        help="Minimum parsed deadline confidence required for auto-confirm candidate selection.",
    )
    parser.add_argument(
        "--statuses",
        nargs="+",
        default=["review_required"],
        help="Instance statuses eligible for candidate selection (default: review_required).",
    )
    parser.add_argument(
        "--require-year-match",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Require parsed deadline year to match instance year (default: true).",
    )
    parser.add_argument(
        "--patch",
        default=str(DEFAULT_PATCH_PATH),
        help="Output patch JSON path.",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply generated patch to data/instances.yml.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show candidates without writing patch or applying changes.",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    patch_path = Path(args.patch).resolve()
    instances = load_yaml(INSTANCES_PATH)
    eligible_statuses = {s.strip() for s in args.statuses if s.strip()}
    generated_at = datetime.now(timezone.utc).isoformat()

    records: list[dict] = []
    for instance in instances:
        status = str(instance.get("status") or "")
        if status not in eligible_statuses:
            continue

        parsed = instance.get("parsed_deadlines") or []
        best = best_parsed_deadline(parsed)
        if not best:
            continue

        confidence = float(best.get("confidence", 0) or 0)
        if confidence < args.threshold:
            continue

        deadline_value = str(best.get("value") or "")
        year = int(instance.get("year") or 0)
        if args.require_year_match and (not deadline_value.startswith(str(year))):
            continue

        # Emit a review patch instead of mutating YAML directly so the batch can be inspected first.
        records.append(
            {
                "id": instance["id"],
                "venue_id": instance.get("venue_id"),
                "year": year,
                "status": "confirmed",
                "deadlines": [
                    {
                        "kind": best.get("kind") or "deadline",
                        "value": deadline_value,
                    }
                ],
                "source_url": instance.get("source_url"),
                "checked_at": instance.get("checked_at"),
                "confidence": max(float(instance.get("confidence") or 0), confidence),
                "scan_preview": instance.get("scan_preview") or [],
                "notes": (
                    f"{instance.get('notes') or ''} | "
                    f"Batch confirmed from parsed_deadlines "
                    f"(confidence>={args.threshold:.2f}, year-match={args.require_year_match}) at {generated_at}."
                ).strip(" |"),
            }
        )

    records.sort(key=lambda item: item["id"])
    print(
        f"[INFO] threshold={args.threshold:.2f} statuses={sorted(eligible_statuses)} "
        f"require_year_match={args.require_year_match} candidates={len(records)}"
    )
    for record in records:
        deadline = (record.get("deadlines") or [{}])[0]
        print(f"[CANDIDATE] {record['id']} -> {deadline.get('kind')} {deadline.get('value')}")

    if args.dry_run:
        print("[DONE] dry run only; no files written")
        return 0

    payload = {
        "exported_at": generated_at,
        "source": "batch_confirm_from_parsed",
        "records": records,
    }
    patch_path.parent.mkdir(parents=True, exist_ok=True)
    patch_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"[OK] wrote patch -> {patch_path}")

    if args.apply:
        # Reuse the same patch application path as the browser/admin review workflow.
        completed = subprocess.run(
            [sys.executable, str(APPLY_PATCH_SCRIPT), str(patch_path)],
            cwd=ROOT,
        )
        if completed.returncode != 0:
            print(f"[FAIL] apply_review_patch failed with code {completed.returncode}")
            return completed.returncode
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
