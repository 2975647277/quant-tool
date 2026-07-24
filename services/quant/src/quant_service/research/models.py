from collections.abc import Callable
from typing import Protocol

import numpy as np
from numpy.typing import NDArray

from .types import PredictionRecord, RankingDataset
from .walk_forward import WalkForwardConfig, build_walk_forward_folds


class RankModel(Protocol):
    model_version: str

    def fit(
        self,
        train: RankingDataset,
        validation: RankingDataset | None = None,
    ) -> None: ...

    def predict(self, dataset: RankingDataset) -> NDArray[np.float64]: ...


class RuleScoreModel:
    model_version = "rule-score-v1"

    def __init__(self, weights: dict[str, float] | None = None) -> None:
        self.weights = weights or {
            "momentum": 0.25,
            "quality": 0.25,
            "value": 0.18,
            "low_volatility": 0.14,
            "liquidity": 0.1,
            "reversal": 0.08,
        }
        self._feature_names: tuple[str, ...] | None = None

    def fit(
        self,
        train: RankingDataset,
        validation: RankingDataset | None = None,
    ) -> None:
        del validation
        self._feature_names = train.feature_names

    def predict(self, dataset: RankingDataset) -> NDArray[np.float64]:
        if self._feature_names is None:
            raise RuntimeError("rule model must be fitted before prediction")
        if dataset.feature_names != self._feature_names:
            raise ValueError("prediction feature names do not match training")
        weights = np.asarray(
            [self.weights.get(name, 0.0) for name in dataset.feature_names],
            dtype=np.float64,
        )
        if np.sum(np.abs(weights)) == 0:
            raise ValueError("at least one rule weight must match a feature")
        return dataset.features @ weights


class LinearFactorModel:
    model_version = "linear-factor-ridge-v1"

    def __init__(self, alpha: float = 1.0) -> None:
        self.alpha = alpha
        self._model: object | None = None
        self._feature_names: tuple[str, ...] | None = None

    def fit(
        self,
        train: RankingDataset,
        validation: RankingDataset | None = None,
    ) -> None:
        del validation
        from sklearn.linear_model import Ridge
        from sklearn.pipeline import make_pipeline
        from sklearn.preprocessing import StandardScaler

        self._feature_names = train.feature_names
        self._model = make_pipeline(StandardScaler(), Ridge(alpha=self.alpha))
        self._model.fit(train.features, train.targets)

    def predict(self, dataset: RankingDataset) -> NDArray[np.float64]:
        if self._model is None or self._feature_names is None:
            raise RuntimeError("linear model must be fitted before prediction")
        if dataset.feature_names != self._feature_names:
            raise ValueError("prediction feature names do not match training")
        return np.asarray(self._model.predict(dataset.features), dtype=np.float64)


class LightGBMRankModel:
    model_version = "lightgbm-lambdarank-v1"

    def __init__(self, random_state: int = 42) -> None:
        self.random_state = random_state
        self._model: object | None = None
        self._feature_names: tuple[str, ...] | None = None

    def fit(
        self,
        train: RankingDataset,
        validation: RankingDataset | None = None,
    ) -> None:
        from lightgbm import LGBMRanker, log_evaluation

        train = train.sorted_by_date()
        validation = validation.sorted_by_date() if validation is not None else None
        self._feature_names = train.feature_names
        self._model = LGBMRanker(
            objective="lambdarank",
            metric="ndcg",
            n_estimators=80,
            learning_rate=0.05,
            num_leaves=15,
            min_child_samples=12,
            reg_alpha=0.1,
            reg_lambda=0.2,
            random_state=self.random_state,
            n_jobs=1,
            verbosity=-1,
        )
        fit_kwargs: dict[str, object] = {
            "group": _group_sizes(train.dates),
            "eval_at": [5, 10, 20],
            "callbacks": [log_evaluation(0)],
        }
        if validation is not None:
            fit_kwargs.update(
                {
                    "eval_X": validation.features,
                    "eval_y": _relevance_labels(validation),
                    "eval_group": [_group_sizes(validation.dates)],
                    "eval_names": ["validation"],
                }
            )
        self._model.fit(
            train.features,
            _relevance_labels(train),
            **fit_kwargs,
        )

    def predict(self, dataset: RankingDataset) -> NDArray[np.float64]:
        if self._model is None or self._feature_names is None:
            raise RuntimeError("LightGBM model must be fitted before prediction")
        if dataset.feature_names != self._feature_names:
            raise ValueError("prediction feature names do not match training")
        return np.asarray(self._model.predict(dataset.features), dtype=np.float64)


def _group_sizes(dates: NDArray[np.datetime64]) -> list[int]:
    _, counts = np.unique(dates, return_counts=True)
    return counts.astype(int).tolist()


def _relevance_labels(
    dataset: RankingDataset,
    levels: int = 5,
) -> NDArray[np.int32]:
    labels = np.zeros(len(dataset.dates), dtype=np.int32)
    for trade_date in dataset.unique_dates:
        indices = np.flatnonzero(dataset.dates == trade_date)
        order = np.argsort(dataset.targets[indices], kind="stable")
        ordinal = np.empty(len(indices), dtype=np.int32)
        ordinal[order] = np.minimum(
            levels - 1,
            np.floor(np.arange(len(indices)) * levels / len(indices)).astype(np.int32),
        )
        labels[indices] = ordinal
    return labels


def run_walk_forward(
    dataset: RankingDataset,
    model_factory: Callable[[], RankModel],
    config: WalkForwardConfig,
) -> list[PredictionRecord]:
    dataset = dataset.sorted_by_date()
    folds = build_walk_forward_folds(dataset.dates, config)
    predictions: list[PredictionRecord] = []

    for fold in folds:
        train = dataset.subset(np.isin(dataset.dates, fold.train_dates))
        validation = dataset.subset(np.isin(dataset.dates, fold.validation_dates))
        test = dataset.subset(np.isin(dataset.dates, fold.test_dates))
        model = model_factory()
        model.fit(train, validation)
        scores = model.predict(test)
        predictions.extend(
            PredictionRecord.create(
                trade_date=trade_date,
                code=str(code),
                score=float(score),
                target_excess_return=float(target),
                model_version=model.model_version,
                data_version=dataset.data_version,
            )
            for trade_date, code, score, target in zip(
                test.dates,
                test.codes,
                scores,
                test.targets,
                strict=True,
            )
        )
    return predictions
