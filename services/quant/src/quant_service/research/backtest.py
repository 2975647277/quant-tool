from dataclasses import dataclass, field
from datetime import date
from math import floor


@dataclass(frozen=True)
class CostModel:
    commission_rate: float = 0.0003
    minimum_commission: float = 5.0
    stamp_duty_rate: float = 0.0005
    transfer_fee_rate: float = 0.00001
    slippage_bps: float = 5.0

    def buy_cost(self, trade_value: float) -> float:
        return self._commission(trade_value) + trade_value * self.transfer_fee_rate

    def sell_cost(self, trade_value: float) -> float:
        return (
            self._commission(trade_value)
            + trade_value * self.transfer_fee_rate
            + trade_value * self.stamp_duty_rate
        )

    def execution_price(self, raw_price: float, side: str) -> float:
        slippage = self.slippage_bps / 10_000
        return raw_price * (1 + slippage if side == "buy" else 1 - slippage)

    def _commission(self, trade_value: float) -> float:
        if trade_value <= 0:
            return 0.0
        return max(self.minimum_commission, trade_value * self.commission_rate)


@dataclass(frozen=True)
class BacktestConfig:
    initial_cash: float = 1_000_000.0
    board_lot: int = 100
    max_volume_fraction: float = 0.1
    execution_delay_days: int = 1
    costs: CostModel = field(default_factory=CostModel)

    def __post_init__(self) -> None:
        if self.initial_cash <= 0:
            raise ValueError("initial_cash must be positive")
        if self.board_lot <= 0:
            raise ValueError("board_lot must be positive")
        if not 0 < self.max_volume_fraction <= 1:
            raise ValueError("max_volume_fraction must be within (0, 1]")
        if self.execution_delay_days < 1:
            raise ValueError("signals must execute at least one trading day later")


@dataclass(frozen=True)
class MarketBar:
    trade_date: date
    code: str
    open_price: float
    close_price: float
    volume_shares: int
    suspended: bool = False
    limit_up: bool = False
    limit_down: bool = False

    def __post_init__(self) -> None:
        if self.open_price <= 0 or self.close_price <= 0:
            raise ValueError("market prices must be positive")
        if self.volume_shares < 0:
            raise ValueError("volume_shares cannot be negative")


@dataclass(frozen=True)
class TargetPortfolio:
    signal_date: date
    weights: dict[str, float]
    model_version: str
    data_version: str

    def __post_init__(self) -> None:
        if any(weight < 0 for weight in self.weights.values()):
            raise ValueError("long-only target weights cannot be negative")
        if sum(self.weights.values()) > 1.000001:
            raise ValueError("target weights cannot exceed 100%")


@dataclass(frozen=True)
class Transaction:
    trade_date: date
    code: str
    side: str
    shares: int
    raw_price: float
    execution_price: float
    trade_value: float
    costs: float
    model_version: str
    data_version: str


@dataclass(frozen=True)
class BlockedOrder:
    trade_date: date
    code: str
    side: str
    requested_shares: int
    reason: str


@dataclass(frozen=True)
class EquityPoint:
    trade_date: date
    equity: float
    cash: float


@dataclass
class _Lot:
    acquired_date: date
    shares: int


@dataclass
class _Position:
    lots: list[_Lot] = field(default_factory=list)

    @property
    def shares(self) -> int:
        return sum(lot.shares for lot in self.lots)

    def available_shares(self, trade_date: date) -> int:
        return sum(lot.shares for lot in self.lots if lot.acquired_date < trade_date)

    def buy(self, trade_date: date, shares: int) -> None:
        self.lots.append(_Lot(acquired_date=trade_date, shares=shares))

    def sell(self, trade_date: date, shares: int) -> None:
        remaining = shares
        for lot in self.lots:
            if lot.acquired_date >= trade_date or remaining == 0:
                continue
            sold = min(lot.shares, remaining)
            lot.shares -= sold
            remaining -= sold
        self.lots = [lot for lot in self.lots if lot.shares > 0]
        if remaining:
            raise RuntimeError("attempted to sell unavailable T+1 shares")


