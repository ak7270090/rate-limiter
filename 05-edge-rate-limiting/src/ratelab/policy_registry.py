"""Route policies from ``policies.yaml``: each route has tiers that must all allow a request."""

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, Field, PositiveFloat, PositiveInt

from ratelab.constants import MODE_ENFORCE, MODE_SHADOW, ON_STORE_FAILURE_ALLOW
from ratelab.rate_limiter import RateLimiter, RateLimitRule


class TierPolicy(BaseModel):
    """One limit inside a route. Tiers with the same name and scope share their counter."""

    name: str
    scope: Literal["global", "route", "caller", "route_caller"]
    algorithm: Literal["gcra", "fixed_window", "sliding_window_counter"]
    limit: PositiveInt
    window_seconds: PositiveFloat
    burst: PositiveInt | None = None

    @property
    def rule(self) -> RateLimitRule:
        return RateLimitRule(self.limit, self.window_seconds, self.burst)


class RoutePolicy(BaseModel):
    """A limited route. ``shadow`` mode decides and records but never rejects."""

    name: str
    method: str
    path: str
    mode: Literal["enforce", "shadow"] = MODE_ENFORCE
    on_store_failure: Literal["allow", "reject"] = ON_STORE_FAILURE_ALLOW
    tiers: list[TierPolicy] = Field(min_length=1)

    @property
    def is_shadow(self) -> bool:
        return self.mode == MODE_SHADOW


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
    replace, e.g. ``{"items": {"mode": "shadow"}}``. ``"*"`` applies to every route.
    """
    raw = yaml.safe_load(policies_file.read_text(encoding="utf-8"))
    overrides = policy_overrides or {}
    for route in raw["routes"]:
        route["method"] = route["method"].upper()
        route.update(overrides.get("*", {}))
        route.update(overrides.get(route["name"], {}))
    return PoliciesFile.model_validate(raw).routes


def build_policy_registry(
    policies: list[RoutePolicy], create_limiter: Callable[[RoutePolicy], RateLimiter]
) -> PolicyRegistry:
    return PolicyRegistry([LimitedRoute(policy, create_limiter(policy)) for policy in policies])
