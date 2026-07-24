import numpy as np

from quant_service.research.walk_forward import (
    WalkForwardConfig,
    build_walk_forward_folds,
)


def test_walk_forward_keeps_ten_day_embargoes() -> None:
    dates = np.arange(
        np.datetime64("2024-01-01"),
        np.datetime64("2024-05-01"),
    )
    config = WalkForwardConfig(
        train_days=20,
        validation_days=5,
        test_days=5,
        embargo_days=10,
        step_days=5,
    )

    first = build_walk_forward_folds(dates, config)[0]

    assert first.validation_start - first.train_end == np.timedelta64(11, "D")
    assert first.test_start - first.validation_dates[-1] == np.timedelta64(11, "D")
    assert len(first.train_dates) == 20
    assert len(first.validation_dates) == 5
    assert len(first.test_dates) == 5
