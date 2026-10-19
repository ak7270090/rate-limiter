"""The standard API: identical in every phase, so results are comparable."""

from fastapi import APIRouter

router = APIRouter()


@router.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/ping")
async def ping() -> dict[str, str]:
    return {"status": "pong"}


@router.get("/items")
async def list_items() -> dict[str, list[int]]:
    return {"items": [1, 2, 3]}


@router.post("/orders")
async def create_order() -> dict[str, str]:
    return {"status": "created"}


@router.get("/search")
async def search() -> dict[str, list[str]]:
    return {"results": []}


@router.post("/reports")
async def create_report() -> dict[str, str]:
    return {"status": "queued"}
