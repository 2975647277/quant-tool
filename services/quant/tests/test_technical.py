from datetime import date, timedelta

from quant_service.data.types import DailyBar
from quant_service.models import StockContext
from quant_service.research.technical import build_stock_chart


def test_double_bottom_is_drawn_with_neckline_and_turning_points() -> None:
    closes = [10 + index * 0.02 for index in range(62)] + [
        11.2,
        10.4,
        9.3,
        8.1,
        9.0,
        10.2,
        11.5,
        10.6,
        9.4,
        8.2,
        9.1,
        10.4,
        11.7,
        12.1,
        12.5,
        12.9,
        13.2,
        13.5,
    ]
    start = date(2026, 4, 1)
    bars = [
        DailyBar(
            trade_date=start + timedelta(days=index),
            code="000001",
            open_price=close - 0.1,
            high_price=close + 0.25,
            low_price=close - 0.25,
            close_price=close,
            adjusted_close=close,
            volume_shares=1_000_000 + index * 10_000,
            amount=close * (1_000_000 + index * 10_000),
            turnover=0.01,
            outstanding_shares=10_000_000_000,
        )
        for index, close in enumerate(closes)
    ]

    chart = build_stock_chart(
        stock=StockContext(code="000001", name="测试股票"),
        data_version="test-data",
        bars=bars,
        display_limit=60,
    )

    double_bottom = next(pattern for pattern in chart.patterns if pattern.kind == "double_bottom")
    assert double_bottom.status == "已确认"
    assert [anchor.label for anchor in double_bottom.anchors] == [
        "左底",
        "颈线",
        "右底",
    ]
    assert any(line.label == "颈线" for line in double_bottom.lines)
