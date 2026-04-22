from rappi_scraper.catalog import RESTAURANTS, ZONES


def test_catalog_scope_is_stable() -> None:
    assert len(ZONES) == 22
    assert len(RESTAURANTS) == 2
    assert {restaurant.canonical_name for restaurant in RESTAURANTS} == {
        "McDonald's",
        "Domino's Pizza",
    }
