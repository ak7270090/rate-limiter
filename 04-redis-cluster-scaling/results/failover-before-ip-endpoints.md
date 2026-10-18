# Failover with hostname endpoints (before the fix)

Same timeline as `failover-cluster.md` / `failover-sentinel.md` (one key at 20 requests/s on
`GET /items`, fail-open, limit 100 per 10 s; primary stopped at 10 s, started at 30 s), but Redis
advertised hostnames.

## Redis Cluster, `--cluster-preferred-endpoint-type hostname`

| Seconds | What happened |
|---|---|
| 12–15 | p95 latency 1.8–6.0 s; 30 of 80 requests failed (client timeout 5 s) |
| 15–38 | every request admitted (20/s, no 429): the limit was not enforced |
| 39 | limiting resumed, about 9 s after the stopped node came back |

Admitted per 10 s window: 142, 167, 201, 195 (limit 100). API log: 39 ×
`RedisClusterException: Redis Cluster cannot be connected. Please provide at least one reachable
node: Timeout connecting to server`, once per breaker trial per replica, for the whole outage.

## Sentinel, `sentinel resolve-hostnames yes` / `announce-hostnames yes`

| Seconds | What happened |
|---|---|
| 15–25 | 188 of 200 requests failed after 6 s (client timeout 5 s) |
| 31–34 | limiting resumed only after the old primary came back; no failover happened |

Sentinel 1 log: `+sdown master`, then `+sdown` for both other Sentinels and the replica, then
`+tilt #tilt mode entered`. API log: 38 × `MasterNotFoundError`.

## Why

```text
getaddrinfo("redis-node-2")  -> 0.02 s
getaddrinfo("redis-node-99") -> 8.0 s, then "Temporary failure in name resolution"
```

A stopped container's name takes 8 s to fail on Docker's DNS. The API resolves names on asyncio's
12 resolver threads; a dozen in-flight lookups of the dead name blocked every other lookup, so
connections to healthy nodes timed out too. Redis and Sentinel resolve on their single main
thread, so the Sentinel froze and saw every peer as down. Advertising IPs removes DNS from the
request path.

## Per second

### Redis Cluster, hostname endpoints

| Second | 200 | 429 | 503 | Errors |
|---|---|---|---|---|
| 0 | 20 | 0 | 0 | 0 |
| 1 | 20 | 0 | 0 | 0 |
| 2 | 20 | 0 | 0 | 0 |
| 3 | 20 | 0 | 0 | 0 |
| 4 | 21 | 0 | 0 | 0 |
| 5 | 16 | 4 | 0 | 0 |
| 6 | 6 | 13 | 0 | 0 |
| 7 | 7 | 14 | 0 | 0 |
| 8 | 6 | 13 | 0 | 0 |
| 9 | 6 | 14 | 0 | 0 |
| 10 | 17 | 3 | 0 | 0 |
| 11 | 20 | 0 | 0 | 0 |
| 12 | 20 | 0 | 0 | 0 |
| 13 | 7 | 0 | 0 | 13 |
| 14 | 3 | 0 | 0 | 17 |
| 15 | 21 | 0 | 0 | 0 |
| 16 | 19 | 0 | 0 | 0 |
| 17 | 20 | 0 | 0 | 0 |
| 18 | 20 | 0 | 0 | 0 |
| 19 | 20 | 0 | 0 | 0 |
| 20 | 20 | 0 | 0 | 0 |
| 21 | 20 | 0 | 0 | 0 |
| 22 | 20 | 0 | 0 | 0 |
| 23 | 21 | 0 | 0 | 0 |
| 24 | 19 | 0 | 0 | 0 |
| 25 | 20 | 0 | 0 | 0 |
| 26 | 20 | 0 | 0 | 0 |
| 27 | 20 | 0 | 0 | 0 |
| 28 | 21 | 0 | 0 | 0 |
| 29 | 20 | 0 | 0 | 0 |
| 30 | 19 | 0 | 0 | 0 |
| 31 | 20 | 0 | 0 | 0 |
| 32 | 20 | 0 | 0 | 0 |
| 33 | 21 | 0 | 0 | 0 |
| 34 | 19 | 0 | 0 | 0 |
| 35 | 21 | 0 | 0 | 0 |
| 36 | 20 | 0 | 0 | 0 |
| 37 | 19 | 0 | 0 | 0 |
| 38 | 20 | 0 | 0 | 0 |
| 39 | 16 | 4 | 0 | 0 |

### Sentinel, hostname endpoints

| Second | 200 | 429 | 503 | Errors |
|---|---|---|---|---|
| 0 | 21 | 0 | 0 | 0 |
| 1 | 20 | 0 | 0 | 0 |
| 2 | 19 | 0 | 0 | 0 |
| 3 | 20 | 0 | 0 | 0 |
| 4 | 20 | 1 | 0 | 0 |
| 5 | 7 | 12 | 0 | 0 |
| 6 | 10 | 10 | 0 | 0 |
| 7 | 10 | 10 | 0 | 0 |
| 8 | 10 | 10 | 0 | 0 |
| 9 | 9 | 11 | 0 | 0 |
| 10 | 19 | 1 | 0 | 0 |
| 11 | 21 | 0 | 0 | 0 |
| 12 | 19 | 0 | 0 | 0 |
| 13 | 20 | 0 | 0 | 0 |
| 14 | 20 | 0 | 0 | 0 |
| 15 | 1 | 0 | 0 | 19 |
| 16 | 0 | 0 | 0 | 20 |
| 17 | 0 | 0 | 0 | 20 |
| 18 | 0 | 0 | 0 | 20 |
| 19 | 0 | 0 | 0 | 20 |
| 20 | 0 | 0 | 0 | 20 |
| 21 | 0 | 0 | 0 | 20 |
| 22 | 0 | 0 | 0 | 20 |
| 23 | 1 | 0 | 0 | 19 |
| 24 | 11 | 0 | 0 | 9 |
| 25 | 18 | 0 | 0 | 2 |
| 26 | 20 | 0 | 0 | 0 |
| 27 | 20 | 0 | 0 | 0 |
| 28 | 19 | 1 | 0 | 0 |
| 29 | 19 | 1 | 0 | 0 |
| 30 | 21 | 0 | 0 | 0 |
| 31 | 2 | 17 | 0 | 0 |
| 32 | 0 | 20 | 0 | 0 |
| 33 | 0 | 20 | 0 | 0 |
| 34 | 0 | 20 | 0 | 0 |
| 35 | 7 | 13 | 0 | 0 |
| 36 | 10 | 10 | 0 | 0 |
| 37 | 9 | 11 | 0 | 0 |
| 38 | 10 | 10 | 0 | 0 |
| 39 | 11 | 9 | 0 | 0 |

