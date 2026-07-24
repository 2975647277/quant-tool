import re
from typing import Annotated

from fastapi import Depends, FastAPI, Header, HTTPException, Query, status

from . import __version__
from .mock_diagnosis import build_mock_diagnosis
from .models import (
    DiagnosisResult,
    HealthResponse,
    P3ResearchReport,
    ServiceState,
)
from .research.demo import build_p3_demo_report

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
        mode="mock",
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
    return build_mock_diagnosis(code, name)


@app.get("/v1/research/p3/demo", response_model=P3ResearchReport)
def p3_research_demo(_: Session) -> P3ResearchReport:
    return build_p3_demo_report()
