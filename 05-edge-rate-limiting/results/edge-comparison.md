# Where the limit is enforced

Same harness, same 3 API replicas. For the edge rows the API ran in shadow mode, so only the edge
limited. Limits: `/items` 100 per API key and `/search` 300 for everyone, per 10 s (per minute
for Envoy's global limit: the rate limit service only has second / minute / hour / day units).

| Enforced by | 150 at 50/s on one key | 200 at once on one key | 100 + 100 around a reset | 600 on the global limit | p95 `/items` vs `/ping` | Headers |
|---|---|---|---|---|---|---|
| app, tiered Lua script in Redis | 100 | 100 | 102 | 318 | 3.2 vs 2.2 ms | IETF `RateLimit` for every tier |
| Envoy x2 + rate limit service (Redis) | 100 | 100 | **200** | 313 cold, 300 warm | 6.4 vs 4.5 ms | `X-RateLimit-*` (draft 03) |
| Envoy x2, local token bucket | – | – | – | **600** | – | none |
| nginx `limit_req` x1 | 130 | 101 | 113 | 313 | 4.7 vs 3.0 ms | none |
| nginx `limit_req` x2 | **150** | **200** | **200** | **600** | 3.4 vs 3.4 ms | none |

- **Anything counted per instance multiplies by the instance count**: two nginx or two Envoy local
  buckets let 600 through a 300 limit, exactly like API replicas that each count in memory.
- **The rate limit service is exact across Envoys** but counts in fixed windows (200 around a
  minute boundary).
- nginx's leaky bucket admits the burst plus the drain rate: 130 of 150 at 50/s (100 + 10/s x 3 s),
  313 of 600 on `/search` (300 + 30/s x 0.42 s).
- The app's 318 and Envoy's cold 313 are calls that timed out at 50 ms during the burst and failed
  open (8 Redis timeouts in the API log; a warm rerun through Envoy gave exactly 300:
  `cluster.api.ratelimit.ok` 150 and `over_limit` 150 on each Envoy).

## Rate limit service down

`envoyproxy/ratelimit` stopped at 10 s and started at 20 s, one key at 20 requests/s on `/items`
([fail open](ratelimit-down-fail-open.md), [fail closed](ratelimit-down-fail-closed.md)):

| Listener | 10–20 s | p95 during the outage | After restart |
|---|---|---|---|
| `failure_mode_deny: false` | every request admitted (~200 over the limit) | 60 ms | 429s again within 1 s |
| `failure_mode_deny: true`, `status_on_error: 503` | every request 503 | 63 ms | 429s again within 1 s |

Envoy has no circuit breaker for the rate limit call, so every request waits the full 50 ms
timeout while the service is down.

## Shadow mode

During the edge runs the API checked every request in shadow mode: `ratelab_decisions_total` on
`/items` showed 283, 278 and 262 `shadow_rejected` on the three replicas and no enforced
rejection.
