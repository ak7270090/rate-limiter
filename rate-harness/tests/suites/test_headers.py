import aiohttp
import pytest

from rateharness.client_factory import create_api_key
from rateharness.config import HarnessSettings
from rateharness.constants import STATUS_TOO_MANY_REQUESTS
from rateharness.header_checks import ExpectedHeaderPolicy, find_header_problems
from rateharness.report_writer import HarnessReport, SuiteResult
from rateharness.traffic_patterns import RequestTarget, send_sequential, wait_for_room_in_window

pytestmark = [pytest.mark.anyio, pytest.mark.headers]


async def test_rate_limit_headers_are_present_and_consistent(
    http_session: aiohttp.ClientSession,
    harness_settings: HarnessSettings,
    harness_report: HarnessReport,
    request: pytest.FixtureRequest,
) -> None:
    target = RequestTarget(harness_settings.per_key_method, harness_settings.per_key_route)
    expected = ExpectedHeaderPolicy(
        policy_name=harness_settings.per_key_policy_name,
        quota=harness_settings.per_key_limit,
        window_seconds=int(harness_settings.per_key_window_seconds),
    )
    await wait_for_room_in_window(harness_settings.per_key_window_seconds, 3.0)

    responses = await send_sequential(
        http_session, target, create_api_key("headers"), harness_settings.header_request_count
    )
    problems = find_header_problems(responses, expected)
    rejected = sum(1 for response in responses if response.status_code == STATUS_TOO_MANY_REQUESTS)

    harness_report.record(
        request.node.nodeid,
        SuiteResult(
            suite="headers",
            route=f"{target.method} {target.path}",
            limit=f"{expected.quota} / {expected.window_seconds} s",
            admitted=str(len(responses) - rejected),
            detail=f"{len(problems)} problem(s) in {len(responses)} responses",
        ),
    )
    assert rejected > 0, "sent more than the limit but nothing was rejected"
    assert not problems, problems[:5]
