import re
from datetime import date
from typing import Annotated

from fastapi import Depends, FastAPI, Header, HTTPException, Query, status

from . import __version__
from .data.store import ArtifactStore
from .mock_diagnosis import build_mock_diagnosis
from .models import (
    CurrentSignalReport,
    DiagnosisResult,
    HealthResponse,
    P2DataReport,
    P3ResearchReport,
    ResearchCoverage,
    ServiceState,
    StockChartView,
    StockContext,
    StockResearchView,
)
from .research.demo import build_p3_demo_report
from .research.technical import build_stock_chart

SESSION_HEADER = "X-Quant-Session"
_stock_code_pattern = re.compile(r"^\d{6}$")
_session_token: str | None = None

app = FastAPI(
    title="Quant Companion Local API",
    version=__version__,
    description="仅供本机桌面伴随应用调用的量化诊断与研究服务。",
)


def configure_session_token(token: str) -> None:
    global _session_token
    _session_token = token


def require_session(
    token: Annotated[str | None, Header(alias=SESSION_HEADER)] = None,
) -> None:
    if not _session_token or token != _session_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid local session",
        )


Session = Annotated[None, Depends(require_session)]


@app.get("/health", response_model=HealthResponse)
def health(_: Session) -> HealthResponse:
    return HealthResponse(
        status=ServiceState.OK,
        service_version=__version__,
        mode="current-daily-research",
    )


@app.get("/v1/stocks/{code}/diagnosis", response_model=DiagnosisResult)
def stock_diagnosis(
    code: str,
    _: Session,
    name: Annotated[str | None, Query(max_length=20)] = None,
) -> DiagnosisResult:
    if not _stock_code_pattern.fullmatch(code):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="stock code must contain exactly 6 digits",
        )
    if name and "指数" in name:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="当前东方财富页面是指数，不是个股，暂不生成个股排名",
        )
    return build_mock_diagnosis(code, name)


@app.get("/v1/research/p3/demo", response_model=P3ResearchReport)
def p3_research_demo(_: Session) -> P3ResearchReport:
    return build_p3_demo_report()


@app.get("/v1/research/p2/status", response_model=P2DataReport)
def p2_data_status(_: Session) -> P2DataReport:
    report = ArtifactStore().load_latest_p2_report()
    if report is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="P2 real-data artifacts not found; run pnpm research:p2",
        )
    return report


@app.get("/v1/research/p3/real", response_model=P3ResearchReport)
def p3_research_real(_: Session) -> P3ResearchReport:
    report = ArtifactStore().load_latest_p3_report()
    if report is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="P3 real-data report not found; run pnpm research:p3:real",
        )
    return report


@app.get("/v1/research/p3/current", response_model=CurrentSignalReport)
def p3_research_current(_: Session) -> CurrentSignalReport:
    report = ArtifactStore().load_latest_current_signal()
    if report is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="current daily signal not found; run pnpm research:daily",
        )
    return report


@app.get("/v1/stocks/{code}/chart", response_model=StockChartView)
def stock_chart(
    code: str,
    _: Session,
    name: Annotated[str | None, Query(max_length=20)] = None,
    limit: Annotated[int, Query(ge=60, le=180)] = 120,
) -> StockChartView:
    if not _stock_code_pattern.fullmatch(code):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="stock code must contain exactly 6 digits",
        )
    if name and "指数" in name:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="当前东方财富页面是指数，不是个股，暂不生成技术形态",
        )
    store = ArtifactStore()
    p2_report = store.load_latest_p2_report()
    if p2_report is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="K线数据不存在，请先运行 pnpm research:daily",
        )
    bars = store.load_stock_bars(
        p2_report.data_version,
        code,
        limit=limit + 60,
    )
    if len(bars) < 60:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="当前股票未包含在本地日线工件中，请先更新当前日频数据",
        )
    return build_stock_chart(
        stock=StockContext(code=code, name=name or code),
        data_version=p2_report.data_version,
        bars=bars,
        display_limit=limit,
    )


@app.get("/v1/stocks/{code}/research", response_model=StockResearchView)
def stock_research(
    code: str,
    _: Session,
    name: Annotated[str | None, Query(max_length=20)] = None,
) -> StockResearchView:
    if not _stock_code_pattern.fullmatch(code):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="stock code must contain exactly 6 digits",
        )
    if name and "指数" in name:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="当前东方财富页面是指数，不是个股，暂不生成个股排名",
        )
    store = ArtifactStore()
    p2_report = store.load_latest_p2_report()
    p3_report = store.load_latest_p3_report()
    current_signal = store.load_latest_current_signal()
    if p2_report is None or p3_report is None or current_signal is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="current research artifacts not found; run pnpm research:daily",
        )
    if not (p2_report.data_version == p3_report.data_version == current_signal.data_version):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="P2, P3, and current signal versions do not match; rerun pnpm research:daily",
        )
    model = next(
        (
            result
            for result in p3_report.model_results
            if result.model_version == "lightgbm-lambdarank-v1"
        ),
        None,
    )
    if model is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="LightGBM real research result is unavailable",
        )
    universe_codes = store.load_universe_codes(p2_report.data_version)
    holding = next(
        (holding for holding in current_signal.rankings if holding.code == code),
        None,
    )
    top20_rank = holding.rank if holding is not None and holding.rank <= 20 else None
    if top20_rank is not None:
        coverage = ResearchCoverage.SELECTED_TOP20
        coverage_label = f"当前日频 Top 20 · 第 {top20_rank} 名"
    elif holding is not None and code in universe_codes:
        coverage = ResearchCoverage.COVERED_NOT_SELECTED
        coverage_label = f"当前研究池 · 第 {holding.rank}/{current_signal.universe_count} 名"
    else:
        coverage = ResearchCoverage.NOT_COVERED
        coverage_label = f"当前{current_signal.universe_count}只研究样本未覆盖"
    signal_age_days = max((date.today() - current_signal.signal_date).days, 0)
    is_current_signal = (
        signal_age_days <= 4 and current_signal.signal_date.isoformat() == p2_report.end_date
    )
    return StockResearchView(
        stock=StockContext(code=code, name=name or code),
        coverage=coverage,
        coverage_label=coverage_label,
        is_current_signal=is_current_signal,
        signal_age_days=signal_age_days,
        signal_date=current_signal.signal_date,
        training_start_date=current_signal.training_start_date,
        training_end_date=current_signal.training_end_date,
        current_rank=holding.rank if holding else None,
        current_score=holding.score if holding else None,
        rank_percentile=holding.rank_percentile if holding else None,
        top20_rank=top20_rank,
        top20_score=holding.score if top20_rank is not None else None,
        top20_weight=holding.weight if top20_rank is not None else None,
        model_version=model.model_version,
        data_version=p2_report.data_version,
        data_start_date=p2_report.start_date,
        data_end_date=p2_report.end_date,
        universe_count=p2_report.universe_count,
        factor_dates=p2_report.factor_dates,
        rank_ic=model.rank_ic,
        icir=model.icir,
        top_group_daily_positive_excess_rate=(model.top_group_daily_positive_excess_rate),
        top_group_mean_excess_return=model.top_group_mean_excess_return,
        top_group_max_drawdown=model.top_group_max_drawdown,
        eligible_for_default=model.eligible_for_default,
        admission_reasons=model.admission_reasons,
        generated_at=current_signal.generated_at,
        disclaimer=current_signal.disclaimer,
    )
