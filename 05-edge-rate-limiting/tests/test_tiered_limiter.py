import pytest
from redis.asyncio import Redis

from ratelab.constants import TIERED_LIMIT_SCRIPT
from ratelab.policies.registry import RoutePolicy, TierPolicy
from ratelab.store.script_loader import register_lua_scripts
from ratelab.store.tiered_limiter import TieredLimiter, build_tier_key

pytestmark = pytest.mark.anyio


def make_policy(route_name: str, *tiers: TierPolicy) -> RoutePolicy:
    return RoutePolicy(name=route_name, method="GET", path=f"/{route_name}", tiers=list(tiers))


def make_tier(name: str, scope: str, algorithm: str, limit: int, **extra) -> TierPolicy:
    return TierPolicy(
        name=name,
        scope=scope,
        algorithm=algorithm,
        limit=limit,
        window_seconds=extra.pop("window_seconds", 60),
        **extra,
    )


def make_limiter(redis_client: Redis, policy: RoutePolicy) -> TieredLimiter:
    return TieredLimiter(policy, register_lua_scripts(redis_client)[TIERED_LIMIT_SCRIPT])


async def test_tier_keys_follow_their_scope() -> None:
    caller = "key:k42"
    tiers = {
        scope: make_tier("t", scope, "gcra", 5)
        for scope in ("global", "route", "caller", "route_caller")
    }

    assert build_tier_key(tiers["global"], "items", caller) == "rl:{t}:gcra"
    assert build_tier_key(tiers["route"], "items", caller) == "rl:{t:items}:gcra"
    assert build_tier_key(tiers["caller"], "items", caller) == "rl:{t:key:k42}:gcra"
    assert build_tier_key(tiers["route_caller"], "items", caller) == "rl:{t:items:key:k42}:gcra"


@pytest.mark.parametrize("algorithm", ["gcra", "fixed_window", "sliding_window_counter"])
async def test_single_tier_admits_its_limit(redis_client: Redis, algorithm: str) -> None:
    limiter = make_limiter(
        redis_client, make_policy("items", make_tier("items", "route_caller", algorithm, 5))
    )

    decisions = [await limiter.acquire("key:k42") for _ in range(7)]

    assert [decision.is_allowed for decision in decisions] == [True] * 5 + [False] * 2
    assert decisions[0].tier_states[0].remaining == 4
    assert decisions[-1].rejected_by == "items"
    assert decisions[-1].retry_after_seconds > 0


async def test_a_rejecting_tier_charges_no_other_tier(redis_client: Redis) -> None:
    user_tier = make_tier("user", "caller", "sliding_window_counter", 3)
    reports = make_limiter(
        redis_client,
        make_policy(
            "reports", make_tier("reports-day", "route_caller", "fixed_window", 10), user_tier
        ),
    )
    items = make_limiter(redis_client, make_policy("items", user_tier))
    for _ in range(3):
        await items.acquire("key:k42")

    rejected = await reports.acquire("key:k42")
    other_caller = await reports.acquire("key:k43")

    assert not rejected.is_allowed
    assert rejected.rejected_by == "user"
    assert rejected.tier_states[0].remaining == 10
    assert other_caller.is_allowed
    assert other_caller.tier_states[0].remaining == 9


async def test_gcra_burst_and_global_tier_shared_by_routes(redis_client: Redis) -> None:
    global_tier = make_tier("global", "global", "gcra", 4)
    orders = make_limiter(
        redis_client,
        make_policy(
            "orders",
            make_tier("orders", "route_caller", "gcra", 10, burst=2),
            global_tier,
        ),
    )
    search = make_limiter(redis_client, make_policy("search", global_tier))

    order_decisions = [(await orders.acquire("key:a")).is_allowed for _ in range(3)]
    search_decisions = [(await search.acquire("key:b")).is_allowed for _ in range(3)]

    assert order_decisions == [True, True, False]
    assert search_decisions == [True, True, False]


async def test_cost_larger_than_smallest_tier_is_refused(redis_client: Redis) -> None:
    limiter = make_limiter(
        redis_client,
        make_policy(
            "items",
            make_tier("items", "route_caller", "gcra", 10),
            make_tier("global", "global", "gcra", 3),
        ),
    )

    with pytest.raises(ValueError, match="cost 4"):
        await limiter.acquire("key:k42", cost=4)
