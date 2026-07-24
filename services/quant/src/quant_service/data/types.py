from dataclasses import dataclass
from datetime import UTC, date, datetime


@dataclass(frozen=True)
class DataProvenance:
    provider_id: str
    dataset: str
    source_url: str
    usage_scope: str
    acquired_at: datetime
    notes: str

    def __post_init__(self) -> None:
        if self.acquired_at.tzinfo is None:
            raise ValueError("acquired_at must be timezone-aware")


@dataclass(frozen=True)
class UniverseMember:
    code: str
    name: str
    exchange: str
    observed_at: date


@dataclass(frozen=True)
class DailyBar:
    trade_date: date
    code: str
    open_price: float
    high_price: float
    low_price: float
    close_price: float
    adjusted_close: float
    volume_shares: int
    amount: float
    turnover: float | None
    outstanding_shares: float | None


@dataclass(frozen=True)
class IndexBar:
    trade_date: date
    code: str
    open_price: float
    high_price: float
    low_price: float
    close_price: float
    volume_shares: int


@dataclass(frozen=True)
class FinancialRecord:
    code: str
    report_date: date
    announced_at: datetime
    updated_at: datetime
    available_at: datetime
    revenue: float | None
    net_income: float | None
    total_assets: float | None
    total_liabilities: float | None
    operating_cashflow: float | None
    currency: str

    def __post_init__(self) -> None:
        timestamps = (self.announced_at, self.updated_at, self.available_at)
        if any(value.tzinfo is None for value in timestamps):
            raise ValueError("financial timestamps must be timezone-aware")
        if self.available_at < max(self.announced_at, self.updated_at):
            raise ValueError("available_at cannot precede announcement or update")

    @property
    def equity(self) -> float | None:
        if self.total_assets is None or self.total_liabilities is None:
            return None
        return self.total_assets - self.total_liabilities


@dataclass(frozen=True)
class MarketSnapshot:
    provenance: tuple[DataProvenance, ...]
    universe: tuple[UniverseMember, ...]
    bars: tuple[DailyBar, ...]
    index_bars: tuple[IndexBar, ...]
    financials: tuple[FinancialRecord, ...]
    index_code: str
    acquired_at: datetime
    universe_survivorship_safe: bool

    def __post_init__(self) -> None:
        if self.acquired_at.tzinfo is None:
            raise ValueError("snapshot acquired_at must be timezone-aware")
        if not self.universe or not self.bars or not self.index_bars:
            raise ValueError("snapshot requires universe, stock bars, and index bars")


def utc_now() -> datetime:
    return datetime.now(UTC)
