from quant_service.research.demo import build_p3_demo_report


def main() -> None:
    report = build_p3_demo_report()
    print(report.model_dump_json(by_alias=True, indent=2))


if __name__ == "__main__":
    main()
