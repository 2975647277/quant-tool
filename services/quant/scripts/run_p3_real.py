from quant_service.data.store import ArtifactStore
from quant_service.research.real import build_p3_real_report


def main() -> None:
    store = ArtifactStore()
    p2_report = store.load_latest_p2_report()
    if p2_report is None:
        raise SystemExit("P2 artifacts not found; run pnpm research:p2 first")
    factors = store.load_factor_result(p2_report.data_version)
    p3_report = build_p3_real_report(factors, p2_report)
    store.save_p3_report(p3_report)
    print(p3_report.model_dump_json(by_alias=True, indent=2))


if __name__ == "__main__":
    main()
