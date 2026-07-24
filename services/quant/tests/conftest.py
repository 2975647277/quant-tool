from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient

from quant_service.main import app, configure_session_token


@pytest.fixture
def session_headers() -> dict[str, str]:
    return {"X-Quant-Session": "test-session"}


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
async def client() -> AsyncIterator[AsyncClient]:
    configure_session_token("test-session")
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as test_client:
        yield test_client
