"""Prometheus metrics, served on ``/metrics`` by every replica."""

from fastapi import APIRouter, Response
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest

from ratelab.constants import METRICS_PATH

DECISIONS = Counter(
    "ratelab_decisions_total", "Rate limit decisions by route and outcome", ["route", "decision"]
)
LIMITER_SECONDS = Histogram(
    "ratelab_limiter_seconds",
    "Time the limiter took to decide",
    ["route"],
    buckets=(0.0005, 0.001, 0.002, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25),
)
STORE_FAILURES = Counter(
    "ratelab_store_failures_total",
    "Limiter calls that could not reach Redis, by what the route did instead",
    ["route", "action"],
)

metrics_router = APIRouter()


@metrics_router.get(METRICS_PATH, include_in_schema=False)
async def read_metrics() -> Response:
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
