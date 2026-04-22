# Lessons

## 2026-04-22

- When debugging notebook `ModuleNotFoundError` issues, verify the active Jupyter kernel first; do not assume the open VS Code notebook is using the repo `.venv` just because the terminal is activated.
- Do not confuse the DuckDB CLI install with the Python `duckdb` package; the notebook needs the Python package available in the selected kernel.
- When the user trims notebook sections for noise reduction, re-scope to the explicit analytical deliverable instead of reintroducing broad exploratory content.
- When notebook charts fail with MIME-rendering errors, check notebook-rendering dependencies like `nbformat`; `plotly` plus `ipykernel` is not sufficient by itself.
