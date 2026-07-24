from datetime import UTC, datetime

import numpy as np
import pytest

from quant_service.research.metrics import (
    calculate_ranking_metrics,
    max_drawdown,
    spearman_rank_correlation,
)
from quant_service.research.models import RuleScoreModel
from quant_service.research.portfolio import build_top_n_portfolios
from quant_service.research.types import PredictionRecord, RankingDataset


def _record(day: str, index: int, score: float, target: float) -> PredictionRecord:
    return PredictionRecord(
        trade_date=np.datetime64(day),
        code=f"{600000 + index:06d}",
        score=score,
        target_excess_return=target,
        model_version="test-model",
        data_version="test-data",
        predicted_at=datetime(2026, 7, 24, tzinfo=UTC),
    )


def test_rank_metrics_reward_correct_cross_sectional_order() -> None:
    predictions = [
        _record(day, index, float(index), index / 1000)
        for day in ("2024-01-02", "2024-01-03")
        for index in range(20)
    ]

    metrics = calculate_ranking_metrics(predictions)

    assert metrics.rank_ic == pytest.approx(1.0)
    assert metrics.top_group_mean_excess_return > 0
    assert metrics.evaluated_dates == 2


def test_spearman_handles_ties_and_drawdown() -> None:
    correlation = spearman_rank_correlation(
        np.asarray([1.0, 1.0, 2.0]),
        np.asarray([1.0, 1.0, 3.0]),
    )

    assert correlation == pytest.approx(1.0)
    assert max_drawdown(np.asarray([0.1, -0.2, 0.05])) == pytest.approx(0.2)
    assert max_drawdown(np.asarray([-0.1])) == pytest.approx(0.1)


def test_top_20_portfolio_is_equal_weighted_and_versioned() -> None:
    predictions = [_record("2024-01-02", index, float(index), index / 1000) for index in range(25)]

    [portfolio] = build_top_n_portfolios(predictions)

    assert len(portfolio.holdings) == 20
    assert sum(holding.weight for holding in portfolio.holdings) == pytest.approx(1)
    assert portfolio.holdings[0].code == "600024"
    assert portfolio.model_version == "test-model"
    assert portfolio.data_version == "test-data"


def test_rule_model_supports_p2_factor_names() -> None:
    feature_names = (
        "momentum_5",
        "momentum_20",
        "momentum_60",
        "reversal_5",
        "volatility_20",
        "downside_volatility_20",
        "max_drawdown_60",
        "price_to_high_60",
        "turnover_mean_20",
        "turnover_change_5_20",
        "amount_log_mean_20",
        "amihud_20",
        "roe_pit",
        "debt_to_assets_pit",
        "revenue_growth_pit",
    )
    dataset = RankingDataset(
        dates=np.asarray([np.datetime64("2024-01-02")] * 2),
        codes=np.asarray(["600001", "600002"]),
        features=np.asarray(
            [
                [0.2, 0.1, 0.3, -0.2, 0.1, 0.2, 0.1, -0.1, 0, 0.1, 0.2, 0.1, 0.3, 0.2, 0.4],
                [-0.2, -0.1, -0.3, 0.2, 0.2, 0.1, 0.2, -0.2, 0.1, 0, 0.1, 0.2, 0.2, 0.3, 0.1],
            ],
            dtype=np.float64,
        ),
        targets=np.asarray([0.01, -0.01], dtype=np.float64),
        feature_names=feature_names,
        data_version="p2-test",
        simulated=False,
    )
    model = RuleScoreModel()
    model.fit(dataset)

    assert np.isfinite(model.predict(dataset)).all()
