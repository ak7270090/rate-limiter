# Harness report: http://localhost:8080

Generated 2026-10-18 11:12 UTC.

| Suite | Route | Limit | Admitted | Outcome | Detail |
|---|---|---|---|---|---|
| accuracy | GET /items | 100 / 10 s | 100 | PASS | 150 sent at 50/s; over-admission 0% |
| boundary_burst | GET /items | 100 / 10 s | 102 | PASS | 2 bursts of 100 1.25 s apart around a window reset; allowed up to 117 |
| concurrency | GET /items | 100 / 10 s | 100 | PASS | 200 parallel requests in 0.06 s; over-admission 0% |
| global_limit | GET /search | 300 / 10 s, all keys | 310 | PASS | 600 requests from 50 keys over 3 replica(s) in 0.63 s |
| headers | GET /items | 100 / 10 s | 100 | PASS | 0 problem(s) in 110 responses |
| latency_overhead | GET /items | - | - | PASS | p95 3.8 ms vs 2.3 ms on /ping (200 sequential requests each) |
