"""
Uber Eats MVP scraper (CDMX): one zone, McDonald's + Domino's via public web APIs.

Flow (mirrors captured traffic in ``uber_location_flow.json`` / ``uber_explore.json`` en esta carpeta):
  1. GET ``/mx`` to seed cookies
  2. POST ``mapsSearchV1`` with free-text address
  3. POST ``getDeliveryLocationV1`` with Google place id from search
  4. POST ``setTargetLocationV1`` + location headers (lat/lng)
  5. POST ``getSearchSuggestionsV1`` + ``getSearchFeedV1`` per brand query
  6. POST ``getStoreV1`` for the first matching store UUID
  7. Heuristic menu extraction + product term matching

Usage:
    python scripts/lib/uber_mvp.py
    cd scripts/lib && python uber_mvp.py --max-zones 1

Paths: relative ``data/...`` defaults resolve to the **repo root**, so running
from ``scripts/lib/`` still finds ``data/catalogs/...``.

Requirements: ``httpx`` (see requirements.txt). No Playwright at runtime.
"""

from __future__ import annotations

import argparse
import base64
import json
import logging
import re
import time
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote

import httpx

log = logging.getLogger("uber_mvp")

# Repo root = intel-rappi/ (this file is under scripts/lib/)
REPO_ROOT = Path(__file__).resolve().parent.parent.parent

BASE = "https://www.ubereats.com"
LOCALE = "mx"
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
# Observed in browser captures; if requests start failing, refresh from DevTools.
UBER_CLIENT_GITREF = "7ea465481956e7c917fa4fa3897ab56ca8a1ccef"

RATE_LIMIT_SEC = 1.5


@dataclass
class BrandTarget:
    """Brand to resolve via search."""

    key: str
    search_query: str
    title_substrings: tuple[str, ...]  # match store title (case-insensitive)
    product_terms: tuple[str, ...]


DEFAULT_BRANDS: tuple[BrandTarget, ...] = (
    BrandTarget(
        key="mcdonalds",
        search_query="mcdonalds",
        title_substrings=("mcdonald", "mc donald"),
        product_terms=("Big Mac", "McNuggets", "Cuarto"),
    ),
    BrandTarget(
        key="dominos",
        search_query="dominos",
        title_substrings=("domino",),
        product_terms=("Mediana", "Grande", "Combo"),
    ),
)


# Display names aligned with Rappi scrape JSON (`restaurant_brand`).
RESTAURANT_BRAND_LABEL: dict[str, str] = {
    "mcdonalds": "McDonald's",
    "dominos": "Domino's Pizza",
}


@dataclass
class BrandSnapshot:
    """One brand in one zone."""

    platform: str
    zone_name: str
    zone_address: str
    brand_key: str
    store_uuid: str | None
    store_title: str | None
    store_slug: str | None
    delivery_eta_text: str | None
    rating_text: str | None
    menu_rows_sample: list[dict[str, Any]] = field(default_factory=list)
    product_matches: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    raw_store_bytes: int = 0
    delivery_fee_mxn: float | None = None
    service_fee_pct: float | None = None
    errors: list[str] = field(default_factory=list)


@dataclass
class ZoneSnapshot:
    zone_name: str
    zone_category: str
    address: str
    anchor_lat: float
    anchor_lon: float
    resolved_lat: float | None
    resolved_lon: float | None
    resolved_title: str | None
    place_reference: str | None
    pl_segment: str | None
    brands: list[BrandSnapshot] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


@dataclass
class RunResult:
    scraped_at: str
    zones: list[ZoneSnapshot]


def _sleep_rl() -> None:
    time.sleep(RATE_LIMIT_SEC)


def encode_pl_segment(address: str, reference: str, lat: float, lng: float) -> str:
    """Build the ``pl`` / cacheKey prefix (base64 of URL-encoded location JSON)."""
    payload = {
        "address": address,
        "reference": reference,
        "referenceType": "google_places",
        "latitude": lat,
        "longitude": lng,
    }
    j = json.dumps(payload, separators=(",", ":"))
    quoted = quote(j, safe="")
    return base64.b64encode(quoted.encode()).decode()


def cache_key_from_pl_segment(pl_segment: str) -> str:
    """Full ``cacheKey`` body field for ``getFeedV1`` (HOME skeleton)."""
    tail = base64.b64encode(quote("[]").encode()).decode()
    return f"{pl_segment}/DELIVERY///0/0//{tail}/undefined//////HOME////////"


