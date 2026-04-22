#!/usr/bin/env python3
"""Run the full pipeline: scrapers first, then warehouse build."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def run_pipeline(*, skip_scrape: bool = False, fail_fast: bool = True) -> int:
    steps: list[list[str]] = []

    if not skip_scrape:
        step = [sys.executable, str(REPO_ROOT / "scripts" / "run_scrapers.py")]
        if not fail_fast:
            step.append("--no-fail-fast")
        steps.append(step)

    steps.append([sys.executable, str(REPO_ROOT / "scripts" / "build_warehouse.py")])

    for step in steps:
        print(f"[run_pipeline] Running: {' '.join(step)}")
        completed = subprocess.run(step, cwd=REPO_ROOT, check=False)
        if completed.returncode != 0:
            return completed.returncode

    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run scrapers and build the warehouse")
    parser.add_argument(
        "--skip-scrape",
        action="store_true",
        help="Skip scraper execution and build the warehouse from existing raw JSON files",
    )
    parser.add_argument(
        "--no-fail-fast",
        action="store_true",
        help="Pass through to the scraper orchestrator so it continues after scraper failures",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    return run_pipeline(skip_scrape=args.skip_scrape, fail_fast=not args.no_fail_fast)


if __name__ == "__main__":
    raise SystemExit(main())
