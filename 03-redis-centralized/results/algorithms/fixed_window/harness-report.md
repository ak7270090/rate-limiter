# Harness report: http://localhost:8080

Generated 2026-10-12 20:00 UTC.

| Suite | Route | Limit | Admitted | Outcome | Detail |
|---|---|---|---|---|---|
| accuracy | GET /items | 100 / 10 s | 100 | PASS | 150 sent at 50/s; over-admission 0% |
| boundary_burst | GET /items | 100 / 10 s | 200 | XFAIL | 2 bursts of 100 1.25 s apart around a window reset; allowed up to 117 |
| concurrency | GET /items | 100 / 10 s | 100 | PASS | 200 parallel requests in 0.08 s; over-admission 0% |
| headers | GET /items | 100 / 10 s | 100 | PASS | 0 problem(s) in 110 responses |
| latency_overhead | GET /items | - | - | PASS | p95 4.0 ms vs 2.8 ms on /ping (200 sequential requests each) |
