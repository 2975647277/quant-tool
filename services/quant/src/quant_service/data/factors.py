from dataclasses import dataclass
from datetime import UTC, date, datetime, time
from math import sqrt
from zoneinfo import ZoneInfo

import numpy as np
from numpy.typing import NDArray

from ..research.backtest import MarketBar
from ..research.types import RankingDataset
from .types import DailyBar, FinancialRecord, MarketSnapshot

CORE_FACTOR_NAMES = (
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
SHANGHAI_TZ = ZoneInfo("Asia/Shanghai")


@dataclass(frozen=True)
class FactorBuildConfig:
    lookback_days: int = 60
    horizon_days: int = 10
    minimum_cross_section: int = 20
    max_missing_fraction: float = 0.4
    winsor_lower: float = 0.01
    winsor_upper: float = 0.99

    def __post_init__(self) -> None:
        if self.lookback_days < 60:
            raise ValueError("lookback_days must be at least 60")
        if self.horizon_days <= 0:
            raise ValueError("horizon_days must be positive")
        if self.minimum_cross_section < 2:
            raise ValueError("minimum_cross_section must be at least two")
        if not 0 <= self.max_missing_fraction < 1:
            raise ValueError("max_missing_fraction must be within [0, 1)")
        if not 0 <= self.winsor_lower < self.winsor_upper <= 1:
            raise ValueError("winsor quantiles are invalid")


@dataclass(frozen=True)
class FactorQuality:
    errors: tuple[str, ...]
    warnings: tuple[str, ...]
    dropped_dates: int
    dropped_rows: int
    imputed_values: int


@dataclass(frozen=True)
class FactorBuildResult:
    dataset: RankingDataset
    latest_dataset: RankingDataset
    market_bars: tuple[MarketBar, ...]
    quality: FactorQuality
    financial_available_at: tuple[datetime | None, ...]
    latest_financial_available_at: tuple[datetime | None, ...]


class PointInTimeFinancialIndex:
    def __init__(self, records: tuple[FinancialRecord, ...]) -> None:
        grouped: dict[str, list[FinancialRecord]] = {}
        for record in records:
            grouped.setdefault(record.code, []).append(record)
        self._records = {
            code: sorted(rows, key=lambda row: (row.available_at, row.report_date))
            for code, rows in grouped.items()
        }

    def latest(self, code: str, as_of: date) -> FinancialRecord | None:
        cutoff = _market_close(as_of)
        eligible = [
            record
            for record in self._records.get(code, [])
            if record.available_at <= cutoff and record.report_date <= as_of
        ]
        return max(eligible, key=lambda row: (row.report_date, row.available_at), default=None)

    def previous_year(
        self,
        code: str,
        current: FinancialRecord,
        as_of: date,
    ) -> FinancialRecord | None:
        cutoff = _market_close(as_of)
        expected_year = current.report_date.year - 1
        eligible = [
            record
            for record in self._records.get(code, [])
            if record.available_at <= cutoff
            and record.report_date.year == expected_year
            and record.report_date.month == current.report_date.month
            and record.report_date.day == current.report_date.day
        ]
        return max(eligible, key=lambda row: row.available_at, default=None)


def build_factor_dataset(
    snapshot: MarketSnapshot,
    *,
    data_version: str,
    config: FactorBuildConfig | None = None,
) -> FactorBuildResult:
    config = config or FactorBuildConfig()
    _validate_snapshot(snapshot)
    benchmark = {bar.trade_date: bar for bar in snapshot.index_bars}
    benchmark_dates = sorted(benchmark)
    benchmark_positions = {trade_date: index for index, trade_date in enumerate(benchmark_dates)}
    bars_by_code: dict[str, list[DailyBar]] = {}
    for bar in snapshot.bars:
        bars_by_code.setdefault(bar.code, []).append(bar)
    for bars in bars_by_code.values():
        bars.sort(key=lambda item: item.trade_date)

    financial_index = PointInTimeFinancialIndex(snapshot.financials)
    latest_dataset, latest_financial_available_at = _build_latest_factor_snapshot(
        bars_by_code,
        financial_index,
        benchmark_dates[-1],
        data_version,
        config,
    )
    raw_rows: list[tuple[date, str, list[float], float, datetime | None]] = []
    skipped_for_missing_future = 0
    for code, bars in sorted(bars_by_code.items()):
        by_date = {bar.trade_date: bar for bar in bars}
        stock_dates = sorted(by_date)
        for stock_position, trade_date in enumerate(stock_dates):
            benchmark_position = benchmark_positions.get(trade_date)
            if stock_position < config.lookback_days - 1 or benchmark_position is None:
                continue
            future_benchmark_position = benchmark_position + config.horizon_days
            if future_benchmark_position >= len(benchmark_dates):
                continue
            future_date = benchmark_dates[future_benchmark_position]
            future_bar = by_date.get(future_date)
            if future_bar is None:
                skipped_for_missing_future += 1
                continue
            history_dates = stock_dates[stock_position - 59 : stock_position + 1]
            history = [by_date[value] for value in history_dates]
            if len(history) != 60:
                continue
            current_bar = history[-1]
            stock_return = future_bar.adjusted_close / current_bar.adjusted_close - 1
            index_return = (
                benchmark[future_date].close_price / benchmark[trade_date].close_price - 1
            )
            financial = financial_index.latest(code, trade_date)
            previous = (
                financial_index.previous_year(code, financial, trade_date)
                if financial is not None
                else None
            )
            features = _raw_features(history, financial, previous)
            raw_rows.append(
                (
                    trade_date,
                    code,
                    features,
                    float(stock_return - index_return),
                    financial.available_at if financial is not None else None,
                )
            )

    if not raw_rows:
        raise ValueError("no factor rows could be built from the snapshot")
    grouped: dict[date, list[tuple[date, str, list[float], float, datetime | None]]] = {}
    for row in raw_rows:
        grouped.setdefault(row[0], []).append(row)

    output_dates: list[np.datetime64] = []
    output_codes: list[str] = []
    output_features: list[NDArray[np.float64]] = []
    output_targets: list[float] = []
    dropped_dates = 0
    dropped_rows = 0
    imputed_values = 0
    for trade_date, rows in sorted(grouped.items()):
        if len(rows) < config.minimum_cross_section:
            dropped_dates += 1
            dropped_rows += len(rows)
            continue
        matrix = np.asarray([row[2] for row in rows], dtype=np.float64)
        missing = ~np.isfinite(matrix)
        if np.any(np.mean(missing, axis=0) > config.max_missing_fraction):
            dropped_dates += 1
            dropped_rows += len(rows)
            continue
        imputed_values += int(np.sum(missing))
        normalized = _normalize_cross_section(matrix, config)
        for row, values in zip(rows, normalized, strict=True):
            output_dates.append(np.datetime64(trade_date.isoformat()))
            output_codes.append(row[1])
            output_features.append(values)
            output_targets.append(row[3])

    if not output_features:
        raise ValueError("all factor dates failed cross-sectional quality gates")
    warnings: list[str] = []
    if skipped_for_missing_future:
        warnings.append(f"rows_without_exact_horizon_bar:{skipped_for_missing_future}")
    if not snapshot.universe_survivorship_safe:
        warnings.append("current_constituent_universe_has_survivorship_bias")
    warnings.extend(
        (
            "historical_financial_revision_chain_unavailable",
            "broad_index_excess_label_used_until_historical_industry_membership_is_available",
        )
    )
    dataset = RankingDataset(
        dates=np.asarray(output_dates),
        codes=np.asarray(output_codes),
        features=np.vstack(output_features).astype(np.float64),
        targets=np.asarray(output_targets, dtype=np.float64),
        feature_names=CORE_FACTOR_NAMES,
        data_version=data_version,
        simulated=False,
    ).sorted_by_date()
    available_lookup = {(value[0], value[1]): value[4] for value in raw_rows}
    sorted_available = tuple(
        available_lookup[(trade_date.astype("datetime64[D]").astype(object), str(code))]
        for trade_date, code in zip(dataset.dates, dataset.codes, strict=True)
    )
    return FactorBuildResult(
        dataset=dataset,
        latest_dataset=latest_dataset,
        market_bars=tuple(build_market_bars(snapshot.bars)),
        quality=FactorQuality(
            errors=(),
            warnings=tuple(warnings),
            dropped_dates=dropped_dates,
            dropped_rows=dropped_rows,
            imputed_values=imputed_values,
        ),
        financial_available_at=sorted_available,
        latest_financial_available_at=latest_financial_available_at,
    )


def _build_latest_factor_snapshot(
    bars_by_code: dict[str, list[DailyBar]],
    financial_index: PointInTimeFinancialIndex,
    signal_date: date,
    data_version: str,
    config: FactorBuildConfig,
) -> tuple[RankingDataset, tuple[datetime | None, ...]]:
    rows: list[tuple[str, list[float], datetime | None]] = []
    for code, bars in sorted(bars_by_code.items()):
        by_date = {bar.trade_date: bar for bar in bars}
        if signal_date not in by_date:
            continue
        stock_dates = sorted(by_date)
        signal_position = stock_dates.index(signal_date)
        if signal_position < config.lookback_days - 1:
            continue
        history_dates = stock_dates[
            signal_position - config.lookback_days + 1 : signal_position + 1
        ]
        history = [by_date[value] for value in history_dates]
        if len(history) != config.lookback_days:
            continue
        financial = financial_index.latest(code, signal_date)
        previous = (
            financial_index.previous_year(code, financial, signal_date)
            if financial is not None
            else None
        )
        rows.append(
            (
                code,
                _raw_features(history, financial, previous),
                financial.available_at if financial is not None else None,
            )
        )

    if len(rows) < config.minimum_cross_section:
        raise ValueError(
            f"latest factor snapshot has only {len(rows)} rows; need {config.minimum_cross_section}"
        )
    matrix = np.asarray([row[1] for row in rows], dtype=np.float64)
    missing = ~np.isfinite(matrix)
    if np.any(np.mean(missing, axis=0) > config.max_missing_fraction):
        raise ValueError("latest factor snapshot failed missing-value quality gate")
    normalized = _normalize_cross_section(matrix, config)
    dataset = RankingDataset(
        dates=np.asarray([np.datetime64(signal_date.isoformat())] * len(rows)),
        codes=np.asarray([row[0] for row in rows]),
        features=normalized,
        targets=np.zeros(len(rows), dtype=np.float64),
        feature_names=CORE_FACTOR_NAMES,
        data_version=data_version,
        simulated=False,
    ).sorted_by_date()
    available_by_code = {row[0]: row[2] for row in rows}
    return dataset, tuple(available_by_code[str(code)] for code in dataset.codes)


def _raw_features(
    history: list[DailyBar],
    financial: FinancialRecord | None,
    previous: FinancialRecord | None,
) -> list[float]:
    adjusted = np.asarray([bar.adjusted_close for bar in history], dtype=np.float64)
    returns = np.diff(np.log(adjusted))
    turnovers = np.asarray(
        [bar.turnover if bar.turnover is not None else np.nan for bar in history],
        dtype=np.float64,
    )
    amounts = np.asarray([bar.amount for bar in history], dtype=np.float64)
    simple_returns = np.diff(adjusted) / adjusted[:-1]
    momentum_5 = adjusted[-1] / adjusted[-6] - 1
    momentum_20 = adjusted[-1] / adjusted[-21] - 1
    momentum_60 = adjusted[-1] / adjusted[0] - 1
    downside = returns[-20:][returns[-20:] < 0]
    peaks = np.maximum.accumulate(adjusted)
    drawdown = float(np.min(adjusted / peaks - 1))
    turnover_5 = _nanmean(turnovers[-5:])
    turnover_20 = _nanmean(turnovers[-20:])
    financial_values = _financial_features(financial, previous)
    return [
        float(momentum_5),
        float(momentum_20),
        float(momentum_60),
        float(-momentum_5),
        float(np.std(returns[-20:], ddof=1) * sqrt(252)),
        float(np.std(downside, ddof=1) * sqrt(252)) if len(downside) > 1 else np.nan,
        abs(drawdown),
        float(adjusted[-1] / np.max(adjusted) - 1),
        turnover_20,
        turnover_5 / turnover_20 - 1 if turnover_20 and np.isfinite(turnover_20) else np.nan,
        float(np.log1p(np.mean(amounts[-20:]))),
        float(np.mean(np.abs(simple_returns[-20:]) / np.maximum(amounts[-20:], 1)) * 1e9),
        *financial_values,
    ]


def _financial_features(
    current: FinancialRecord | None,
    previous: FinancialRecord | None,
) -> list[float]:
    if current is None:
        return [np.nan, np.nan, np.nan]
    equity = current.equity
    roe = (
        current.net_income / equity
        if current.net_income is not None and equity is not None and equity > 0
        else np.nan
    )
    leverage = (
        current.total_liabilities / current.total_assets
        if current.total_liabilities is not None
        and current.total_assets is not None
        and current.total_assets > 0
        else np.nan
    )
    growth = (
        current.revenue / previous.revenue - 1
        if previous is not None
        and current.revenue is not None
        and previous.revenue is not None
        and previous.revenue != 0
        else np.nan
    )
    return [float(roe), float(leverage), float(growth)]


def _normalize_cross_section(
    matrix: NDArray[np.float64],
    config: FactorBuildConfig,
) -> NDArray[np.float64]:
    result = matrix.copy()
    for column in range(result.shape[1]):
        values = result[:, column]
        finite = np.isfinite(values)
        median = float(np.median(values[finite]))
        values[~finite] = median
        lower, upper = np.quantile(
            values,
            [config.winsor_lower, config.winsor_upper],
        )
        values[:] = np.clip(values, lower, upper)
        standard_deviation = float(np.std(values))
        values[:] = (
            (values - float(np.mean(values))) / standard_deviation
            if standard_deviation > 0
            else 0.0
        )
    return result


def _nanmean(values: NDArray[np.float64]) -> float:
    finite = values[np.isfinite(values)]
    return float(np.mean(finite)) if len(finite) else np.nan


def _validate_snapshot(snapshot: MarketSnapshot) -> None:
    seen: set[tuple[date, str]] = set()
    for bar in snapshot.bars:
        key = (bar.trade_date, bar.code)
        if key in seen:
            raise ValueError(f"duplicate daily bar: {bar.code} {bar.trade_date}")
        seen.add(key)
        if min(bar.open_price, bar.high_price, bar.low_price, bar.close_price) <= 0:
            raise ValueError(f"non-positive OHLC: {bar.code} {bar.trade_date}")
        if bar.high_price < max(bar.open_price, bar.close_price, bar.low_price):
            raise ValueError(f"invalid high price: {bar.code} {bar.trade_date}")
        if bar.low_price > min(bar.open_price, bar.close_price, bar.high_price):
            raise ValueError(f"invalid low price: {bar.code} {bar.trade_date}")
        if bar.volume_shares < 0 or bar.amount < 0:
            raise ValueError(f"negative volume or amount: {bar.code} {bar.trade_date}")


def build_market_bars(bars: tuple[DailyBar, ...]) -> list[MarketBar]:
    output: list[MarketBar] = []
    prior_close: dict[str, float] = {}
    for bar in sorted(bars, key=lambda item: (item.trade_date, item.code)):
        previous = prior_close.get(bar.code)
        threshold = _price_limit_threshold(bar.code)
        change = bar.open_price / previous - 1 if previous else 0.0
        output.append(
            MarketBar(
                trade_date=bar.trade_date,
                code=bar.code,
                open_price=bar.open_price,
                close_price=bar.close_price,
                volume_shares=bar.volume_shares,
                suspended=bar.volume_shares == 0,
                limit_up=change >= threshold,
                limit_down=change <= -threshold,
            )
        )
        prior_close[bar.code] = bar.close_price
    return output


def _price_limit_threshold(code: str) -> float:
    if code.startswith(("300", "301", "688", "689")):
        return 0.195
    if code.startswith(("4", "8")):
        return 0.295
    return 0.095


def _market_close(trade_date: date) -> datetime:
    return datetime.combine(
        trade_date,
        time(hour=15),
        tzinfo=SHANGHAI_TZ,
    ).astimezone(UTC)
