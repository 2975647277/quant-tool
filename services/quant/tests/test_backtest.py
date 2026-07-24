from datetime import date

import pytest

from quant_service.research.backtest import (
    AShareBacktester,
    BacktestConfig,
    MarketBar,
    TargetPortfolio,
)

D1 = date(2024, 1, 2)
D2 = date(2024, 1, 3)
D3 = date(2024, 1, 4)
D4 = date(2024, 1, 5)


def _bar(
    trade_date: date,
    code: str = "600000",
    *,
    price: float = 10,
    volume: int = 1_000_000,
    suspended: bool = False,
    limit_up: bool = False,
    limit_down: bool = False,
) -> MarketBar:
    return MarketBar(
        trade_date=trade_date,
        code=code,
        open_price=price,
        close_price=price,
        volume_shares=volume,
        suspended=suspended,
        limit_up=limit_up,
        limit_down=limit_down,
    )


def _target(signal_date: date, weights: dict[str, float]) -> TargetPortfolio:
    return TargetPortfolio(
        signal_date=signal_date,
        weights=weights,
        model_version="test-model",
        data_version="test-data",
    )


def test_signals_execute_next_day_with_costs_and_limit_down_block() -> None:
    bars = [
        _bar(D1),
        _bar(D2),
        _bar(D3, limit_down=True),
        _bar(D4),
    ]
    targets = [
        _target(D1, {"600000": 1.0}),
        _target(D2, {}),
        _target(D3, {}),
    ]

    result = AShareBacktester().run(bars, targets)

    buy, sell = result.transactions
    assert buy.trade_date == D2
    assert sell.trade_date == D4
    assert buy.execution_price > buy.raw_price
    assert sell.execution_price < sell.raw_price
    assert buy.costs > 0
    assert sell.costs > buy.costs
    assert any(order.reason == "limit_down" for order in result.blocked_orders)
    assert result.final_holdings == {}


def test_limit_up_suspension_and_volume_capacity_block_buys() -> None:
    bars = [
        _bar(D1, "600000"),
        _bar(D1, "600001"),
        _bar(D1, "600002"),
        _bar(D2, "600000", limit_up=True),
        _bar(D2, "600001", suspended=True, volume=0),
        _bar(D2, "600002", volume=1_000),
    ]
    target = _target(
        D1,
        {"600000": 0.3, "600001": 0.3, "600002": 0.4},
    )
    config = BacktestConfig(initial_cash=100_000, max_volume_fraction=0.1)

    result = AShareBacktester(config).run(bars, [target])

    reasons = {order.reason for order in result.blocked_orders}
    assert {"limit_up", "suspended", "liquidity_or_cash"} <= reasons
    [transaction] = result.transactions
    assert transaction.code == "600002"
    assert transaction.shares == 100


def test_backtest_rejects_same_day_signal_execution() -> None:
    with pytest.raises(ValueError, match="at least one trading day"):
        BacktestConfig(execution_delay_days=0)
