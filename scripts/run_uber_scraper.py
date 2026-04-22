#!/usr/bin/env python3
"""
Uber Eats production scrape (CDMX): all zones × McDonald's + Domino's, Rappi-shaped JSON.

Uses the same ``_p/api`` flow as ``scripts/lib/uber_mvp.py`` (httpx, no Playwright). Output mirrors
``data/raw/rappi_<run_id>.json`` so dashboards and diffs stay aligned:

  - ``run_id``, ``started_at``, ``completed_at``
  - ``total_snapshots``, ``successful``, ``failed``
  - ``snapshots[]`` with ``platform: "uber_eats"``, ``products_matched``, ``error``, …

Examples::

    python scripts/run_uber_scraper.py
    cd scripts && python run_uber_scraper.py --max-zones 3
    python scripts/run_uber_scraper.py --output data/raw/uber_eats_custom.json

Paths: ``data/...`` defaults resolve to the repo root (same as ``scripts/lib/uber_mvp.py``).
"""

from __future__ import annotations

import argparse
import json
import logging
import random
import sys
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

# Import shared Uber runtime from ``scripts/lib/``.
_SCRIPT_DIR = Path(__file__).resolve().parent
_LIB_DIR = _SCRIPT_DIR / "lib"
if str(_LIB_DIR) not in sys.path:
    sys.path.insert(0, str(_LIB_DIR))

import uber_mvp as um  # noqa: E402

log = logging.getLogger("run_uber_scraper")

_PROMO_HINTS = (
    "descuento",
    "promo",
    "2x1",
    "3x2",
    "%",
    "exclusivo",
    "combo",
    "oferta",
    "gratis",
    "rebaja",
    "ahorro",
)

_TRANSIENT_MARKERS = (
    "429",
    "502",
    "503",
    "504",
    "timeout",
    "timed out",
    "connection reset",
    "connecterror",
    "temporarily unavailable",
)


def _discount_count_from_menu(menu: list[dict[str, Any]]) -> int:
    n = 0
    for row in menu:
        name = (row.get("name") or "").lower()
        if any(h in name for h in _PROMO_HINTS):
            n += 1
    return n


def _failure_is_transient(snap: um.ZoneSnapshot) -> bool:
    blobs: list[str] = [e.lower() for e in snap.errors]
    for b in snap.brands:
        blobs.extend(x.lower() for x in b.errors)
    return any(any(m in b for m in _TRANSIENT_MARKERS) for b in blobs)


