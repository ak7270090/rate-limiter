from pathlib import Path

import pytest
from pydantic import ValidationError
from starlette.requests import Request

from ratelab.algorithms.token_bucket import TokenBucketLimiter
from ratelab.api.caller_key import CallerKeyExtractor
from ratelab.api.headers import build_rate_limit_headers
from ratelab.api.middleware import hash_caller_key
from ratelab.config import ApiSettings
from ratelab.limiter import RateLimitDecision
from ratelab.policies.route_policies import RoutePolicy, build_policy_registry, load_route_policies

EXTRACTOR = CallerKeyExtractor(["10.0.0.0/8"])
ITEMS_POLICY = RoutePolicy(
    name="items",
    method="get",
    path="/items",
    algorithm="token_bucket",
    limit=100,
    window_seconds=10,
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


def test_headers_round_reset_up_and_add_retry_after_on_rejection() -> None:
    allowed = RateLimitDecision(True, 100, 42, reset_after_seconds=5.2)
    rejected = RateLimitDecision(False, 100, 0, reset_after_seconds=9.9, retry_after_seconds=0.1)

    assert build_rate_limit_headers(ITEMS_POLICY, allowed) == {
        "RateLimit-Policy": '"items";q=100;w=10',
        "RateLimit": '"items";r=42;t=6',
    }
    assert build_rate_limit_headers(ITEMS_POLICY, rejected)["Retry-After"] == "1"


def test_policies_file_is_validated_at_load(tmp_path: Path) -> None:
    bad_file = tmp_path / "bad.yaml"
    bad_file.write_text(
        "routes:\n  - {name: x, method: GET, path: /x, algorithm: magic, limit: 1, "
        "window_seconds: 1}\n",
        encoding="utf-8",
    )

    with pytest.raises(ValidationError, match="unknown algorithm"):
        load_route_policies(bad_file)


def test_registry_finds_routes_case_insensitively_by_method() -> None:
    registry = build_policy_registry([ITEMS_POLICY], lambda policy: TokenBucketLimiter(policy.rule))

    assert registry.find("get", "/items").policy.name == "items"
    assert registry.find("POST", "/items") is None
    assert [policy.name for policy in registry.policies] == ["items"]


def test_algorithm_overrides_replace_a_routes_algorithm(tmp_path: Path) -> None:
    project_dir = Path(__file__).parents[1]

    policies = load_route_policies(project_dir / "policies.yaml", {"items": "gcra"})

    assert {policy.name: policy.algorithm for policy in policies}["items"] == "gcra"
    with pytest.raises(ValidationError):
        load_route_policies(project_dir / "policies.yaml", {"items": "magic"})


def test_shipped_policies_load() -> None:
    project_dir = Path(__file__).parents[1]
    for policies_file in project_dir.glob("policies*.yaml"):
        assert load_route_policies(policies_file)


def test_settings_and_key_hash() -> None:
    settings = ApiSettings(replica_id="r1")

    assert settings.policies_file == Path("policies.yaml")
    assert len(hash_caller_key("key:k1")) == 12
    assert hash_caller_key("key:k1") != hash_caller_key("key:k2")
