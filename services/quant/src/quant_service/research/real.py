from datetime import date

import numpy as np

from ..data.factors import FactorBuildResult
from ..models import (
    BacktestSummary,
    P2DataReport,
    P3ResearchReport,
    PortfolioHoldingResult,
    RankingMetricResult,
)
from .backtest import AShareBacktester, TargetPortfolio
from .demo import MODEL_FACTORIES, admission_decision
from .metrics import calculate_ranking_metrics
from .models import run_walk_forward
from .portfolio import build_top_n_portfolios
from .walk_forward import WalkForwardConfig, build_walk_forward_folds

REAL_WALK_FORWARD = WalkForwardConfig(
    train_days=252,
    validation_days=63,
    test_days=63,
    embargo_days=10,
    step_days=63,
    max_train_days=756,
)


def build_p3_real_report(
    factors: FactorBuildResult,
    p2_report: P2DataReport,
) -> P3ResearchReport:
    dataset = factors.dataset
    if dataset.simulated:
        raise ValueError("real P3 validation refuses simulated datasets")
    folds = build_walk_forward_folds(dataset.dates, REAL_WALK_FORWARD)
    predictions_by_model = {}
    model_results: list[RankingMetricResult] = []
    data_blockers = _data_admission_blockers(p2_report)
    for model_version, factory in MODEL_FACTORIES:
        predictions = run_walk_forward(dataset, factory, REAL_WALK_FORWARD)
        predictions_by_model[model_version] = predictions
        metrics = calculate_ranking_metrics(predictions)
        eligible, reasons = admission_decision(metrics, simulated=False)
        reasons.extend(data_blockers)
        eligible = eligible and not data_blockers
        model_results.append(
            RankingMetricResult(
                model_version=model_version,
                data_version=dataset.data_version,
                predicted_at=max(item.predicted_at for item in predictions),
                rank_ic=metrics.rank_ic,
                icir=metrics.icir,
                top_group_mean_excess_return=metrics.top_group_mean_excess_return,
                top_group_cumulative_excess_return=metrics.top_group_cumulative_excess_return,
                top_group_max_drawdown=metrics.top_group_max_drawdown,
                evaluated_dates=metrics.evaluated_dates,
                eligible_for_default=eligible,
                admission_reasons=reasons,
            )
        )

    ranking_predictions = predictions_by_model["lightgbm-lambdarank-v1"]
    portfolios = build_top_n_portfolios(ranking_predictions, top_n=20, rebalance_every=5)
    if not portfolios:
        raise ValueError("real P3 validation produced no portfolio snapshots")
    targets = [
        TargetPortfolio(
            signal_date=_to_date(snapshot.signal_date),
            weights={holding.code: holding.weight for holding in snapshot.holdings},
            model_version=snapshot.model_version,
            data_version=snapshot.data_version,
        )
        for snapshot in portfolios
    ]
    backtest = AShareBacktester().run(list(factors.market_bars), targets)
    latest = portfolios[-1]
    default_candidate = max(
        (result for result in model_results if result.eligible_for_default),
        key=lambda item: item.rank_ic,
        default=None,
    )
    return P3ResearchReport(
        status="completed_with_admission_blockers" if data_blockers else "completed",
        simulated=False,
        data_version=dataset.data_version,
        feature_names=list(dataset.feature_names),
        walk_forward_folds=len(folds),
        embargo_trading_days=REAL_WALK_FORWARD.embargo_days,
        model_results=model_results,
        latest_top20=[
            PortfolioHoldingResult(
                code=holding.code,
                score=holding.score,
                weight=holding.weight,
            )
            for holding in latest.holdings
        ],
        backtest=BacktestSummary(
            total_return=backtest.total_return,
            max_drawdown=backtest.max_drawdown,
            turnover=backtest.turnover,
            transaction_count=len(backtest.transactions),
            blocked_order_count=len(backtest.blocked_orders),
            final_equity=backtest.equity_curve[-1].equity,
        ),
        covered_constraints=[
            "real_unadjusted_execution_prices",
            "real_adjusted_return_features",
            "signals_execute_next_trading_day",
            "t_plus_one",
            "opening_price_limit_estimate_by_board",
            "missing_bar_trade_block",
            "commission",
            "sell_stamp_duty",
            "transfer_fee",
            "slippage",
            "volume_capacity",
        ],
        default_model=default_candidate.model_version if default_candidate else None,
        generated_at=latest.predicted_at,
        disclaimer=(
            "本报告使用真实历史数据完成研究流程验证，不构成投资建议。"
            "当前成分股幸存者偏差、财务历史修订链和历史行业成员数据未解决前，"
            "任何模型均不得成为正式默认模型。"
        ),
    )


def _data_admission_blockers(report: P2DataReport) -> list[str]:
    blockers = list(report.quality.errors)
    blockers.extend(
        warning
        for warning in report.quality.warnings
        if warning
        in {
            "current_constituent_universe_has_survivorship_bias",
            "historical_financial_revision_chain_unavailable",
            "broad_index_excess_label_used_until_historical_industry_membership_is_available",
        }
    )
    return list(dict.fromkeys(blockers))


def _to_date(value: np.datetime64) -> date:
    return value.astype("datetime64[D]").astype(object)
