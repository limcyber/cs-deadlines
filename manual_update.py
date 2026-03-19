from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path
from datetime import datetime

ROOT = Path(__file__).resolve().parent


def run_step(name: str, cmd: list[str]) -> int:
    # Keep each subprocess visible so local runs are easy to debug without extra tooling.
    print(f"\n{'=' * 72}")
    print(f"[STEP] {name}")
    print(f"[CMD ] {' '.join(cmd)}")
    print(f"{'=' * 72}")
    completed = subprocess.run(cmd, cwd=ROOT)
    if completed.returncode != 0:
        print(f"[FAIL] {name} failed with exit code {completed.returncode}")
        return completed.returncode
    print(f"[OK] {name} completed")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the local manual update pipeline for the CS deadlines tracker."
    )
    parser.add_argument(
        "--skip-fetch",
        action="store_true",
        help="Skip scripts/fetch.py and only validate/build existing local data.",
    )
    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="Run only scripts/validate.py.",
    )
    parser.add_argument(
        "--build-only",
        action="store_true",
        help="Run only scripts/build_site.py.",
    )
    parser.add_argument(
        "--phase",
        type=int,
        choices=[1, 2, 3],
        default=3,
        help="Auto-review phase. 1=very conservative, 2=moderate, 3=advanced.",
    )
    parser.add_argument(
        "--python",
        default=sys.executable,
        help="Python executable to use for subcommands. Default: current interpreter.",
    )
    parser.add_argument(
        "--seed-history",
        action="store_true",
        help="After fetch, create a small bootstrap set of confirmed history seeds before auto-review.",
    )
    parser.add_argument(
        "--seed-limit",
        type=int,
        default=8,
        help="Maximum number of bootstrap confirmed history seeds to create when --seed-history is enabled.",
    )
    parser.add_argument(
        "--discover-candidates",
        action="store_true",
        help="Run scripts/discover_candidates.py before fetch to discover new venue candidates from external feeds.",
    )
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    if args.validate_only and args.build_only:
        print("[ERROR] --validate-only and --build-only cannot be used together.")
        return 2

    py = args.python
    started_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[INFO] Manual update started at {started_at}")
    print(f"[INFO] Project root: {ROOT}")
    print(f"[INFO] Python: {py}")

    if args.validate_only:
        return run_step("Validate YAML data", [py, "scripts/validate.py"])

    if args.build_only:
        return run_step("Build static site assets", [py, "scripts/build_site.py"])

    steps: list[tuple[str, list[str]]] = [
        ("Validate YAML data", [py, "scripts/validate.py"]),
    ]

    if not args.skip_fetch:
        # The local pipeline mirrors the deploy flow, with optional helper steps for curation.
        if args.discover_candidates:
            steps.append(("Discover candidate venues", [py, "scripts/discover_candidates.py"]))
        steps.append(("Fetch latest scan data", [py, "scripts/fetch.py"]))
        if args.seed_history:
            steps.append(("Bootstrap confirmed history seeds", [py, "scripts/seed_confirmed_history.py", "--limit", str(args.seed_limit)]))
        steps.append((f"Score-based auto review (phase {args.phase})", [py, "scripts/auto_review.py", "--phase", str(args.phase)]))

    steps.append(("Build static site assets", [py, "scripts/build_site.py"]))

    for name, cmd in steps:
        code = run_step(name, cmd)
        if code != 0:
            return code

    print("\n[DONE] Local manual update finished successfully.")
    print("[NEXT] Open docs/index.html or run dev.py / a local static server to preview the site.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
