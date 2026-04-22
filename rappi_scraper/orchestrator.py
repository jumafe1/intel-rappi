"""Coordinates the scraping pipeline: zones × restaurants -> snapshots."""

from __future__ import annotations

import logging
from datetime import datetime
from uuid import uuid4

from rappi_scraper.catalog import Restaurant, Zone
from rappi_scraper.client import RappiClient, RappiClientError
from rappi_scraper.models import ScrapeRun, StoreSnapshot
from rappi_scraper.parser import find_matching_products, parse_menu_from_html

log = logging.getLogger(__name__)


def _maybe_float(v: object) -> float | None:
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _maybe_int(v: object) -> int | None:
    if v is None:
        return None
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def scrape_one(
    client: RappiClient,
    zone: Zone,
    restaurant: Restaurant,
) -> StoreSnapshot:
    """Scrape one (zone, restaurant) combination. Always returns a snapshot, even on error."""
    base_kwargs: dict = {
        "platform": "rappi",
        "zone_name": zone.name,
        "zone_category": zone.category,
        "zone_lat": zone.anchor_lat,
        "zone_lng": zone.anchor_lng,
        "zone_address_input": zone.address,
        "zone_address_resolved": "",
        "restaurant_brand": restaurant.canonical_name,
        "brand_id": restaurant.brand_id,
        "store_id": None,
        "store_name": None,
        "store_address": None,
        "delivery_fee": None,
        "service_fee_pct": None,
        "eta_label": None,
        "eta_minutes": None,
        "is_open": None,
        "rating": None,
        "discount_count": 0,
        "products_total": 0,
        "products_matched": {},
        "scraped_at": datetime.now(),
    }

    try:
        # 1. Resolve zone address to precise lat/lng
        lat, lng, resolved = client.resolve_address(
            zone.address, zone.anchor_lat, zone.anchor_lng
        )
        base_kwargs["zone_address_resolved"] = resolved
        log.info(
            "[%s | %s] Resolved address -> (%.5f, %.5f)",
            zone.name,
            restaurant.canonical_name,
            lat,
            lng,
        )

        # 2. Get store info by brand_id
        store_info = client.get_store_by_brand(restaurant.brand_id, lat, lng)

        if not store_info or not store_info.get("has_coverage", True):
            raise RappiClientError(
                f"No coverage for {restaurant.canonical_name} at {zone.name}"
            )

        store_id = store_info.get("store_id")
        if not store_id:
            raise RappiClientError(
                f"No store_id returned for {restaurant.canonical_name} at {zone.name}"
            )

        rating_obj = store_info.get("rating") or {}
        score = rating_obj.get("score")
        rating_f = _maybe_float(score)

        base_kwargs.update(
            {
                "store_id": int(store_id),
                "store_name": store_info.get("name"),
                "store_address": store_info.get("address"),
                "delivery_fee": _maybe_float(store_info.get("delivery_price")),
                "service_fee_pct": _maybe_float(store_info.get("percentage_service_fee")),
                "eta_label": store_info.get("eta"),
                "eta_minutes": _maybe_int(store_info.get("eta_value")),
                "is_open": store_info.get("is_currently_available"),
                "rating": rating_f,
                "discount_count": len(store_info.get("discount_tags") or []),
            }
        )

        delivery_display = _maybe_float(store_info.get("delivery_price")) or 0.0
        log.info(
            "[%s | %s] Store: %s | delivery=$%.2f | eta=%s",
            zone.name,
            restaurant.canonical_name,
            store_info.get("name", "?"),
            delivery_display,
            store_info.get("eta", "?"),
        )

        # 3. Get HTML and parse menu
        html = client.get_store_html(int(store_id), restaurant.url_slug)
        menu = parse_menu_from_html(html)
        matches = find_matching_products(menu, restaurant.products_to_match)

        base_kwargs["products_total"] = len(menu)
        base_kwargs["products_matched"] = matches

        log.info(
            "[%s | %s] %d products, matches: %s",
            zone.name,
            restaurant.canonical_name,
            len(menu),
            {t: len(items) for t, items in matches.items()},
        )

    except (RappiClientError, Exception) as e:
        log.error("[%s | %s] Failed: %s", zone.name, restaurant.canonical_name, e)
        base_kwargs["error"] = f"{type(e).__name__}: {e}"

    return StoreSnapshot(**base_kwargs)


def run_pipeline(
    zones: list[Zone],
    restaurants: list[Restaurant],
    rate_limit_sec: float = 2.0,
) -> ScrapeRun:
    """Run the full pipeline for all zone × restaurant combinations."""
    run = ScrapeRun(
        run_id=str(uuid4())[:8],
        started_at=datetime.now(),
        completed_at=None,
    )

    log.info("=" * 70)
    log.info(
        "RAPPI PIPELINE | run_id=%s | %d zones × %d restaurants = %d scrapes",
        run.run_id,
        len(zones),
        len(restaurants),
        len(zones) * len(restaurants),
    )
    log.info("=" * 70)

    client = RappiClient(rate_limit_sec=rate_limit_sec)
    try:
        client.authenticate()

        total = len(zones) * len(restaurants)
        for i, zone in enumerate(zones, 1):
            for j, restaurant in enumerate(restaurants, 1):
                progress = (i - 1) * len(restaurants) + j
                log.info(
                    "--- [%d/%d] %s × %s ---",
                    progress,
                    total,
                    zone.name,
                    restaurant.canonical_name,
                )
                snapshot = scrape_one(client, zone, restaurant)
                run.snapshots.append(snapshot)

    except Exception as e:
        log.exception("Pipeline failed catastrophically")
        run.errors.append({"type": type(e).__name__, "message": str(e)})
    finally:
        client.close()
        run.completed_at = datetime.now()

    successful = sum(1 for s in run.snapshots if s.error is None)
    failed = len(run.snapshots) - successful
    log.info("=" * 70)
    log.info(
        "PIPELINE DONE | %d successful | %d failed | duration=%s",
        successful,
        failed,
        (run.completed_at - run.started_at) if run.completed_at else "?",
    )
    log.info("=" * 70)

    return run
