import logging
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from starlette.middleware.base import BaseHTTPMiddleware

from app.api.routes import router
from app.core.config import assert_production_safe, settings
from app.core.database import SessionLocal
from app.core.errors import AppError
from app.core.limiter import limiter
from app.core.redis import redis_client

logger = logging.getLogger("wms")

OPENAPI_DESCRIPTION = """
Multi-tenant warehouse system for a 3PL.

Inventory quantity is never edited. It is the sum of the append-only ledger:

- physical = INBOUND + OUTBOUND + MOVE + ADJUSTMENT
- reserved = RESERVED
- available = physical − reserved

Customer users are scoped to their own customer. A customer token cannot read another customer's stock, orders, or files.
Warehouse roles share the building and must pass `customer_id` when the action is for one account.

Stock leaves the building only when a shipment is dispatched.
"""


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get("x-request-id") or str(uuid.uuid4())
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        return response


@asynccontextmanager
async def lifespan(_app: FastAPI):
    logging.basicConfig(level=logging.INFO)
    assert_production_safe()
    if settings.STORAGE_BACKEND == "local":
        Path(settings.LOCAL_STORAGE_PATH).mkdir(parents=True, exist_ok=True)
    yield


app = FastAPI(
    title="3PL Warehouse Management System",
    version="1.0.0",
    description=OPENAPI_DESCRIPTION,
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)
app.state.limiter = limiter
app.add_exception_handler(
    RateLimitExceeded,
    lambda request, exc: JSONResponse(status_code=429, content={"detail": "Too many requests", "code": "rate_limited"}),
)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(SlowAPIMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(router)


@app.exception_handler(AppError)
async def app_error(_request: Request, exc: AppError):
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.message, "code": exc.code})


@app.exception_handler(IntegrityError)
async def integrity_error(_request: Request, exc: IntegrityError):
    logger.warning("Integrity error: %s", exc)
    return JSONResponse(status_code=409, content={"detail": "Conflict with existing data", "code": "conflict"})


@app.get("/health", tags=["health"])
def health():
    db = SessionLocal()
    try:
        db.execute(text("SELECT 1"))
    finally:
        db.close()
    redis_status = "skipped"
    client = redis_client()
    if client is not None:
        try:
            client.ping()
            redis_status = "ok"
        except Exception:
            redis_status = "down"
        finally:
            client.close()
    return {"status": "ok", "database": "ok", "redis": redis_status}


@app.get("/", include_in_schema=False)
def root():
    return {"service": "3PL WMS", "docs": "/docs", "health": "/health"}
