# Harness report: http://localhost:8080

Generated 2026-10-12 19:40 UTC.

| Suite | Route | Limit | Admitted | Outcome | Detail |
|---|---|---|---|---|---|
| accuracy | GET /items | 100 / 10 s | 150 | XFAIL | 150 sent at 50/s; over-admission 15% |
| boundary_burst | GET /items | 100 / 10 s | 200 | XFAIL | 2 bursts of 100 1.28 s apart around a window reset; allowed up to 118 |
| concurrency | GET /items | 100 / 10 s | 200 | XFAIL | 200 parallel requests in 0.08 s; over-admission 98% |
| global_limit | GET /search | 300 / 10 s, all keys | 600 | XFAIL | 600 requests from 50 keys over 3 replica(s) in 0.39 s |
| headers | GET /items | 100 / 10 s | 110 | XFAIL | 0 problem(s) in 110 responses |
| latency_overhead | GET /items | - | - | PASS | p95 3.6 ms vs 3.7 ms on /ping (200 sequential requests each) |
