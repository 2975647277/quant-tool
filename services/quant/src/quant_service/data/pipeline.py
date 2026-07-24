import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime

from ..models import P2DataQuality, P2DataReport
from .factors import FactorBuildConfig, FactorBuildResult, build_factor_dataset
from .protocol import MarketDataProvider
from .store import ArtifactStore
from .types import MarketSnapshot, UniverseMember, utc_now


@dataclass(frozen=True)
class P2PipelineConfig:
    start_date: date
    end_date: date
    index_code: str = "000300"
    universe_size: int = 30
    required_codes: tuple[str, ...] = ()
    factor_config: FactorBuildConfig = FactorBuildConfig()

    def __post_init__(self) -> None:
        if self.start_date >= self.end_date:
            raise ValueError("start_date must precede end_date")
        if self.universe_size < self.factor_config.minimum_cross_section:
            raise ValueError("universe_size cannot be smaller than minimum_cross_section")
        if len(set(self.required_codes)) > self.universe_size:
            raise ValueError("required_codes cannot exceed universe_size")
        if any(len(code) != 6 or not code.isdigit() for code in self.required_codes):
            raise ValueError("required_codes must contain six-digit stock codes")


@dataclass(frozen=True)
class P2PipelineResult:
    snapshot: MarketSnapshot
    factors: FactorBuildResult
    report: P2DataReport


def run_p2_pipeline(
    provider: MarketDataProvider,
    config: P2PipelineConfig,
    *,
    store: ArtifactStore | None = None,
) -> P2PipelineResult:
    store = store or ArtifactStore()
    available_members = provider.fetch_universe(config.index_code)
    members = _select_pilot_universe(
        available_members,
        config.index_code,
        config.universe_size,
        config.required_codes,
    )
    codes = [member.code for member in members]
    bars = provider.fetch_daily_bars(codes, config.start_date, config.end_date)
    index_bars = provider.fetch_index_bars(
        config.index_code,
        config.start_date,
        config.end_date,
    )
    financials = provider.fetch_financials(codes, config.end_date)
    acquired_at = utc_now()
    actual_end_date = max(bar.trade_date for bar in index_bars)
    snapshot = MarketSnapshot(
        provenance=provider.provenance(),
        universe=tuple(members),
        bars=tuple(bars),
        index_bars=tuple(index_bars),
        financials=tuple(financials),
        index_code=config.index_code,
        acquired_at=acquired_at,
        universe_survivorship_safe=False,
    )
    data_version = _data_version(snapshot, config)
    factors = build_factor_dataset(
        snapshot,
        data_version=data_version,
        config=config.factor_config,
    )
    report = P2DataReport(
        status="completed_with_warnings" if factors.quality.warnings else "completed",
        provider_id=provider.provider_id,
        usage_scope="local_noncommercial_research",
        data_version=data_version,
        start_date=config.start_date.isoformat(),
        end_date=actual_end_date.isoformat(),
        index_code=config.index_code,
        universe_count=len(members),
        trading_days=len({bar.trade_date for bar in index_bars}),
        stock_bar_count=len(bars),
        financial_record_count=len(financials),
        factor_rows=len(factors.dataset.dates),
        factor_dates=len(factors.dataset.unique_dates),
        feature_names=list(factors.dataset.feature_names),
        point_in_time_enforced=True,
        universe_survivorship_safe=snapshot.universe_survivorship_safe,
        quality=P2DataQuality(
            errors=list(factors.quality.errors),
            warnings=list(factors.quality.warnings),
            dropped_dates=factors.quality.dropped_dates,
            dropped_rows=factors.quality.dropped_rows,
            imputed_values=factors.quality.imputed_values,
        ),
        generated_at=acquired_at,
        disclaimer=(
            "真实数据仅用于本地非商业研究。财务值按公告/更新时间保守生效；"
            "当前成分股存在幸存者偏差，历史行业成员尚未接入，因此不得注册正式默认模型。"
        ),
    )
    store.save_snapshot(data_version, snapshot)
    store.save_factor_result(data_version, factors)
    store.save_p2_report(report)
    return P2PipelineResult(snapshot=snapshot, factors=factors, report=report)


def _select_pilot_universe(
    members: list[UniverseMember],
    index_code: str,
    size: int,
    required_codes: tuple[str, ...] = (),
) -> list[UniverseMember]:
    unique = {member.code: member for member in members}
    if len(unique) < size:
        raise ValueError(f"provider returned only {len(unique)} unique members; need {size}")
    observed_at = max(member.observed_at for member in unique.values())
    required = {
        code: unique.get(code)
        or UniverseMember(
            code=code,
            name=code,
            exchange=("上海证券交易所" if code.startswith(("5", "6", "9")) else "深圳证券交易所"),
            observed_at=observed_at,
        )
        for code in required_codes
    }
    ranked = sorted(
        (member for code, member in unique.items() if code not in required),
        key=lambda member: hashlib.sha256(
            f"{index_code}:{member.code}".encode(),
        ).digest(),
    )
    selected = [*required.values(), *ranked[: size - len(required)]]
    return sorted(selected, key=lambda member: member.code)


def _data_version(snapshot: MarketSnapshot, config: P2PipelineConfig) -> str:
    digest = hashlib.sha256()
    header = {
        "provider": snapshot.provenance[0].provider_id,
        "index": config.index_code,
        "start": config.start_date.isoformat(),
        "end": config.end_date.isoformat(),
        "required_codes": sorted(set(config.required_codes)),
        "factors": list(config.factor_config.__dict__.values()),
    }
    digest.update(json.dumps(header, sort_keys=True).encode())
    for collection in (
        snapshot.universe,
        snapshot.bars,
        snapshot.index_bars,
        snapshot.financials,
    ):
        for value in collection:
            payload = asdict(value)
            digest.update(
                json.dumps(
                    payload,
                    default=_serialize,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode()
            )
    return f"p2-real-{digest.hexdigest()[:16]}"


def _serialize(value: object) -> str:
    if isinstance(value, (date, datetime)):
        if isinstance(value, datetime):
            return value.astimezone(UTC).isoformat()
        return value.isoformat()
    raise TypeError(f"unsupported version field: {type(value)!r}")
