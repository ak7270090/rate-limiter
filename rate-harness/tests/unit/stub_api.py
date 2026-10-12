"""A tiny in-process API with a never-resetting per-key counter, for testing the harness itself."""

from collections import Counter

from fastapi import APIRouter, FastAPI, Request, Response

STUB_LIMIT = 5
STUB_WINDOW_SECONDS = 10
STUB_POLICY_NAME = "items"

stub_router = APIRouter()


@stub_router.get("/ping")
async def ping() -> dict[str, str]:
    return {"status": "ok"}


@stub_router.get("/items")
async def items(request: Request, response: Response) -> dict[str, str]:
    api_key = request.headers.get("X-API-Key", "anonymous")
    counts: Counter[str] = request.app.state.counts
    counts[api_key] += 1
    remaining = max(STUB_LIMIT - counts[api_key], 0)
    response.headers["X-Replica-Id"] = "stub-1"
    response.headers["RateLimit-Policy"] = (
        f'"{STUB_POLICY_NAME}";q={STUB_LIMIT};w={STUB_WINDOW_SECONDS}'
    )
    response.headers["RateLimit"] = f'"{STUB_POLICY_NAME}";r={remaining};t=3'
    if counts[api_key] > STUB_LIMIT:
        response.status_code = 429
        response.headers["Retry-After"] = "3"
    return {"api_key": api_key}


def create_stub_api() -> FastAPI:
    app = FastAPI()
    app.state.counts = Counter()
    app.include_router(stub_router)
    return app
