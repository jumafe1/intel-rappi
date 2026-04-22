#!/usr/bin/env python3
"""Run the 3 production scrapers sequentially."""

from __future__ import annotations

import argparse
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = REPO_ROOT / "data" / "raw"


@dataclass(frozen=True)
class ScraperCommand:
    platform: str
    command: list[str]


def build_scraper_commands(python_executable: str) -> list[ScraperCommand]:
    return [
        ScraperCommand(
            platform="rappi",
            command=[
                python_executable,
                str(REPO_ROOT / "scripts" / "run_rappi_scraper.py"),
                "--output-dir",
                str(RAW_DIR),
            ],
        ),
        ScraperCommand(
            platform="uber_eats",
            command=[
                python_executable,
                str(REPO_ROOT / "scripts" / "run_uber_scraper.py"),
                "--output",
                str(RAW_DIR / "uber_eats_latest.json"),
            ],
        ),
        ScraperCommand(
            platform="didi_food",
            command=[
                python_executable,
                str(REPO_ROOT / "scripts" / "run_didi_scraper.py"),
                "--output",
                str(RAW_DIR / "didi_food_latest.json"),
            ],
        ),
    ]


def run_scrapers(*, fail_fast: bool = True, python_executable: str = sys.executable) -> int:
    commands = build_scraper_commands(python_executable)
    failures = 0

    for scraper in commands:
        print(f"[run_scrapers] Running {scraper.platform}: {' '.join(scraper.command)}")
        completed = subprocess.run(scraper.command, cwd=REPO_ROOT, check=False)
        if completed.returncode != 0:
            failures += 1
            print(f"[run_scrapers] {scraper.platform} failed with exit code {completed.returncode}")
            if fail_fast:
                return completed.returncode

    return 0 if failures == 0 else 1


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run all production scrapers sequentially")
    parser.add_argument(
        "--no-fail-fast",
        action="store_true",
        help="Continue running the remaining scrapers even if one scraper fails",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    return run_scrapers(fail_fast=not args.no_fail_fast)


if __name__ == "__main__":
    raise SystemExit(main())
