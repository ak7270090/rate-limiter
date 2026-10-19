"""Route policies from ``policies.yaml``, each with its own limiter."""

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, PositiveFloat, PositiveInt, field_validator

from ratelab.constants import (
    HOT_KEY_STRATEGY_NONE,
    ON_STORE_FAILURE_ALLOW,
    SCOPE_GLOBAL,
    SCOPE_PER_KEY,
)
from ratelab.limiter import RateLimiter, RateLimitRule
from ratelab.storage.redis_limiters import REDIS_ALGORITHMS


class RoutePolicy(BaseModel):
    """One limited route: algorithm, limit per window, counted per what, and what to do when
    Redis is unavailable."""

    name: str
    method: str
    path: str
    algorithm: str
    limit: PositiveInt
    window_seconds: PositiveFloat
    burst: PositiveInt | None = None
    scope: Literal["per_key", "global"] = SCOPE_PER_KEY
    on_store_failure: Literal["allow", "reject", "local"] = ON_STORE_FAILURE_ALLOW
    hot_key_strategy: Literal["none", "split", "lease"] = HOT_KEY_STRATEGY_NONE
    split_count: PositiveInt = 10
    lease_size: PositiveInt = 30
    lease_ttl_seconds: PositiveFloat = 1.0

    @field_validator("algorithm")
    @classmethod
    def algorithm_must_exist(cls, algorithm: str) -> str:
        if algorithm not in REDIS_ALGORITHMS:
            raise ValueError(
                f"unknown algorithm {algorithm!r}; use one of {sorted(REDIS_ALGORITHMS)}"
            )
        return algorithm

    @field_validator("method")
    @classmethod
    def method_is_upper_case(cls, method: str) -> str:
        return method.upper()

    @property
    def rule(self) -> RateLimitRule:
        return RateLimitRule(self.limit, self.window_seconds, self.burst)

    @property
    def is_global(self) -> bool:
        return self.scope == SCOPE_GLOBAL


class PoliciesFile(BaseModel):
    routes: list[RoutePolicy]


@dataclass(frozen=True)
class LimitedRoute:
    policy: RoutePolicy
    limiter: RateLimiter


class PolicyRegistry:
    """Finds the policy and limiter for a request's method and path."""

    def __init__(self, routes: list[LimitedRoute]) -> None:
        self._routes = {(route.policy.method, route.policy.path): route for route in routes}

    def find(self, method: str, path: str) -> LimitedRoute | None:
        return self._routes.get((method.upper(), path))

    @property
    def policies(self) -> list[RoutePolicy]:
        return [route.policy for route in self._routes.values()]


def load_route_policies(
    policies_file: Path, policy_overrides: dict[str, dict[str, Any]] | None = None
) -> list[RoutePolicy]:
    """Read and validate the policies file; ``policy_overrides`` maps route name -> fields to
    replace, e.g. ``{"search": {"hot_key_strategy": "lease"}}``.

    Fails at startup, not on the first request.
    """
    raw = yaml.safe_load(policies_file.read_text(encoding="utf-8"))
    for route in raw["routes"]:
        route.update((policy_overrides or {}).get(route["name"], {}))
    return PoliciesFile.model_validate(raw).routes


def build_policy_registry(
    policies: list[RoutePolicy], create_limiter: Callable[[RoutePolicy], RateLimiter]
) -> PolicyRegistry:
    return PolicyRegistry([LimitedRoute(policy, create_limiter(policy)) for policy in policies])
