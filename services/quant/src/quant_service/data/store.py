import json
import os
import tempfile
from dataclasses import asdict
from datetime import date, datetime
from pathlib import Path
from typing import Any

import numpy as np

from ..models import CurrentSignalReport, P2DataReport, P3ResearchReport
from ..research.types import RankingDataset
from .factors import FactorBuildResult, FactorQuality, build_market_bars
from .types import DailyBar, MarketSnapshot


def default_data_root() -> Path:
    configured = os.environ.get("QUANT_DATA_DIR")
    if configured:
        return Path(configured).expanduser().resolve()
    current = Path.cwd().resolve()
    for candidate in (current, *current.parents):
        if (candidate / "package.json").exists() and (candidate / "services" / "quant").exists():
            return candidate / "data"
    return Path.home() / "Library" / "Application Support" / "quant-tool" / "data"


class ArtifactStore:
    def __init__(self, root: Path | None = None) -> None:
        self.root = (root or default_data_root()).resolve()

    def save_snapshot(self, data_version: str, snapshot: MarketSnapshot) -> None:
        target = self.root / "raw" / data_version
        target.mkdir(parents=True, exist_ok=True)
        _write_jsonl(target / "provenance.jsonl", snapshot.provenance)
        _write_jsonl(target / "universe.jsonl", snapshot.universe)
        _write_jsonl(target / "daily-bars.jsonl", snapshot.bars)
        _write_jsonl(target / "index-bars.jsonl", snapshot.index_bars)
        _write_jsonl(target / "financials.jsonl", snapshot.financials)

    def save_factor_result(
        self,
        data_version: str,
        result: FactorBuildResult,
    ) -> None:
        target = self.root / "factors" / data_version
        target.mkdir(parents=True, exist_ok=True)
        dataset = result.dataset
        np.savez_compressed(
            target / "ranking-dataset.npz",
            dates=dataset.dates,
            codes=dataset.codes,
            features=dataset.features,
            targets=dataset.targets,
            feature_names=np.asarray(dataset.feature_names),
            latest_dates=result.latest_dataset.dates,
            latest_codes=result.latest_dataset.codes,
            latest_features=result.latest_dataset.features,
            latest_targets=result.latest_dataset.targets,
        )
        _atomic_json(
            target / "metadata.json",
            {
                "dataVersion": data_version,
                "simulated": dataset.simulated,
                "rows": len(dataset.dates),
                "dates": len(dataset.unique_dates),
                "featureNames": list(dataset.feature_names),
                "latestFactorDate": str(result.latest_dataset.unique_dates[-1]),
                "latestRows": len(result.latest_dataset.dates),
                "quality": asdict(result.quality),
            },
        )

    def load_factor_dataset(self, data_version: str) -> RankingDataset:
        path = self.root / "factors" / data_version / "ranking-dataset.npz"
        with np.load(path) as data:
            return RankingDataset(
                dates=data["dates"],
                codes=data["codes"],
                features=data["features"],
                targets=data["targets"],
                feature_names=tuple(str(value) for value in data["feature_names"]),
                data_version=data_version,
                simulated=False,
            )

    def load_factor_result(self, data_version: str) -> FactorBuildResult:
        target = self.root / "factors" / data_version
        metadata = json.loads((target / "metadata.json").read_text(encoding="utf-8"))
        quality = metadata["quality"]
        bars = tuple(
            DailyBar(
                trade_date=date.fromisoformat(payload["trade_date"]),
                code=payload["code"],
                open_price=float(payload["open_price"]),
                high_price=float(payload["high_price"]),
                low_price=float(payload["low_price"]),
                close_price=float(payload["close_price"]),
                adjusted_close=float(payload["adjusted_close"]),
                volume_shares=int(payload["volume_shares"]),
                amount=float(payload["amount"]),
                turnover=_optional_float(payload.get("turnover")),
                outstanding_shares=_optional_float(payload.get("outstanding_shares")),
            )
            for payload in _read_jsonl(self.root / "raw" / data_version / "daily-bars.jsonl")
        )
        dataset = self.load_factor_dataset(data_version)
        with np.load(target / "ranking-dataset.npz") as data:
            latest_dataset = RankingDataset(
                dates=data["latest_dates"],
                codes=data["latest_codes"],
                features=data["latest_features"],
                targets=data["latest_targets"],
                feature_names=tuple(str(value) for value in data["feature_names"]),
                data_version=data_version,
                simulated=False,
            )
        return FactorBuildResult(
            dataset=dataset,
            latest_dataset=latest_dataset,
            market_bars=tuple(build_market_bars(bars)),
            quality=FactorQuality(
                errors=tuple(quality["errors"]),
                warnings=tuple(quality["warnings"]),
                dropped_dates=int(quality["dropped_dates"]),
                dropped_rows=int(quality["dropped_rows"]),
                imputed_values=int(quality["imputed_values"]),
            ),
            financial_available_at=(None,) * len(dataset.dates),
            latest_financial_available_at=(None,) * len(latest_dataset.dates),
        )

    def save_p2_report(self, report: P2DataReport) -> None:
        target = self.root / "curated" / report.data_version
        target.mkdir(parents=True, exist_ok=True)
        _atomic_json(
            target / "p2-report.json",
            report.model_dump(mode="json", by_alias=True),
        )
        _atomic_json(
            self.root / "curated" / "latest.json",
            {"dataVersion": report.data_version},
        )

    def save_p3_report(self, report: P3ResearchReport) -> None:
        target = self.root / "models" / report.data_version
        target.mkdir(parents=True, exist_ok=True)
        _atomic_json(
            target / "p3-real-report.json",
            report.model_dump(mode="json", by_alias=True),
        )
        _atomic_json(
            self.root / "models" / "latest.json",
            {"dataVersion": report.data_version},
        )

    def save_current_signal(self, report: CurrentSignalReport) -> None:
        target = self.root / "models" / report.data_version
        target.mkdir(parents=True, exist_ok=True)
        _atomic_json(
            target / "current-signal.json",
            report.model_dump(mode="json", by_alias=True),
        )

    def load_latest_p2_report(self) -> P2DataReport | None:
        version = self._latest_version("curated")
        if version is None:
            return None
        path = self.root / "curated" / version / "p2-report.json"
        return P2DataReport.model_validate_json(path.read_text(encoding="utf-8"))

    def load_latest_p3_report(self) -> P3ResearchReport | None:
        version = self._latest_version("models")
        if version is None:
            return None
        path = self.root / "models" / version / "p3-real-report.json"
        return P3ResearchReport.model_validate_json(path.read_text(encoding="utf-8"))

    def load_latest_current_signal(self) -> CurrentSignalReport | None:
        version = self._latest_version("models")
        if version is None:
            return None
        path = self.root / "models" / version / "current-signal.json"
        if not path.exists():
            return None
        return CurrentSignalReport.model_validate_json(path.read_text(encoding="utf-8"))

    def load_universe_codes(self, data_version: str) -> set[str]:
        path = self.root / "raw" / data_version / "universe.jsonl"
        if not path.exists():
            return set()
        return {str(payload["code"]) for payload in _read_jsonl(path)}

    def _latest_version(self, layer: str) -> str | None:
        pointer = self.root / layer / "latest.json"
        if not pointer.exists():
            return None
        payload = json.loads(pointer.read_text(encoding="utf-8"))
        version = payload.get("dataVersion")
        return str(version) if version else None


def _write_jsonl(path: Path, values: Any) -> None:
    lines = [
        json.dumps(_json_value(asdict(value)), ensure_ascii=False, sort_keys=True)
        for value in values
    ]
    _atomic_text(path, "\n".join(lines) + ("\n" if lines else ""))


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
    ]


def _optional_float(value: Any) -> float | None:
    return float(value) if value is not None else None


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    _atomic_text(
        path,
        json.dumps(_json_value(payload), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
    )


def _atomic_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=path.parent,
        delete=False,
    ) as handle:
        handle.write(content)
        temporary = Path(handle.name)
    temporary.replace(path)


def _json_value(value: Any) -> Any:
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, dict):
        return {key: _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    return value
