import json
from datetime import UTC, date, datetime, timedelta
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
        "serviceVersion": "0.6.1",
        "mode": "current-daily-research",
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


async def test_stock_research_rejects_index_code_collision(
    client: AsyncClient,
    session_headers: dict[str, str],
) -> None:
    response = await client.get(
        "/v1/stocks/000001/research",
        params={"name": "上证指数"},
        headers=session_headers,
    )

    assert response.status_code == 422
    assert "不是个股" in response.json()["detail"]


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
    current = await client.get("/v1/research/p3/current", headers=session_headers)

    assert p2.status_code == 404
    assert p3.status_code == 404
    assert current.status_code == 404
    assert "pnpm research:p2" in p2.json()["detail"]


def write_research_artifacts(data_dir: Path) -> None:
    data_version = "p2-real-test"
    generated_at = datetime(2026, 7, 24, tzinfo=UTC).isoformat()
    signal_date = (date.today() - timedelta(days=1)).isoformat()
    p2_report = {
        "status": "complete",
        "providerId": "test-provider",
        "usageScope": "test",
        "dataVersion": data_version,
        "startDate": "2020-01-01",
        "endDate": signal_date,
        "indexCode": "000300.SH",
        "universeCount": 25,
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
    current_signal = {
        "status": "completed_with_admission_blockers",
        "dataVersion": data_version,
        "modelVersion": "lightgbm-lambdarank-v1",
        "signalDate": signal_date,
        "trainingStartDate": "2023-06-01",
        "trainingEndDate": "2026-07-09",
        "trainingSampleCount": 25000,
        "universeCount": 25,
        "rankings": [
            {
                "code": f"{index:06d}",
                "rank": index,
                "rankPercentile": index / 25,
                "score": 1 - index / 25,
                "weight": 0.05 if index <= 20 else None,
            }
            for index in range(1, 26)
        ],
        "eligibleForDefault": False,
        "admissionReasons": ["max_drawdown_above_15_percent"],
        "generatedAt": generated_at,
        "disclaimer": "current daily research test",
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
    (model_dir / "current-signal.json").write_text(
        json.dumps(current_signal),
        encoding="utf-8",
    )
    (raw_dir / "universe.jsonl").write_text(
        "\n".join(
            json.dumps({"code": f"{index:06d}", "name": f"{index:06d}"}) for index in range(1, 26)
        ),
        encoding="utf-8",
    )
    closes = [10 + index * 0.02 for index in range(62)] + [
        11.2,
        10.4,
        9.3,
        8.1,
        9.0,
        10.2,
        11.5,
        10.6,
        9.4,
        8.2,
        9.1,
        10.4,
        11.7,
        12.1,
        12.5,
        12.9,
        13.2,
        13.5,
    ]
    start = date(2026, 4, 1)
    (raw_dir / "daily-bars.jsonl").write_text(
        "\n".join(
            json.dumps(
                {
                    "trade_date": (start + timedelta(days=index)).isoformat(),
                    "code": "000001",
                    "open_price": close - 0.1,
                    "high_price": close + 0.25,
                    "low_price": close - 0.25,
                    "close_price": close,
                    "adjusted_close": close,
                    "volume_shares": 1_000_000 + index * 10_000,
                    "amount": close * (1_000_000 + index * 10_000),
                    "turnover": 0.01,
                    "outstanding_shares": 10_000_000_000,
                }
            )
            for index, close in enumerate(closes)
        )
        + "\n",
        encoding="utf-8",
    )


@pytest.mark.parametrize(
    ("code", "expected_coverage", "expected_rank"),
    [
        ("000001", "selected_top20", 1),
        ("000025", "covered_not_selected", None),
        ("002463", "not_covered", None),
    ],
)
async def test_stock_research_reports_current_daily_coverage(
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
    assert payload["isCurrentSignal"] is True
    assert payload["signalDate"] == (date.today() - timedelta(days=1)).isoformat()
    assert payload["signalAgeDays"] == 1
    assert payload["trainingEndDate"] == "2026-07-09"
    assert payload["topGroupDailyPositiveExcessRate"] == pytest.approx(0.532)
    if expected_coverage != "not_covered":
        assert payload["currentRank"] is not None
        assert payload["rankPercentile"] is not None
    if expected_coverage == "not_covered":
        assert payload["currentRank"] is None
        assert payload["currentScore"] is None
        assert payload["top20Score"] is None
        assert payload["top20Weight"] is None


async def test_current_signal_endpoint_exposes_training_and_signal_dates(
    client: AsyncClient,
    session_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    write_research_artifacts(tmp_path)
    monkeypatch.setenv("QUANT_DATA_DIR", str(tmp_path))

    response = await client.get(
        "/v1/research/p3/current",
        headers=session_headers,
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["signalDate"] == (date.today() - timedelta(days=1)).isoformat()
    assert payload["trainingEndDate"] == "2026-07-09"
    assert len(payload["rankings"]) == 25


async def test_stock_chart_exposes_real_bars_indicators_and_patterns(
    client: AsyncClient,
    session_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    write_research_artifacts(tmp_path)
    monkeypatch.setenv("QUANT_DATA_DIR", str(tmp_path))

    response = await client.get(
        "/v1/stocks/000001/chart",
        params={"name": "测试股票", "limit": 60},
        headers=session_headers,
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["stock"] == {"code": "000001", "name": "测试股票"}
    assert len(payload["points"]) == 60
    assert payload["points"][-1]["ma5"] is not None
    assert payload["points"][-1]["ma20"] is not None
    assert payload["points"][-1]["ma60"] is not None
    assert payload["points"][-1]["volumeMa5"] is not None
    assert payload["points"][-1]["volumeMa20"] is not None
    assert payload["latestVolumeShares"] > 0
    assert payload["volumeMa5"] > 0
    assert payload["volumeMa20"] > 0
    assert payload["volumeRatio"] > 0
    assert payload["volumeChangeRate"] is not None
    assert payload["latestRsi14"] is not None
    assert payload["patterns"]
    assert {"startDate", "startPrice", "endDate", "endPrice"}.issubset(
        payload["patterns"][0]["lines"][0]
    )
