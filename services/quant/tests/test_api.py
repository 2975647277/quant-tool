import json
from datetime import UTC, datetime
from pathlib import Path

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
        "serviceVersion": "0.4.0",
        "mode": "historical-research",
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
    assert payload["latestSignalDate"]
    assert all(
        0 <= result["topGroupDailyPositiveExcessRate"] <= 1 for result in payload["modelResults"]
    )


async def test_real_research_endpoints_report_missing_artifacts(
    client: AsyncClient,
    session_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: object,
) -> None:
    monkeypatch.setenv("QUANT_DATA_DIR", str(tmp_path))

    p2 = await client.get("/v1/research/p2/status", headers=session_headers)
    p3 = await client.get("/v1/research/p3/real", headers=session_headers)

    assert p2.status_code == 404
    assert p3.status_code == 404
    assert "pnpm research:p2" in p2.json()["detail"]


def write_research_artifacts(data_dir: Path) -> None:
    data_version = "p2-real-test"
    generated_at = datetime(2026, 7, 24, tzinfo=UTC).isoformat()
    p2_report = {
        "status": "complete",
        "providerId": "test-provider",
        "usageScope": "test",
        "dataVersion": data_version,
        "startDate": "2020-01-01",
        "endDate": "2025-12-31",
        "indexCode": "000300.SH",
        "universeCount": 3,
        "tradingDays": 1000,
        "stockBarCount": 3000,
        "financialRecordCount": 30,
        "factorRows": 3000,
        "factorDates": 1000,
        "featureNames": ["momentum_20d"],
        "pointInTimeEnforced": True,
        "universeSurvivorshipSafe": False,
        "quality": {
            "errors": [],
            "warnings": ["test warning"],
            "droppedDates": 0,
            "droppedRows": 0,
            "imputedValues": 0,
        },
        "generatedAt": generated_at,
        "disclaimer": "test",
    }
    model_result = {
        "modelVersion": "lightgbm-lambdarank-v1",
        "dataVersion": data_version,
        "predictedAt": generated_at,
        "rankIc": 0.039,
        "icir": 2.94,
        "topGroupMeanExcessReturn": 0.009,
        "topGroupCumulativeExcessReturn": 0.18,
        "topGroupMaxDrawdown": 0.175,
        "topGroupIndividualPositiveExcessRate": 0.54,
        "topGroupDailyPositiveExcessRate": 0.532,
        "evaluatedDates": 100,
        "eligibleForDefault": False,
        "admissionReasons": ["max_drawdown_above_15_percent"],
    }
    p3_report = {
        "status": "complete",
        "simulated": False,
        "dataVersion": data_version,
        "featureNames": ["momentum_20d"],
        "walkForwardFolds": 4,
        "embargoTradingDays": 10,
        "modelResults": [model_result],
        "latestTop20": [
            {"code": "000001", "score": 1.25, "weight": 0.5},
            {"code": "000002", "score": 1.1, "weight": 0.5},
        ],
        "backtest": {
            "totalReturn": 0.1,
            "maxDrawdown": 0.12,
            "turnover": 1.5,
            "transactionCount": 10,
            "blockedOrderCount": 1,
            "finalEquity": 1.1,
        },
        "coveredConstraints": ["test"],
        "defaultModel": None,
        "latestSignalDate": "2025-12-17",
        "generatedAt": generated_at,
        "disclaimer": "test",
    }
    curated_dir = data_dir / "curated" / data_version
    model_dir = data_dir / "models" / data_version
    raw_dir = data_dir / "raw" / data_version
    curated_dir.mkdir(parents=True)
    model_dir.mkdir(parents=True)
    raw_dir.mkdir(parents=True)
    (data_dir / "curated" / "latest.json").write_text(
        json.dumps({"dataVersion": data_version}),
        encoding="utf-8",
    )
    (data_dir / "models" / "latest.json").write_text(
        json.dumps({"dataVersion": data_version}),
        encoding="utf-8",
    )
    (curated_dir / "p2-report.json").write_text(
        json.dumps(p2_report),
        encoding="utf-8",
    )
    (model_dir / "p3-real-report.json").write_text(
        json.dumps(p3_report),
        encoding="utf-8",
    )
    (raw_dir / "universe.jsonl").write_text(
        "\n".join(
            json.dumps({"code": code, "name": code}) for code in ("000001", "000002", "000003")
        ),
        encoding="utf-8",
    )


@pytest.mark.parametrize(
    ("code", "expected_coverage", "expected_rank"),
    [
        ("000001", "selected_top20", 1),
        ("000003", "covered_not_selected", None),
        ("002463", "not_covered", None),
    ],
)
async def test_stock_research_reports_real_coverage_without_fabricated_signal(
    client: AsyncClient,
    session_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    code: str,
    expected_coverage: str,
    expected_rank: int | None,
) -> None:
    write_research_artifacts(tmp_path)
    monkeypatch.setenv("QUANT_DATA_DIR", str(tmp_path))

    response = await client.get(
        f"/v1/stocks/{code}/research",
        params={"name": "测试股票"},
        headers=session_headers,
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["coverage"] == expected_coverage
    assert payload["top20Rank"] == expected_rank
    assert payload["isCurrentSignal"] is False
    assert payload["signalDate"] == "2025-12-17"
    assert payload["topGroupDailyPositiveExcessRate"] == pytest.approx(0.532)
    if expected_coverage == "not_covered":
        assert payload["top20Score"] is None
        assert payload["top20Weight"] is None
