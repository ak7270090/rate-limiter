from pathlib import Path

import pytest
from pydantic import ValidationError
from starlette.requests import Request

from ratelab.api.caller_key import CallerKeyExtractor
from ratelab.api.headers import build_rate_limit_headers
from ratelab.api.middleware import hash_caller_key
from ratelab.config import ApiSettings
from ratelab.limiter import RateLimitDecision, TierState
from ratelab.policies.registry import (
    RoutePolicy,
    TierPolicy,
    build_policy_registry,
    load_route_policies,
)

EXTRACTOR = CallerKeyExtractor(["10.0.0.0/8"])
PROJECT_DIR = Path(__file__).parents[1]
REPORTS_POLICY = RoutePolicy(
    name="reports",
    method="POST",
    path="/reports",
    tiers=[
        TierPolicy(
            name="reports-day",
            scope="route_caller",
            algorithm="fixed_window",
            limit=50,
            window_seconds=86400,
        ),
        TierPolicy(name="user", scope="caller", algorithm="gcra", limit=200, window_seconds=10),
    ],
)


def make_request(headers: dict[str, str], client_host: str | None = "10.1.2.3") -> Request:
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/items",
        "headers": [(name.lower().encode(), value.encode()) for name, value in headers.items()],
        "client": (client_host, 1234) if client_host else None,
    }
    return Request(scope)


def test_caller_key_prefers_api_key_then_user_then_ip() -> None:
    assert EXTRACTOR.extract_caller_key(make_request({"X-API-Key": "k1", "X-User-Id": "u"})) == (
        "key:k1"
    )
    assert EXTRACTOR.extract_caller_key(make_request({"X-User-Id": "u7"})) == "user:u7"
    assert EXTRACTOR.extract_caller_key(make_request({})) == "ip:10.1.2.3"


def test_forwarded_for_is_trusted_only_from_a_trusted_proxy() -> None:
    forwarded = {"X-Forwarded-For": "203.0.113.9, 10.1.2.3"}

    assert EXTRACTOR.extract_client_address(make_request(forwarded)) == "203.0.113.9"
    assert EXTRACTOR.extract_client_address(make_request(forwarded, "198.51.100.1")) == (
        "198.51.100.1"
    )
    assert EXTRACTOR.extract_client_address(make_request(forwarded, None)) == "unknown"


def test_headers_list_every_tier_including_the_daily_quota() -> None:
    states = (
        TierState("reports-day", 50, 86400, 49, 3600.2),
        TierState("user", 200, 10, 199, 0.05),
    )
    allowed = RateLimitDecision(True, 50, 49, 3600.2, tier_states=states)
    rejected = RateLimitDecision(
        False, 50, 0, 3600.2, retry_after_seconds=3600.2, tier_states=states
    )

    assert build_rate_limit_headers(REPORTS_POLICY, allowed) == {
        "RateLimit-Policy": '"reports-day";q=50;w=86400, "user";q=200;w=10',
        "RateLimit": '"reports-day";r=49;t=3601, "user";r=199;t=1',
    }
    assert build_rate_limit_headers(REPORTS_POLICY, rejected)["Retry-After"] == "3601"


def test_fail_open_decision_has_policy_but_no_remaining() -> None:
    headers = build_rate_limit_headers(REPORTS_POLICY, RateLimitDecision(True, 50, 50, 0.0))

    assert set(headers) == {"RateLimit-Policy"}


def test_policies_are_validated_at_load(tmp_path: Path) -> None:
    bad_file = tmp_path / "bad.yaml"
    bad_file.write_text(
        "routes:\n  - {name: x, method: GET, path: /x, tiers: [{name: x, scope: route, "
        "algorithm: magic, limit: 1, window_seconds: 1}]}\n",
        encoding="utf-8",
    )
    empty_tiers = tmp_path / "empty.yaml"
    empty_tiers.write_text("routes:\n  - {name: x, method: GET, path: /x, tiers: []}\n")

    with pytest.raises(ValidationError, match="algorithm"):
        load_route_policies(bad_file)
    with pytest.raises(ValidationError, match="tiers"):
        load_route_policies(empty_tiers)


def test_registry_finds_routes_case_insensitively_by_method() -> None:
    registry = build_policy_registry([REPORTS_POLICY], lambda policy: None)

    assert registry.find("post", "/reports").policy.name == "reports"
    assert registry.find("GET", "/reports") is None
    assert [policy.name for policy in registry.policies] == ["reports"]


def test_overrides_apply_to_one_route_or_all() -> None:
    policies = load_route_policies(
        PROJECT_DIR / "policies.yaml",
        {"*": {"mode": "shadow"}, "orders": {"on_store_failure": "allow"}},
    )
    by_name = {policy.name: policy for policy in policies}

    assert all(policy.is_shadow for policy in policies)
    assert by_name["orders"].on_store_failure == "allow"
    assert by_name["reports"].on_store_failure == "reject"


def test_settings_and_key_hash() -> None:
    settings = ApiSettings(replica_id="r1")

    assert settings.policies_file == Path("policies.yaml")
    assert len(hash_caller_key("key:k1")) == 12
    assert hash_caller_key("key:k1") != hash_caller_key("key:k2")
