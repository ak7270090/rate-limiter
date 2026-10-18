# Hot key strategies on Redis Cluster

`GET /search` has one global limit (300 per 10 s, sliding window counter). The harness
`global_limit` suite sends 600 requests from 50 API keys through 3 API replicas. Script calls are
`cmdstat_evalsha` from `INFO commandstats` on each primary, reset before the measured run. Each
strategy is measured after a warm-up run of the same suite and a 21 s pause.

| Strategy | Redis timeout | Admitted (limit 300) | Script calls | Calls per primary |
|---|---|---|---|---|
| none | 250 ms | 300 | 600 | node-1=600 |
| split into 10 sub-keys | 250 ms | 300 | 600 | node-1=184, node-2=173, node-3=243 |
| lease 30 tokens per call | 250 ms | 302 | 32 | node-1=32 |
| none | 50 ms | 300 | 600 | node-1=600 |
| split into 10 sub-keys | 50 ms | 300 | 600 | node-1=188, node-2=169, node-3=243 |
| lease 30 tokens per call | 50 ms | 300 | 16 | node-1=16 |

## Earlier runs, with cold connections

Right after the API replicas restarted, their Redis connections were opened in the middle of the
burst. Calls timed out at 50 ms, the circuit breaker opened, and `/search` fell back to its local
limit (300 / 3 per replica):

| Strategy | Admitted | Script calls | Calls that never reached Redis |
|---|---|---|---|
| none (cold) | 376 | 524 | 76 |
| split (cold) | 431 | 469 | 131 |
| split (warmed via `/items` only, other primaries cold) | 448 | 433 | 167 |
| split (warm, 50 ms) | 382 | 518 | 82 |

The first lease version made 610 calls for 600 requests: after Redis refused a lease, every request
tried a lease and then a single token. It now rejects locally until the retry-after time.
