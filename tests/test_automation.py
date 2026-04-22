import sys

from scripts.run_pipeline import run_pipeline
from scripts.run_scrapers import RAW_DIR, build_scraper_commands, run_scrapers


def test_build_scraper_commands_uses_expected_outputs() -> None:
    commands = build_scraper_commands("python-test")

    assert [command.platform for command in commands] == ["rappi", "uber_eats", "didi_food"]
    assert commands[0].command[-2:] == ["--output-dir", str(RAW_DIR)]
    assert commands[1].command[-2:] == ["--output", str(RAW_DIR / "uber_eats_latest.json")]
    assert commands[2].command[-2:] == ["--output", str(RAW_DIR / "didi_food_latest.json")]


def test_run_scrapers_stops_on_first_failure(monkeypatch) -> None:
    calls: list[list[str]] = []

    def fake_run(command: list[str], cwd, check: bool):
        calls.append(command)
        return type("Completed", (), {"returncode": 7 if "run_uber_scraper.py" in command[1] else 0})()

    monkeypatch.setattr("scripts.run_scrapers.subprocess.run", fake_run)

    exit_code = run_scrapers(fail_fast=True, python_executable="python-test")

    assert exit_code == 7
    assert len(calls) == 2


def test_run_pipeline_can_skip_scrape(monkeypatch) -> None:
    calls: list[list[str]] = []

    def fake_run(command: list[str], cwd, check: bool):
        calls.append(command)
        return type("Completed", (), {"returncode": 0})()

    monkeypatch.setattr("scripts.run_pipeline.subprocess.run", fake_run)

    exit_code = run_pipeline(skip_scrape=True, fail_fast=True)

    assert exit_code == 0
    assert calls == [[sys.executable, str((RAW_DIR.parent.parent / "scripts" / "build_warehouse.py"))]]
