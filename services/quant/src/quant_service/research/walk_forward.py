from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray


@dataclass(frozen=True)
class WalkForwardConfig:
    train_days: int = 50
    validation_days: int = 10
    test_days: int = 10
    embargo_days: int = 10
    step_days: int = 10
    max_train_days: int | None = None

    def __post_init__(self) -> None:
        positive = (
            self.train_days,
            self.validation_days,
            self.test_days,
            self.step_days,
        )
        if any(value <= 0 for value in positive):
            raise ValueError("walk-forward day counts must be positive")
        if self.embargo_days < 0:
            raise ValueError("embargo_days cannot be negative")
        if self.max_train_days is not None and self.max_train_days < self.train_days:
            raise ValueError("max_train_days cannot be smaller than train_days")


@dataclass(frozen=True)
class WalkForwardFold:
    index: int
    train_dates: NDArray[np.datetime64]
    validation_dates: NDArray[np.datetime64]
    test_dates: NDArray[np.datetime64]

    @property
    def train_start(self) -> np.datetime64:
        return self.train_dates[0]

    @property
    def train_end(self) -> np.datetime64:
        return self.train_dates[-1]

    @property
    def validation_start(self) -> np.datetime64:
        return self.validation_dates[0]

    @property
    def test_start(self) -> np.datetime64:
        return self.test_dates[0]


def build_walk_forward_folds(
    dates: NDArray[np.datetime64],
    config: WalkForwardConfig,
) -> list[WalkForwardFold]:
    unique_dates = np.unique(dates)
    first_train_end = config.train_days
    folds: list[WalkForwardFold] = []
    train_end = first_train_end

    while True:
        validation_start = train_end + config.embargo_days
        validation_end = validation_start + config.validation_days
        test_start = validation_end + config.embargo_days
        test_end = test_start + config.test_days
        if test_end > len(unique_dates):
            break

        train_start = 0
        if config.max_train_days is not None:
            train_start = max(0, train_end - config.max_train_days)

        folds.append(
            WalkForwardFold(
                index=len(folds),
                train_dates=unique_dates[train_start:train_end],
                validation_dates=unique_dates[validation_start:validation_end],
                test_dates=unique_dates[test_start:test_end],
            )
        )
        train_end += config.step_days

    if not folds:
        required = (
            config.train_days + config.validation_days + config.test_days + 2 * config.embargo_days
        )
        raise ValueError(f"not enough dates for walk-forward validation: need at least {required}")
    return folds
