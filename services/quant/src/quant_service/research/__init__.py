"""P3 ranking, portfolio construction, and A-share backtesting."""

from .backtest import (
    AShareBacktester,
    BacktestConfig,
    BacktestResult,
    CostModel,
    MarketBar,
    TargetPortfolio,
)
from .metrics import RankingMetrics, calculate_ranking_metrics, max_drawdown
from .models import (
    LightGBMRankModel,
    LinearFactorModel,
    RuleScoreModel,
    run_walk_forward,
)
from .portfolio import PortfolioSnapshot, build_top_n_portfolios
from .types import PredictionRecord, RankingDataset
from .walk_forward import WalkForwardConfig, WalkForwardFold, build_walk_forward_folds

__all__ = [
    "AShareBacktester",
    "BacktestConfig",
    "BacktestResult",
    "CostModel",
    "LightGBMRankModel",
    "LinearFactorModel",
    "MarketBar",
    "PortfolioSnapshot",
    "PredictionRecord",
    "RankingDataset",
    "RankingMetrics",
    "RuleScoreModel",
    "TargetPortfolio",
    "WalkForwardConfig",
    "WalkForwardFold",
    "build_top_n_portfolios",
    "build_walk_forward_folds",
    "calculate_ranking_metrics",
    "max_drawdown",
    "run_walk_forward",
]
