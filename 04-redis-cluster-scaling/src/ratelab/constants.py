"""Algorithm names, tolerances, header names and other fixed values."""

ENV_PREFIX = "RATELAB_"

API_KEY_HEADER = "X-API-Key"
USER_ID_HEADER = "X-User-Id"
FORWARDED_FOR_HEADER = "X-Forwarded-For"
REPLICA_ID_HEADER = "X-Replica-Id"
RATE_LIMIT_HEADER = "RateLimit"
RATE_LIMIT_POLICY_HEADER = "RateLimit-Policy"
RETRY_AFTER_HEADER = "Retry-After"

SCOPE_PER_KEY = "per_key"
SCOPE_GLOBAL = "global"
GLOBAL_CALLER_KEY = "all"
CALLER_KEY_PREFIX_API_KEY = "key"
CALLER_KEY_PREFIX_USER = "user"
CALLER_KEY_PREFIX_IP = "ip"
UNKNOWN_CLIENT_ADDRESS = "unknown"

RATE_LIMITED_DETAIL = "rate limit exceeded"
LIMITER_UNAVAILABLE_DETAIL = "rate limiter unavailable"
API_KEY_HASH_LENGTH = 12

# Variants without Lua, kept to show the race condition and its common fix.
ALGORITHM_FIXED_WINDOW_NAIVE = "fixed_window_naive"
ALGORITHM_FIXED_WINDOW_INCR = "fixed_window_incr"

REDIS_KEY_PREFIX = "rl"
LUA_SCRIPT_PACKAGE = "ratelab"
LUA_SCRIPT_DIRECTORY = "lua"
LUA_SCRIPT_SUFFIX = ".lua"

HOT_KEY_STRATEGY_NONE = "none"
HOT_KEY_STRATEGY_SPLIT = "split"
HOT_KEY_STRATEGY_LEASE = "lease"
SPLIT_KEY_SEPARATOR = "#"

ON_STORE_FAILURE_ALLOW = "allow"
ON_STORE_FAILURE_REJECT = "reject"
ON_STORE_FAILURE_LOCAL = "local"

DECISION_ALLOWED = "allowed"
DECISION_REJECTED = "rejected"
DECISION_UNAVAILABLE = "unavailable"
METRICS_PATH = "/metrics"

ALGORITHM_FIXED_WINDOW = "fixed_window"
ALGORITHM_SLIDING_WINDOW_LOG = "sliding_window_log"
ALGORITHM_SLIDING_WINDOW_COUNTER = "sliding_window_counter"
ALGORITHM_TOKEN_BUCKET = "token_bucket"
ALGORITHM_LEAKY_BUCKET = "leaky_bucket"
ALGORITHM_LEAKY_BUCKET_QUEUE = "leaky_bucket_queue"
ALGORITHM_GCRA = "gcra"

# Float sums such as 100 x 0.1 land a hair above 10.0; comparisons allow this much slack.
FLOAT_TOLERANCE = 1e-9
# Added to every retry-after so a client retrying exactly then is on the allowed side.
RETRY_MARGIN_SECONDS = 1e-6

DEFAULT_SWEEP_INTERVAL_OPERATIONS = 10_000
