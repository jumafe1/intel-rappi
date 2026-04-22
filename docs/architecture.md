# Architecture

This repo now keeps only the active raw-collection path plus the docs needed
for the next warehouse step.

1. Each production script runs one platform-specific collection flow.
2. Each script writes a raw JSON artifact under `data/raw/`.
3. The next step is a warehouse builder that normalizes those artifacts into one
   analytical model.

```mermaid
flowchart LR
    A[scripts/run_rappi_scraper.py] --> B[rappi_scraper/]
    C[scripts/run_uber_scraper.py] --> D[scripts/lib/uber_mvp.py]
    E[scripts/run_didi_scraper.py] --> F[Public DiDi pages]
    B --> G[data/raw/*.json]
    D --> G
    F --> G
    G --> H[scripts/build_warehouse.py]
    H --> I[data/warehouse/*]
```

## Design Notes

- **Raw contract first**: the practical source of truth is the shape already
  emitted into `data/raw/*.json`.
- **Platform-specific collection**: each scraper keeps the logic closest to the
  source it actually talks to.
- **Warehouse next**: normalization and analytics should now be built from the
  real raw artifacts, not from removed scaffold code.
- **Operational safety**: rate limiting, retries, and explicit legal/ethical constraints are first-class.
