"""Harness settings from ``HARNESS_*`` environment variables or the ``HARNESS_ENV_FILE`` file."""

import os
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

from rateharness.constants import ENV_FILE_VARIABLE, ENV_PREFIX


class HarnessSettings(BaseSettings):
    """Which API to test, the limits it should enforce, and what this phase is expected to fail."""

    model_config = SettingsConfigDict(env_prefix=ENV_PREFIX, extra="ignore")

    target_url: str = "http://localhost:8080"
    expected_replica_count: int = 1
    expected_failures: set[str] = set()
    skipped_suites: set[str] = set()
    tolerance_percent: float = 5.0
    request_timeout_seconds: float = 10.0
    max_parallel_requests: int = 50

    per_key_method: str = "GET"
    per_key_route: str = "/items"
    per_key_policy_name: str = "items"
    per_key_limit: int = 100
    per_key_window_seconds: float = 10.0
    accuracy_request_count: int = 150
    accuracy_rate_per_second: float = 50.0
    concurrency_client_count: int = 200
    boundary_lead_seconds: float = 1.0
    boundary_after_seconds: float = 0.2
    header_request_count: int = 110

    global_method: str = "GET"
    global_route: str = "/search"
    global_limit: int = 300
    global_window_seconds: float = 10.0
    global_request_count: int = 600
    global_key_count: int = 50

    baseline_route: str = "/ping"
    latency_sample_count: int = 200
    max_overhead_ms: float = 20.0

    fail_open_method: str = "GET"
    fail_open_route: str = "/items"
    fail_closed_method: str = "POST"
    fail_closed_route: str = "/orders"
    failover_request_count: int = 10
    max_failover_latency_seconds: float = 1.0
    kill_command: str = ""
    restore_command: str = ""
    failover_settle_seconds: float = 2.0
    restore_settle_seconds: float = 5.0
    command_timeout_seconds: float = 30.0

    load_api_key_count: int = 500
    load_zipf_exponent: float = 1.1
    load_wait_min_seconds: float = 0.05
    load_wait_max_seconds: float = 0.2
    load_warmup_users: int = 10
    load_warmup_seconds: int = 60
    load_steady_users: int = 200
    load_steady_seconds: int = 300
    load_spike_users: int = 1000
    load_spike_ramp_seconds: int = 30

    results_dir: Path = Path("results")


def load_harness_settings() -> HarnessSettings:
    """Read settings; real environment variables override the optional ``HARNESS_ENV_FILE``."""
    env_file = os.environ.get(ENV_FILE_VARIABLE)
    return HarnessSettings(_env_file=env_file) if env_file else HarnessSettings()
