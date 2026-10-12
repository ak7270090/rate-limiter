import shlex
import subprocess

import aiohttp
import anyio
import pytest

from rateharness.client_factory import create_api_key
from rateharness.config import HarnessSettings
from rateharness.constants import STATUS_OK, STATUS_SERVICE_UNAVAILABLE
from rateharness.report_writer import HarnessReport, SuiteResult
from rateharness.traffic_patterns import ObservedResponse, RequestTarget, send_sequential

pytestmark = [pytest.mark.anyio, pytest.mark.failover]


def run_chaos_command(command: str, timeout_seconds: float) -> None:
    subprocess.run(shlex.split(command), check=True, timeout=timeout_seconds, capture_output=True)


def count_status(responses: list[ObservedResponse], status_code: int) -> int:
    return sum(1 for response in responses if response.status_code == status_code)


async def test_store_outage_follows_fail_open_and_fail_closed_policy(
    http_session: aiohttp.ClientSession,
    harness_settings: HarnessSettings,
    harness_report: HarnessReport,
    request: pytest.FixtureRequest,
) -> None:
    if not harness_settings.kill_command or not harness_settings.restore_command:
        pytest.skip("HARNESS_KILL_COMMAND and HARNESS_RESTORE_COMMAND are not set")
    fail_open = RequestTarget(harness_settings.fail_open_method, harness_settings.fail_open_route)
    fail_closed = RequestTarget(
        harness_settings.fail_closed_method, harness_settings.fail_closed_route
    )
    request_count = harness_settings.failover_request_count

    run_chaos_command(harness_settings.kill_command, harness_settings.command_timeout_seconds)
    try:
        await anyio.sleep(harness_settings.failover_settle_seconds)
        open_responses = await send_sequential(
            http_session, fail_open, create_api_key("failover"), request_count
        )
        closed_responses = await send_sequential(
            http_session, fail_closed, create_api_key("failover"), request_count
        )
    finally:
        run_chaos_command(
            harness_settings.restore_command, harness_settings.command_timeout_seconds
        )
        await anyio.sleep(harness_settings.restore_settle_seconds)
    recovered = await send_sequential(http_session, fail_closed, create_api_key("failover"), 1)
    slowest_seconds = max(r.elapsed_seconds for r in open_responses + closed_responses)

    harness_report.record(
        request.node.nodeid,
        SuiteResult(
            suite="failover",
            route=f"{fail_open.path} open, {fail_closed.path} closed",
            limit="-",
            admitted=f"{count_status(open_responses, STATUS_OK)} / {request_count}",
            detail=f"fail-closed 503s {count_status(closed_responses, STATUS_SERVICE_UNAVAILABLE)}"
            f" / {request_count}; slowest {slowest_seconds * 1000:.0f} ms; "
            f"after restore {recovered[0].status_code}",
        ),
    )
    assert count_status(open_responses, STATUS_OK) == request_count
    assert count_status(closed_responses, STATUS_SERVICE_UNAVAILABLE) == request_count
    assert slowest_seconds <= harness_settings.max_failover_latency_seconds
    assert recovered[0].status_code == STATUS_OK
