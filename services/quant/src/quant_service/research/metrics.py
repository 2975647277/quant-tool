from dataclasses import dataclass
from math import sqrt

import numpy as np
from numpy.typing import NDArray

from .types import PredictionRecord


@dataclass(frozen=True)
class RankingMetrics:
    rank_ic: float
    icir: float
    top_group_mean_excess_return: float
    top_group_cumulative_excess_return: float
    top_group_max_drawdown: float
    evaluated_dates: int


def average_ranks(values: NDArray[np.float64]) -> NDArray[np.float64]:
    order = np.argsort(values, kind="stable")
    ranks = np.empty(len(values), dtype=np.float64)
    cursor = 0
    while cursor < len(values):
        end = cursor + 1
        while end < len(values) and values[order[end]] == values[order[cursor]]:
            end += 1
        ranks[order[cursor:end]] = (cursor + end - 1) / 2
        cursor = end
    return ranks


def spearman_rank_correlation(
    scores: NDArray[np.float64],
    targets: NDArray[np.float64],
) -> float:
    if len(scores) < 2:
        return 0.0
    score_ranks = average_ranks(scores)
    target_ranks = average_ranks(targets)
    if np.std(score_ranks) == 0 or np.std(target_ranks) == 0:
        return 0.0
    return float(np.corrcoef(score_ranks, target_ranks)[0, 1])


def max_drawdown(returns: NDArray[np.float64]) -> float:
    if len(returns) == 0:
        return 0.0
    equity = np.concatenate(
        [np.asarray([1.0]), np.cumprod(1 + returns)],
    )
    peaks = np.maximum.accumulate(equity)
    drawdowns = equity / peaks - 1
    return float(abs(np.min(drawdowns)))


def calculate_ranking_metrics(
    predictions: list[PredictionRecord],
    top_fraction: float = 0.1,
    holding_period_days: int = 10,
) -> RankingMetrics:
    if not predictions:
        raise ValueError("predictions cannot be empty")
    if not 0 < top_fraction <= 1:
        raise ValueError("top_fraction must be within (0, 1]")
    if holding_period_days <= 0:
        raise ValueError("holding_period_days must be positive")

    by_date: dict[np.datetime64, list[PredictionRecord]] = {}
    for record in predictions:
        by_date.setdefault(record.trade_date, []).append(record)

    daily_ics: list[float] = []
    top_returns: list[float] = []
    for trade_date in sorted(by_date):
        records = by_date[trade_date]
        scores = np.asarray([record.score for record in records], dtype=np.float64)
        targets = np.asarray(
            [record.target_excess_return for record in records],
            dtype=np.float64,
        )
        daily_ics.append(spearman_rank_correlation(scores, targets))
        top_count = max(1, int(np.ceil(len(records) * top_fraction)))
        top_indices = np.argsort(scores, kind="stable")[-top_count:]
        top_returns.append(float(np.mean(targets[top_indices])))

    ic_array = np.asarray(daily_ics, dtype=np.float64)
    top_array = np.asarray(top_returns, dtype=np.float64)
    rank_ic = float(np.mean(ic_array))
    ic_std = float(np.std(ic_array, ddof=1)) if len(ic_array) > 1 else 0.0
    icir = rank_ic / ic_std * sqrt(252) if ic_std > 0 else 0.0
    non_overlapping_top_returns = top_array[::holding_period_days]

    return RankingMetrics(
        rank_ic=rank_ic,
        icir=icir,
        top_group_mean_excess_return=float(np.mean(top_array)),
        top_group_cumulative_excess_return=float(np.prod(1 + non_overlapping_top_returns) - 1),
        top_group_max_drawdown=max_drawdown(non_overlapping_top_returns),
        evaluated_dates=len(by_date),
    )
