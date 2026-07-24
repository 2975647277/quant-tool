from dataclasses import dataclass
from datetime import datetime

import numpy as np

from .types import PredictionRecord


@dataclass(frozen=True)
class PortfolioHolding:
    code: str
    score: float
    weight: float


@dataclass(frozen=True)
class PortfolioSnapshot:
    signal_date: np.datetime64
    holdings: tuple[PortfolioHolding, ...]
    model_version: str
    data_version: str
    predicted_at: datetime


def build_top_n_portfolios(
    predictions: list[PredictionRecord],
    *,
    top_n: int = 20,
    rebalance_every: int = 5,
) -> list[PortfolioSnapshot]:
    if top_n <= 0 or rebalance_every <= 0:
        raise ValueError("top_n and rebalance_every must be positive")
    if not predictions:
        return []

    by_date: dict[np.datetime64, list[PredictionRecord]] = {}
    for record in predictions:
        by_date.setdefault(record.trade_date, []).append(record)

    snapshots: list[PortfolioSnapshot] = []
    for date_index, signal_date in enumerate(sorted(by_date)):
        if date_index % rebalance_every != 0:
            continue
        records = sorted(
            by_date[signal_date],
            key=lambda record: (-record.score, record.code),
        )[:top_n]
        weight = 1 / len(records)
        snapshots.append(
            PortfolioSnapshot(
                signal_date=signal_date,
                holdings=tuple(
                    PortfolioHolding(
                        code=record.code,
                        score=record.score,
                        weight=weight,
                    )
                    for record in records
                ),
                model_version=records[0].model_version,
                data_version=records[0].data_version,
                predicted_at=max(record.predicted_at for record in records),
            )
        )
    return snapshots
