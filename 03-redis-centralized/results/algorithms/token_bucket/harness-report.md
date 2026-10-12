# Harness report: http://localhost:8080

Generated 2026-10-12 20:02 UTC.

| Suite | Route | Limit | Admitted | Outcome | Detail |
|---|---|---|---|---|---|
| accuracy | GET /items | 100 / 10 s | 129 | PASS | 150 sent at 50/s; over-admission 0% |
| boundary_burst | GET /items | 100 / 10 s | 113 | PASS | 2 bursts of 100 1.29 s apart around a window reset; allowed up to 118 |
| concurrency | GET /items | 100 / 10 s | 102 | PASS | 200 parallel requests in 0.07 s; over-admission 1% |
| headers | GET /items | 100 / 10 s | 104 | PASS | 0 problem(s) in 110 responses |
| latency_overhead | GET /items | - | - | PASS | p95 8.7 ms vs 4.5 ms on /ping (200 sequential requests each) |
