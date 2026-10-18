# Harness report: http://localhost:8080

Generated 2026-10-18 11:34 UTC.

| Suite | Route | Limit | Admitted | Outcome | Detail |
|---|---|---|---|---|---|
| accuracy | GET /items | 100 / 60 s | 100 | PASS | 150 sent at 50/s; over-admission 0% |
| boundary_burst | GET /items | 100 / 60 s | 200 | XFAIL | 2 bursts of 100 1.27 s apart around a window reset; allowed up to 107 |
| concurrency | GET /items | 100 / 60 s | 100 | PASS | 200 parallel requests in 0.06 s; over-admission 0% |
| global_limit | GET /search | 300 / 60 s, all keys | 313 | PASS | 600 requests from 50 keys over 3 replica(s) in 0.59 s |
| latency_overhead | GET /items | - | - | PASS | p95 6.4 ms vs 4.5 ms on /ping (200 sequential requests each) |
