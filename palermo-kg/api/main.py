import os
import time
from collections import defaultdict, deque

from fastapi import FastAPI, Request
from contextlib import asynccontextmanager
from fastapi.responses import JSONResponse
from api.db import get_pool, close_pool
from api.routers import entity, geographies, insights, query, search, search_natural

@asynccontextmanager
async def lifespan(app: FastAPI):
    await get_pool()
    yield
    await close_pool()

app = FastAPI(
    title="CABA Knowledge Graph API",
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(entity.router, prefix="/api")
app.include_router(geographies.router, prefix="/api")
app.include_router(insights.router, prefix="/api")
app.include_router(query.router,  prefix="/api")
app.include_router(search.router, prefix="/api")
app.include_router(search_natural.router, prefix="/api")

_request_windows: dict[str, deque[float]] = defaultdict(deque)


@app.middleware("http")
async def protect_api(request: Request, call_next):
    """ProtecciÃ³n simple para despliegue individual; configurable por entorno."""
    if not request.url.path.startswith("/api/"):
        return await call_next(request)
    configured_key = os.getenv("KG_API_KEY")
    if configured_key and request.headers.get("x-api-key") != configured_key:
        return JSONResponse({"detail": "API key invÃ¡lida"}, status_code=401)
    client = request.client.host if request.client else "unknown"
    now = time.monotonic()
    window = _request_windows[client]
    while window and now - window[0] > 60:
        window.popleft()
    limit = int(os.getenv("KG_RATE_LIMIT_PER_MINUTE", "120"))
    if len(window) >= limit:
        return JSONResponse({"detail": "LÃ­mite de consultas excedido"}, status_code=429, headers={"Retry-After": "60"})
    window.append(now)
    return await call_next(request)

@app.get("/health")
async def health():
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.fetchval("SELECT 1")
    return {"status": "ok"}
