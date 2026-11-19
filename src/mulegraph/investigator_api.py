"""Local, bounded, read-only HTTP adapter over the existing frozen services."""

import os
from collections.abc import Awaitable, Callable, Iterator
from datetime import datetime, timedelta
from pathlib import Path
from threading import BoundedSemaphore
from typing import Annotated, Literal

import duckdb
import psycopg
from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware

from mulegraph.dashboard_data import DashboardData
from mulegraph.evidence_quality import assess_evidence
from mulegraph.explanations import ExplanationService
from mulegraph.graph import GraphLimitExceeded

ROOT = Path(__file__).resolve().parents[2]
slots = BoundedSemaphore(2)


def bounded_request() -> Iterator[None]:
    """Reject overload rather than queue expensive graph/model work without bound."""
    if not slots.acquire(blocking=False):
        raise HTTPException(429, "Two requests are already running. Try again shortly.")
    try:
        yield
    finally:
        slots.release()


def data_service() -> DashboardData:
    return DashboardData(ROOT)


def explanation_service() -> ExplanationService:
    return ExplanationService(ROOT)


app = FastAPI(
    title="MuleGraph local investigation API",
    docs_url=None,
    redoc_url=None,
    dependencies=[Depends(bounded_request)],
)
app.add_middleware(
    TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost", "testserver"]
)


@app.middleware("http")
async def private_response(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    response = await call_next(request)
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    return response


@app.exception_handler(GraphLimitExceeded)
async def limit_error(request: Request, exc: GraphLimitExceeded) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content={
            "detail": (
                "This history exceeds investigation limits. No partial network "
                "or findings were returned. Choose the 24-hour scope "
                "or reduce the date window."
            ),
            "code": "scope_limit",
        },
    )


@app.exception_handler(ValueError)
async def integrity_error(request: Request, exc: ValueError) -> JSONResponse:
    return JSONResponse(
        status_code=409,
        content={
            "detail": (
                "The request or frozen input checks failed. Check the dates; "
                "if valid, restore original artifacts. No model was changed."
            ),
            "code": "integrity",
        },
    )


async def unavailable(request: Request, exc: Exception) -> JSONResponse:
    return JSONResponse(
        status_code=503,
        content={
            "detail": (
                "Local data or database is unavailable. Start PostgreSQL "
                "and check the original artifact folders, then retry."
            ),
            "code": "unavailable",
        },
    )


for error in (OSError, psycopg.Error, duckdb.Error):
    app.add_exception_handler(error, unavailable)


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok", "mode": "local-read-only"}


@app.get("/api/queue")
def queue(
    data: Annotated[DashboardData, Depends(data_service)],
    split: Literal["validation", "test", "stress"] = "test",
    page: Annotated[int, Query(ge=0, le=1000)] = 0,
    source: Annotated[int | None, Query(ge=1)] = None,
    alerts_only: bool = True,
) -> dict:
    rows, more = data.queue(
        split, page=page, size=10, source=source, alerts_only=alerts_only
    )
    return {"transactions": rows, "more": more, "page": page, "split": split}


@app.get("/api/transactions/{source}/explanation")
def explain(
    source: int, service: Annotated[ExplanationService, Depends(explanation_service)]
) -> dict:
    if source < 1:
        raise HTTPException(422, "Source reference must be a positive integer.")
    result = service.explain([source])[0]
    if result["status"] == "SOURCE_NOT_FOUND":
        raise HTTPException(404, "No transaction exists with that source reference.")
    return result


@app.get("/api/transactions/{source}/investigation")
def investigate(
    source: int,
    data: Annotated[DashboardData, Depends(data_service)],
    service: Annotated[ExplanationService, Depends(explanation_service)],
    scope: Literal["day", "wide"] = "day",
    start: datetime | None = None,
    hops: Annotated[int, Query(ge=1, le=2)] = 1,
) -> dict:
    detail = explain(source, service)
    focal = detail["transaction"]
    cutoff = datetime.fromisoformat(focal["occurred_at"])
    lower = datetime(2022, 9, 1)
    begin = start or (
        max(lower, cutoff - timedelta(days=1)) if scope == "day" else lower
    )
    if begin.tzinfo is not None or not lower <= begin < cutoff:
        raise HTTPException(
            422,
            "Start must be September 1 or later and before the selected transfer, "
            "using source time without a timezone.",
        )
    dsn = os.environ.get("DATABASE_URL")
    if not dsn:
        raise HTTPException(
            503, "Start the API with --env-file .env to enable PostgreSQL."
        )
    report = data.investigate(
        dsn,
        begin,
        cutoff,
        account=(focal["from_bank_id"], focal["from_account"]),
        focal=source,
        hops=hops,
        nodes=500,
        edges=5000,
    )
    return {
        "report": report,
        "evidence_quality": assess_evidence(report),
        "focal_explanation": detail,
        "scope": scope,
        "hops": hops,
    }


# Built frontend shares the API origin; no cross-origin wildcard or write endpoints.
if (ROOT / "frontend/dist").is_dir():
    app.mount(
        "/", StaticFiles(directory=ROOT / "frontend/dist", html=True), name="frontend"
    )
