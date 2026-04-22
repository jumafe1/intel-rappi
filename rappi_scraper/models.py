"""Output schemas for scraped data."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class Product:
    """A single menu item with its price."""

    section: str
    name: str
    description: str
    price: float
    currency: str = "MXN"


@dataclass
class StoreSnapshot:
    """One scrape of one restaurant in one zone."""

    platform: str  # "rappi"
    zone_name: str
    zone_category: str  # "premium" | "medium" | "peripheral"
    zone_lat: float
    zone_lng: float
    zone_address_input: str
    zone_address_resolved: str

    restaurant_brand: str
    brand_id: int
    store_id: int | None
    store_name: str | None
    store_address: str | None

    delivery_fee: float | None
    service_fee_pct: float | None
    eta_label: str | None
    eta_minutes: int | None
    is_open: bool | None
    rating: float | None
    discount_count: int

    products_total: int
    products_matched: dict[str, list[Product]]

    scraped_at: datetime
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["scraped_at"] = self.scraped_at.isoformat()
        # asdict already converts nested Product dicts
        return d


@dataclass
class ScrapeRun:
    """One full execution of the pipeline."""

    run_id: str
    started_at: datetime
    completed_at: datetime | None
    snapshots: list[StoreSnapshot] = field(default_factory=list)
    errors: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "started_at": self.started_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "total_snapshots": len(self.snapshots),
            "successful": sum(1 for s in self.snapshots if s.error is None),
            "failed": sum(1 for s in self.snapshots if s.error is not None),
            "snapshots": [s.to_dict() for s in self.snapshots],
            "errors": self.errors,
        }
