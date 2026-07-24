from datetime import UTC, date, datetime

import numpy as np

from quant_service.data.factors import FactorBuildResult, FactorQuality
from quant_service.models import (
    BacktestSummary,
    P2DataQuality,
    P2DataReport,
    P3ResearchReport,
    RankingMetricResult,
)
from quant_service.research.current import build_current_signal_report
from quant_service.research.types import RankingDataset


def test_current_signal_trains_on_labeled_rows_and_scores_latest_date() -> None:
    rng = np.random.default_rng(42)
    codes = np.asarray([f"{600000 + index:06d}" for index in range(25)])
    dates = np.busday_offset(
        np.datetime64("2025-01-02"),
        np.arange(90),
        roll="forward",
    )
    row_dates = np.repeat(dates, len(codes))
    row_codes = np.tile(codes, len(dates))
    features = rng.normal(size=(len(row_dates), 3))
    targets = features @ np.asarray([0.02, -0.01, 0.005])
    data_version = "p2-current-test"
    dataset = RankingDataset(
        dates=row_dates,
        codes=row_codes,
        features=features,
        targets=targets,
        feature_names=("momentum_5", "volatility_20", "roe_pit"),
        data_version=data_version,
    )
    signal_date = np.busday_offset(dates[-1], 10, roll="forward")
    latest = RankingDataset(
        dates=np.repeat(signal_date, len(codes)),
        codes=codes,
        features=rng.normal(size=(len(codes), 3)),
        targets=np.zeros(len(codes)),
        feature_names=dataset.feature_names,
        data_version=data_version,
    )
    factors = FactorBuildResult(
        dataset=dataset,
        latest_dataset=latest,
        market_bars=(),
        quality=FactorQuality(
            errors=(),
            warnings=(),
            dropped_dates=0,
            dropped_rows=0,
            imputed_values=0,
        ),
        financial_available_at=(None,) * len(dataset.dates),
        latest_financial_available_at=(None,) * len(latest.dates),
    )
    p2_report = _p2_report(data_version, signal_date)
    p3_report = _p3_report(data_version)

    report = build_current_signal_report(factors, p2_report, p3_report)

    assert report.signal_date == signal_date.astype("datetime64[D]").astype(object)
    assert report.training_end_date == dates[-1].astype("datetime64[D]").astype(object)
    assert report.training_sample_count == len(dataset.dates)
    assert len(report.rankings) == len(codes)
    assert [holding.rank for holding in report.rankings] == list(range(1, 26))
    assert np.isclose(sum(holding.weight or 0 for holding in report.rankings), 1)
    assert report.eligible_for_default is False


def _p2_report(data_version: str, signal_date: np.datetime64) -> P2DataReport:
    return P2DataReport(
        status="completed",
        provider_id="test",
        usage_scope="test",
        data_version=data_version,
        start_date="2025-01-02",
        end_date=str(signal_date),
        index_code="000300",
        universe_count=25,
        trading_days=100,
        stock_bar_count=2500,
        financial_record_count=100,
        factor_rows=2250,
        factor_dates=90,
        feature_names=["momentum_5", "volatility_20", "roe_pit"],
        point_in_time_enforced=True,
        universe_survivorship_safe=False,
        quality=P2DataQuality(
            errors=[],
            warnings=[],
            dropped_dates=0,
            dropped_rows=0,
            imputed_values=0,
        ),
        generated_at=datetime(2026, 7, 24, tzinfo=UTC),
        disclaimer="test",
    )


def _p3_report(data_version: str) -> P3ResearchReport:
    result = RankingMetricResult(
        model_version="lightgbm-lambdarank-v1",
        data_version=data_version,
        predicted_at=datetime(2026, 7, 24, tzinfo=UTC),
        rank_ic=0.04,
        icir=1.2,
        top_group_mean_excess_return=0.01,
        top_group_cumulative_excess_return=0.1,
        top_group_max_drawdown=0.18,
        top_group_individual_positive_excess_rate=0.52,
        top_group_daily_positive_excess_rate=0.55,
        evaluated_dates=50,
        eligible_for_default=False,
        admission_reasons=["max_drawdown_above_15_percent"],
    )
    return P3ResearchReport(
        status="completed_with_admission_blockers",
        simulated=False,
        data_version=data_version,
        feature_names=["momentum_5", "volatility_20", "roe_pit"],
        walk_forward_folds=2,
        embargo_trading_days=10,
        model_results=[result],
        latest_top20=[],
        backtest=BacktestSummary(
            total_return=0.1,
            max_drawdown=0.18,
            turnover=1,
            transaction_count=10,
            blocked_order_count=0,
            final_equity=1_100_000,
        ),
        covered_constraints=[],
        default_model=None,
        latest_signal_date=date(2026, 1, 1),
        generated_at=datetime(2026, 7, 24, tzinfo=UTC),
        disclaimer="test",
    )
