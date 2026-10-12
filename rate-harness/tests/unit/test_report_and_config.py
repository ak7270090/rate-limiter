from pathlib import Path

import pytest

from rateharness.config import load_harness_settings
from rateharness.report_writer import HarnessReport, SuiteResult


def test_report_writes_markdown_with_outcomes(tmp_path: Path) -> None:
    report = HarnessReport()
    report.record("t::a", SuiteResult("accuracy", "GET /items", "100 / 10 s", "100", "ok"))
    report.set_outcome("t::a", "PASS")
    report.set_outcome("t::unknown", "FAIL")

    report_path = report.write(tmp_path / "results", "http://localhost:8080")

    text = report_path.read_text(encoding="utf-8")
    assert "| accuracy | GET /items | 100 / 10 s | 100 | PASS | ok |" in text
    assert len(report.results) == 1


def test_settings_load_from_env_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    env_file = tmp_path / "phase.env"
    env_file.write_text(
        'HARNESS_TARGET_URL=http://localhost:9999\nHARNESS_EXPECTED_FAILURES=["global_limit"]\n',
        encoding="utf-8",
    )
    monkeypatch.setenv("HARNESS_ENV_FILE", str(env_file))

    settings = load_harness_settings()

    assert settings.target_url == "http://localhost:9999"
    assert settings.expected_failures == {"global_limit"}


def test_settings_default_without_env_file(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("HARNESS_ENV_FILE", raising=False)

    assert load_harness_settings().per_key_limit == 100
