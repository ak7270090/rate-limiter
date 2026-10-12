# Harness report: http://localhost:8080

Generated 2026-10-12 20:03 UTC.

| Suite | Route | Limit | Admitted | Outcome | Detail |
|---|---|---|---|---|---|
| accuracy | GET /items | 100 / 10 s | 129 | PASS | 150 sent at 50/s; over-admission 0% |
| boundary_burst | GET /items | 100 / 10 s | 112 | PASS | 2 bursts of 100 1.24 s apart around a window reset; allowed up to 117 |
| concurrency | GET /items | 100 / 10 s | 102 | PASS | 200 parallel requests in 0.07 s; over-admission 1% |
| headers | GET /items | 100 / 10 s | 102 | PASS | 0 problem(s) in 110 responses |
| latency_overhead | GET /items | - | - | PASS | p95 4.3 ms vs 3.7 ms on /ping (200 sequential requests each) |
