"""Standard load profile: warm-up, steady, spike, over API keys with a Zipf distribution.

Run from ``rate-harness/``:
``.venv/Scripts/locust -f load/locustfile.py --headless --host http://localhost:8080``
"""

import itertools
import random
from collections import Counter

from locust import HttpUser, LoadTestShape, between, events, task

from rateharness.client_factory import build_api_key_headers
from rateharness.config import load_harness_settings
from rateharness.constants import (
    LOAD_REJECTIONS_FILE_NAME,
    STATUS_OK,
    STATUS_TOO_MANY_REQUESTS,
)

SETTINGS = load_harness_settings()
API_KEYS = [f"load-key-{rank}" for rank in range(1, SETTINGS.load_api_key_count + 1)]
CUMULATIVE_KEY_WEIGHTS = list(
    itertools.accumulate(
        1 / rank**SETTINGS.load_zipf_exponent for rank in range(1, len(API_KEYS) + 1)
    )
)
RESPONSES_BY_ROUTE: Counter[tuple[str, int]] = Counter()


def pick_api_key() -> str:
    """A few heavy keys and a long tail of light ones."""
    return random.choices(API_KEYS, cum_weights=CUMULATIVE_KEY_WEIGHTS)[0]


class RateLimitedApiUser(HttpUser):
    """One client calling the standard API; a 429 counts as a correct answer, not a failure."""

    wait_time = between(SETTINGS.load_wait_min_seconds, SETTINGS.load_wait_max_seconds)

    def call_route(self, method: str, path: str) -> None:
        with self.client.request(
            method,
            path,
            headers=build_api_key_headers(pick_api_key()),
            name=f"{method} {path}",
            catch_response=True,
        ) as response:
            RESPONSES_BY_ROUTE[(f"{method} {path}", response.status_code)] += 1
            if response.status_code in (STATUS_OK, STATUS_TOO_MANY_REQUESTS):
                response.success()
            else:
                response.failure(f"status {response.status_code}")

    @task(50)
    def list_items(self) -> None:
        self.call_route("GET", "/items")

    @task(20)
    def search(self) -> None:
        self.call_route("GET", "/search")

    @task(15)
    def create_order(self) -> None:
        self.call_route("POST", "/orders")

    @task(10)
    def ping(self) -> None:
        self.call_route("GET", "/ping")

    @task(5)
    def create_report(self) -> None:
        self.call_route("POST", "/reports")


class StandardLoadShape(LoadTestShape):
    """Warm-up, steady and spike stages from the harness settings."""

    def tick(self) -> tuple[int, float] | None:
        run_time = self.get_run_time()
        warmup_end = SETTINGS.load_warmup_seconds
        steady_end = warmup_end + SETTINGS.load_steady_seconds
        spike_end = steady_end + SETTINGS.load_spike_ramp_seconds
        if run_time < warmup_end:
            return SETTINGS.load_warmup_users, SETTINGS.load_warmup_users
        if run_time < steady_end:
            return SETTINGS.load_steady_users, SETTINGS.load_steady_users
        if run_time < spike_end:
            spawn_rate = SETTINGS.load_spike_users / SETTINGS.load_spike_ramp_seconds
            return SETTINGS.load_spike_users, spawn_rate
        return None


@events.test_stop.add_listener
def write_rejection_summary(**_: object) -> None:
    """Write how many requests per route were admitted and rejected."""
    routes = sorted({route for route, _ in RESPONSES_BY_ROUTE})
    lines = ["| Route | 200 | 429 | other |", "|---|---|---|---|"]
    for route in routes:
        admitted = RESPONSES_BY_ROUTE[(route, STATUS_OK)]
        rejected = RESPONSES_BY_ROUTE[(route, STATUS_TOO_MANY_REQUESTS)]
        total = sum(count for (name, _), count in RESPONSES_BY_ROUTE.items() if name == route)
        lines.append(f"| {route} | {admitted} | {rejected} | {total - admitted - rejected} |")
    SETTINGS.results_dir.mkdir(parents=True, exist_ok=True)
    (SETTINGS.results_dir / LOAD_REJECTIONS_FILE_NAME).write_text(
        "\n".join(lines) + "\n", encoding="utf-8"
    )
