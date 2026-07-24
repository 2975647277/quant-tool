from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date

import numpy as np

from ..data.types import DailyBar
from ..models import (
    KlinePoint,
    StockChartView,
    StockContext,
    TechnicalDirection,
    TechnicalPattern,
    TechnicalPatternAnchor,
    TechnicalPatternLine,
)


@dataclass(frozen=True)
class Pivot:
    index: int
    trade_date: date
    price: float


def build_stock_chart(
    *,
    stock: StockContext,
    data_version: str,
    bars: Sequence[DailyBar],
    display_limit: int = 120,
) -> StockChartView:
    if len(bars) < 60:
        raise ValueError("at least 60 daily bars are required for technical analysis")
    ordered = sorted(bars, key=lambda item: item.trade_date)
    closes = np.asarray([bar.close_price for bar in ordered], dtype=np.float64)
    highs = np.asarray([bar.high_price for bar in ordered], dtype=np.float64)
    lows = np.asarray([bar.low_price for bar in ordered], dtype=np.float64)
    volumes = np.asarray([bar.volume_shares for bar in ordered], dtype=np.float64)

    ma5 = _rolling_mean(closes, 5)
    ma20 = _rolling_mean(closes, 20)
    ma60 = _rolling_mean(closes, 60)
    volume_ma5 = _rolling_mean(volumes, 5)
    volume_ma20 = _rolling_mean(volumes, 20)
    rsi14 = _rsi(closes, 14)
    macd, macd_signal, macd_histogram = _macd(closes)
    points = [
        KlinePoint(
            trade_date=bar.trade_date,
            open_price=bar.open_price,
            high_price=bar.high_price,
            low_price=bar.low_price,
            close_price=bar.close_price,
            volume_shares=bar.volume_shares,
            volume_ma5=_finite_or_none(volume_ma5[index]),
            volume_ma20=_finite_or_none(volume_ma20[index]),
            ma5=_finite_or_none(ma5[index]),
            ma20=_finite_or_none(ma20[index]),
            ma60=_finite_or_none(ma60[index]),
            rsi14=_finite_or_none(rsi14[index]),
            macd=_finite_or_none(macd[index]),
            macd_signal=_finite_or_none(macd_signal[index]),
            macd_histogram=_finite_or_none(macd_histogram[index]),
        )
        for index, bar in enumerate(ordered)
    ]

    patterns = _detect_patterns(ordered, highs, lows, closes, volumes)
    trend, trend_label, trend_summary = _classify_trend(
        closes,
        ma20,
        ma60,
        macd_histogram,
        patterns,
    )
    recent = ordered[-20:]
    visible = points[-display_limit:]
    latest_volume = int(volumes[-1])
    latest_volume_ma5 = float(volume_ma5[-1])
    latest_volume_ma20 = float(volume_ma20[-1])
    return StockChartView(
        stock=stock,
        data_version=data_version,
        start_date=visible[0].trade_date,
        end_date=visible[-1].trade_date,
        trend=trend,
        trend_label=trend_label,
        trend_summary=trend_summary,
        support_price=float(min(bar.low_price for bar in recent)),
        resistance_price=float(max(bar.high_price for bar in recent)),
        latest_volume_shares=latest_volume,
        volume_ma5=latest_volume_ma5,
        volume_ma20=latest_volume_ma20,
        volume_ratio=(latest_volume / latest_volume_ma20 if latest_volume_ma20 > 0 else 0),
        volume_change_rate=(float(latest_volume / volumes[-2] - 1) if volumes[-2] > 0 else None),
        latest_rsi14=_finite_or_none(rsi14[-1]),
        latest_macd_histogram=_finite_or_none(macd_histogram[-1]),
        points=visible,
        patterns=patterns[:3],
        disclaimer=(
            "技术形态由历史日线规则自动识别，拐点和关键线存在滞后与误判，"
            "仅供本地研究，不构成交易建议。"
        ),
    )


def _detect_patterns(
    bars: Sequence[DailyBar],
    highs: np.ndarray,
    lows: np.ndarray,
    closes: np.ndarray,
    volumes: np.ndarray,
) -> list[TechnicalPattern]:
    start = max(0, len(bars) - 80)
    high_pivots, low_pivots = _pivots(bars, start=start)
    patterns: list[TechnicalPattern] = []
    double_bottom = _double_bottom(bars, high_pivots, low_pivots, closes[-1])
    double_top = _double_top(bars, high_pivots, low_pivots, closes[-1])
    if double_bottom is not None:
        patterns.append(double_bottom)
    if double_top is not None:
        patterns.append(double_top)
    breakout = _breakout(bars, highs, lows, closes, volumes)
    if breakout is not None:
        patterns.append(breakout)
    channel = _channel(bars, high_pivots, low_pivots)
    if channel is not None:
        patterns.append(channel)
    consolidation = _consolidation(bars, highs, lows, closes)
    if not patterns and consolidation is not None:
        patterns.append(consolidation)
    return sorted(
        patterns,
        key=lambda pattern: (
            pattern.status == "已确认",
            pattern.confidence,
        ),
        reverse=True,
    )


