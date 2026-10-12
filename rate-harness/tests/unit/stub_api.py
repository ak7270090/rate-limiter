"""A tiny in-process API with a never-resetting per-key counter, for testing the harness itself."""

from collections import Counter

from aiohttp import web

STUB_LIMIT = 5
STUB_WINDOW_SECONDS = 10
STUB_POLICY_NAME = "items"
COUNTS_KEY = web.AppKey("counts", Counter)


async def ping(request: web.Request) -> web.Response:
    return web.json_response({"status": "ok"})


async def items(request: web.Request) -> web.Response:
    api_key = request.headers.get("X-API-Key", "anonymous")
    counts = request.app[COUNTS_KEY]
    counts[api_key] += 1
    remaining = max(STUB_LIMIT - counts[api_key], 0)
    headers = {
        "X-Replica-Id": "stub-1",
        "RateLimit-Policy": f'"{STUB_POLICY_NAME}";q={STUB_LIMIT};w={STUB_WINDOW_SECONDS}',
        "RateLimit": f'"{STUB_POLICY_NAME}";r={remaining};t=3',
    }
    if counts[api_key] > STUB_LIMIT:
        headers["Retry-After"] = "3"
        return web.json_response({"detail": "limited"}, status=429, headers=headers)
    return web.json_response({"api_key": api_key}, headers=headers)


def create_stub_api() -> web.Application:
    app = web.Application()
    app[COUNTS_KEY] = Counter()
    app.router.add_get("/ping", ping)
    app.router.add_get("/items", items)
    return app
