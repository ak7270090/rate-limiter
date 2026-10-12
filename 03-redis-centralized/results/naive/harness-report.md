# Harness report: http://localhost:8080

Generated 2026-10-12 19:59 UTC.

| Suite | Route | Limit | Admitted | Outcome | Detail |
|---|---|---|---|---|---|
| accuracy | GET /items | 100 / 10 s | 100 | PASS | 150 sent at 50/s; over-admission 0% |
| boundary_burst | GET /items | 100 / 10 s | 200 | XFAIL | 2 bursts of 100 1.27 s apart around a window reset; allowed up to 118 |
| concurrency | GET /items | 100 / 10 s | 117 | XFAIL | 200 parallel requests in 0.07 s; over-admission 16% |
| global_limit | GET /search | 300 / 10 s, all keys | 300 | PASS | 600 requests from 50 keys over 3 replica(s) in 0.43 s |
| headers | GET /items | 100 / 10 s | 100 | PASS | 0 problem(s) in 110 responses |
| latency_overhead | GET /items | - | - | PASS | p95 4.9 ms vs 3.1 ms on /ping (200 sequential requests each) |
