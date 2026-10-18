# Harness report: http://localhost:8081

Generated 2026-10-18 11:36 UTC.

| Suite | Route | Limit | Admitted | Outcome | Detail |
|---|---|---|---|---|---|
| accuracy | GET /items | 100 / 10 s | 130 | PASS | 150 sent at 50/s; over-admission 0% |
| boundary_burst | GET /items | 100 / 10 s | 113 | PASS | 2 bursts of 100 1.22 s apart around a window reset; allowed up to 117 |
| concurrency | GET /items | 100 / 10 s | 101 | PASS | 200 parallel requests in 0.06 s; over-admission 0% |
| global_limit | GET /search | 300 / 10 s, all keys | 313 | PASS | 600 requests from 50 keys over 3 replica(s) in 0.42 s |
| latency_overhead | GET /items | - | - | PASS | p95 4.7 ms vs 3.0 ms on /ping (200 sequential requests each) |
