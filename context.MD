# Intel-Rappi Context (Handoff)

This document is a high-detail handoff so another AI/engineer can continue without losing context.

Last updated from repo state on: 2026-04-22.

---

## 1) Project objective

Competitive intelligence across food-delivery platforms in Mexico, using a shared output shape:

- Platforms in scope:
  - `rappi` (real scraping)
  - `uber_eats` (real scraping)
  - `didi_food` (real public-web scraping)
- Geography:
  - CDMX zone catalog with 22 zones.
- Brands:
  - McDonald's
  - Domino's Pizza

Target artifact shape is the same family used in `data/raw/*.json`: top-level run metadata + `snapshots[]`.

---

## 2) Current scripts status

### Final scripts (`scripts/`)

- `scripts/run_rappi_scraper.py`
  - Uses `rappi_scraper/` package.
  - Real scraping.
  - Expected output: 22 zones x 2 brands = 44 snapshots.

- `scripts/run_uber_scraper.py`
  - Uses `scripts/lib/uber_mvp.py` internals.
  - Real scraping via Uber web APIs.
  - Can produce 44 snapshots if full run succeeds.

- `scripts/run_didi_scraper.py`
  - Final DiDi scraper using public `web.didiglobal.com` listing/store pages.
  - Real scraping (public web HTML), no app login.
  - Expected output: 44 snapshots.
  - Technical caveat: zone-level location targeting is not equivalent to Uber/Rappi APIs; zones are represented in output while stores are chosen from CDMX city listings.

### Repo cleanup status

- Legacy DiDi synthetic/reference files were removed.
- Legacy scaffold folders were removed:
  - `core/`
  - `pipeline/`
  - `scrapers/`
  - `dashboard/`
  - `tests/`
- Old exploration files under `scripts/pruebas/` were removed after moving the
  Uber shared runtime to `scripts/lib/uber_mvp.py`.

---

## 3) Raw data currently selected (latest in `data/raw/`)

Detected latest per platform:

- Rappi: `data/raw/rappi_1734f984.json`
- Uber: `data/raw/uber_eats_9063ede5.json`
- DiDi: `data/raw/didi_food_6c758b1f.json`

---

## 4) Data quality snapshot (current files)

## Rappi (`rappi_1734f984.json`)

- `total_snapshots`: 44
- `successful`: 41
- `failed`: 3
- Unique zones: 22
- Zone cardinality: min=2, max=2 (good)
- Brand counts:
  - McDonald's: 22
  - Domino's Pizza: 22
- Null / missing health:
  - `store_name` null: 3
  - `delivery_fee` null: 3
  - `eta_minutes` null: 3
  - `rating` null: 3
  - `products_total` in (0/null): 9
  - `products_matched` all empty: 9
  - `error` non-null: 3
- Sample errors:
  - No coverage for McDonald's at Tláhuac
  - No coverage for McDonald's at Milpa Alta
  - No coverage for Domino's Pizza at Milpa Alta

Interpretation:
- Structurally good.
- Known coverage gaps in peripheral zones.

## Uber (`uber_eats_9063ede5.json`)

- `total_snapshots`: 40
- `successful`: 40
- `failed`: 0
- Unique zones: 20
- Zone cardinality: min=2, max=2
- Brand counts:
  - McDonald's: 20
  - Domino's Pizza: 20
- Null / missing health:
  - `store_name` null: 0
  - `delivery_fee` null: 40 (all null)
  - `eta_minutes` null: 2
  - `rating` null: 0
  - `products_total` in (0/null): 0
  - `products_matched` all empty: 0
  - `error` non-null: 0
- Zone mismatch vs Rappi:
  - Missing zones: `Cuautepec`, `Del Valle`

Interpretation:
- High quality on products and store selection.
- Incomplete zone coverage (40 vs expected 44).
- Delivery fee extraction still not available in this run.

## DiDi (`didi_food_6c758b1f.json`)

- `total_snapshots`: 44
- `successful`: 44
- `failed`: 0
- Unique zones: 22
- Zone cardinality: min=2, max=2
- Brand counts:
  - McDonald's: 22
  - Domino's Pizza: 22
