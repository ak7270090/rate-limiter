# API replicas 1 → 3 → 6

Sentinel setup (one primary), Locust standard task mix, 100 users for about 30 s per run. Redis
ops/s is one `instantaneous_ops_per_sec` sample from the primary, taken mid-run.

| API replicas | Requests/s | p50 ms | p95 ms | Failures | Redis ops/s (primary) |
|---|---|---|---|---|---|
| 1 | 411 | 25 | 270 | 0 | 2,810 |
| 3 | 342 | 58 | 250 | 0 | 662 |
| 6 | 308 | 72 | 200 | 0 | 1,732 |

One Locust process on the same laptop is the ceiling (about 400 requests/s), and every replica
shares the same CPUs, so more replicas do not add throughput here. Redis stays far below the
62,000 script calls/s it handled in `store-throughput.md`.
