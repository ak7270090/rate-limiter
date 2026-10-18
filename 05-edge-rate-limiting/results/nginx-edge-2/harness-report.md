# Harness report: http://localhost:8081

Generated 2026-10-18 11:36 UTC.

| Suite | Route | Limit | Admitted | Outcome | Detail |
|---|---|---|---|---|---|
| accuracy | GET /items | 100 / 10 s | 150 | XFAIL | 150 sent at 50/s; over-admission 16% |
| boundary_burst | GET /items | 100 / 10 s | 200 | XFAIL | 2 bursts of 100 1.26 s apart around a window reset; allowed up to 118 |
| concurrency | GET /items | 100 / 10 s | 200 | XFAIL | 200 parallel requests in 0.06 s; over-admission 99% |
| global_limit | GET /search | 300 / 10 s, all keys | 600 | XFAIL | 600 requests from 50 keys over 3 replica(s) in 0.61 s |
| latency_overhead | GET /items | - | - | PASS | p95 3.4 ms vs 3.4 ms on /ping (200 sequential requests each) |
