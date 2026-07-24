from datetime import date
from typing import Protocol

from .types import (
    DailyBar,
    DataProvenance,
    FinancialRecord,
    IndexBar,
    UniverseMember,
)


class MarketDataProvider(Protocol):
    provider_id: str

    def provenance(self) -> tuple[DataProvenance, ...]: ...

    def fetch_universe(self, index_code: str) -> list[UniverseMember]: ...

    def fetch_daily_bars(
        self,
        codes: list[str],
        start_date: date,
        end_date: date,
    ) -> list[DailyBar]: ...

    def fetch_index_bars(
        self,
        index_code: str,
        start_date: date,
        end_date: date,
    ) -> list[IndexBar]: ...

    def fetch_financials(
        self,
        codes: list[str],
        end_date: date,
    ) -> list[FinancialRecord]: ...