def _pivots(
    bars: Sequence[DailyBar],
    *,
    start: int,
    window: int = 2,
) -> tuple[list[Pivot], list[Pivot]]:
    highs: list[Pivot] = []
    lows: list[Pivot] = []
    for index in range(max(start, window), len(bars) - window):
        neighbours = bars[index - window : index + window + 1]
        high = bars[index].high_price
        low = bars[index].low_price
        if high == max(item.high_price for item in neighbours):
            highs.append(Pivot(index, bars[index].trade_date, high))
        if low == min(item.low_price for item in neighbours):
            lows.append(Pivot(index, bars[index].trade_date, low))
    return highs, lows


def _double_bottom(
    bars: Sequence[DailyBar],
    highs: Sequence[Pivot],
    lows: Sequence[Pivot],
    latest_close: float,
) -> TechnicalPattern | None:
    for right in reversed(lows[-6:]):
        for left in reversed([pivot for pivot in lows if pivot.index < right.index]):
            separation = right.index - left.index
            difference = abs(right.price / left.price - 1)
            if not 5 <= separation <= 35 or difference > 0.035:
                continue
            middle_highs = [pivot for pivot in highs if left.index < pivot.index < right.index]
            if not middle_highs:
                continue
            neckline = max(middle_highs, key=lambda pivot: pivot.price)
            depth = neckline.price / max(left.price, right.price) - 1
            if depth < 0.04:
                continue
            confirmed = latest_close > neckline.price
            confidence = min(0.94, 0.62 + depth * 1.4 + (0.1 if confirmed else 0))
            return TechnicalPattern(
                kind="double_bottom",
                label="双底（W形态）",
                direction=TechnicalDirection.BULLISH,
                status="已确认" if confirmed else "形成中",
                confidence=confidence,
                summary=(
                    f"两次低点相差 {difference * 100:.1f}%，"
                    f"{'已突破' if confirmed else '尚未突破'}颈线 {neckline.price:.2f}。"
                ),
                anchors=[
                    _anchor(left, "左底"),
                    _anchor(neckline, "颈线"),
                    _anchor(right, "右底"),
                ],
                lines=[
                    _line(left, right, "双底支撑"),
                    TechnicalPatternLine(
                        start_date=left.trade_date,
                        start_price=neckline.price,
                        end_date=bars[-1].trade_date,
                        end_price=neckline.price,
                        label="颈线",
                    ),
                ],
            )
    return None


def _double_top(
    bars: Sequence[DailyBar],
    highs: Sequence[Pivot],
    lows: Sequence[Pivot],
    latest_close: float,
) -> TechnicalPattern | None:
    for right in reversed(highs[-6:]):
        for left in reversed([pivot for pivot in highs if pivot.index < right.index]):
            separation = right.index - left.index
            difference = abs(right.price / left.price - 1)
            if not 5 <= separation <= 35 or difference > 0.035:
                continue
            middle_lows = [pivot for pivot in lows if left.index < pivot.index < right.index]
            if not middle_lows:
                continue
            neckline = min(middle_lows, key=lambda pivot: pivot.price)
            depth = min(left.price, right.price) / neckline.price - 1
            if depth < 0.04:
                continue
            confirmed = latest_close < neckline.price
            confidence = min(0.94, 0.62 + depth * 1.4 + (0.1 if confirmed else 0))
            return TechnicalPattern(
                kind="double_top",
                label="双顶（M形态）",
                direction=TechnicalDirection.BEARISH,
                status="已确认" if confirmed else "形成中",
                confidence=confidence,
                summary=(
                    f"两次高点相差 {difference * 100:.1f}%，"
                    f"{'已跌破' if confirmed else '尚未跌破'}颈线 {neckline.price:.2f}。"
                ),
                anchors=[
                    _anchor(left, "左顶"),
                    _anchor(neckline, "颈线"),
                    _anchor(right, "右顶"),
                ],
                lines=[
                    _line(left, right, "双顶压力"),
                    TechnicalPatternLine(
                        start_date=left.trade_date,
                        start_price=neckline.price,
                        end_date=bars[-1].trade_date,
                        end_price=neckline.price,
                        label="颈线",
                    ),
                ],
            )
    return None


