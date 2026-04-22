from pathlib import Path

import duckdb

from scripts.build_warehouse import build_warehouse


REPO_ROOT = Path(__file__).resolve().parent.parent


def test_build_warehouse_creates_expected_tables(tmp_path: Path) -> None:
    result = build_warehouse(
        raw_dir=REPO_ROOT / "data" / "raw",
        output_dir=tmp_path,
        zones_file=REPO_ROOT / "data" / "catalogs" / "zones_cdmx.json",
        products_file=REPO_ROOT / "data" / "catalogs" / "products_catalog.json",
        export_parquet=True,
    )

    assert result.db_path.exists()
    assert (tmp_path / "runs.parquet").exists()
    assert (tmp_path / "snapshots.parquet").exists()
    assert (tmp_path / "product_matches.parquet").exists()
    assert (tmp_path / "data_quality_checks.parquet").exists()

    con = duckdb.connect(str(result.db_path))
    try:
        assert con.execute("SELECT COUNT(*) FROM runs").fetchone()[0] == 3
        assert con.execute("SELECT COUNT(*) FROM snapshots").fetchone()[0] == 128
        assert con.execute("SELECT COUNT(*) FROM zones_dim").fetchone()[0] == 22
        assert con.execute("SELECT COUNT(*) FROM brands_dim").fetchone()[0] == 2
        assert con.execute("SELECT COUNT(*) FROM product_matches").fetchone()[0] > 0
        assert con.execute("SELECT COUNT(*) FROM data_quality_checks").fetchone()[0] > 0
        missing_uber_zones = con.execute(
            """
            SELECT observed_value
            FROM data_quality_checks
            WHERE platform = 'uber_eats' AND check_name = 'missing_zone_count'
            """
        ).fetchone()[0]
        assert missing_uber_zones == 2.0
    finally:
        con.close()
