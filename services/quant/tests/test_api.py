import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.anyio


async def test_health_requires_local_session(client: AsyncClient) -> None:
    assert (await client.get("/health")).status_code == 401


async def test_health_returns_service_mode(
    client: AsyncClient,
    session_headers: dict[str, str],
) -> None:
    response = await client.get("/health", headers=session_headers)

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "serviceVersion": "0.2.0",
        "mode": "mock",
    }


async def test_diagnosis_is_stable_and_camel_case(
    client: AsyncClient,
    session_headers: dict[str, str],
) -> None:
    first = await client.get(
        "/v1/stocks/600519/diagnosis",
        params={"name": "贵州茅台"},
        headers=session_headers,
    )
    second = await client.get(
        "/v1/stocks/600519/diagnosis",
        params={"name": "贵州茅台"},
        headers=session_headers,
    )

    assert first.status_code == 200
    assert first.json()["compositeScore"] == second.json()["compositeScore"]
    assert first.json()["stock"] == {"code": "600519", "name": "贵州茅台"}
    assert len(first.json()["dimensions"]) == 4
    assert first.json()["simulated"] is True


async def test_diagnosis_rejects_invalid_code(
    client: AsyncClient,
    session_headers: dict[str, str],
) -> None:
    response = await client.get(
        "/v1/stocks/ABC519/diagnosis",
        headers=session_headers,
    )

    assert response.status_code == 422


async def test_p3_demo_exposes_models_backtest_and_no_default(
    client: AsyncClient,
    session_headers: dict[str, str],
) -> None:
    response = await client.get(
        "/v1/research/p3/demo",
        headers=session_headers,
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["simulated"] is True
    assert payload["walkForwardFolds"] >= 1
    assert len(payload["modelResults"]) == 3
    assert len(payload["latestTop20"]) == 20
    assert payload["backtest"]["transactionCount"] > 0
    assert payload["defaultModel"] is None
    assert all(
        "simulated_data_cannot_be_default" in result["admissionReasons"]
        for result in payload["modelResults"]
    )
    assert all(
        result["dataVersion"] == payload["dataVersion"] and result["predictedAt"]
        for result in payload["modelResults"]
    )
