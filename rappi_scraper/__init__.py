"""Rappi competitive scraping package (production-style layout).

Modules:
    - ``client``: HTTP + guest auth + rate limit + retries
    - ``parser``: JSON-LD menu extraction
    - ``models``: ``Product``, ``StoreSnapshot``, ``ScrapeRun``
    - ``catalog``: embedded ``ZONES`` and ``RESTAURANTS``
    - ``orchestrator``: ``scrape_one``, ``run_pipeline``
"""

from rappi_scraper.catalog import RESTAURANTS, ZONES, Restaurant, Zone
from rappi_scraper.client import RappiClient, RappiClientError
from rappi_scraper.models import Product, ScrapeRun, StoreSnapshot
from rappi_scraper.orchestrator import run_pipeline, scrape_one

__all__ = [
    "RESTAURANTS",
    "ZONES",
    "Restaurant",
    "Zone",
    "RappiClient",
    "RappiClientError",
    "Product",
    "ScrapeRun",
    "StoreSnapshot",
    "run_pipeline",
    "scrape_one",
]
