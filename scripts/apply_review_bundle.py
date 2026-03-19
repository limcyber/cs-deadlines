from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PATCH_PATH = ROOT / "data" / "review_patch.json"


def run_step(name: str, cmd: list[str]) -> int:
    # Keep the wrapper transparent so failures still point to the underlying script command.
    print(f"\n[STEP] {name}")
    print(f"[CMD ] {' '.join(cmd)}")
    completed = subprocess.run(cmd, cwd=ROOT)
    if completed.returncode != 0:
        print(f"[FAIL] {name} failed with exit code {completed.returncode}")
        return completed.returncode
    print(f"[OK] {name} completed")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Apply a review patch, validate YAML, and build site assets in one command."
    )
    parser.add_argument(
        "patch",
        nargs="?",
        default=str(DEFAULT_PATCH_PATH),
        help="Path to review patch JSON (default: data/review_patch.json).",
    )
    parser.add_argument(
        "--python",
        default=sys.executable,
        help="Python executable to use for subcommands. Default: current interpreter.",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    py = args.python
    patch_path = Path(args.patch).resolve()

    if not patch_path.exists():
        print(f"[FAIL] Patch file not found: {patch_path}")
        return 1

    steps = [
        # This mirrors the most common local review workflow after exporting a patch from the admin page.
        ("Apply review patch", [py, "scripts/apply_review_patch.py", str(patch_path)]),
        ("Validate YAML data", [py, "scripts/validate.py"]),
        ("Build static site assets", [py, "scripts/build_site.py"]),
    ]

    for name, cmd in steps:
        code = run_step(name, cmd)
        if code != 0:
            return code

    print("\n[DONE] Patch apply + validate + build completed successfully.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