@dataclass(frozen=True)
class BacktestResult:
    equity_curve: tuple[EquityPoint, ...]
    transactions: tuple[Transaction, ...]
    blocked_orders: tuple[BlockedOrder, ...]
    final_holdings: dict[str, int]
    total_return: float
    max_drawdown: float
    turnover: float


class AShareBacktester:
    def __init__(self, config: BacktestConfig | None = None) -> None:
        self.config = config or BacktestConfig()

    def run(
        self,
        bars: list[MarketBar],
        targets: list[TargetPortfolio],
    ) -> BacktestResult:
        if not bars:
            raise ValueError("backtest bars cannot be empty")
        bars_by_date: dict[date, dict[str, MarketBar]] = {}
        for bar in bars:
            date_bars = bars_by_date.setdefault(bar.trade_date, {})
            if bar.code in date_bars:
                raise ValueError(f"duplicate bar for {bar.code} on {bar.trade_date}")
            date_bars[bar.code] = bar

        targets_by_date = {target.signal_date: target for target in targets}
        dates = sorted(bars_by_date)
        cash = self.config.initial_cash
        positions: dict[str, _Position] = {}
        last_prices: dict[str, float] = {}
        transactions: list[Transaction] = []
        blocked_orders: list[BlockedOrder] = []
        equity_curve: list[EquityPoint] = []
        total_trade_value = 0.0

        for date_index, trade_date in enumerate(dates):
            date_bars = bars_by_date[trade_date]
            open_prices = {code: bar.open_price for code, bar in date_bars.items()}
            valuation_prices = {**last_prices, **open_prices}
            open_equity = cash + _holdings_value(positions, valuation_prices)

            signal_index = date_index - self.config.execution_delay_days
            if signal_index >= 0:
                signal = targets_by_date.get(dates[signal_index])
                if signal is not None:
                    cash, traded_value = self._rebalance(
                        trade_date=trade_date,
                        signal=signal,
                        equity=open_equity,
                        cash=cash,
                        positions=positions,
                        bars=date_bars,
                        transactions=transactions,
                        blocked_orders=blocked_orders,
                    )
                    total_trade_value += traded_value

            for code, bar in date_bars.items():
                last_prices[code] = bar.close_price
            close_equity = cash + _holdings_value(positions, last_prices)
            equity_curve.append(
                EquityPoint(
                    trade_date=trade_date,
                    equity=close_equity,
                    cash=cash,
                )
            )

        equities = [point.equity for point in equity_curve]
        average_equity = sum(equities) / len(equities)
        return BacktestResult(
            equity_curve=tuple(equity_curve),
            transactions=tuple(transactions),
            blocked_orders=tuple(blocked_orders),
            final_holdings={
                code: position.shares for code, position in positions.items() if position.shares > 0
            },
            total_return=equities[-1] / self.config.initial_cash - 1,
            max_drawdown=_equity_max_drawdown(equities),
            turnover=total_trade_value / average_equity if average_equity else 0.0,
        )

    def _rebalance(
        self,
        *,
        trade_date: date,
        signal: TargetPortfolio,
        equity: float,
        cash: float,
        positions: dict[str, _Position],
        bars: dict[str, MarketBar],
        transactions: list[Transaction],
        blocked_orders: list[BlockedOrder],
    ) -> tuple[float, float]:
        total_trade_value = 0.0
        all_codes = sorted(set(positions) | set(signal.weights))

        for code in all_codes:
            position = positions.setdefault(code, _Position())
            bar = bars.get(code)
            current_shares = position.shares
            target_weight = signal.weights.get(code, 0.0)
            desired_shares = (
                _round_lot(equity * target_weight / bar.open_price, self.config.board_lot)
                if bar is not None
                else 0
            )
            requested = max(0, current_shares - desired_shares)
            if requested == 0:
                continue
            if bar is None:
                _block(blocked_orders, trade_date, code, "sell", requested, "no_bar")
                continue
            reason = _blocked_reason(bar, "sell")
            if reason:
                _block(blocked_orders, trade_date, code, "sell", requested, reason)
                continue

            available = position.available_shares(trade_date)
            sellable = min(requested, available)
            volume_cap = _round_lot(
                bar.volume_shares * self.config.max_volume_fraction,
                self.config.board_lot,
            )
            shares = min(sellable, volume_cap)
            if shares > 0:
                execution_price = self.config.costs.execution_price(
                    bar.open_price,
                    "sell",
                )
                trade_value = shares * execution_price
                costs = self.config.costs.sell_cost(trade_value)
                position.sell(trade_date, shares)
                cash += trade_value - costs
                total_trade_value += trade_value
                transactions.append(
                    Transaction(
                        trade_date=trade_date,
                        code=code,
                        side="sell",
                        shares=shares,
                        raw_price=bar.open_price,
                        execution_price=execution_price,
                        trade_value=trade_value,
                        costs=costs,
                        model_version=signal.model_version,
                        data_version=signal.data_version,
                    )
                )
            if requested > shares:
                reason = "t_plus_one" if available < requested else "liquidity"
                _block(
                    blocked_orders,
                    trade_date,
                    code,
                    "sell",
                    requested - shares,
                    reason,
                )

        for code in sorted(signal.weights):
            bar = bars.get(code)
            if bar is None:
                _block(blocked_orders, trade_date, code, "buy", 0, "no_bar")
                continue
            position = positions.setdefault(code, _Position())
            desired_shares = _round_lot(
                equity * signal.weights[code] / bar.open_price,
                self.config.board_lot,
            )
            requested = max(0, desired_shares - position.shares)
            if requested == 0:
                continue
            reason = _blocked_reason(bar, "buy")
            if reason:
                _block(blocked_orders, trade_date, code, "buy", requested, reason)
                continue

            volume_cap = _round_lot(
                bar.volume_shares * self.config.max_volume_fraction,
                self.config.board_lot,
            )
            execution_price = self.config.costs.execution_price(
                bar.open_price,
                "buy",
            )
            affordable = _affordable_shares(
                cash,
                execution_price,
                self.config.board_lot,
                self.config.costs,
            )
            shares = min(requested, volume_cap, affordable)
            if shares > 0:
                trade_value = shares * execution_price
                costs = self.config.costs.buy_cost(trade_value)
                cash -= trade_value + costs
                total_trade_value += trade_value
                position.buy(trade_date, shares)
                transactions.append(
                    Transaction(
                        trade_date=trade_date,
                        code=code,
                        side="buy",
                        shares=shares,
                        raw_price=bar.open_price,
                        execution_price=execution_price,
                        trade_value=trade_value,
                        costs=costs,
                        model_version=signal.model_version,
                        data_version=signal.data_version,
                    )
                )
            if requested > shares:
                _block(
                    blocked_orders,
                    trade_date,
                    code,
                    "buy",
                    requested - shares,
                    "liquidity_or_cash",
                )
        return cash, total_trade_value


