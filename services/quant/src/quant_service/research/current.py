from datetime import UTC, date, datetime

import numpy as np

from ..data.factors import FactorBuildResult
from ..models import (
    CurrentSignalHolding,
    CurrentSignalReport,
    P2DataReport,
    P3ResearchReport,
)
from .models import LightGBMRankModel

FINAL_TRAINING_DAYS = 756
MODEL_VERSION = "lightgbm-lambdarank-v1"


def build_current_signal_report(
    factors: FactorBuildResult,
    p2_report: P2DataReport,
    p3_report: P3ResearchReport,
) -> CurrentSignalReport:
    dataset = factors.dataset.sorted_by_date()
    latest = factors.latest_dataset.sorted_by_date()
    if dataset.simulated or latest.simulated:
        raise ValueError("current signal refuses simulated datasets")
    if not (
        dataset.data_version
        == latest.data_version
        == p2_report.data_version
        == p3_report.data_version
    ):
        raise ValueError("P2, P3, and latest factor data versions must match")
    if len(latest.unique_dates) != 1:
        raise ValueError("latest factor dataset must contain exactly one signal date")

    training_dates = dataset.unique_dates[-FINAL_TRAINING_DAYS:]
    training = dataset.subset(np.isin(dataset.dates, training_dates))
    model = LightGBMRankModel()
    model.fit(training)
    scores = model.predict(latest)
    order = np.lexsort((latest.codes, -scores))
    top_n = min(20, len(order))
    top_weight = 1 / top_n
    holdings: list[CurrentSignalHolding] = []
    for rank, row_index in enumerate(order, start=1):
        holdings.append(
            CurrentSignalHolding(
                code=str(latest.codes[row_index]),
                rank=rank,
                rank_percentile=rank / len(order),
                score=float(scores[row_index]),
                weight=top_weight if rank <= top_n else None,
            )
        )

    validation = next(
        (result for result in p3_report.model_results if result.model_version == MODEL_VERSION),
        None,
    )
    if validation is None:
        raise ValueError("LightGBM validation result is unavailable")
    return CurrentSignalReport(
        status=(
            "completed" if validation.eligible_for_default else "completed_with_admission_blockers"
        ),
        data_version=dataset.data_version,
        model_version=MODEL_VERSION,
        signal_date=_to_date(latest.unique_dates[0]),
        training_start_date=_to_date(training.unique_dates[0]),
        training_end_date=_to_date(training.unique_dates[-1]),
        training_sample_count=len(training.dates),
        universe_count=len(holdings),
        rankings=holdings,
        eligible_for_default=validation.eligible_for_default,
        admission_reasons=validation.admission_reasons,
        generated_at=datetime.now(UTC),
        disclaimer=(
            "这是使用最新已完成日线生成的实验性横截面研究信号，不是盘中实时模型，"
            "且模型尚未通过正式准入，不构成投资建议。"
        ),
    )


def _to_date(value: np.datetime64) -> date:
    return value.astype("datetime64[D]").astype(object)
