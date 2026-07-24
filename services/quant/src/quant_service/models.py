from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel


class ApiModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class ServiceState(StrEnum):
    OK = "ok"


class RiskLevel(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class HealthResponse(ApiModel):
    status: ServiceState
    service_version: str
    mode: str


class StockContext(ApiModel):
    code: str = Field(pattern=r"^\d{6}$")
    name: str


class ScoreDimension(ApiModel):
    key: str
    label: str
    score: int = Field(ge=0, le=100)
    summary: str


class DiagnosisResult(ApiModel):
    stock: StockContext
    composite_score: int = Field(ge=0, le=100)
    risk_level: RiskLevel
    risk_label: str
    horizon_trading_days: int
    excess_return_rank_percentile: int = Field(ge=0, le=100)
    upside_probability: float = Field(ge=0, le=1)
    expected_return_percent: float
    downside_risk_percent: float
    dimensions: list[ScoreDimension]
    explanations: list[str]
    warnings: list[str]
    model_version: str
    data_version: str
    generated_at: datetime
    simulated: bool
    disclaimer: str


class RankingMetricResult(ApiModel):
    model_version: str
    data_version: str
    predicted_at: datetime
    rank_ic: float
    icir: float
    top_group_mean_excess_return: float
    top_group_cumulative_excess_return: float
    top_group_max_drawdown: float
    evaluated_dates: int
    eligible_for_default: bool
    admission_reasons: list[str]


class PortfolioHoldingResult(ApiModel):
    code: str
    score: float
    weight: float


class BacktestSummary(ApiModel):
    total_return: float
    max_drawdown: float
    turnover: float
    transaction_count: int
    blocked_order_count: int
    final_equity: float


class P2DataQuality(ApiModel):
    errors: list[str]
    warnings: list[str]
    dropped_dates: int
    dropped_rows: int
    imputed_values: int


class P2DataReport(ApiModel):
    status: str
    provider_id: str
    usage_scope: str
    data_version: str
    start_date: str
    end_date: str
    index_code: str
    universe_count: int
    trading_days: int
    stock_bar_count: int
    financial_record_count: int
    factor_rows: int
    factor_dates: int
    feature_names: list[str]
    point_in_time_enforced: bool
    universe_survivorship_safe: bool
    quality: P2DataQuality
    generated_at: datetime
    disclaimer: str


class P3ResearchReport(ApiModel):
    status: str
    simulated: bool
    data_version: str
    feature_names: list[str]
    walk_forward_folds: int
    embargo_trading_days: int
    model_results: list[RankingMetricResult]
    latest_top20: list[PortfolioHoldingResult]
    backtest: BacktestSummary
    covered_constraints: list[str]
    default_model: str | None
    generated_at: datetime
    disclaimer: str
