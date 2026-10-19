"""Header names, tier scopes, algorithm names and other fixed values."""

ENV_PREFIX = "RATELAB_"

API_KEY_HEADER = "X-API-Key"
USER_ID_HEADER = "X-User-Id"
FORWARDED_FOR_HEADER = "X-Forwarded-For"
REPLICA_ID_HEADER = "X-Replica-Id"
RATE_LIMIT_HEADER = "RateLimit"
RATE_LIMIT_POLICY_HEADER = "RateLimit-Policy"
RETRY_AFTER_HEADER = "Retry-After"

CALLER_KEY_PREFIX_API_KEY = "key"
CALLER_KEY_PREFIX_USER = "user"
CALLER_KEY_PREFIX_IP = "ip"
UNKNOWN_CLIENT_ADDRESS = "unknown"

# What a tier counts: everything, one route, one caller across routes, or one caller on a route.
TIER_SCOPE_GLOBAL = "global"
TIER_SCOPE_ROUTE = "route"
TIER_SCOPE_CALLER = "caller"
TIER_SCOPE_ROUTE_CALLER = "route_caller"

ALGORITHM_GCRA = "gcra"
ALGORITHM_FIXED_WINDOW = "fixed_window"
ALGORITHM_SLIDING_WINDOW_COUNTER = "sliding_window_counter"
TIERED_LIMIT_SCRIPT = "tiered_limit"

MODE_ENFORCE = "enforce"
MODE_SHADOW = "shadow"

RATE_LIMITED_DETAIL = "rate limit exceeded"
LIMITER_UNAVAILABLE_DETAIL = "rate limiter unavailable"
API_KEY_HASH_LENGTH = 12

REDIS_KEY_PREFIX = "rl"
LUA_SCRIPT_PACKAGE = "ratelab.store"
LUA_SCRIPT_DIRECTORY = "lua"
LUA_SCRIPT_SUFFIX = ".lua"

ON_STORE_FAILURE_ALLOW = "allow"
ON_STORE_FAILURE_REJECT = "reject"

DECISION_ALLOWED = "allowed"
DECISION_REJECTED = "rejected"
DECISION_SHADOW_REJECTED = "shadow_rejected"
DECISION_UNAVAILABLE = "unavailable"
METRICS_PATH = "/metrics"
