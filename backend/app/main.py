from __future__ import annotations

from contextlib import asynccontextmanager
import logging
import time
import uuid

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from starlette.responses import JSONResponse
from sqlalchemy import text
from redis.asyncio import Redis

from .background import create_scheduler
from .config import get_settings
from .database import AsyncSessionLocal
from .ratelimit import limiter
from .routers import API_ROUTERS
from .seeds import ensure_seed_data
from .services.observability import configure_json_logging, init_sentry, request_id_context


settings = get_settings()
configure_json_logging()
init_sentry(settings, service_name="backend")
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings.uploads_dir.mkdir(parents=True, exist_ok=True)
    async with AsyncSessionLocal() as session:
        await ensure_seed_data(session)
        await session.commit()
    scheduler = create_scheduler(settings)
    scheduler.start()
    try:
        yield
    finally:
        scheduler.shutdown(wait=False)


app = FastAPI(title="VPK Zvezda API", version="0.1.0", lifespan=lifespan)
app.state.limiter = limiter
app.add_middleware(SlowAPIMiddleware)


@app.middleware("http")
async def request_context_middleware(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex
    token = request_id_context.set(request_id)
    started = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        logger.exception("Unhandled request error", extra={"path": request.url.path})
        raise
    finally:
        elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
        logger.info("request completed method=%s path=%s duration_ms=%s", request.method, request.url.path, elapsed_ms)
        request_id_context.reset(token)
    response.headers["X-Request-ID"] = request_id
    return response

if settings.cors_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )


@app.exception_handler(RateLimitExceeded)
async def rate_limit_handler(request, exc):
    return JSONResponse(status_code=429, content={"detail": "Too many requests."})


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/readiness")
async def readiness() -> JSONResponse:
    checks: dict[str, str] = {}
    try:
        async with AsyncSessionLocal() as session:
            await session.execute(text("SELECT 1"))
        checks["postgres"] = "ok"
    except Exception:  # noqa: BLE001
        checks["postgres"] = "failed"
    if settings.redis_url:
        redis = Redis.from_url(settings.redis_url)
        try:
            await redis.ping()
            checks["redis"] = "ok"
        except Exception:  # noqa: BLE001
            checks["redis"] = "failed"
        finally:
            await redis.aclose()
    else:
        checks["redis"] = "not_configured"
    ready = checks["postgres"] == "ok" and checks["redis"] in {"ok", "not_configured"}
    return JSONResponse(status_code=200 if ready else 503, content={"status": "ready" if ready else "not_ready", "checks": checks})


for router in API_ROUTERS:
    app.include_router(router, prefix="/api")
