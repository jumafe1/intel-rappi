# DiDi Food Methodology

## Current Strategy

DiDi Food is currently collected from public `web.didiglobal.com` pages using
`scripts/run_didi_scraper.py`.

The scraper does not use login flows or app instrumentation. It works by:

1. Crawling public city listing pages for the selected brand categories.
2. Filtering store URLs by brand-specific slug hints.
3. Deterministically assigning one discovered store link per zone.
4. Fetching public store pages and parsing visible menu rows.
5. Building the same raw snapshot shape used by the other platform outputs.

## Important Limitation

DiDi does not expose zone-targeted location behavior on the public web in the
same way Rappi and Uber do.

Because of that:

- output rows still represent the 22 CDMX zones
- but store selection is based on city listing discovery, not exact zone-level
  delivery simulation

This is good enough for a comparable menu-and-store benchmark, but it is not the
same location fidelity as the other two sources.

## Fields That Are Reliable Today

- store discovery from public listing pages
- store title
- store address when present in page metadata
- menu rows and matched product terms

## Fields Not Reliably Available Today

- `delivery_fee`
- `eta_minutes`
- `rating`

Null values for those fields in DiDi runs should be treated as source/extraction
limitations, not proof that the platform has no such values.

## Why The Old Reference Approach Was Removed

This repo previously contained a synthetic/reference DiDi path. That path was
removed during cleanup so the repository has only one active DiDi collection
mode: the public-web scraper.

## If More Fidelity Is Needed Later

Getting zone-accurate fee, ETA, and checkout pricing parity may require a much
heavier app-analysis workflow. That should be treated as a separate project with
its own legal and security review.
