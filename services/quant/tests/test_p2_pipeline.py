from datetime import date

from quant_service.data.pipeline import _select_pilot_universe
from quant_service.data.types import UniverseMember


def test_required_stock_can_extend_beyond_current_index_members() -> None:
    members = [
        UniverseMember(
            code=f"60000{index}",
            name=f"member-{index}",
            exchange="上海证券交易所",
            observed_at=date(2026, 7, 23),
        )
        for index in range(1, 6)
    ]

    selected = _select_pilot_universe(
        members,
        "000300",
        3,
        ("001309",),
    )

    assert len(selected) == 3
    external = next(member for member in selected if member.code == "001309")
    assert external.exchange == "深圳证券交易所"
    assert external.observed_at == date(2026, 7, 23)
