# Data Dictionary

This document defines the practical raw-output contract currently used in
`data/raw/*.json`.

## Top-Level Entity: raw run file

- `run_id` (`str`): unique execution identifier.
- `started_at` (`datetime`): run start timestamp.
- `completed_at` (`datetime | None`): run completion timestamp.
- `total_snapshots` (`int`): number of snapshot rows emitted.
- `successful` (`int`): snapshot rows with no `error`.
- `failed` (`int`): snapshot rows with non-null `error`.
- `snapshots` (`list[Snapshot]`): collected observations.
- `errors` (`list[dict]`): structured execution errors.
- `collection_mode` (`str | None`): optional metadata on some runs.

## `Snapshot`

- `platform` (`"rappi" | "uber_eats" | "didi_food"`): source platform.
- `zone_name` (`str`): CDMX zone label.
- `zone_category` (`str`): zone segment such as `premium`, `medio`, or `periferico`.
- `zone_lat` (`float`): zone latitude.
- `zone_lng` (`float`): zone longitude.
- `zone_address_input` (`str`): configured address for the zone.
- `zone_address_resolved` (`str`): location actually resolved or reused by the scraper.
- `restaurant_brand` (`str`): canonical brand name.
- `brand_id` (`int | None`): platform-specific brand identifier when available.
- `store_id` (`str | int | None`): platform-specific store identifier.
- `store_name` (`str | None`): chosen store display name.
- `store_address` (`str | None`): chosen store address when available.
- `delivery_fee` (`float | None`): delivery fee extracted from the source.
- `service_fee_pct` (`float | None`): percentage service fee when available.
- `eta_label` (`str | None`): raw ETA label from source.
- `eta_minutes` (`int | None`): normalized minute estimate when available.
- `is_open` (`bool | None`): availability/open state when available.
- `rating` (`float | None`): store rating when available.
- `discount_count` (`int`): count of detected promo-like menu rows or tags.
- `products_total` (`int`): total extracted menu rows before term filtering.
- `products_matched` (`dict[str, list[ProductMatch]]`): matched products by tracked search term.
- `scraped_at` (`datetime`): snapshot timestamp.
- `error` (`str | None`): row-level failure or no-coverage information.
- `source` (`str | None`): optional source mode metadata.

## `ProductMatch`

- `section` (`str`): menu section name when available.
- `name` (`str`): product name as displayed by the platform.
- `description` (`str`): product description when available.
- `price` (`float`): listed price.
- `currency` (`str`): usually `MXN`.

## Notes

- The warehouse step should treat `products_matched` as the product-level fact source.
- Nulls in `delivery_fee`, `eta_minutes`, and `rating` can mean extraction limits,
  not necessarily absence on the platform.
- Rappi explicitly emits failed coverage rows and those should be preserved in downstream models.
