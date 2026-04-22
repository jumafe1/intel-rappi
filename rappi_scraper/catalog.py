"""Catalog of zones (CDMX) and restaurants to scrape."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Zone:
    name: str
    category: str  # "premium" | "medium" | "peripheral"
    address: str
    anchor_lat: float
    anchor_lng: float


@dataclass(frozen=True)
class Restaurant:
    canonical_name: str
    search_keyword: str  # what to send to Rappi
    brand_id: int
    url_slug: str  # used in /restaurantes/{store_id}-{slug}
    products_to_match: list[str]


# CDMX zones - 22 zones across premium / medium / peripheral
ZONES: list[Zone] = [
    # Premium (7)
    Zone("Polanco", "premium", "Av. Presidente Masaryk 200, Polanco", 19.4326, -99.1956),
    Zone(
        "Lomas de Chapultepec",
        "premium",
        "Paseo de la Reforma 2620, Lomas de Chapultepec",
        19.4231,
        -99.2118,
    ),
    Zone("Roma Norte", "premium", "Álvaro Obregón 100, Roma Norte", 19.4194, -99.1631),
    Zone("Condesa", "premium", "Av. Tamaulipas 95, Condesa", 19.4131, -99.1718),
    Zone("Santa Fe", "premium", "Av. Vasco de Quiroga 3800, Santa Fe", 19.3601, -99.2596),
    Zone("Del Valle", "premium", "Av. Insurgentes Sur 1457, Del Valle", 19.3878, -99.1751),
    Zone("Coyoacán Centro", "premium", "Centenario 1, Villa Coyoacán", 19.3494, -99.1620),
    # Medium (8)
    Zone("Narvarte", "medium", "Av. Cuauhtémoc 1236, Narvarte", 19.3918, -99.1547),
    Zone("Escandón", "medium", "Av. Patriotismo 350, Escandón", 19.4063, -99.1839),
    Zone("Anzures", "medium", "Bahía de Santa Bárbara 145, Anzures", 19.4309, -99.1768),
    Zone("Portales", "medium", "Av. Universidad 1149, Portales", 19.3699, -99.1577),
    Zone("Doctores", "medium", "Dr. Vértiz 200, Doctores", 19.4197, -99.1485),
    Zone("San Rafael", "medium", "Sadi Carnot 60, San Rafael", 19.4373, -99.1576),
    Zone("Tacubaya", "medium", "Av. Jalisco 33, Tacubaya", 19.4032, -99.1875),
    Zone("Mixcoac", "medium", "Av. Insurgentes Sur 1602, Mixcoac", 19.3771, -99.1805),
    # Peripheral (7)
    Zone(
        "Iztapalapa Centro",
        "peripheral",
        "Av. Ermita Iztapalapa 100, Iztapalapa",
        19.3574,
        -99.0668,
    ),
    Zone("Tláhuac", "peripheral", "Av. Tláhuac 5800, Tláhuac", 19.2868, -99.0001),
    Zone("Xochimilco", "peripheral", "Av. Guadalupe I. Ramírez 4, Xochimilco", 19.2604, -99.1031),
    Zone("Tlalpan", "peripheral", "Calz. de Tlalpan 4395, Tlalpan", 19.2933, -99.1671),
    Zone("Cuautepec", "peripheral", "Av. Cuautepec 100, Gustavo A. Madero", 19.5491, -99.1377),
    Zone("Azcapotzalco", "peripheral", "Av. Azcapotzalco 605, Azcapotzalco", 19.4843, -99.1842),
    Zone("Milpa Alta", "peripheral", "Av. México 100, Milpa Alta", 19.1922, -99.0231),
]


RESTAURANTS: list[Restaurant] = [
    Restaurant(
        canonical_name="McDonald's",
        search_keyword="McDonald's",
        brand_id=706,
        url_slug="mcdonalds",
        products_to_match=["Big Mac", "McNuggets", "Cuarto de Libra"],
    ),
    Restaurant(
        canonical_name="Domino's Pizza",
        search_keyword="Domino's",
        brand_id=19713,
        url_slug="dominos-pizza",  # may need adjustment after first run
        products_to_match=["Mediana", "Grande", "Combo"],
    ),
]
