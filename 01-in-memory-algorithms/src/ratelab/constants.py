"""Algorithm names and numeric tolerances shared by every limiter."""

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
