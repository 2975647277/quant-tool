from __future__ import annotations

import socket
from datetime import UTC, date, datetime, time
from importlib.metadata import version
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd

from ..types import (
    DailyBar,
    DataProvenance,
    FinancialRecord,
    IndexBar,
    UniverseMember,
    utc_now,
)

SHANGHAI_TZ = ZoneInfo("Asia/Shanghai")


class AkshareSinaProvider:
    """Research-only adapter using AKShare's documented Sina/CNInfo/CSI routes."""

    provider_id = "akshare-sina-csindex"

    def __init__(self, *, timeout_seconds: float = 20.0) -> None:
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        self.timeout_seconds = timeout_seconds
        self._acquired_at = utc_now()
        self._adapter_version = version("akshare")

    def provenance(self) -> tuple[DataProvenance, ...]:
        common = {
            "provider_id": self.provider_id,
            "usage_scope": "local_noncommercial_research",
            "acquired_at": self._acquired_at,
        }
        return (
            DataProvenance(
                dataset="daily_stock_and_index",
                source_url="https://finance.sina.com.cn/",
                notes=(
                    f"AKShare {self._adapter_version} documented Sina daily endpoints; "
                    "raw and adjusted prices fetched."
                ),
                **common,
            ),
            DataProvenance(
                dataset="financial_statements",
                source_url="https://money.finance.sina.com.cn/",
                notes=(
                    f"AKShare {self._adapter_version}; announcement and update timestamps "
                    "retained for conservative PIT use."
                ),
                **common,
            ),
            DataProvenance(
                dataset="current_index_constituents",
                source_url="https://www.csindex.com.cn/#/indices/family/detail?indexCode=000300",
                notes=(
                    "Current constituents only; survivorship-safe historical "
                    f"membership unavailable; AKShare {self._adapter_version}."
                ),
                **common,
            ),
        )

    def fetch_universe(self, index_code: str) -> list[UniverseMember]:
        ak = _akshare(self.timeout_seconds)
        frame = ak.index_stock_cons_csindex(symbol=index_code)
        required = {"日期", "成分券代码", "成分券名称", "交易所"}
        _require_columns(frame, required, "index constituents")
        members = [
            UniverseMember(
                code=str(row["成分券代码"]).zfill(6),
                name=str(row["成分券名称"]),
                exchange=str(row["交易所"]),
                observed_at=_as_date(row["日期"]),
            )
            for _, row in frame.iterrows()
        ]
        return sorted(
            {member.code: member for member in members}.values(),
            key=lambda item: item.code,
        )

    def fetch_daily_bars(
        self,
        codes: list[str],
        start_date: date,
        end_date: date,
    ) -> list[DailyBar]:
        ak = _akshare(self.timeout_seconds)
        bars: list[DailyBar] = []
        start = start_date.strftime("%Y%m%d")
        end = end_date.strftime("%Y%m%d")
        for code in codes:
            symbol = _stock_symbol(code)
            raw = ak.stock_zh_a_daily(
                symbol=symbol,
                start_date=start,
                end_date=end,
                adjust="",
            )
            adjusted = ak.stock_zh_a_daily(
                symbol=symbol,
                start_date=start,
                end_date=end,
                adjust="hfq",
            )
            bars.extend(normalize_daily_frames(code, raw, adjusted))
        return sorted(bars, key=lambda item: (item.trade_date, item.code))

    def fetch_index_bars(
        self,
        index_code: str,
        start_date: date,
        end_date: date,
    ) -> list[IndexBar]:
        ak = _akshare(self.timeout_seconds)
        symbol = f"sh{index_code}" if index_code.startswith("000") else f"sz{index_code}"
        frame = ak.stock_zh_index_daily(symbol=symbol)
        required = {"date", "open", "high", "low", "close", "volume"}
        _require_columns(frame, required, "index daily bars")
        rows: list[IndexBar] = []
        for _, row in frame.iterrows():
            trade_date = _as_date(row["date"])
            if start_date <= trade_date <= end_date:
                rows.append(
                    IndexBar(
                        trade_date=trade_date,
                        code=index_code,
                        open_price=float(row["open"]),
                        high_price=float(row["high"]),
                        low_price=float(row["low"]),
                        close_price=float(row["close"]),
                        volume_shares=int(row["volume"]),
                    )
                )
        return sorted(rows, key=lambda item: item.trade_date)

    def fetch_financials(
        self,
        codes: list[str],
        end_date: date,
    ) -> list[FinancialRecord]:
        ak = _akshare(self.timeout_seconds)
        records: list[FinancialRecord] = []
        for code in codes:
            frames = {
                name: ak.stock_financial_report_sina(
                    stock=_stock_symbol(code),
                    symbol=name,
                )
                for name in ("资产负债表", "利润表", "现金流量表")
            }
            records.extend(normalize_financial_frames(code, frames, end_date=end_date))
        return sorted(records, key=lambda item: (item.code, item.report_date, item.available_at))


