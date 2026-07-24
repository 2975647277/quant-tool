from datetime import date
from zoneinfo import ZoneInfo

import pandas as pd

from quant_service.data.providers.akshare_sina import (
    normalize_daily_frames,
    normalize_financial_frames,
)


def test_normalize_daily_frames_preserves_raw_and_adjusted_prices() -> None:
    raw = pd.DataFrame(
        [
            {
                "date": date(2024, 1, 2),
                "open": 10.0,
                "high": 10.5,
                "low": 9.8,
                "close": 10.2,
                "volume": 1000,
                "amount": 10_200,
                "turnover": 0.01,
                "outstanding_share": 1_000_000,
            }
        ]
    )
    adjusted = pd.DataFrame([{"date": date(2024, 1, 2), "close": 22.4}])

    bars = normalize_daily_frames("600000", raw, adjusted)

    assert len(bars) == 1
    assert bars[0].close_price == 10.2
    assert bars[0].adjusted_close == 22.4


def test_financial_available_time_uses_latest_statement_timestamp() -> None:
    frames = {
        "资产负债表": _statement(
            {"资产总计": 200.0, "负债合计": 80.0},
            update="2024-04-29T19:00:00",
        ),
        "利润表": _statement(
            {"营业收入": 100.0, "净利润": 10.0},
            update="2024-04-29T20:00:00",
        ),
        "现金流量表": _statement(
            {"经营活动产生的现金流量净额": 12.0},
            update="2024-04-29T19:30:00",
        ),
    }

    records = normalize_financial_frames("600000", frames, end_date=date(2024, 12, 31))

    assert len(records) == 1
    assert records[0].available_at.astimezone(ZoneInfo("Asia/Shanghai")).date() == date(
        2024,
        4,
        30,
    )
    assert records[0].equity == 120.0
    assert records[0].revenue == 100.0


def _statement(values: dict[str, float], *, update: str) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "报告日": "20240331",
                "公告日期": "20240430",
                "更新日期": update,
                "币种": "CNY",
                **values,
            }
        ]
    )
