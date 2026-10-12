from collections.abc import AsyncIterator, Generator

import pytest

from rateharness.client_factory import create_http_session, open_connections
from rateharness.config import HarnessSettings, load_harness_settings
from rateharness.constants import (
    ALL_SUITES,
    OUTCOME_FAIL,
    OUTCOME_PASS,
    OUTCOME_XFAIL,
    OUTCOME_XPASS,
)
from rateharness.report_writer import HarnessReport

HARNESS_REPORT = HarnessReport()


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture(scope="session")
def harness_settings() -> HarnessSettings:
    return load_harness_settings()


@pytest.fixture(scope="session")
def harness_report() -> HarnessReport:
    return HARNESS_REPORT


@pytest.fixture
async def http_session(harness_settings: HarnessSettings) -> AsyncIterator:
    async with create_http_session(harness_settings) as session:
        await open_connections(
            session, harness_settings.connection_pool_size, harness_settings.baseline_route
        )
        yield session


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """Apply the phase's expectations: skip suites that don't apply, mark expected failures."""
    settings = load_harness_settings()
    for item in items:
        item_suites = {marker.name for marker in item.iter_markers()} & ALL_SUITES
        if item_suites & settings.skipped_suites:
            item.add_marker(pytest.mark.skip(reason="suite does not apply to this phase"))
        elif item_suites & settings.expected_failures:
            item.add_marker(
                pytest.mark.xfail(strict=True, reason="expected to fail for this phase")
            )


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item: pytest.Item, call: pytest.CallInfo) -> Generator:
    outcome = yield
    report = outcome.get_result()
    if report.when != "call":
        return
    was_expected_to_fail = hasattr(report, "wasxfail")
    if was_expected_to_fail:
        result = OUTCOME_XPASS if report.passed else OUTCOME_XFAIL
    else:
        result = OUTCOME_PASS if report.passed else OUTCOME_FAIL
    HARNESS_REPORT.set_outcome(item.nodeid, result)


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    if HARNESS_REPORT.results:
        settings = load_harness_settings()
        HARNESS_REPORT.write(settings.results_dir, settings.target_url)
