from datetime import UTC, date, datetime, timedelta

import numpy as np
import pytest

from quant_service.data.factors import (
    CORE_FACTOR_NAMES,
    FactorBuildConfig,
    PointInTimeFinancialIndex,
    build_factor_dataset,
)
from quant_service.data.types import (
    DailyBar,
    DataProvenance,
    FinancialRecord,
    IndexBar,
    MarketSnapshot,
    UniverseMember,
)


def test_factor_dataset_is_real_finite_and_point_in_time() -> None:
    snapshot = _snapshot()
    result = build_factor_dataset(
        snapshot,
        data_version="p2-test-real",
        config=FactorBuildConfig(minimum_cross_section=3),
    )

    assert result.dataset.simulated is False
    assert result.dataset.feature_names == CORE_FACTOR_NAMES
    assert result.dataset.features.shape[1] == 15
    assert np.isfinite(result.dataset.features).all()
    assert np.isfinite(result.dataset.targets).all()
    assert len(result.dataset.unique_dates) > 40
    for trade_date, available_at in zip(
        result.dataset.dates,
        result.financial_available_at,
        strict=True,
    ):
        assert available_at is not None
        assert available_at.date() <= trade_date.astype("datetime64[D]").astype(object)


def test_factor_builder_rejects_duplicate_market_rows() -> None:
    snapshot = _snapshot()
    duplicate = MarketSnapshot(
        provenance=snapshot.provenance,
        universe=snapshot.universe,
        bars=(*snapshot.bars, snapshot.bars[0]),
        index_bars=snapshot.index_bars,
        financials=snapshot.financials,
        index_code=snapshot.index_code,
        acquired_at=snapshot.acquired_at,
        universe_survivorship_safe=False,
    )

    with pytest.raises(ValueError, match="duplicate daily bar"):
        build_factor_dataset(
            duplicate,
            data_version="p2-test-duplicate",
            config=FactorBuildConfig(minimum_cross_section=3),
        )


def test_financial_update_after_market_close_is_not_visible_same_day() -> None:
    prior = _financial(
        "600001",
        report_date=date(2023, 9, 30),
        available_at=datetime(2023, 10, 31, tzinfo=UTC),
        revenue=100,
    )
    after_close = _financial(
        "600001",
        report_date=date(2024, 3, 31),
        available_at=datetime(2024, 4, 30, 8, tzinfo=UTC),
        revenue=200,
    )
    index = PointInTimeFinancialIndex((prior, after_close))

    assert index.latest("600001", date(2024, 4, 30)) == prior
    assert index.latest("600001", date(2024, 5, 6)) == after_close


def _snapshot() -> MarketSnapshot:
    start = date(2024, 1, 2)
    trading_dates = [
        start + timedelta(days=offset)
        for offset in range(200)
        if (start + timedelta(days=offset)).weekday() < 5
    ]
    codes = ("600001", "600002", "000001", "000002")
    bars: list[DailyBar] = []
    for code_index, code in enumerate(codes):
        adjusted = 10.0 + code_index
        for day_index, trade_date in enumerate(trading_dates):
            daily_return = 0.001 + 0.004 * np.sin((day_index + code_index) / 4)
            adjusted *= 1 + daily_return
            close = adjusted / (1 + code_index * 0.01)
            bars.append(
                DailyBar(
                    trade_date=trade_date,
                    code=code,
                    open_price=close * 0.998,
                    high_price=close * 1.01,
                    low_price=close * 0.99,
                    close_price=close,
                    adjusted_close=adjusted,
                    volume_shares=1_000_000 + day_index * 100,
                    amount=close * (1_000_000 + day_index * 100),
                    turnover=0.01 + code_index * 0.001,
                    outstanding_shares=1_000_000_000,
                )
            )
    index_bars = tuple(
        IndexBar(
            trade_date=trade_date,
            code="000300",
            open_price=4000 + day_index,
            high_price=4010 + day_index,
            low_price=3990 + day_index,
            close_price=4005 + day_index,
            volume_shares=10_000_000,
        )
        for day_index, trade_date in enumerate(trading_dates)
    )
    financials: list[FinancialRecord] = []
    for code_index, code in enumerate(codes):
        financials.extend(
            (
                _financial(
                    code,
                    report_date=date(2022, 9, 30),
                    available_at=datetime(2022, 10, 31, tzinfo=UTC),
                    revenue=80 + code_index,
                ),
                _financial(
                    code,
                    report_date=date(2023, 9, 30),
                    available_at=datetime(2023, 10, 31, tzinfo=UTC),
                    revenue=100 + code_index,
                ),
                _financial(
                    code,
                    report_date=date(2024, 3, 31),
                    available_at=datetime(2025, 4, 30, tzinfo=UTC),
                    revenue=1_000_000,
                ),
            )
        )
    acquired_at = datetime(2026, 7, 24, tzinfo=UTC)
    return MarketSnapshot(
        provenance=(
            DataProvenance(
                provider_id="fixture",
                dataset="fixture",
                source_url="https://example.test",
                usage_scope="test",
                acquired_at=acquired_at,
                notes="fixture",
            ),
        ),
        universe=tuple(
            UniverseMember(
                code=code,
                name=code,
                exchange="test",
                observed_at=acquired_at.date(),
            )
            for code in codes
        ),
        bars=tuple(bars),
        index_bars=index_bars,
        financials=tuple(financials),
        index_code="000300",
        acquired_at=acquired_at,
        universe_survivorship_safe=False,
    )


def _financial(
    code: str,
    *,
    report_date: date,
    available_at: datetime,
    revenue: float,
) -> FinancialRecord:
    return FinancialRecord(
        code=code,
        report_date=report_date,
        announced_at=available_at,
        updated_at=available_at,
        available_at=available_at,
        revenue=revenue,
        net_income=10,
        total_assets=200,
        total_liabilities=80,
        operating_cashflow=12,
        currency="CNY",
    )
