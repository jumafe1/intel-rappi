#!/usr/bin/env python3
"""Build a DuckDB warehouse from the latest raw scrape artifacts."""

from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import duckdb
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parent.parent
PLATFORMS = ("rappi", "uber_eats", "didi_food")
REQUIRED_TOP_LEVEL_FIELDS = {
    "run_id",
    "started_at",
    "completed_at",
    "total_snapshots",
    "successful",
    "failed",
    "snapshots",
    "errors",
}
REQUIRED_SNAPSHOT_FIELDS = {
    "platform",
    "zone_name",
    "zone_category",
    "zone_lat",
    "zone_lng",
    "zone_address_input",
    "zone_address_resolved",
    "restaurant_brand",
    "brand_id",
    "store_id",
    "store_name",
    "store_address",
    "delivery_fee",
    "service_fee_pct",
    "eta_label",
    "eta_minutes",
    "is_open",
    "rating",
    "discount_count",
    "products_total",
    "products_matched",
    "scraped_at",
    "error",
}


@dataclass(frozen=True)
class BuildResult:
    db_path: Path
    parquet_dir: Path
    selected_files: dict[str, Path]
    table_counts: dict[str, int]


def normalize_zone_category(raw_value: str | None) -> str | None:
    if raw_value is None:
        return None
    mapping = {
        "premium": "premium",
        "medio": "medium",
        "medium": "medium",
        "periferico": "peripheral",
        "peripheral": "peripheral",
    }
    return mapping.get(str(raw_value).strip().lower(), str(raw_value).strip().lower())


def to_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def to_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def to_str(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)


def snapshot_id(run_id: str, platform: str, zone_name: str, restaurant_brand: str) -> str:
    raw = f"{run_id}|{platform}|{zone_name}|{restaurant_brand}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:20]


def discover_latest_raw_files(raw_dir: Path) -> dict[str, Path]:
    selected: dict[str, Path] = {}
    for platform in PLATFORMS:
        matches = sorted(
            raw_dir.glob(f"{platform}_*.json"),
            key=lambda path: (path.stat().st_mtime, path.name),
        )
        if not matches:
            raise FileNotFoundError(f"No raw file found for platform={platform!r} in {raw_dir}")
        selected[platform] = matches[-1]
    return selected


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def validate_payload(payload: dict[str, Any], raw_path: Path, platform: str) -> None:
    missing_top = REQUIRED_TOP_LEVEL_FIELDS - set(payload)
    if missing_top:
        missing = ", ".join(sorted(missing_top))
        raise ValueError(f"{raw_path.name}: missing top-level fields for {platform}: {missing}")

    snapshots = payload.get("snapshots")
    if not isinstance(snapshots, list):
        raise ValueError(f"{raw_path.name}: snapshots must be a list")

    for index, snapshot in enumerate(snapshots):
        if not isinstance(snapshot, dict):
            raise ValueError(f"{raw_path.name}: snapshot at index {index} is not an object")
        missing_snapshot = REQUIRED_SNAPSHOT_FIELDS - set(snapshot)
        if missing_snapshot:
            missing = ", ".join(sorted(missing_snapshot))
            raise ValueError(f"{raw_path.name}: snapshot[{index}] missing fields: {missing}")
        if snapshot.get("platform") != platform:
            raise ValueError(
                f"{raw_path.name}: snapshot[{index}] has platform={snapshot.get('platform')!r}, "
                f"expected {platform!r}"
            )


def build_brand_mappings(products_catalog: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, str]]:
    brand_rows: list[dict[str, Any]] = []
    canonical_to_key: dict[str, str] = {}
    for brand_key, brand_data in products_catalog.items():
        canonical_name = str(brand_data["brand_canonical"])
        canonical_to_key[canonical_name] = brand_key
        tracked_products = brand_data.get("products", [])
        search_terms_total = sum(len(product.get("search_terms", [])) for product in tracked_products)
        brand_rows.append(
            {
                "brand_key": brand_key,
                "restaurant_brand": canonical_name,
                "platform_id_rappi": to_str(brand_data.get("platform_ids", {}).get("rappi")),
                "platform_id_uber_eats": to_str(brand_data.get("platform_ids", {}).get("uber_eats")),
                "platform_id_didi_food": to_str(brand_data.get("platform_ids", {}).get("didi_food")),
                "tracked_products_count": len(tracked_products),
                "tracked_search_terms_count": search_terms_total,
            }
        )
    return brand_rows, canonical_to_key