def normalize_daily_frames(
    code: str,
    raw: pd.DataFrame,
    adjusted: pd.DataFrame,
) -> list[DailyBar]:
    required = {
        "date",
        "open",
        "high",
        "low",
        "close",
        "volume",
        "amount",
        "turnover",
        "outstanding_share",
    }
    _require_columns(raw, required, f"daily bars for {code}")
    _require_columns(adjusted, {"date", "close"}, f"adjusted bars for {code}")
    adjusted_by_date = {
        _as_date(row["date"]): _optional_float(row["close"]) for _, row in adjusted.iterrows()
    }
    result: list[DailyBar] = []
    for _, row in raw.iterrows():
        trade_date = _as_date(row["date"])
        adjusted_close = adjusted_by_date.get(trade_date)
        if adjusted_close is None:
            continue
        result.append(
            DailyBar(
                trade_date=trade_date,
                code=code,
                open_price=float(row["open"]),
                high_price=float(row["high"]),
                low_price=float(row["low"]),
                close_price=float(row["close"]),
                adjusted_close=adjusted_close,
                volume_shares=int(float(row["volume"])),
                amount=float(row["amount"]),
                turnover=_optional_float(row["turnover"]),
                outstanding_shares=_optional_float(row["outstanding_share"]),
            )
        )
    return result


def normalize_financial_frames(
    code: str,
    frames: dict[str, pd.DataFrame],
    *,
    end_date: date,
) -> list[FinancialRecord]:
    for name, frame in frames.items():
        _require_columns(
            frame,
            {"报告日", "公告日期", "更新日期"},
            f"{name} for {code}",
        )
    by_statement: dict[str, dict[date, pd.Series[Any]]] = {}
    for name, frame in frames.items():
        candidates: dict[date, pd.Series[Any]] = {}
        for _, row in frame.iterrows():
            report_date = _compact_date(row["报告日"])
            if report_date > end_date:
                continue
            current = candidates.get(report_date)
            if current is None or _available_at(row) > _available_at(current):
                candidates[report_date] = row
        by_statement[name] = candidates

    common_dates = set.intersection(*(set(rows) for rows in by_statement.values()))
    records: list[FinancialRecord] = []
    for report_date in sorted(common_dates):
        balance = by_statement["资产负债表"][report_date]
        income = by_statement["利润表"][report_date]
        cashflow = by_statement["现金流量表"][report_date]
        rows = (balance, income, cashflow)
        announced_at = max(_announced_at(row) for row in rows)
        updated_at = max(_updated_at(row) for row in rows)
        available_at = max(announced_at, updated_at)
        records.append(
            FinancialRecord(
                code=code,
                report_date=report_date,
                announced_at=announced_at,
                updated_at=updated_at,
                available_at=available_at,
                revenue=_optional_float(income.get("营业收入")),
                net_income=_first_number(income, "归属于母公司的净利润", "净利润"),
                total_assets=_optional_float(balance.get("资产总计")),
                total_liabilities=_optional_float(balance.get("负债合计")),
                operating_cashflow=_optional_float(cashflow.get("经营活动产生的现金流量净额")),
                currency=str(
                    income.get("币种") or balance.get("币种") or cashflow.get("币种") or "CNY"
                ),
            )
        )
    return records


def _akshare(timeout_seconds: float) -> Any:
    socket.setdefaulttimeout(timeout_seconds)
    import akshare

    return akshare


def _stock_symbol(code: str) -> str:
    return f"sh{code}" if code.startswith(("5", "6", "9")) else f"sz{code}"


def _require_columns(frame: pd.DataFrame, required: set[str], label: str) -> None:
    missing = sorted(required - set(frame.columns))
    if missing:
        raise ValueError(f"{label} missing columns: {', '.join(missing)}")


def _as_date(value: Any) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


def _compact_date(value: Any) -> date:
    return datetime.strptime(str(value), "%Y%m%d").date()


def _announced_at(row: pd.Series[Any]) -> datetime:
    announced = _compact_date(row["公告日期"])
    return datetime.combine(announced, time.min, tzinfo=SHANGHAI_TZ).astimezone(UTC)


def _updated_at(row: pd.Series[Any]) -> datetime:
    parsed = datetime.fromisoformat(str(row["更新日期"]))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=SHANGHAI_TZ)
    return parsed.astimezone(UTC)


def _available_at(row: pd.Series[Any]) -> datetime:
    return max(_announced_at(row), _updated_at(row))


def _first_number(row: pd.Series[Any], *keys: str) -> float | None:
    for key in keys:
        value = _optional_float(row.get(key))
        if value is not None:
            return value
    return None


def _optional_float(value: Any) -> float | None:
    if value is None or pd.isna(value):
        return None
    number = float(value)
    return number if pd.notna(number) else None