def _uber_product_rows_to_rappi_shape(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for row in rows:
        name = row.get("name") or ""
        price = row.get("price_mxn")
        if price is None:
            continue
        out.append(
            {
                "section": "",
                "name": name,
                "description": name,
                "price": float(price),
                "currency": "MXN",
            }
        )
    return out


def _zone_address_resolved(zs: um.ZoneSnapshot) -> str | None:
    if zs.resolved_title:
        return zs.resolved_title
    if zs.resolved_lat is not None and zs.resolved_lon is not None:
        return f"{zs.resolved_lat:.5f}, {zs.resolved_lon:.5f}"
    return None


def brand_to_rappi_snapshot(
    zone_cat: dict[str, Any],
    zs: um.ZoneSnapshot,
    bs: um.BrandSnapshot,
    scraped_at: datetime,
) -> dict[str, Any]:
    """One row in ``snapshots`` list (same keys as Rappi export)."""
    zone_name = str(zone_cat.get("name", zs.zone_name))
    err_parts = list(zs.errors) + list(bs.errors)
    error = "; ".join(err_parts) if err_parts else None

    full_menu = bs.menu_rows_sample
    products_matched = {
        term: _uber_product_rows_to_rappi_shape(rows) for term, rows in bs.product_matches.items()
    }

    return {
        "platform": "uber_eats",
        "zone_name": zone_name,
        "zone_category": str(zone_cat.get("category", zs.zone_category)),
        "zone_lat": float(zone_cat["lat"]),
        "zone_lng": float(zone_cat["lon"]),
        "zone_address_input": str(zone_cat.get("address", zs.address)),
        "zone_address_resolved": _zone_address_resolved(zs) or str(zone_cat.get("address", "")),
        "restaurant_brand": um.RESTAURANT_BRAND_LABEL.get(bs.brand_key, bs.brand_key),
        "brand_id": None,
        "store_id": bs.store_uuid,
        "store_name": bs.store_title,
        "store_address": None,
        "delivery_fee": bs.delivery_fee_mxn,
        "service_fee_pct": bs.service_fee_pct,
        "eta_label": bs.delivery_eta_text,
        "eta_minutes": um.parse_eta_minutes(bs.delivery_eta_text),
        "is_open": True if (bs.store_uuid and not err_parts) else None,
        "rating": um.parse_rating_float(bs.rating_text),
        "discount_count": _discount_count_from_menu(full_menu),
        "products_total": len(full_menu),
        "products_matched": products_matched,
        "scraped_at": scraped_at.isoformat(),
        "error": error,
    }


def run_zone_with_retries(
    zone: dict[str, Any],
    brands: tuple[um.BrandTarget, ...],
    *,
    retries: int,
    menu_row_limit: int | None,
    max_product_matches_per_term: int | None,
) -> um.ZoneSnapshot:
    last: um.ZoneSnapshot | None = None
    for attempt in range(max(1, retries)):
        client = um.UberEatsMVPClient()
        try:
            snap = um.run_zone(
                client,
                zone,
                brands,
                menu_row_limit=menu_row_limit,
                max_product_matches_per_term=max_product_matches_per_term,
            )
        finally:
            client.close()
        last = snap
        if not snap.errors and not _failure_is_transient(snap):
            return snap
        if not _failure_is_transient(snap):
            return snap
        if attempt < retries - 1:
            delay = (2**attempt) + random.uniform(0, 0.5)
            log.warning(
                "Transient failure zone=%s attempt=%s/%s sleep=%.1fs",
                zone.get("name"),
                attempt + 1,
                retries,
                delay,
            )
            time.sleep(delay)
    assert last is not None
    return last


def main() -> int:
    parser = argparse.ArgumentParser(description="Uber Eats full CDMX scrape → Rappi-shaped JSON")
    parser.add_argument(
        "--zones-file",
        type=Path,
        default=um.REPO_ROOT / "data/catalogs/zones_cdmx.json",
        help="Zones JSON (name, category, lat, lon, address)",
    )
    parser.add_argument(
        "--max-zones",
        type=int,
        default=0,
        help="Cap number of zones (0 = all)",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=None,
        help="Output JSON path (default: data/raw/uber_eats_<run_id>.json)",
    )
    parser.add_argument("--retries", type=int, default=3, help="Retries per zone on transient HTTP errors")
    parser.add_argument(
        "--menu-limit",
        type=int,
        default=0,
        help="Max menu rows per store (0 = unlimited, full catalog walk)",
    )
    parser.add_argument(
        "--match-limit",
        type=int,
        default=0,
        help="Max rows per product term in products_matched (0 = unlimited)",
    )
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s | %(levelname)-7s | %(message)s",
        datefmt="%H:%M:%S",
    )

    zones_path = um.resolve_read_path(args.zones_file)
    zones_all = um.load_zones(zones_path)
    if args.max_zones and args.max_zones > 0:
        zones = zones_all[: args.max_zones]
    else:
        zones = zones_all

    run_id = uuid.uuid4().hex[:8]
    started = datetime.now()
    output_path = um.resolve_write_path(
        args.output
        if args.output is not None
        else (um.REPO_ROOT / "data/raw" / f"uber_eats_{run_id}.json")
    )

    menu_limit: int | None = None if args.menu_limit == 0 else args.menu_limit
    match_limit: int | None = None if args.match_limit == 0 else args.match_limit

    brands = um.DEFAULT_BRANDS
    snapshots: list[dict[str, Any]] = []
    run_errors: list[dict[str, Any]] = []

    for z in zones:
        zname = z.get("name")
        log.info("Zone: %s", zname)
        t0 = time.perf_counter()
        try:
            snap = run_zone_with_retries(
                z,
                brands,
                retries=args.retries,
                menu_row_limit=menu_limit,
                max_product_matches_per_term=match_limit,
            )
        except Exception as e:
            log.exception("Zone %s crashed", zname)
            run_errors.append({"zone": zname, "error": f"{type(e).__name__}: {e}"})
            # Emit empty rows per brand so counts stay aligned
            for bt in brands:
                dead = um.BrandSnapshot(
                    platform="uber_eats",
                    zone_name=str(z.get("name", "")),
                    zone_address=str(z.get("address", "")),
                    brand_key=bt.key,
                    store_uuid=None,
                    store_title=None,
                    store_slug=None,
                    delivery_eta_text=None,
                    rating_text=None,
                    errors=[f"{type(e).__name__}: {e}"],
                )
                zs_dead = um.ZoneSnapshot(
                    zone_name=str(z.get("name", "")),
                    zone_category=str(z.get("category", "")),
                    address=str(z.get("address", "")),
                    anchor_lat=float(z["lat"]),
                    anchor_lon=float(z["lon"]),
                    resolved_lat=None,
                    resolved_lon=None,
                    resolved_title=None,
                    place_reference=None,
                    pl_segment=None,
                    errors=[f"{type(e).__name__}: {e}"],
                    brands=[dead],
                )
                snapshots.append(
                    brand_to_rappi_snapshot(z, zs_dead, dead, datetime.now()),
                )
            continue

        elapsed = time.perf_counter() - t0
        log.info("Zone %s done in %.1fs", zname, elapsed)
        for bs in snap.brands:
            snapshots.append(brand_to_rappi_snapshot(z, snap, bs, datetime.now()))

    completed = datetime.now()
    failed = sum(1 for s in snapshots if s.get("error"))
    successful = len(snapshots) - failed

    payload = {
        "run_id": run_id,
        "started_at": started.isoformat(),
        "completed_at": completed.isoformat(),
        "total_snapshots": len(snapshots),
        "successful": successful,
        "failed": failed,
        "snapshots": snapshots,
        "errors": run_errors,
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    log.info("Wrote %s (%s snapshots, ok=%s fail=%s)", output_path, len(snapshots), successful, failed)

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
