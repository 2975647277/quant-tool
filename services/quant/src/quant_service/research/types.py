from dataclasses import dataclass
from datetime import UTC, datetime

import numpy as np
from numpy.typing import NDArray


@dataclass(frozen=True)
class RankingDataset:
    dates: NDArray[np.datetime64]
    codes: NDArray[np.str_]
    features: NDArray[np.float64]
    targets: NDArray[np.float64]
    feature_names: tuple[str, ...]
    data_version: str
    simulated: bool = False

    def __post_init__(self) -> None:
        row_count = len(self.dates)
        if self.features.ndim != 2:
            raise ValueError("features must be a two-dimensional matrix")
        if not (row_count == len(self.codes) == len(self.features) == len(self.targets)):
            raise ValueError("dataset arrays must contain the same number of rows")
        if self.features.shape[1] != len(self.feature_names):
            raise ValueError("feature_names must match the feature matrix width")
        if row_count == 0:
            raise ValueError("ranking dataset cannot be empty")
        if not np.isfinite(self.features).all() or not np.isfinite(self.targets).all():
            raise ValueError("ranking dataset cannot contain NaN or infinity")

    @property
    def unique_dates(self) -> NDArray[np.datetime64]:
        return np.unique(self.dates)

    def subset(self, mask: NDArray[np.bool_]) -> "RankingDataset":
        return RankingDataset(
            dates=self.dates[mask],
            codes=self.codes[mask],
            features=self.features[mask],
            targets=self.targets[mask],
            feature_names=self.feature_names,
            data_version=self.data_version,
            simulated=self.simulated,
        )

    def sorted_by_date(self) -> "RankingDataset":
        order = np.lexsort((self.codes, self.dates))
        return RankingDataset(
            dates=self.dates[order],
            codes=self.codes[order],
            features=self.features[order],
            targets=self.targets[order],
            feature_names=self.feature_names,
            data_version=self.data_version,
            simulated=self.simulated,
        )


@dataclass(frozen=True)
class PredictionRecord:
    trade_date: np.datetime64
    code: str
    score: float
    target_excess_return: float
    model_version: str
    data_version: str
    predicted_at: datetime

    @classmethod
    def create(
        cls,
        *,
        trade_date: np.datetime64,
        code: str,
        score: float,
        target_excess_return: float,
        model_version: str,
        data_version: str,
    ) -> "PredictionRecord":
        return cls(
            trade_date=trade_date,
            code=code,
            score=score,
            target_excess_return=target_excess_return,
            model_version=model_version,
            data_version=data_version,
            predicted_at=datetime.now(UTC),
        )
