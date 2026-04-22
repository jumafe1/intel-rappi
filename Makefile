install:
	uv pip install -r requirements.txt -r requirements-dev.txt

notebook-kernel:
	python -m ipykernel install --user --name intel-rappi --display-name "Python (intel-rappi)"

scrape-rappi:
	python scripts/run_rappi_scraper.py

scrape-uber:
	python scripts/run_uber_scraper.py

scrape-didi:
	python scripts/run_didi_scraper.py

scrape-all:
	python scripts/run_scrapers.py

warehouse:
	python scripts/build_warehouse.py

pipeline:
	python scripts/run_pipeline.py

test:
	pytest

lint:
	ruff check .

format:
	ruff format .

clean:
	rm -rf __pycache__ */__pycache__ .pytest_cache .ruff_cache .DS_Store
