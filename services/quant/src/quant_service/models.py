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