def _blocked_reason(bar: MarketBar, side: str) -> str | None:
    if bar.suspended or bar.volume_shares == 0:
        return "suspended"
    if side == "buy" and bar.limit_up:
        return "limit_up"
    if side == "sell" and bar.limit_down:
        return "limit_down"
    return None


def _block(
    blocked_orders: list[BlockedOrder],
    trade_date: date,
    code: str,
    side: str,
    shares: int,
    reason: str,
) -> None:
    blocked_orders.append(
        BlockedOrder(
            trade_date=trade_date,
            code=code,
            side=side,
            requested_shares=shares,
            reason=reason,
        )
    )


def _round_lot(shares: float, board_lot: int) -> int:
    return max(0, floor(shares / board_lot) * board_lot)


def _affordable_shares(
    cash: float,
    execution_price: float,
    board_lot: int,
    costs: CostModel,
) -> int:
    estimate = _round_lot(cash / execution_price, board_lot)
    while estimate > 0:
        value = estimate * execution_price
        if value + costs.buy_cost(value) <= cash:
            return estimate
        estimate -= board_lot
    return 0


def _holdings_value(
    positions: dict[str, _Position],
    prices: dict[str, float],
) -> float:
    return sum(position.shares * prices.get(code, 0.0) for code, position in positions.items())


def _equity_max_drawdown(equities: list[float]) -> float:
    peak = equities[0]
    maximum = 0.0
    for equity in equities:
        peak = max(peak, equity)
        maximum = max(maximum, 1 - equity / peak)
    return maximum