- Null / missing health:
  - `store_name` null: 0
  - `delivery_fee` null: 44 (all null)
  - `eta_minutes` null: 44 (all null)
  - `rating` null: 44 (all null)
  - `products_total` in (0/null): 0
  - `products_matched` all empty: 0
  - `error` non-null: 0
- Zone mismatch vs Rappi:
  - Missing zones: none

Interpretation:
- Full zone coverage and strong menu extraction.
- Fee/ETA/rating not exposed by current public-web extraction flow.

---

## 5) Consistency conclusions

- Snapshot granularity is consistent enough for cross-platform benchmarking:
  - one row per `(platform, zone, restaurant_brand)` in `snapshots`.
- Product-level structure is not natively uniform but can be normalized from `products_matched`.
- Main comparability risks:
  1. Uber has only 20 zones in current selected file.
  2. Fee/ETA/rating completeness differs by platform.
  3. Rappi includes explicit no-coverage rows (`error`) that should be preserved, not dropped silently.

---

## 6) Recommended execution plan (data-first)

## Phase A — finalize raw selection (quick)

1. Decide whether to:
   - keep current Uber file (`40` snapshots), or
   - rerun Uber to target `44` snapshots.
2. Freeze one file per platform as canonical input for warehouse build.

## Phase B — normalization pipeline (priority)

Implement `scripts/build_warehouse.py` with outputs:

- `data/warehouse/intel_rappi.duckdb`
- optional parquet exports in `data/warehouse/`:
  - `runs.parquet`
  - `snapshots.parquet`
  - `product_matches.parquet`
  - `data_quality_checks.parquet`

### Suggested tables

1. `runs`
   - `platform`, `run_id`, `started_at`, `completed_at`, `total_snapshots`, `successful`, `failed`, `raw_file`

2. `snapshots`
   - keys: `platform`, `run_id`, `zone_name`, `restaurant_brand`
   - core fields: store, fee, ETA, rating, error, products_total, timestamps

3. `product_matches`
   - one row per matched product item
   - fields: snapshot foreign key + `term`, `product_name`, `price`, `currency`, `section`, `description`

4. `zones_dim` (from catalog)
   - `zone_name`, `zone_category`, `zone_lat`, `zone_lng`, `zone_address`

5. `brands_dim`
   - `restaurant_brand`, standardized brand key

### Suggested quality checks inside pipeline

- Uniqueness:
  - no duplicate `(platform, run_id, zone_name, restaurant_brand)` in snapshots.
- Coverage:
  - expected rows = `22 zones x 2 brands = 44` (flag by platform).
- Value ranges:
  - price > 0 and < 2000 (warn if outside).
  - ETA minutes > 0 and < 180 (warn if outside).
- Null-rate report:
  - fee, eta, rating, store_name, products_total.
- Product match health:
  - count of snapshots with fully empty `products_matched`.

## Phase C — insight notebook

Create `notebooks/competitive_insights.ipynb`:

1. Load from DuckDB (not raw JSON directly).
2. Build 3 canonical cuts:
   - by platform + brand
   - by zone + platform
   - by product term + platform
3. Produce top 5 insights with direct query evidence.

## Phase D — analytics layer

After warehouse is ready:

- add a notebook or lightweight app that reads DuckDB/parquet
- start with filters (`platform`, `zone`, `brand`, `term`)
- build KPI cards + 2-3 core charts only after the warehouse contract is stable

---

## 7) Known caveats and communication guidance

- DiDi data is now scraped from public web pages, but:
  - current pipeline does not reliably obtain delivery fee/ETA/rating.
- Uber fee field also null in selected file; this is not necessarily "no fee", just extraction limitation.
- Rappi includes explicit failure rows (valuable for coverage transparency).

For any report/demo, clearly label:
- what is measured directly,
- what is unavailable/null due to source constraints.

---

## 8) Immediate next task (single best next step)

Implement and run `scripts/build_warehouse.py` so all analysis and dashboard work starts from one normalized source of truth.
