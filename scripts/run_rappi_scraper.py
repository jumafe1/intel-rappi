#!/usr/bin/env python3
"""Rappi production scrape: todas las zonas × McDonald's + Domino's → JSON en ``data/raw/``.

Misma lógica que el proyecto ``rappi-explore`` (paquete ``rappi_scraper`` en la raíz de
este repo). Salida: ``data/raw/rappi_<run_id>.json``.

Examples::

    python scripts/run_rappi_scraper.py
    python scripts/run_rappi_scraper.py --zones 1
    python scripts/run_rappi_scraper.py --rate-limit 2.5 --log-level DEBUG
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def setup_logging(level: str = "INFO") -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s | %(levelname)-7s | %(name)-30s | %(message)s",
        datefmt="%H:%M:%S",
    )


def main() -> None:
    from rappi_scraper.catalog import RESTAURANTS, ZONES
    from rappi_scraper.orchestrator import run_pipeline

    parser = argparse.ArgumentParser(description="Scrape Rappi for competitive intelligence")
    parser.add_argument(
        "--zones",
        type=int,
        default=None,
        help="Limit to N first zones (for testing)",
    )
    parser.add_argument(
        "--rate-limit",
        type=float,
        default=2.0,
        help="Seconds between requests (default 2.0)",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Base output directory (default: <repo>/data/raw)",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        help="DEBUG, INFO, WARNING, ERROR",
    )
    args = parser.parse_args()

    setup_logging(args.log_level)

    zones = ZONES[: args.zones] if args.zones else ZONES
    restaurants = RESTAURANTS

    run = run_pipeline(zones, restaurants, rate_limit_sec=args.rate_limit)

    out_base = args.output_dir if args.output_dir is not None else (REPO_ROOT / "data" / "raw")
    if not out_base.is_absolute():
        out_base = REPO_ROOT / out_base

    out_base.mkdir(parents=True, exist_ok=True)
    output_file = out_base / f"rappi_{run.run_id}.json"

    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(run.to_dict(), f, indent=2, ensure_ascii=False)

    print(f"\nSaved to: {output_file}")
    print(f"   Total snapshots: {len(run.snapshots)}")
    print(f"   Successful: {sum(1 for s in run.snapshots if s.error is None)}")
    print(f"   Failed: {sum(1 for s in run.snapshots if s.error is not None)}")


if __name__ == "__main__":
    main()
