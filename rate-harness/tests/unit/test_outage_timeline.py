import sys
from pathlib import Path

import anyio.to_thread
import pytest
from aiohttp.test_utils import TestServer
from multidict import CIMultiDict
from stub_api import STUB_LIMIT, create_stub_api

from rateharness.outage_timeline import (
    TimelineEvent,
    main,
    parse_event,
    summarize_by_second,
)
from rateharness.traffic_patterns import ObservedResponse

pytestmark = pytest.mark.anyio


def make_response(sent_at: float, status_code: int) -> ObservedResponse:
    return ObservedResponse(sent_at, 0.002, status_code, CIMultiDict())


async def test_parse_event_splits_time_and_command() -> None:
    assert parse_event("10=docker stop node-1") == TimelineEvent(10.0, "docker stop node-1")


async def test_summary_buckets_statuses_by_second() -> None:
    responses = [
        make_response(100.1, 200),
        make_response(100.5, 429),
        make_response(101.2, 503),
        make_response(101.3, 0),
    ]

    seconds = summarize_by_second(responses, started=100.0)

    assert [(s.second, s.admitted, s.rejected, s.unavailable, s.errors) for s in seconds] == [
        (0, 1, 1, 0, 0),
        (1, 0, 0, 1, 1),
    ]


async def test_timeline_runs_traffic_and_events(tmp_path: Path) -> None:
    server = TestServer(create_stub_api())
    await server.start_server()
    output = tmp_path / "timeline.md"
    arguments = [
        "--target",
        str(server.make_url("")),
        "--rate",
        "20",
        "--seconds",
        "1",
        "--event",
        f'0.2="{sys.executable}" -c "print(1)"',
        "--output",
        str(output),
    ]
    try:
        report = await anyio.to_thread.run_sync(main, arguments)
    finally:
        await server.close()

    assert f"| 0 | {STUB_LIMIT} | 15 | 0 | 0 |" in report
    assert "| 0.2 |" in report and "| 0 |\n" in report
    assert f"| 0–10 s | {STUB_LIMIT} |" in report
    assert output.read_text(encoding="utf-8") == report