def build_zone_rows(zones_catalog: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for zone in zones_catalog:
        rows.append(
            {
                "zone_name": str(zone["name"]),
                "zone_category": normalize_zone_category(zone.get("category")),
                "zone_category_raw": to_str(zone.get("category")),
                "zone_lat": to_float(zone.get("lat")),
                "zone_lng": to_float(zone.get("lon")),
                "zone_address": to_str(zone.get("address")),
            }
        )
    return rows


def build_rows(
    selected_files: dict[str, Path],
    brand_key_by_name: dict[str, str],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    run_rows: list[dict[str, Any]] = []
    snapshot_rows: list[dict[str, Any]] = []
    product_rows: list[dict[str, Any]] = []

    for platform, raw_path in selected_files.items():
        payload = load_json(raw_path)
        validate_payload(payload, raw_path, platform)

        run_rows.append(
            {
                "platform": platform,
                "run_id": to_str(payload["run_id"]),
                "started_at": to_str(payload["started_at"]),
                "completed_at": to_str(payload["completed_at"]),
                "total_snapshots": to_int(payload["total_snapshots"]),
                "successful": to_int(payload["successful"]),
                "failed": to_int(payload["failed"]),
                "raw_file": raw_path.name,
            }
        )

        for snapshot in payload["snapshots"]:
            run_id = str(payload["run_id"])
            zone_name = str(snapshot["zone_name"])
            restaurant_brand = str(snapshot["restaurant_brand"])
            products_matched = snapshot.get("products_matched") or {}
            snap_id = snapshot_id(run_id, platform, zone_name, restaurant_brand)
            matched_items_total = sum(len(rows or []) for rows in products_matched.values())

            snapshot_rows.append(
                {
                    "snapshot_id": snap_id,
                    "run_id": run_id,
                    "platform": platform,
                    "brand_key": brand_key_by_name.get(restaurant_brand),
                    "restaurant_brand": restaurant_brand,
                    "zone_name": zone_name,
                    "zone_category": normalize_zone_category(snapshot.get("zone_category")),
                    "zone_category_raw": to_str(snapshot.get("zone_category")),
                    "zone_lat": to_float(snapshot.get("zone_lat")),
                    "zone_lng": to_float(snapshot.get("zone_lng")),
                    "zone_address_input": to_str(snapshot.get("zone_address_input")),
                    "zone_address_resolved": to_str(snapshot.get("zone_address_resolved")),
                    "brand_id": to_int(snapshot.get("brand_id")),
                    "store_id": to_str(snapshot.get("store_id")),
                    "store_name": to_str(snapshot.get("store_name")),
                    "store_address": to_str(snapshot.get("store_address")),
                    "delivery_fee": to_float(snapshot.get("delivery_fee")),
                    "service_fee_pct": to_float(snapshot.get("service_fee_pct")),
                    "eta_label": to_str(snapshot.get("eta_label")),
                    "eta_minutes": to_int(snapshot.get("eta_minutes")),
                    "is_open": snapshot.get("is_open"),
                    "rating": to_float(snapshot.get("rating")),
                    "discount_count": to_int(snapshot.get("discount_count")) or 0,
                    "products_total": to_int(snapshot.get("products_total")) or 0,
                    "matched_terms_total": len(products_matched),
                    "matched_items_total": matched_items_total,
                    "scraped_at": to_str(snapshot.get("scraped_at")),
                    "error": to_str(snapshot.get("error")),
                    "source": to_str(snapshot.get("source")),
                    "is_successful": snapshot.get("error") is None,
                    "has_product_price": matched_items_total > 0,
                    "has_delivery_fee": snapshot.get("delivery_fee") is not None,
                    "has_service_fee": snapshot.get("service_fee_pct") is not None,
                    "has_eta": snapshot.get("eta_minutes") is not None or snapshot.get("eta_label") is not None,
                    "has_discount_signal": snapshot.get("discount_count") is not None,
                    "has_availability": snapshot.get("is_open") is not None,
                    "has_final_total": False,
                }
            )

            for search_term, matches in products_matched.items():
                for match_rank, item in enumerate(matches or [], start=1):
                    product_rows.append(
                        {
                            "snapshot_id": snap_id,
                            "run_id": run_id,
                            "platform": platform,
                            "brand_key": brand_key_by_name.get(restaurant_brand),
                            "restaurant_brand": restaurant_brand,
                            "zone_name": zone_name,
                            "search_term": to_str(search_term),
                            "match_rank": match_rank,
                            "product_name": to_str(item.get("name")),
                            "description": to_str(item.get("description")),
                            "section": to_str(item.get("section")) or "",
                            "price": to_float(item.get("price")),
                            "currency": to_str(item.get("currency")) or "MXN",
                        }
                    )

    return run_rows, snapshot_rows, product_rows


def build_quality_checks(
    runs_df: pd.DataFrame,
    snapshots_df: pd.DataFrame,
    product_matches_df: pd.DataFrame,
    zones_df: pd.DataFrame,
    brands_df: pd.DataFrame,
) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []
    expected_snapshots = len(zones_df) * len(brands_df)
    all_zone_names = set(zones_df["zone_name"].tolist())

    metric_fields = {
        "product_price": "has_product_price",
        "delivery_fee": "has_delivery_fee",
        "service_fee": "has_service_fee",
        "eta": "has_eta",
        "discounts": "has_discount_signal",
        "availability": "has_availability",
        "final_total": "has_final_total",
    }

    def add_check(
        *,
        platform: str,
        run_id: str,
        check_name: str,
        severity: str,
        status: str,
        observed_value: float,
        expected_value: float,
        details: str = "",
    ) -> None:
        checks.append(
            {
                "platform": platform,
                "run_id": run_id,
                "check_name": check_name,
                "severity": severity,
                "status": status,
                "observed_value": observed_value,
                "expected_value": expected_value,
                "details": details,
            }
        )

    for run in runs_df.itertuples(index=False):
        platform_snapshots = snapshots_df[snapshots_df["platform"] == run.platform].copy()
        platform_products = product_matches_df[product_matches_df["platform"] == run.platform].copy()
        observed_total = float(len(platform_snapshots))
        unique_snapshot_keys = float(platform_snapshots["snapshot_id"].nunique())
        missing_zones = sorted(all_zone_names - set(platform_snapshots["zone_name"].tolist()))
        empty_match_snapshots = float((platform_snapshots["matched_items_total"] == 0).sum())
        price_outliers = float(
            ((platform_products["price"] <= 0) | (platform_products["price"] >= 2000)).sum()
        ) if not platform_products.empty else 0.0
        eta_values = platform_snapshots["eta_minutes"].dropna()
        eta_outliers = float(((eta_values <= 0) | (eta_values >= 180)).sum()) if not eta_values.empty else 0.0

        add_check(
            platform=run.platform,
            run_id=run.run_id,
            check_name="coverage_expected_snapshots",
            severity="warn",
            status="pass" if observed_total == float(expected_snapshots) else "warn",
            observed_value=observed_total,
            expected_value=float(expected_snapshots),
            details="expected 22 zones x 2 brands",
        )
        add_check(
            platform=run.platform,
            run_id=run.run_id,
            check_name="successful_failed_matches_total",
            severity="fail",
            status="pass" if (run.successful + run.failed) == run.total_snapshots else "fail",
            observed_value=float(run.successful + run.failed),
            expected_value=float(run.total_snapshots),
        )
        add_check(
            platform=run.platform,
            run_id=run.run_id,
            check_name="duplicate_snapshot_keys",
            severity="fail",
            status="pass" if unique_snapshot_keys == observed_total else "fail",
            observed_value=observed_total - unique_snapshot_keys,
            expected_value=0.0,
        )
        add_check(
            platform=run.platform,
            run_id=run.run_id,
            check_name="missing_zone_count",
            severity="warn",
            status="pass" if not missing_zones else "warn",
            observed_value=float(len(missing_zones)),
            expected_value=0.0,
            details=", ".join(missing_zones),
        )
        add_check(
            platform=run.platform,
            run_id=run.run_id,
            check_name="empty_product_match_snapshots",
            severity="warn",
            status="pass" if empty_match_snapshots == 0 else "warn",
            observed_value=empty_match_snapshots,
            expected_value=0.0,
        )
        add_check(
            platform=run.platform,
            run_id=run.run_id,
            check_name="product_price_out_of_range",
            severity="fail",
            status="pass" if price_outliers == 0 else "fail",
            observed_value=price_outliers,
            expected_value=0.0,
        )
        add_check(
            platform=run.platform,
            run_id=run.run_id,
            check_name="eta_out_of_range",
            severity="fail",
            status="pass" if eta_outliers == 0 else "fail",
            observed_value=eta_outliers,
            expected_value=0.0,
        )

        for field_name in ("store_name", "delivery_fee", "service_fee_pct", "eta_minutes", "rating"):
            null_rate = float(platform_snapshots[field_name].isna().mean())
            add_check(
                platform=run.platform,
                run_id=run.run_id,
                check_name=f"null_rate_{field_name}",
                severity="warn",
                status="pass" if null_rate == 0.0 else "warn",
                observed_value=null_rate,
                expected_value=0.0,
            )

        for metric_name, column_name in metric_fields.items():
            metric_count = float(platform_snapshots[column_name].sum())
            add_check(
                platform=run.platform,
                run_id=run.run_id,
                check_name=f"metric_presence_{metric_name}",
                severity="warn",
                status="pass" if metric_count == observed_total else "warn",
                observed_value=metric_count,
                expected_value=observed_total,
            )

    return checks


def to_frame(rows: list[dict[str, Any]], columns: list[str]) -> pd.DataFrame:
    if rows:
        return pd.DataFrame(rows)
    return pd.DataFrame(columns=columns)


def build_warehouse(
    *,
    raw_dir: Path,
    output_dir: Path,
    zones_file: Path,
    products_file: Path,
    export_parquet: bool = True,
) -> BuildResult:
    selected_files = discover_latest_raw_files(raw_dir)
    zones_catalog = load_json(zones_file)
    products_catalog = load_json(products_file)
    brands_rows, brand_key_by_name = build_brand_mappings(products_catalog)
    zones_rows = build_zone_rows(zones_catalog)
    run_rows, snapshot_rows, product_rows = build_rows(selected_files, brand_key_by_name)

    runs_df = to_frame(
        run_rows,
        ["platform", "run_id", "started_at", "completed_at", "total_snapshots", "successful", "failed", "raw_file"],
    )
    snapshots_df = to_frame(snapshot_rows, [])
    product_matches_df = to_frame(product_rows, [])
    zones_df = to_frame(zones_rows, [])
    brands_df = to_frame(brands_rows, [])

    for frame, columns in (
        (runs_df, ["started_at", "completed_at"]),
        (snapshots_df, ["scraped_at"]),
    ):
        for column in columns:
            frame[column] = pd.to_datetime(frame[column], errors="coerce")

    quality_checks_df = to_frame(
        build_quality_checks(runs_df, snapshots_df, product_matches_df, zones_df, brands_df),
        [],
    )

    output_dir.mkdir(parents=True, exist_ok=True)
    db_path = output_dir / "intel_rappi.duckdb"
    con = duckdb.connect(str(db_path))
    try:
        con.register("runs_df", runs_df)
        con.register("snapshots_df", snapshots_df)
        con.register("product_matches_df", product_matches_df)
        con.register("zones_df", zones_df)
        con.register("brands_df", brands_df)
        con.register("quality_checks_df", quality_checks_df)

        con.execute("CREATE OR REPLACE TABLE runs AS SELECT * FROM runs_df")
        con.execute("CREATE OR REPLACE TABLE snapshots AS SELECT * FROM snapshots_df")
        con.execute("CREATE OR REPLACE TABLE product_matches AS SELECT * FROM product_matches_df")
        con.execute("CREATE OR REPLACE TABLE zones_dim AS SELECT * FROM zones_df")
        con.execute("CREATE OR REPLACE TABLE brands_dim AS SELECT * FROM brands_df")
        con.execute("CREATE OR REPLACE TABLE data_quality_checks AS SELECT * FROM quality_checks_df")

        if export_parquet:
            for table_name in (
                "runs",
                "snapshots",
                "product_matches",
                "zones_dim",
                "brands_dim",
                "data_quality_checks",
            ):
                parquet_path = output_dir / f"{table_name}.parquet"
                con.execute(
                    f"COPY {table_name} TO '{parquet_path.as_posix()}' "
                    "(FORMAT PARQUET, COMPRESSION ZSTD, OVERWRITE_OR_IGNORE 1)"
                )

        table_counts = {
            table_name: con.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()[0]
            for table_name in (
                "runs",
                "snapshots",
                "product_matches",
                "zones_dim",
                "brands_dim",
                "data_quality_checks",
            )
        }
    finally:
        con.close()

    return BuildResult(
        db_path=db_path,
        parquet_dir=output_dir,
        selected_files=selected_files,
        table_counts=table_counts,
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build DuckDB warehouse from latest raw scrape artifacts")
    parser.add_argument(
        "--raw-dir",
        type=Path,
        default=REPO_ROOT / "data" / "raw",
        help="Directory containing raw platform JSON files",
    )
    parser.add_argument(
        "--zones-file",
        type=Path,
        default=REPO_ROOT / "data" / "catalogs" / "zones_cdmx.json",
        help="Zones catalog JSON",
    )
    parser.add_argument(
        "--products-file",
        type=Path,
        default=REPO_ROOT / "data" / "catalogs" / "products_catalog.json",
        help="Products catalog JSON",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=REPO_ROOT / "data" / "warehouse",
        help="Warehouse output directory",
    )
    parser.add_argument(
        "--export-parquet",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Export parquet copies for downstream analysis",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    result = build_warehouse(
        raw_dir=args.raw_dir,
        output_dir=args.output_dir,
        zones_file=args.zones_file,
        products_file=args.products_file,
        export_parquet=args.export_parquet,
    )

    print(f"Warehouse written to: {result.db_path}")
    print("Selected raw files:")
    for platform, path in result.selected_files.items():
        print(f"  - {platform}: {path}")
    print("Table counts:")
    for table_name, count in result.table_counts.items():
        print(f"  - {table_name}: {count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
