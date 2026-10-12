# Rate Limiting Lab

[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](./LICENSE)

How do you stop one client from using up an API's capacity, and keep that working when the API
runs on many servers? This lab builds the same rate limiter several ways, from an in-memory
counter to Redis with Lua scripts to limits enforced at the edge, and runs the exact same tests
against each one.

---

## The problem

You add a limit: 100 requests per 10 seconds per API key. It works on your laptop. Then:

- *A client sends 100 requests just before the minute ends and 100 just after.* Both batches pass.
- *You scale to three replicas.* Every replica keeps its own count, so the real limit is 300.
- *You move the count to Redis.* Under load two replicas read 99, both allow, and the count ends
  at 101.
- *Redis restarts.* Do you let every request through, or reject every request?

Each of these is a design decision, and each one shows up in system design interviews.

## What this lab does

<p align="center"><img src="docs/images/plan-overview.png" alt="Six phases in a row: 01 in-memory, 02 middleware, 03 Redis and Lua, 04 cluster, 05 edge, 06 write-up; the rate-harness sends the same HTTP suites and load to phases 02 to 05; panels show the five standard routes with their limits and an example 429 response with Retry-After and RateLimit headers" width="100%"></p>

- 🧪 **One test harness for every setup.** Steady traffic, a burst on each side of a window reset,
  200 clients at the same instant, a global limit shared by all keys, the response headers, a
  store outage, and the latency the limiter adds.
- 📐 **Six algorithms behind one interface:** fixed window, sliding window log, sliding window
  counter, token bucket, leaky bucket and GCRA.
- 📊 **Every number is measured**, and the raw results are saved in each phase's `results/`.

| Phase | Status |
|---|---|
| 00 · test harness | ✅ |
| 01 · in-memory algorithms | planned |
| 02 · single-node middleware | planned |
| 03 · Redis + Lua | planned |
| 04 · Redis Cluster scaling | planned |
| 05 · edge rate limiting | planned |
| 06 · interview write-up | planned |

---

## The test harness

<p align="center"><img src="docs/images/plan-phase-0-harness.png" alt="Four traffic patterns (steady, burst, boundary straddle, 200-client fan-out) go to the phase URL; responses go to limit_accuracy and header_checks, which also read the expected policy and expected failures from the phase settings file, and write a report of limit versus admitted per suite" width="100%"></p>

The harness never imports server code. It talks HTTP to a URL, and a small settings file per setup
says which checks should pass and which failures are expected, so an expected failure shows up as
`XFAIL` instead of red.

How it decides pass or fail: starting from an empty limit, any correct algorithm admits at most
`limit` at once plus what refills while the batch is being sent (`limit × elapsed / window`).
Anything above that, plus a 5% tolerance, is over-admission.

| Suite | Traffic | Passes when |
|---|---|---|
| `accuracy` | 150 requests at 50/s on one key | admitted stays within the bound |
| `boundary_burst` | 100 just before a window reset, 100 just after | the most admitted in any window stays within the bound |
| `concurrency` | 200 requests on one key released at once | admitted stays within the bound |
| `global_limit` | 600 requests from 50 keys, new connection each | the shared limit holds across replicas |
| `headers` | 110 sequential requests | `RateLimit` / `RateLimit-Policy` match the policy, `429` has `Retry-After` |
| `failover` | store killed, then requests | fail-open routes answer 200, fail-closed routes 503, nobody waits |
| `latency_overhead` | 200 requests on `/ping` and on a limited route | p95 difference within budget |

---

## Run it locally

### Prerequisites

- Python 3.11+ and Docker Desktop
- Windows PowerShell commands below; on macOS/Linux use `.venv/bin/python` instead of
  `.\.venv\Scripts\python.exe`

### Install the harness

```powershell
cd rate-limiting-patterns\rate-harness
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m pytest          # harness self-tests
```

---

## Project structure

```text
rate-limiting-patterns/
├── rate-harness/              the client side: pytest suites, Locust profile
│   ├── src/rateharness/       config, traffic patterns, limit accuracy, header checks, report
│   ├── tests/suites/          the seven behaviour checks, one pytest marker each
│   ├── tests/unit/            harness self-tests against an in-process stub API
│   └── load/                  Locust user + load shape
├── docs/images/               diagrams (.excalidraw source + .png)
└── ruff.toml, LICENSE
```

## License

MIT, see [LICENSE](./LICENSE).
