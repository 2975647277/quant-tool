from datetime import date
from functools import lru_cache

import numpy as np

from ..models import (
    BacktestSummary,
    P3ResearchReport,
    PortfolioHoldingResult,
    RankingMetricResult,
)
from .backtest import AShareBacktester, MarketBar, TargetPortfolio
from .metrics import RankingMetrics, calculate_ranking_metrics
from .models import (
    LightGBMRankModel,
    LinearFactorModel,
    RuleScoreModel,
    run_walk_forward,
)
from .portfolio import build_top_n_portfolios
from .types import RankingDataset
from .walk_forward import WalkForwardConfig, build_walk_forward_folds

FEATURE_NAMES = (
    "momentum",
    "quality",
    "value",
    "low_volatility",
    "liquidity",
    "reversal",
)
DATA_VERSION = "p3-deterministic-research-v1"
MODEL_FACTORIES = (
    ("rule-score-v1", RuleScoreModel),
    ("linear-factor-ridge-v1", LinearFactorModel),
    ("lightgbm-lambdarank-v1", LightGBMRankModel),
)


@lru_cache(maxsize=1)
def build_p3_demo_report() -> P3ResearchReport:
    dataset = build_deterministic_research_dataset()
    config = WalkForwardConfig()
    model_results: list[RankingMetricResult] = []
    predictions_by_model = {}

    for model_version, factory in MODEL_FACTORIES:
        predictions = run_walk_forward(dataset, factory, config)
        predictions_by_model[model_version] = predictions
        metrics = calculate_ranking_metrics(predictions)
        eligible, reasons = admission_decision(metrics, dataset.simulated)
        model_results.append(
            RankingMetricResult(
                model_version=model_version,
                data_version=dataset.data_version,
                predicted_at=max(prediction.predicted_at for prediction in predictions),
                rank_ic=metrics.rank_ic,
                icir=metrics.icir,
                top_group_mean_excess_return=metrics.top_group_mean_excess_return,
                top_group_cumulative_excess_return=(metrics.top_group_cumulative_excess_return),
                top_group_max_drawdown=metrics.top_group_max_drawdown,
                evaluated_dates=metrics.evaluated_dates,
                eligible_for_default=eligible,
                admission_reasons=reasons,
            )
        )

    ranking_predictions = predictions_by_model["lightgbm-lambdarank-v1"]
    portfolios = build_top_n_portfolios(ranking_predictions)
    targets = [
        TargetPortfolio(
            signal_date=_to_date(snapshot.signal_date),
            weights={holding.code: holding.weight for holding in snapshot.holdings},
            model_version=snapshot.model_version,
            data_version=snapshot.data_version,
        )
        for snapshot in portfolios
    ]
    backtest_result = AShareBacktester().run(
        build_deterministic_market_bars(dataset),
        targets,
    )
    latest = portfolios[-1]
    default_candidate = max(
        (result for result in model_results if result.eligible_for_default),
        key=lambda result: result.rank_ic,
        default=None,
    )

    return P3ResearchReport(
        status="completed",
        simulated=True,
        data_version=dataset.data_version,
        feature_names=list(dataset.feature_names),
        walk_forward_folds=len(build_walk_forward_folds(dataset.dates, config)),
        embargo_trading_days=config.embargo_days,
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
            total_return=backtest_result.total_return,
            max_drawdown=backtest_result.max_drawdown,
            turnover=backtest_result.turnover,
            transaction_count=len(backtest_result.transactions),
            blocked_order_count=len(backtest_result.blocked_orders),
            final_equity=backtest_result.equity_curve[-1].equity,
        ),
        covered_constraints=[
            "signals_execute_next_trading_day",
            "t_plus_one",
            "limit_up_buy_block",
            "limit_down_sell_block",
            "suspension",
            "commission",
            "sell_stamp_duty",
            "transfer_fee",
            "slippage",
            "volume_capacity",
        ],
        default_model=(default_candidate.model_version if default_candidate is not None else None),
        generated_at=latest.predicted_at,
        disclaimer=(
            "P3 使用确定性研究样本验证工程能力；不含真实市场数据，"
            "任何模型都不得注册为默认或用于投资决策。"
        ),
    )


