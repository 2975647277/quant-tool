import hashlib
from datetime import UTC, datetime

from .models import DiagnosisResult, RiskLevel, ScoreDimension, StockContext

_KNOWN_NAMES = {
    "000001": "平安银行",
    "001309": "德明利",
    "300750": "宁德时代",
    "600036": "招商银行",
    "600519": "贵州茅台",
}

_DIMENSIONS = (
    ("trend", "趋势质量"),
    ("quality", "基本面质量"),
    ("valuation", "估值位置"),
    ("capital", "资金行为"),
)


def _stable_values(code: str, count: int) -> list[int]:
    digest = hashlib.sha256(f"p1-mock:{code}".encode()).digest()
    return [45 + digest[index] % 44 for index in range(count)]


def build_mock_diagnosis(code: str, name: str | None = None) -> DiagnosisResult:
    values = _stable_values(code, len(_DIMENSIONS) + 4)
    dimensions = [
        ScoreDimension(
            key=key,
            label=label,
            score=score,
            summary=_dimension_summary(key, score),
        )
        for (key, label), score in zip(
            _DIMENSIONS,
            values[: len(_DIMENSIONS)],
            strict=True,
        )
    ]
    composite_score = round(sum(item.score for item in dimensions) / len(dimensions))
    risk_level, risk_label = _risk(values[4])
    percentile = min(96, max(5, composite_score + values[5] % 12 - 6))
    upside_probability = round(0.43 + values[6] / 500, 2)
    expected_return = round((composite_score - 50) / 8.5, 1)
    downside_risk = round(-(2.8 + values[7] / 18), 1)

    strongest = max(dimensions, key=lambda item: item.score)
    weakest = min(dimensions, key=lambda item: item.score)
    stock_name = (name or "").strip() or _KNOWN_NAMES.get(code, "未命名股票")

    return DiagnosisResult(
        stock=StockContext(code=code, name=stock_name),
        composite_score=composite_score,
        risk_level=risk_level,
        risk_label=risk_label,
        horizon_trading_days=10,
        excess_return_rank_percentile=percentile,
        upside_probability=upside_probability,
        expected_return_percent=expected_return,
        downside_risk_percent=downside_risk,
        dimensions=dimensions,
        explanations=[
            f"{strongest.label}是当前模拟评分中最强的维度（{strongest.score} 分）。",
            f"{weakest.label}相对偏弱，后续真实数据阶段需要重点验证。",
            "评分随东方财富当前股票自动刷新，用于验证桌面联动和信息层级。",
        ],
        warnings=[
            "当前结果由确定性模拟数据生成，不包含真实行情、财务或资金数据。",
            "该页面仅用于产品原型验证，不构成证券投资建议。",
        ],
        model_version="mock-p1-v1",
        data_version="mock-deterministic-v1",
        generated_at=datetime.now(UTC),
        simulated=True,
        disclaimer="模拟结果，仅用于软件功能验证，不构成投资建议。",
    )


def _dimension_summary(key: str, score: int) -> str:
    tone = "相对积极" if score >= 70 else "中性" if score >= 55 else "偏弱"
    labels = {
        "trend": "中短期趋势",
        "quality": "盈利与现金流质量",
        "valuation": "行业与历史估值位置",
        "capital": "成交活跃与资金变化",
    }
    return f"{labels[key]}模拟信号{tone}"


def _risk(value: int) -> tuple[RiskLevel, str]:
    if value >= 75:
        return RiskLevel.HIGH, "较高"
    if value >= 58:
        return RiskLevel.MEDIUM, "中等"
    return RiskLevel.LOW, "较低"
