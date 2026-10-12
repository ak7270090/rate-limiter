"""Route policies from ``policies.yaml``, each with its own limiter."""

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, PositiveFloat, PositiveInt, field_validator

from ratelab.algorithm_registry import IN_MEMORY_LIMITERS, create_in_memory_limiter
from ratelab.clock import Clock
from ratelab.constants import SCOPE_GLOBAL, SCOPE_PER_KEY
from ratelab.rate_limiter import RateLimiter, RateLimitRule


class RoutePolicy(BaseModel):
    """One limited route: which algorithm, how many requests per window, counted per what."""

    name: str
    method: str
    path: str
    algorithm: str
    limit: PositiveInt
    window_seconds: PositiveFloat
    burst: PositiveInt | None = None
    scope: Literal["per_key", "global"] = SCOPE_PER_KEY

    @field_validator("algorithm")
    @classmethod
    def algorithm_must_exist(cls, algorithm: str) -> str:
        if algorithm not in IN_MEMORY_LIMITERS:
            raise ValueError(
                f"unknown algorithm {algorithm!r}; use one of {list(IN_MEMORY_LIMITERS)}"
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


def load_route_policies(policies_file: Path) -> list[RoutePolicy]:
    """Read and validate the policies file; fails at startup, not on the first request."""
    raw = yaml.safe_load(policies_file.read_text(encoding="utf-8"))
    return PoliciesFile.model_validate(raw).routes


def build_policy_registry(
    policies: list[RoutePolicy], clock: Clock | None = None
) -> PolicyRegistry:
    return PolicyRegistry(
        [
            LimitedRoute(policy, create_in_memory_limiter(policy.algorithm, policy.rule, clock))
            for policy in policies
        ]
    )
