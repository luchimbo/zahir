import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pytest
import httpx
from dotenv import load_dotenv

load_dotenv()

from api.main import app


@pytest.fixture(scope="session", autouse=True)
async def _close_pool_at_session_end():
    yield
    from api.db import close_pool

    await close_pool()


@pytest.fixture
async def client():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver", timeout=60
    ) as async_client:
        yield async_client
