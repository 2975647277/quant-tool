from datetime import date, datetime
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
    top_group_individual_positive_excess_rate: float
    top_group_daily_positive_excess_rate: float
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
    latest_signal_date: date
    generated_at: datetime
    disclaimer: str


class CurrentSignalHolding(ApiModel):
    code: str = Field(pattern=r"^\d{6}$")
    rank: int = Field(ge=1)
    rank_percentile: float = Field(gt=0, le=1)
    score: float
    weight: float | None


class CurrentSignalReport(ApiModel):
    status: str
    data_version: str
    model_version: str
    signal_date: date
    training_start_date: date
    training_end_date: date
    training_sample_count: int
    universe_count: int
    rankings: list[CurrentSignalHolding]
    eligible_for_default: bool
    admission_reasons: list[str]
    generated_at: datetime
    disclaimer: str


class TechnicalDirection(StrEnum):
    BULLISH = "bullish"
    BEARISH = "bearish"
    SIDEWAYS = "sideways"


class KlinePoint(ApiModel):
    trade_date: date
    open_price: float
    high_price: float
    low_price: float
    close_price: float
    volume_shares: int
    volume_ma5: float | None
    volume_ma20: float | None
    ma5: float | None
    ma20: float | None
    ma60: float | None
    rsi14: float | None
    macd: float | None
    macd_signal: float | None
    macd_histogram: float | None


class TechnicalPatternAnchor(ApiModel):
    trade_date: date
    price: float
    label: str


class TechnicalPatternLine(ApiModel):
    start_date: date
    start_price: float
    end_date: date
    end_price: float
    label: str


class TechnicalPattern(ApiModel):
    kind: str
    label: str
    direction: TechnicalDirection
    status: str
    confidence: float = Field(ge=0, le=1)
    summary: str
    anchors: list[TechnicalPatternAnchor]
    lines: list[TechnicalPatternLine]


class StockChartView(ApiModel):
    stock: StockContext
    data_version: str
    start_date: date
    end_date: date
    trend: TechnicalDirection
    trend_label: str
    trend_summary: str
    support_price: float
    resistance_price: float
    latest_volume_shares: int
    volume_ma5: float
    volume_ma20: float
    volume_ratio: float
    volume_change_rate: float | None
    latest_rsi14: float | None
    latest_macd_histogram: float | None
    points: list[KlinePoint]
    patterns: list[TechnicalPattern]
    disclaimer: str


class ResearchCoverage(StrEnum):
    SELECTED_TOP20 = "selected_top20"
    COVERED_NOT_SELECTED = "covered_not_selected"
    NOT_COVERED = "not_covered"


class StockResearchView(ApiModel):
    stock: StockContext
    coverage: ResearchCoverage
    coverage_label: str
    is_current_signal: bool
    signal_age_days: int
    signal_date: date
    training_start_date: date
    training_end_date: date
    current_rank: int | None
    current_score: float | None
    rank_percentile: float | None
    top20_rank: int | None
    top20_score: float | None
    top20_weight: float | None
    model_version: str
    data_version: str
    data_start_date: str
    data_end_date: str
    universe_count: int
    factor_dates: int
    rank_ic: float
    icir: float
    top_group_daily_positive_excess_rate: float
    top_group_mean_excess_return: float
    top_group_max_drawdown: float
    eligible_for_default: bool
    admission_reasons: list[str]
    generated_at: datetime
    disclaimer: str