class UberEatsMVPClient:
    """Minimal session-aware client for ``_p/api`` endpoints."""

    def __init__(self) -> None:
        self.session_id = str(uuid.uuid4())
        self.ciid = str(uuid.uuid4())
        self._lat: float = 19.4326
        self._lng: float = -99.1332
        self._client = httpx.Client(
            base_url=BASE,
            timeout=45.0,
            follow_redirects=True,
            headers={
                "user-agent": USER_AGENT,
                "accept-language": "es-MX",
                "origin": BASE,
            },
        )

    def close(self) -> None:
        self._client.close()

    def set_coords(self, lat: float, lng: float) -> None:
        self._lat = lat
        self._lng = lng

    def _loc_headers(self) -> dict[str, str]:
        return {
            "x-uber-device-location-latitude": str(self._lat),
            "x-uber-device-location-longitude": str(self._lng),
            "x-uber-target-location-latitude": str(self._lat),
            "x-uber-target-location-longitude": str(self._lng),
        }

    def _api_headers(self, referer_path: str) -> dict[str, str]:
        return {
            "content-type": "application/json",
            "accept": "application/json",
            "x-csrf-token": "x",
            "x-uber-session-id": self.session_id,
            "x-uber-ciid": self.ciid,
            "x-uber-client-gitref": UBER_CLIENT_GITREF,
            "x-uber-request-id": str(uuid.uuid4()),
            "referer": f"{BASE}{referer_path}",
            **self._loc_headers(),
        }

    def bootstrap(self) -> None:
        log.info("GET /%s (bootstrap cookies)", LOCALE)
        _sleep_rl()
        r = self._client.get(f"/{LOCALE}", headers={"user-agent": USER_AGENT, "accept-language": "es-MX"})
        r.raise_for_status()

    def maps_search(self, query: str) -> list[dict[str, Any]]:
        _sleep_rl()
        r = self._client.post(
            f"/_p/api/mapsSearchV1?localeCode={LOCALE}",
            headers=self._api_headers(referer_path=f"/{LOCALE}"),
            json={"query": query},
        )
        r.raise_for_status()
        data = r.json()
        if data.get("status") != "success":
            raise RuntimeError(f"mapsSearchV1: {data}")
        return list(data.get("data") or [])

    def get_delivery_location(self, place_id: str) -> dict[str, Any]:
        _sleep_rl()
        r = self._client.post(
            f"/_p/api/getDeliveryLocationV1?localeCode={LOCALE}",
            headers=self._api_headers(referer_path=f"/{LOCALE}"),
            json={
                "placeId": place_id,
                "provider": "google_places",
                "source": "manual_auto_complete",
            },
        )
        r.raise_for_status()
        data = r.json()
        if data.get("status") != "success":
            raise RuntimeError(f"getDeliveryLocationV1: {data}")
        return dict(data.get("data") or {})

    def warm_feed_page(self, pl_segment: str) -> str:
        """GET feed HTML with ``pl`` so Uber sets delivery-location cookies (browser parity)."""
        pl_q = quote(pl_segment, safe="")
        path = f"/{LOCALE}/feed?pl={pl_q}"
        _sleep_rl()
        r = self._client.get(
            path,
            headers={
                "user-agent": USER_AGENT,
                "accept-language": "es-MX",
                "accept": "text/html,application/xhtml+xml",
                "upgrade-insecure-requests": "1",
                "referer": f"{BASE}/{LOCALE}",
            },
        )
        r.raise_for_status()
        return path

    def get_instruction_for_location(self, location_payload: dict[str, Any], referer_path: str) -> None:
        """Optional: align with web shell before ``setTargetLocation``."""
        _sleep_rl()
        r = self._client.post(
            f"/_p/api/getInstructionForLocationV1?localeCode={LOCALE}",
            headers=self._api_headers(referer_path=referer_path),
            json={"location": location_payload},
        )
        r.raise_for_status()
        body = r.json()
        if body.get("status") != "success":
            raise RuntimeError(f"getInstructionForLocationV1: {body}")

    def set_target_location(self, referer_pl_path: str) -> None:
        _sleep_rl()
        r = self._client.post(
            f"/_p/api/setTargetLocationV1?localeCode={LOCALE}",
            headers=self._api_headers(referer_path=referer_pl_path),
            json={},
        )
        r.raise_for_status()
        body = r.json()
        if body.get("status") != "success":
            raise RuntimeError(f"setTargetLocationV1: {body}")

    def get_search_suggestions(self, user_query: str, referer_pl_path: str) -> dict[str, Any]:
        _sleep_rl()
        r = self._client.post(
            f"/_p/api/getSearchSuggestionsV1?localeCode={LOCALE}",
            headers=self._api_headers(referer_path=referer_pl_path),
            json={
                "userQuery": user_query,
                "date": "",
                "startTime": 0,
                "endTime": 0,
                "vertical": "ALL",
            },
        )
        r.raise_for_status()
        return r.json()

    def get_search_feed(self, user_query: str, referer_search_path: str) -> dict[str, Any]:
        _sleep_rl()
        r = self._client.post(
            f"/_p/api/getSearchFeedV1?localeCode={LOCALE}",
            headers=self._api_headers(referer_path=referer_search_path),
            json={
                "userQuery": user_query,
                "date": "",
                "startTime": 0,
                "endTime": 0,
                "sortAndFilters": [],
                "vertical": "ALL",
                "searchSource": "SEARCH_BAR",
                "displayType": "SEARCH_RESULTS",
                "searchType": "GLOBAL_SEARCH",
                "keyName": "",
                "cacheKey": "",
                "recaptchaToken": "",
            },
        )
        r.raise_for_status()
        return r.json()

    def get_store(self, store_uuid: str, referer_store_path: str) -> dict[str, Any]:
        _sleep_rl()
        r = self._client.post(
            f"/_p/api/getStoreV1?localeCode={LOCALE}",
            headers=self._api_headers(referer_path=referer_store_path),
            json={
                "storeUuid": store_uuid,
                "diningMode": "DELIVERY",
                "time": {"asap": True},
                "cbType": "EATER_ENDORSED",
            },
        )
        r.raise_for_status()
        return r.json()


