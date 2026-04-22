#!/usr/bin/env python3
"""
DiDi Food final scraper (public web): same zone grid as Rappi/Uber.

Output matches the Rappi/Uber raw contract:
  - run_id / started_at / completed_at
  - total_snapshots / successful / failed
  - snapshots[] with platform, zone, products_matched, error, etc.

Notes:
  - Uses `web.didiglobal.com` public restaurant pages.
  - Zone-level geo targeting is not exposed like Uber/Rappi APIs, so zones are
    represented in output while stores are selected from CDMX city listings.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import unicodedata
import uuid
from dataclasses import dataclass
from datetime import datetime
from html import unescape
from pathlib import Path
from typing import Any

import httpx

REPO_ROOT = Path(__file__).resolve().parent.parent
BASE = "https://web.didiglobal.com"
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

PROMO_HINTS = ("descuento", "promo", "2x1", "3x2", "%", "exclusivo", "combo", "oferta", "gratis")


@dataclass(frozen=True)
class BrandTarget:
    key: str
    display_name: str
    brand_id: int
    category_slug: str
    store_hint_substrings: tuple[str, ...]
    product_terms: tuple[str, ...]


@dataclass(frozen=True)
class StoreLink:
    slug: str
    store_id: str
    path: str


FINAL_BRANDS: tuple[BrandTarget, ...] = (
    BrandTarget(
        key="mcdonalds",
        display_name="McDonald's",
        brand_id=706,
        category_slug="hamburguesas",
        store_hint_substrings=("mcdonalds", "mcdonald's", "mcdonald"),
        product_terms=("Big Mac", "McNuggets", "Cuarto de Libra"),
    ),
    BrandTarget(
        key="dominos",
        display_name="Domino's Pizza",
        brand_id=19713,
        category_slug="pizza",
        store_hint_substrings=("dominos", "domino's", "domino"),
        product_terms=("Mediana", "Grande", "Combo"),
    ),
)


def _norm(s: str) -> str:
    x = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode("ascii")
    return x.lower().strip()


def resolve_read_path(path: Path) -> Path:
    if path.is_absolute():
        return path
    cwd_candidate = (Path.cwd() / path).resolve()
    if cwd_candidate.exists():
        return cwd_candidate
    return (REPO_ROOT / path).resolve()


def resolve_write_path(path: Path) -> Path:
    if path.is_absolute():
        return path
    if path.parts and path.parts[0] == "data":
        return (REPO_ROOT / path).resolve()
    return (Path.cwd() / path).resolve()


def fetch_html(client: httpx.Client, path: str) -> str:
    r = client.get(
        path,
        headers={
            "user-agent": USER_AGENT,
            "accept-language": "es-MX",
            "accept": "text/html,application/xhtml+xml",
        },
    )
    r.raise_for_status()
    return r.text


def parse_store_links_from_listing(html: str, city_slug: str) -> list[StoreLink]:
    pattern = rf"/mx/food/{re.escape(city_slug)}/([a-z0-9\-]+)/([0-9]{{10,}})/"
    out: list[StoreLink] = []
    seen: set[tuple[str, str]] = set()
    for m in re.finditer(pattern, html, flags=re.IGNORECASE):
        slug = m.group(1)
        sid = m.group(2)
        key = (slug, sid)
        if key in seen:
            continue
        seen.add(key)
        out.append(StoreLink(slug=slug, store_id=sid, path=f"/mx/food/{city_slug}/{slug}/{sid}/"))
    return out


def crawl_brand_links(client: httpx.Client, city_slug: str, brand: BrandTarget, max_pages: int) -> list[StoreLink]:
    links: list[StoreLink] = []
    seen: set[tuple[str, str]] = set()
    hints = tuple(_norm(x) for x in brand.store_hint_substrings)
    for page in range(1, max_pages + 1):
        html = fetch_html(client, f"/mx/food/{city_slug}/categoria/{brand.category_slug}/?page={page}")
        for link in parse_store_links_from_listing(html, city_slug=city_slug):
            slug_n = _norm(link.slug)
            if not any(h in slug_n for h in hints):
                continue
            key = (link.slug, link.store_id)
            if key in seen:
                continue
            seen.add(key)
            links.append(link)
    return links


def choose_store_for_zone(zone_name: str, links: list[StoreLink]) -> StoreLink | None:
    if not links:
        return None
    # Deterministic spread across available stores so 22 zones don't all map to one branch.
    digest = hashlib.md5(zone_name.encode("utf-8")).hexdigest()
    idx = int(digest[:8], 16) % len(links)
    return links[idx]


def parse_title(html: str) -> str | None:
    m = re.search(r"<title>(.*?)</title>", html, flags=re.IGNORECASE | re.DOTALL)
    if not m:
        return None
    return unescape(m.group(1)).replace("| DiDi Food México", "").strip()


def parse_address_from_meta(html: str) -> str | None:
    m = re.search(r'<meta name="description" content="(.*?)"', html, flags=re.IGNORECASE | re.DOTALL)
    if not m:
        return None
    desc = unescape(m.group(1))
    mk = "Puedes encontrarlo ubicado en "
    if mk in desc:
        return desc.split(mk, 1)[1].strip().rstrip(".")
    return None


def parse_menu_rows(html: str, max_rows: int = 220) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen: set[tuple[str, float]] = set()
    regex = re.compile(
        r"<h4[^>]*>(?P<name>.*?)</h4>.*?MX\$(?P<price>\d+(?:\.\d{2})?).*?<p[^>]*>(?P<desc>.*?)</p>",
        flags=re.IGNORECASE | re.DOTALL,
    )
    for m in regex.finditer(html):
        name = re.sub(r"<[^>]+>", "", unescape(m.group("name"))).strip()
        desc = re.sub(r"<[^>]+>", "", unescape(m.group("desc"))).strip()
        if not name:
            continue
        try:
            price = float(m.group("price"))
        except ValueError:
            continue
        key = (name, price)
        if key in seen:
            continue
        seen.add(key)
        rows.append(
            {
                "section": "",
                "name": name,
                "description": desc or name,
                "price": price,
                "currency": "MXN",
            }
        )
        if len(rows) >= max_rows:
            break
    return rows


def match_products(menu: list[dict[str, Any]], terms: tuple[str, ...], max_per_term: int = 8) -> dict[str, list[dict[str, Any]]]:
    out: dict[str, list[dict[str, Any]]] = {t: [] for t in terms}
    for row in menu:
        n = _norm(str(row.get("name", "")))
        for t in terms:
            if _norm(t) in n and len(out[t]) < max_per_term:
                out[t].append(row)
    return out


def discount_count(menu: list[dict[str, Any]]) -> int:
    return sum(1 for r in menu if any(h in _norm(str(r.get("name", ""))) for h in PROMO_HINTS))


def snapshot_for_zone_brand(
    zone: dict[str, Any],
    brand: BrandTarget,
    store_link: StoreLink | None,
    store_cache: dict[str, dict[str, Any]],
    client: httpx.Client,
) -> dict[str, Any]:
    zone_name = str(zone["name"])
    out: dict[str, Any] = {
        "platform": "didi_food",
        "zone_name": zone_name,
        "zone_category": str(zone.get("category", "")),
        "zone_lat": float(zone["lat"]),
        "zone_lng": float(zone["lon"]),
        "zone_address_input": str(zone["address"]),
        "zone_address_resolved": str(zone["address"]),
        "restaurant_brand": brand.display_name,
        "brand_id": brand.brand_id,
        "store_id": None,
        "store_name": None,
        "store_address": None,
        "delivery_fee": None,
        "service_fee_pct": None,
        "eta_label": None,
        "eta_minutes": None,
        "is_open": True,
        "rating": None,
        "discount_count": 0,
        "products_total": 0,
        "products_matched": {t: [] for t in brand.product_terms},
        "scraped_at": datetime.now().isoformat(),
        "error": None,
        "source": "scraped",
    }

    if not store_link:
        out["error"] = f"No {brand.display_name} store link found in city listing"
        out["is_open"] = None
        return out

    cache_key = store_link.path
    if cache_key not in store_cache:
        html = fetch_html(client, store_link.path)
        menu = parse_menu_rows(html)
        store_cache[cache_key] = {
            "title": parse_title(html),
            "address": parse_address_from_meta(html),
            "menu": menu,
        }
    cached = store_cache[cache_key]
    menu_rows = list(cached["menu"])

    out["store_id"] = store_link.store_id
    out["store_name"] = cached["title"] or store_link.slug
    out["store_address"] = cached["address"]
    out["discount_count"] = discount_count(menu_rows)
    out["products_total"] = len(menu_rows)
    out["products_matched"] = match_products(menu_rows, brand.product_terms)
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description="DiDi Food final scraper (public web)")
    parser.add_argument("--city-slug", default="ciudad-de-mexico-cdmx", help="DiDi city slug to crawl")
    parser.add_argument(
        "--zones-file",
        type=Path,
        default=REPO_ROOT / "data/catalogs/zones_cdmx.json",
        help="Zones catalog JSON (same used by Rappi/Uber)",
    )
    parser.add_argument("--max-zones", type=int, default=0, help="Limit number of zones (0 = all)")
    parser.add_argument("--max-pages", type=int, default=8, help="Pages per category to scan for stores")
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=None,
        help="Output path (default: data/raw/didi_food_<run_id>.json)",
    )
    args = parser.parse_args()

    zones_path = resolve_read_path(args.zones_file)
    zones_all: list[dict[str, Any]] = json.loads(zones_path.read_text(encoding="utf-8"))
    zones = zones_all[: args.max_zones] if args.max_zones and args.max_zones > 0 else zones_all

    run_id = uuid.uuid4().hex[:8]
    started = datetime.now()
    output_path = resolve_write_path(
        args.output if args.output is not None else (REPO_ROOT / "data/raw" / f"didi_food_{run_id}.json")
    )

    snapshots: list[dict[str, Any]] = []
    run_errors: list[dict[str, Any]] = []
    store_cache: dict[str, dict[str, Any]] = {}

    client = httpx.Client(base_url=BASE, timeout=45.0, follow_redirects=True)
    try:
        links_by_brand: dict[str, list[StoreLink]] = {}
        for brand in FINAL_BRANDS:
            links = crawl_brand_links(client, args.city_slug, brand, max_pages=args.max_pages)
            links_by_brand[brand.key] = links
            if not links:
                run_errors.append(
                    {"brand": brand.display_name, "error": f"No links found in {args.city_slug} pages 1..{args.max_pages}"}
                )

        for zone in zones:
            for brand in FINAL_BRANDS:
                links = links_by_brand.get(brand.key, [])
                pick = choose_store_for_zone(str(zone["name"]), links)
                snap = snapshot_for_zone_brand(zone, brand, pick, store_cache, client)
                snapshots.append(snap)
    finally:
        client.close()

    completed = datetime.now()
    failed = sum(1 for s in snapshots if s.get("error"))
    payload = {
        "run_id": run_id,
        "started_at": started.isoformat(),
        "completed_at": completed.isoformat(),
        "total_snapshots": len(snapshots),
        "successful": len(snapshots) - failed,
        "failed": failed,
        "snapshots": snapshots,
        "errors": run_errors,
        "collection_mode": "public_web_city_listing",
        "city_slug": args.city_slug,
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Wrote {output_path} ({len(snapshots)} snapshots, ok={len(snapshots)-failed}, fail={failed})")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
