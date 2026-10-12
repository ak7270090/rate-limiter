"""Collect one row per suite run and write them as a Markdown table into ``results/``."""

from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path

from rateharness.constants import OUTCOME_SKIPPED, REPORT_FILE_NAME


@dataclass(frozen=True)
class SuiteResult:
    """What one suite measured; ``outcome`` is filled in once pytest knows it."""

    suite: str
    route: str
    limit: str
    admitted: str
    detail: str
    outcome: str = OUTCOME_SKIPPED


class HarnessReport:
    """Rows recorded by tests during a run, keyed by pytest node ID."""

    def __init__(self) -> None:
        self._results: dict[str, SuiteResult] = {}

    def record(self, node_id: str, result: SuiteResult) -> None:
        self._results[node_id] = result

    def set_outcome(self, node_id: str, outcome: str) -> None:
        if node_id in self._results:
            self._results[node_id] = replace(self._results[node_id], outcome=outcome)

    @property
    def results(self) -> list[SuiteResult]:
        return list(self._results.values())

    def render_markdown(self, target_url: str) -> str:
        generated_at = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
        lines = [
            f"# Harness report: {target_url}",
            "",
            f"Generated {generated_at}.",
            "",
            "| Suite | Route | Limit | Admitted | Outcome | Detail |",
            "|---|---|---|---|---|---|",
        ]
        lines.extend(
            f"| {result.suite} | {result.route} | {result.limit} | {result.admitted} "
            f"| {result.outcome} | {result.detail} |"
            for result in self.results
        )
        return "\n".join(lines) + "\n"

    def write(self, results_dir: Path, target_url: str) -> Path:
        results_dir.mkdir(parents=True, exist_ok=True)
        report_path = results_dir / REPORT_FILE_NAME
        report_path.write_text(self.render_markdown(target_url), encoding="utf-8")
        return report_path