def pick_maps_result_mx(results: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Prefer a Google Places row that looks like CDMX."""
    hints = ("méxico", "mexico", "cdmx", "ciudad de méxico", "ciudad de mexico", "cmx")
    for row in results:
        line2 = (row.get("addressLine2") or "").lower()
        if any(h in line2 for h in hints):
            return row
    return results[0] if results else None


def store_matches_brand(store_obj: dict[str, Any], brand: BrandTarget) -> bool:
    title = ((store_obj.get("title") or {}).get("text")) or ""
    t = title.lower()
    return any(s in t for s in brand.title_substrings)


def iter_stores_from_search_feed(feed: dict[str, Any]):
    """Yield store dicts from getSearchFeedV1 ``feedItems``."""
    items = (feed.get("data") or {}).get("feedItems") or []
    for it in items:
        if it.get("type") == "REGULAR_STORE" and isinstance(it.get("store"), dict):
            yield it["store"]
        car = it.get("carousel") or {}
        for st in car.get("stores") or []:
            if isinstance(st, dict):
                yield st


def pick_store_for_brand(feed: dict[str, Any], brand: BrandTarget) -> dict[str, Any] | None:
    for st in iter_stores_from_search_feed(feed):
        if store_matches_brand(st, brand):
            return st
    return None


def meta_text(store: dict[str, Any], badge_type: str) -> str | None:
    for m in store.get("meta") or []:
        if m.get("badgeType") == badge_type:
            return m.get("text")
    return None


def extract_eta_rating(store: dict[str, Any]) -> tuple[str | None, str | None]:
    return meta_text(store, "ETD"), (store.get("rating") or {}).get("text")


def walk_priced_items(node: Any, out: list[dict[str, Any]], depth: int = 0) -> None:
    """Collect nodes that look like menu line items (title + numeric price)."""
    if depth > 35:
        return
    if isinstance(node, dict):
        title_obj = node.get("title")
        text: str | None = None
        if isinstance(title_obj, str):
            text = title_obj
        elif isinstance(title_obj, dict):
            text = title_obj.get("text")
        price = node.get("price")
        if price is None:
            price = node.get("itemPrice")
        if text and price is not None:
            try:
                p = float(price)
            except (TypeError, ValueError):
                p = None
            if p is not None and len(text.strip()) > 1:
                # Uber web payloads often use minor currency units (e.g. centavos).
                if p >= 500 and p == int(p):
                    p = round(p / 100.0, 2)
                out.append({"name": text.strip(), "price_mxn": p})
        for v in node.values():
            walk_priced_items(v, out, depth + 1)
    elif isinstance(node, list):
        for x in node:
            walk_priced_items(x, out, depth + 1)


def match_products(
    menu: list[dict[str, Any]],
    terms: tuple[str, ...],
    max_per_term: int | None = 8,
) -> dict[str, list[dict[str, Any]]]:
    matches: dict[str, list[dict[str, Any]]] = {t: [] for t in terms}
    for row in menu:
        name_l = row["name"].lower()
        for term in terms:
            cap_ok = max_per_term is None or len(matches[term]) < max_per_term
            if term.lower() in name_l and cap_ok:
                matches[term].append(row)
    return matches


def parse_eta_minutes(eta_text: str | None) -> int | None:
    """Parse ``'16 min'`` / ``'15-35 min'`` style badges into a single minute estimate."""
    if not eta_text:
        return None
    m = re.search(r"(\d+)\s*-\s*(\d+)", eta_text)
    if m:
        return (int(m.group(1)) + int(m.group(2))) // 2
    m2 = re.search(r"(\d+)", eta_text)
    return int(m2.group(1)) if m2 else None


def parse_rating_float(rating_text: str | None) -> float | None:
    if not rating_text:
        return None
    try:
        return float(rating_text.replace(",", "."))
    except ValueError:
        return None


def extract_delivery_fee_mxn(store_root: Any) -> float | None:
    """Best-effort delivery fee from ``getStoreV1`` payload (keys vary by client version)."""
    candidates: list[float] = []

    def walk(o: Any, depth: int = 0) -> None:
        if depth > 48:
            return
        if isinstance(o, dict):
            for k, v in o.items():
                lk = str(k).lower()
                if isinstance(v, (int, float)) and not isinstance(v, bool):
                    if ("delivery" in lk and "fee" in lk) or lk in (
                        "bookingfee",
                        "deliveryfee",
                        "delivery_fee",
                        "feeamount",
                    ):
                        val = float(v)
                        if val >= 500 and val == int(val):
                            val = round(val / 100.0, 2)
                        if 0 < val < 800:
                            candidates.append(val)
                walk(v, depth + 1)
        elif isinstance(o, list):
            for x in o:
                walk(x, depth + 1)

    walk(store_root)
    return min(candidates) if candidates else None


def slug_from_action_url(action_url: str | None) -> str | None:
    if not action_url:
        return None
    # "/store/dominos-anzures/dlLBnevCSBeaE-DQ1n5UNA"
    m = re.search(r"/store/([^/]+)/", action_url)
    return m.group(1) if m else None


def run_zone(
    client: UberEatsMVPClient,
    zone: dict[str, Any],
    brands: tuple[BrandTarget, ...],
    *,
    menu_row_limit: int | None = 80,
    max_product_matches_per_term: int | None = 8,
) -> ZoneSnapshot:
    name = str(zone["name"])
    cat = str(zone.get("category", ""))
    address = str(zone["address"])
    lat0 = float(zone["lat"])
    lon0 = float(zone["lon"])

    snap = ZoneSnapshot(
        zone_name=name,
        zone_category=cat,
        address=address,
        anchor_lat=lat0,
        anchor_lon=lon0,
        resolved_lat=None,
        resolved_lon=None,
        resolved_title=None,
        place_reference=None,
        pl_segment=None,
    )

    try:
        client.bootstrap()
        maps = client.maps_search(address)
        pick = pick_maps_result_mx(maps)
        if not pick:
            snap.errors.append("mapsSearchV1: no results")
            return snap

        place_id = pick.get("id")
        if not place_id:
            snap.errors.append("mapsSearchV1: missing id")
            return snap

        loc = client.get_delivery_location(str(place_id))
        addr = loc.get("address") or {}
        rlat = float(loc["latitude"])
        rlon = float(loc["longitude"])
        ref = str(loc.get("reference") or "")
        title = str(addr.get("title") or addr.get("address1") or name)

        snap.resolved_lat = rlat
        snap.resolved_lon = rlon
        snap.resolved_title = title
        snap.place_reference = ref or None

        client.set_coords(rlat, rlon)

        pl_seg = encode_pl_segment(title, ref, rlat, rlon)
        snap.pl_segment = pl_seg
        pl_q = quote(pl_seg, safe="")
        feed_path = f"/{LOCALE}/feed?pl={pl_q}"

        # Browser sets cookies when loading feed; without this, setTargetLocation may fail.
        feed_get_path = client.warm_feed_page(pl_seg)
        client.get_instruction_for_location(loc, feed_get_path)
        client.set_target_location(feed_path)

        for brand in brands:
            bs = BrandSnapshot(
                platform="uber_eats",
                zone_name=name,
                zone_address=address,
                brand_key=brand.key,
                store_uuid=None,
                store_title=None,
                store_slug=None,
                delivery_eta_text=None,
                rating_text=None,
            )
            try:
                client.get_search_suggestions(brand.search_query, feed_path)
                search_path = (
                    f"/{LOCALE}/search?pl={pl_q}&q={quote(brand.search_query)}"
                    "&sc=SEARCH_BAR&searchType=GLOBAL_SEARCH&vertical=ALL"
                )
                sf = client.get_search_feed(brand.search_query, search_path)
                if sf.get("status") != "success":
                    bs.errors.append(f"getSearchFeedV1: {sf.get('status')}")
                    snap.brands.append(bs)
                    continue

                st = pick_store_for_brand(sf, brand)
                if not st:
                    bs.errors.append("no store matched title heuristics in search feed")
                    snap.brands.append(bs)
                    continue

                uuid_s = st.get("storeUuid")
                bs.store_uuid = str(uuid_s) if uuid_s else None
                bs.store_title = (st.get("title") or {}).get("text")
                bs.store_slug = slug_from_action_url(st.get("actionUrl"))
                bs.delivery_eta_text, bs.rating_text = extract_eta_rating(st)

                slug = bs.store_slug or "store"
                store_path = f"/{LOCALE}/store/{slug}?surfaceName="
                raw = client.get_store(str(uuid_s), store_path)
                if raw.get("status") != "success":
                    bs.errors.append(f"getStoreV1: {raw.get('status')}")
                    snap.brands.append(bs)
                    continue

                body = json.dumps(raw, ensure_ascii=False)
                bs.raw_store_bytes = len(body.encode("utf-8"))
                bs.delivery_fee_mxn = extract_delivery_fee_mxn(raw.get("data"))
                bs.service_fee_pct = 0.0

                menu: list[dict[str, Any]] = []
                walk_priced_items(raw.get("data"), menu)
                # Dedupe by name+price
                seen: set[tuple[str, float]] = set()
                uniq: list[dict[str, Any]] = []
                for row in menu:
                    key = (row["name"], row["price_mxn"])
                    if key in seen:
                        continue
                    seen.add(key)
                    uniq.append(row)
                if menu_row_limit is None:
                    bs.menu_rows_sample = uniq
                else:
                    bs.menu_rows_sample = uniq[:menu_row_limit]
                bs.product_matches = {
                    k: v
                    for k, v in match_products(
                        uniq, brand.product_terms, max_per_term=max_product_matches_per_term
                    ).items()
                }
            except httpx.HTTPStatusError as e:
                bs.errors.append(f"HTTP {e.response.status_code}: {e.response.text[:240]}")
            except Exception as e:
                bs.errors.append(f"{type(e).__name__}: {e}")
            snap.brands.append(bs)

    except Exception as e:
        snap.errors.append(f"{type(e).__name__}: {e}")

    return snap


def load_zones(path: Path) -> list[dict[str, Any]]:
    return json.loads(path.read_text(encoding="utf-8"))


def resolve_read_path(path: Path) -> Path:
    """Resolve a file to read: cwd first, then repo root (for ``scripts/`` cwd)."""
    if path.is_absolute():
        return path
    cwd_candidate = (Path.cwd() / path).resolve()
    if cwd_candidate.exists():
        return cwd_candidate
    return (REPO_ROOT / path).resolve()


def resolve_write_path(path: Path) -> Path:
    """Resolve output path: ``data/...`` → repo; other relative paths → cwd."""
    if path.is_absolute():
        return path
    parts = path.parts
    if parts and parts[0] == "data":
        return (REPO_ROOT / path).resolve()
    return (Path.cwd() / path).resolve()


def main() -> int:
    parser = argparse.ArgumentParser(description="Uber Eats MVP scrape (httpx)")
    parser.add_argument(
        "--zones-file",
        type=Path,
        default=REPO_ROOT / "data/catalogs/zones_cdmx.json",
        help="Zones JSON (name, category, lat, lon, address)",
    )
    parser.add_argument("--max-zones", type=int, default=1, help="Number of zones to scrape")
    parser.add_argument(
        "--output",
        type=Path,
        default=REPO_ROOT / "data/raw" / f"uber_mvp_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
    )
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s | %(levelname)-7s | %(message)s",
        datefmt="%H:%M:%S",
    )

    zones_path = resolve_read_path(args.zones_file)
    output_path = resolve_write_path(args.output)

    zones = load_zones(zones_path)[: max(1, args.max_zones)]
    client = UberEatsMVPClient()
    out_zones: list[ZoneSnapshot] = []
    try:
        for z in zones:
            log.info("Zone: %s", z.get("name"))
            out_zones.append(run_zone(client, z, DEFAULT_BRANDS))
    finally:
        client.close()

    result = RunResult(scraped_at=datetime.now().isoformat(), zones=out_zones)
    # Serialize dataclasses manually (nested)
    payload = {
        "scraped_at": result.scraped_at,
        "zones": [asdict(z) for z in result.zones],
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    log.info("Wrote %s", output_path)

    ok = all(not z.errors for z in out_zones) and all(not b.errors for z in out_zones for b in z.brands)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
