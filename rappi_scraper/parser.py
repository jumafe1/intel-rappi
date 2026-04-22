"""Parses store HTML to extract menu items with prices from JSON-LD."""

from __future__ import annotations

import json
import logging
from collections.abc import Iterator
from typing import Any

from bs4 import BeautifulSoup

from rappi_scraper.models import Product

log = logging.getLogger(__name__)


def _flatten(x: Any) -> Iterator[Any]:
    """Flatten arbitrarily nested lists. JSON-LD sometimes wraps things in extra arrays."""
    if isinstance(x, list):
        for item in x:
            yield from _flatten(item)
    else:
        yield x


def parse_menu_from_html(html: str) -> list[Product]:
    """Extract all menu items with prices from the JSON-LD <script> tag."""
    soup = BeautifulSoup(html, "html.parser")
    schema_tag = soup.find("script", id="seo-structured-schema")

    if not schema_tag or not schema_tag.string:
        log.warning("JSON-LD script tag not found in HTML")
        return []

    try:
        data = json.loads(schema_tag.string)
    except json.JSONDecodeError as e:
        log.error("Failed to parse JSON-LD: %s", e)
        return []

    products: list[Product] = []
    sections = data.get("hasMenu", {}).get("hasMenuSection", [])

    for section in _flatten(sections):
        if not isinstance(section, dict):
            continue
        section_name = str(section.get("name", ""))
        for item in _flatten(section.get("hasMenuItem", [])):
            if not isinstance(item, dict):
                continue
            offers = item.get("offers", {})
            if isinstance(offers, list):
                offers = offers[0] if offers else {}
            if not isinstance(offers, dict):
                continue
            price = offers.get("price")
            if price is None:
                continue
            products.append(
                Product(
                    section=section_name,
                    name=str(item.get("name", "")),
                    description=str(item.get("description", "")),
                    price=float(price),
                    currency=str(offers.get("priceCurrency", "MXN")),
                )
            )

    return products


def find_matching_products(
    menu: list[Product],
    search_terms: list[str],
    max_per_term: int = 5,
) -> dict[str, list[Product]]:
    """For each search term, find menu items whose name contains it (case-insensitive)."""
    matches: dict[str, list[Product]] = {term: [] for term in search_terms}
    for product in menu:
        name_lower = product.name.lower()
        for term in search_terms:
            if term.lower() in name_lower and len(matches[term]) < max_per_term:
                matches[term].append(product)
    return matches