def _breakout(
    bars: Sequence[DailyBar],
    highs: np.ndarray,
    lows: np.ndarray,
    closes: np.ndarray,
    volumes: np.ndarray,
) -> TechnicalPattern | None:
    if len(bars) < 21:
        return None
    previous_high = float(np.max(highs[-21:-1]))
    previous_low = float(np.min(lows[-21:-1]))
    average_volume = float(np.mean(volumes[-21:-1]))
    volume_ratio = float(volumes[-1] / average_volume) if average_volume > 0 else 1
    current = bars[-1]
    if closes[-1] > previous_high * 1.003:
        return TechnicalPattern(
            kind="bullish_breakout",
            label="向上突破",
            direction=TechnicalDirection.BULLISH,
            status="已确认",
            confidence=min(0.95, 0.68 + max(volume_ratio - 1, 0) * 0.12),
            summary=f"收盘突破20日压力 {previous_high:.2f}，量比约 {volume_ratio:.2f}。",
            anchors=[
                TechnicalPatternAnchor(
                    trade_date=current.trade_date,
                    price=current.close_price,
                    label="突破",
                )
            ],
            lines=[
                TechnicalPatternLine(
                    start_date=bars[-21].trade_date,
                    start_price=previous_high,
                    end_date=current.trade_date,
                    end_price=previous_high,
                    label="原压力线",
                )
            ],
        )
    if closes[-1] < previous_low * 0.997:
        return TechnicalPattern(
            kind="bearish_breakdown",
            label="向下跌破",
            direction=TechnicalDirection.BEARISH,
            status="已确认",
            confidence=min(0.95, 0.68 + max(volume_ratio - 1, 0) * 0.12),
            summary=f"收盘跌破20日支撑 {previous_low:.2f}，量比约 {volume_ratio:.2f}。",
            anchors=[
                TechnicalPatternAnchor(
                    trade_date=current.trade_date,
                    price=current.close_price,
                    label="跌破",
                )
            ],
            lines=[
                TechnicalPatternLine(
                    start_date=bars[-21].trade_date,
                    start_price=previous_low,
                    end_date=current.trade_date,
                    end_price=previous_low,
                    label="原支撑线",
                )
            ],
        )
    return None


def _channel(
    bars: Sequence[DailyBar],
    highs: Sequence[Pivot],
    lows: Sequence[Pivot],
) -> TechnicalPattern | None:
    if len(highs) < 2 or len(lows) < 2:
        return None
    first_high, second_high = highs[-2:]
    first_low, second_low = lows[-2:]
    rising = second_high.price > first_high.price and second_low.price > first_low.price
    falling = second_high.price < first_high.price and second_low.price < first_low.price
    if not rising and not falling:
        return None
    direction = TechnicalDirection.BULLISH if rising else TechnicalDirection.BEARISH
    return TechnicalPattern(
        kind="ascending_channel" if rising else "descending_channel",
        label="上升通道" if rising else "下降通道",
        direction=direction,
        status="延续中",
        confidence=0.67,
        summary=(
            "近期高点和低点同步抬高，通道结构仍在延续。"
            if rising
            else "近期高点和低点同步下移，下降通道仍在延续。"
        ),
        anchors=[
            _anchor(first_low, "低点1"),
            _anchor(second_low, "低点2"),
            _anchor(first_high, "高点1"),
            _anchor(second_high, "高点2"),
        ],
        lines=[
            _extended_line(
                first_low,
                second_low,
                bars[-1],
                len(bars) - 1,
                "趋势支撑",
            ),
            _extended_line(
                first_high,
                second_high,
                bars[-1],
                len(bars) - 1,
                "趋势压力",
            ),
        ],
    )


def _consolidation(
    bars: Sequence[DailyBar],
    highs: np.ndarray,
    lows: np.ndarray,
    closes: np.ndarray,
) -> TechnicalPattern | None:
    if len(bars) < 20:
        return None
    resistance = float(np.max(highs[-20:]))
    support = float(np.min(lows[-20:]))
    width = resistance / max(support, 1e-9) - 1
    if width > 0.12:
        return None
    return TechnicalPattern(
        kind="consolidation",
        label="箱体震荡",
        direction=TechnicalDirection.SIDEWAYS,
        status="延续中",
        confidence=max(0.5, 0.78 - width),
        summary=f"近20日主要在 {support:.2f}–{resistance:.2f} 区间运行。",
        anchors=[],
        lines=[
            TechnicalPatternLine(
                start_date=bars[-20].trade_date,
                start_price=support,
                end_date=bars[-1].trade_date,
                end_price=support,
                label="箱体支撑",
            ),
            TechnicalPatternLine(
                start_date=bars[-20].trade_date,
                start_price=resistance,
                end_date=bars[-1].trade_date,
                end_price=resistance,
                label="箱体压力",
            ),
        ],
    )


