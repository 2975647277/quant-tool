import argparse
from datetime import date
from pathlib import Path

from quant_service.data.pipeline import P2PipelineConfig, run_p2_pipeline
from quant_service.data.providers import AkshareSinaProvider
from quant_service.data.store import ArtifactStore, default_data_root
from quant_service.research.real import build_p3_real_report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Fetch a real-data P2 research snapshot and rerun P3 validation",
    )
    parser.add_argument("--start", type=date.fromisoformat, default=date(2021, 1, 1))
    parser.add_argument("--end", type=date.fromisoformat, default=date(2025, 12, 31))
    parser.add_argument("--index", default="000300")
    parser.add_argument("--universe-size", type=int, default=30)
    parser.add_argument("--timeout", type=float, default=20.0)
    parser.add_argument("--data-dir", type=Path, default=default_data_root())
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    store = ArtifactStore(args.data_dir)
    result = run_p2_pipeline(
        AkshareSinaProvider(timeout_seconds=args.timeout),
        P2PipelineConfig(
            start_date=args.start,
            end_date=args.end,
            index_code=args.index,
            universe_size=args.universe_size,
        ),
        store=store,
    )
    p3_report = build_p3_real_report(result.factors, result.report)
    store.save_p3_report(p3_report)
    print(
        result.report.model_dump_json(
            by_alias=True,
            indent=2,
        )
    )
    print(
        p3_report.model_dump_json(
            by_alias=True,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