def build_deterministic_research_dataset() -> RankingDataset:
    rng = np.random.default_rng(20260724)
    dates = np.busday_offset(
        np.datetime64("2024-01-02"),
        np.arange(120),
        roll="forward",
    ).astype("datetime64[D]")
    codes = np.asarray([f"{600000 + index:06d}" for index in range(60)])
    row_dates = np.repeat(dates, len(codes))
    row_codes = np.tile(codes, len(dates))
    features = rng.normal(0, 1, size=(len(row_dates), len(FEATURE_NAMES)))

    code_effects = rng.normal(0, 0.0015, size=len(codes))
    day_regimes = rng.normal(0, 0.001, size=len(dates))
    hidden_weights = np.asarray([0.34, 0.28, 0.2, 0.12, 0.08, -0.1])
    targets = features @ hidden_weights * 0.012
    targets += np.tile(code_effects, len(dates))
    targets += np.repeat(day_regimes, len(codes))
    targets += rng.normal(0, 0.006, size=len(row_dates))

    for trade_date in dates:
        mask = row_dates == trade_date
        targets[mask] -= np.mean(targets[mask])
    targets = np.clip(targets, -0.09, 0.09)

    return RankingDataset(
        dates=row_dates,
        codes=row_codes,
        features=features.astype(np.float64),
        targets=targets.astype(np.float64),
        feature_names=FEATURE_NAMES,
        data_version=DATA_VERSION,
        simulated=True,
    )


def build_deterministic_market_bars(
    dataset: RankingDataset,
) -> list[MarketBar]:
    rng = np.random.default_rng(20260725)
    codes = np.unique(dataset.codes)
    dates = dataset.unique_dates
    prior_close = {str(code): 10.0 + index * 0.15 for index, code in enumerate(codes)}
    bars: list[MarketBar] = []
    daily_weights = np.asarray([0.2, 0.18, 0.1, 0.06, 0.04, -0.08])

    for day_index, trade_date in enumerate(dates):
        mask = dataset.dates == trade_date
        feature_by_code = {
            str(code): features
            for code, features in zip(
                dataset.codes[mask],
                dataset.features[mask],
                strict=True,
            )
        }
        for code_index, code_value in enumerate(codes):
            code = str(code_value)
            overnight = float(rng.normal(0, 0.0015))
            open_price = prior_close[code] * (1 + overnight)
            intraday = float(
                feature_by_code[code] @ daily_weights * 0.002 + rng.normal(0.0002, 0.003)
            )
            intraday = float(np.clip(intraday, -0.09, 0.09))
            close_price = open_price * (1 + intraday)
            suspended = day_index % 37 == 0 and code_index == 0
            limit_up = day_index % 43 == 0 and code_index == 1
            limit_down = day_index % 41 == 0 and code_index == 2
            volume = 0 if suspended else 800_000 + code_index * 12_000
            bars.append(
                MarketBar(
                    trade_date=_to_date(trade_date),
                    code=code,
                    open_price=open_price,
                    close_price=close_price,
                    volume_shares=volume,
                    suspended=suspended,
                    limit_up=limit_up,
                    limit_down=limit_down,
                )
            )
            prior_close[code] = close_price
    return bars


def admission_decision(
    metrics: RankingMetrics,
    simulated: bool,
) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    if metrics.rank_ic < 0.02:
        reasons.append("rank_ic_below_0.02")
    if metrics.icir < 0.8:
        reasons.append("icir_below_0.8")
    if metrics.top_group_mean_excess_return <= 0:
        reasons.append("top_group_excess_not_positive")
    if metrics.top_group_max_drawdown > 0.15:
        reasons.append("max_drawdown_above_15_percent")
    if simulated:
        reasons.append("simulated_data_cannot_be_default")
    return not reasons, reasons


def _to_date(value: np.datetime64) -> date:
    return value.astype("datetime64[D]").astype(object)