def _classify_trend(
    closes: np.ndarray,
    ma20: np.ndarray,
    ma60: np.ndarray,
    macd_histogram: np.ndarray,
    patterns: Sequence[TechnicalPattern],
) -> tuple[TechnicalDirection, str, str]:
    primary = patterns[0] if patterns else None
    ma20_rising = np.isfinite(ma20[-6]) and ma20[-1] > ma20[-6]
    ma20_falling = np.isfinite(ma20[-6]) and ma20[-1] < ma20[-6]
    bullish = (
        np.isfinite(ma20[-1])
        and np.isfinite(ma60[-1])
        and closes[-1] > ma20[-1] > ma60[-1]
        and ma20_rising
        and macd_histogram[-1] > 0
    )
    bearish = (
        np.isfinite(ma20[-1])
        and np.isfinite(ma60[-1])
        and closes[-1] < ma20[-1] < ma60[-1]
        and ma20_falling
        and macd_histogram[-1] < 0
    )
    if bullish or (primary and primary.direction == TechnicalDirection.BULLISH):
        return (
            TechnicalDirection.BULLISH,
            "趋势偏强",
            "价格与中期均线结构偏多，结合形态观察支撑和突破有效性。",
        )
    if bearish or (primary and primary.direction == TechnicalDirection.BEARISH):
        return (
            TechnicalDirection.BEARISH,
            "趋势偏弱",
            "价格与中期均线结构偏空，结合形态观察压力和跌破风险。",
        )
    return (
        TechnicalDirection.SIDEWAYS,
        "震荡整理",
        "均线和动量尚未形成一致方向，重点观察箱体边界与放量突破。",
    )


def _rolling_mean(values: np.ndarray, window: int) -> np.ndarray:
    result = np.full(len(values), np.nan, dtype=np.float64)
    if len(values) < window:
        return result
    cumulative = np.cumsum(np.insert(values, 0, 0.0))
    result[window - 1 :] = (cumulative[window:] - cumulative[:-window]) / window
    return result


def _ema(values: np.ndarray, period: int) -> np.ndarray:
    result = np.empty(len(values), dtype=np.float64)
    result[0] = values[0]
    alpha = 2 / (period + 1)
    for index in range(1, len(values)):
        result[index] = alpha * values[index] + (1 - alpha) * result[index - 1]
    return result


def _macd(values: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    difference = _ema(values, 12) - _ema(values, 26)
    signal = _ema(difference, 9)
    return difference, signal, (difference - signal) * 2


def _rsi(values: np.ndarray, period: int) -> np.ndarray:
    result = np.full(len(values), np.nan, dtype=np.float64)
    if len(values) <= period:
        return result
    changes = np.diff(values)
    gains = np.maximum(changes, 0)
    losses = np.maximum(-changes, 0)
    for index in range(period, len(values)):
        average_gain = float(np.mean(gains[index - period : index]))
        average_loss = float(np.mean(losses[index - period : index]))
        if average_loss == 0:
            result[index] = 100
        else:
            relative_strength = average_gain / average_loss
            result[index] = 100 - 100 / (1 + relative_strength)
    return result


def _anchor(pivot: Pivot, label: str) -> TechnicalPatternAnchor:
    return TechnicalPatternAnchor(
        trade_date=pivot.trade_date,
        price=pivot.price,
        label=label,
    )


def _line(left: Pivot, right: Pivot, label: str) -> TechnicalPatternLine:
    return TechnicalPatternLine(
        start_date=left.trade_date,
        start_price=left.price,
        end_date=right.trade_date,
        end_price=right.price,
        label=label,
    )


def _extended_line(
    left: Pivot,
    right: Pivot,
    latest: DailyBar,
    latest_index: int,
    label: str,
) -> TechnicalPatternLine:
    span = max(right.index - left.index, 1)
    projected = right.price + (right.price - left.price) / span * (latest_index - right.index)
    return TechnicalPatternLine(
        start_date=left.trade_date,
        start_price=left.price,
        end_date=latest.trade_date,
        end_price=projected,
        label=label,
    )


def _finite_or_none(value: float) -> float | None:
    return float(value) if np.isfinite(value) else None
