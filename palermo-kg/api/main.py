from fastapi import FastAPI
from contextlib import asynccontextmanager
from api.db import get_pool, close_pool
from api.routers import entity, insights, query, search, search_natural

@asynccontextmanager
async def lifespan(app: FastAPI):
    await get_pool()
    yield
    await close_pool()

app = FastAPI(
    title="Palermo Knowledge Graph API",
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(entity.router, prefix="/api")
app.include_router(insights.router, prefix="/api")
app.include_router(query.router,  prefix="/api")
app.include_router(search.router, prefix="/api")
app.include_router(search_natural.router, prefix="/api")

@app.get("/health")
async def health():
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.fetchval("SELECT 1")
    return {"status": "ok"}
