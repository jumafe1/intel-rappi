# Competitive Analysis Notebook Plan

## Scope

- [x] Confirm the current notebook state and warehouse coverage before editing
- [x] Keep the notebook focused on the sections the user actually wants
- [x] Add a short coverage/scope section so metric gaps by platform are explicit
- [x] Implement structured comparative analysis for:
  - [x] price positioning
  - [x] operational ETA comparison
  - [x] fee structure comparison
  - [x] promotional strategy comparison
  - [x] geographic variability
- [x] Add supporting visualizations for the comparative analysis
- [x] Keep Rappi vs Uber, Rappi vs DiDi, and 3-platform comparisons explicit where the data allows it
- [x] Document analytical caveats where DiDi or Uber have missing metrics
- [x] Verify notebook execution end to end
- [x] Run repo verification after notebook changes

## Detailed Spec

- The notebook should not reintroduce noisy exploratory sections that are not needed for the current deliverable.
- The analysis should read from `data/warehouse/intel_rappi.duckdb` and only pull from raw artifacts if a comparison cannot be supported from the warehouse alone.
- Price positioning should use comparable observations by brand, zone, and normalized tracked product term.
- ETA analysis should compare Rappi vs Uber Eats directly and state that DiDi currently lacks ETA coverage in the warehouse.
- Fee analysis should compare both observed values and metric availability, because delivery-fee and service-fee coverage is not symmetric across platforms.
- Promotion analysis should separate promo intensity (`discount_count`) from promo-type inference derived from tracked matched-product text.
- Geographic variability should show where Rappi is more or less competitive by zone, not just a citywide average.

## Delivery Plan

- Phase 1: replace the old notebook focus with a compact comparative-analysis block
- Phase 2: add the required charts and short narrative interpretation below each section
- Phase 3: verify notebook execution, lint, and tests

## Review

- Kept the notebook narrow instead of reintroducing broad exploratory sections the user had already removed
- Removed the stale table-by-table dictionary section that no longer had backing variables
- Added a compact metric-coverage section to define which platform comparisons are valid
- Added structured comparative analysis for pricing, ETA, fees, promotions, and zone variability
- Added supporting charts and narrative callouts for each comparison block
- Strengthened the notebook with executive-style `Finding / Impacto / Recomendación` insight blocks backed by warehouse numbers, including the exact Rappi no-coverage cases and anchor-item price examples
- Moved the metric-coverage strategic insight into the operational section so it reads as an actionable advantage rather than a disconnected note
- Preserved `product_term`, `platform_brand`, and `zone_platform` analytical tables inside the notebook for direct inspection
- Updated notebook smoke tests to align with the current notebook scope
- Verification completed:
  - notebook code-cell smoke execution against DuckDB
  - `ruff check .`
  - `pytest`
