import json
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent


def test_competitive_insights_notebook_exists_and_has_expected_sections() -> None:
    notebook_path = REPO_ROOT / "notebooks" / "competitive_insights.ipynb"
    payload = json.loads(notebook_path.read_text(encoding="utf-8"))

    assert payload["nbformat"] == 4
    assert len(payload["cells"]) >= 10

    joined_sources = "\n".join(
        "".join(cell.get("source", []))
        for cell in payload["cells"]
    )
    assert "data/warehouse/intel_rappi.duckdb" in joined_sources
    assert "render_mermaid" in joined_sources
    assert "workflow_mermaid" in joined_sources
    assert "schema_mermaid" in joined_sources
    assert "metric_coverage" in joined_sources
    assert "platform_brand" in joined_sources
    assert "product_term" in joined_sources
    assert "eta_summary" in joined_sources
    assert "promo_intensity" in joined_sources
    assert "availability_summary" in joined_sources


def test_competitive_insights_notebook_code_cells_execute() -> None:
    notebook_path = REPO_ROOT / "notebooks" / "competitive_insights.ipynb"
    payload = json.loads(notebook_path.read_text(encoding="utf-8"))

    namespace = {"__name__": "__main__"}
    for idx, cell in enumerate(payload["cells"]):
        if cell.get("cell_type") != "code":
            continue
        source = "".join(cell.get("source", []))
        if not source.strip():
            continue
        exec(compile(source, f"{notebook_path.name}-cell-{idx}", "exec"), namespace)
