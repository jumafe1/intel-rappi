# Intel-Rappi Competitive Scraping

This repo collects competitive food-delivery data for CDMX across:

- `rappi`
- `uber_eats`
- `didi_food`
- 22 CDMX zones
- 2 brands: McDonald's and Domino's Pizza

The repo is organized around one practical flow:

1. scrape raw data from the 3 platforms
2. build the DuckDB warehouse
3. analyze the warehouse in the Jupyter notebook

The competitive reports and analytical findings are delivered inside the repo in the notebook:

- [`notebooks/competitive_insights.ipynb`](notebooks/competitive_insights.ipynb)

## Setup

Create and activate the project environment:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
```

Alternative:

```bash
make install
```

## Run The Full Pipeline

If you want the complete project flow in one command, use:

```bash
make pipeline
```

That runs:

1. the 3 scrapers
2. the warehouse build

Equivalent command:

```bash
python scripts/run_pipeline.py
```

## Run Only The Scrapers

If you only want fresh raw outputs from the 3 platforms, use:

```bash
make scrape-all
```

Equivalent command:

```bash
python scripts/run_scrapers.py
```

## Run Only One Scraper

Use these if you want to collect data from just one platform:

```bash
make scrape-rappi
make scrape-uber
make scrape-didi
```

Equivalent direct commands:

```bash
python scripts/run_rappi_scraper.py
python scripts/run_uber_scraper.py
python scripts/run_didi_scraper.py
```

Quick limited runs:

```bash
python scripts/run_rappi_scraper.py --zones 1
python scripts/run_uber_scraper.py --max-zones 3
python scripts/run_didi_scraper.py --max-zones 3
```

## Build Only The Warehouse

If the raw JSON files already exist and you only want to rebuild the analytical layer:

```bash
make warehouse
```

Equivalent direct command:

```bash
python scripts/build_warehouse.py
```

If you want to use the pipeline entrypoint but skip scraping:

```bash
python scripts/run_pipeline.py --skip-scrape
```

## Open The Notebook

The analytical notebook lives in:

- [`notebooks/competitive_insights.ipynb`](notebooks/competitive_insights.ipynb)

This notebook is also where the competitive reports live: pricing, ETA, fees, promotions, availability, charts, and the actionable insights derived from the warehouse.

It reads from:

- `data/warehouse/intel_rappi.duckdb`

Recommended flow:

1. run `make pipeline` if you want the full refresh
2. open the notebook
3. select the project `.venv` as the kernel
4. restart the kernel
5. run all cells

Notebook runtime notes:

- if you see `ModuleNotFoundError: No module named 'duckdb'`, the notebook is using the wrong Python environment
- if Plotly shows `Mime type rendering requires nbformat>=4.2.0`, reinstall notebook deps and restart the kernel

If VS Code does not offer the project environment as a kernel, register it explicitly:

```bash
source .venv/bin/activate
make notebook-kernel
```

## Useful Commands

```bash
make install
make scrape-all
make warehouse
make pipeline
make test
make lint
```

## Ethics

Legal and operational guardrails are documented in:

- [`docs/ethics_and_legality.md`](docs/ethics_and_legality.md)
