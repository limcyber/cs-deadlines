from __future__ import annotations

import json
from pathlib import Path
import sys
import yaml

ROOT = Path(__file__).resolve().parents[1]
INSTANCES_PATH = ROOT / "data" / "instances.yml"
DEFAULT_PATCH_PATH = ROOT / "data" / "review_patch.json"


def load_yaml(path: Path):
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or []


def dump_yaml(path: Path, data):
    with path.open("w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, sort_keys=False, allow_unicode=True)


def load_patch(path: Path):
    with path.open("r", encoding="utf-8") as f:
        payload = json.load(f)
    # Accept both the exported envelope format and a raw list for quick local edits.
    records = payload.get("records", payload if isinstance(payload, list) else [])
    if not isinstance(records, list):
        raise ValueError("Patch file must contain a top-level 'records' list or be a list itself.")
    return records


def apply_patch(instances, patch_records):
    by_id = {item["id"]: item for item in instances if item.get("id")}
    changed = 0

    for patch in patch_records:
        record_id = patch.get("id")
        if not record_id:
            continue

        target = by_id.get(record_id)
        if target is None:
            # Allow review patches to create a missing instance when the reviewer is ahead of the dataset.
            target = {
                "id": record_id,
                "venue_id": patch.get("venue_id"),
                "year": patch.get("year"),
            }
            instances.append(target)
            by_id[record_id] = target

        for key in [
            "venue_id",
            "year",
            "status",
            "deadlines",
            "venue_date_start",
            "venue_date_end",
            "location",
            "source_url",
            "checked_at",
            "confidence",
            "scan_preview",
            "notes",
        ]:
            # Only whitelisted fields are patchable from the review workflow.
            if key in patch:
                target[key] = patch[key]
        changed += 1

    instances.sort(key=lambda item: (str(item.get("venue_id", "")), int(item.get("year", 0))))
    return changed


def main() -> int:
    patch_path = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else DEFAULT_PATCH_PATH
    if not patch_path.exists():
        print(f"[FAIL] Patch file not found: {patch_path}")
        return 1

    instances = load_yaml(INSTANCES_PATH)
    patch_records = load_patch(patch_path)
    changed = apply_patch(instances, patch_records)
    dump_yaml(INSTANCES_PATH, instances)

    print(f"[OK] Applied {changed} review patch record(s) from {patch_path}")
    print(f"[OK] Updated {INSTANCES_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
