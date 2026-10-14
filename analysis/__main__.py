"""CLI: python -m analysis  ->  reports/sparsity_report.md + reports/sparsity_stats.json"""
import argparse

from analysis.sparsity import run
from common.config import REPORTS_DIR, setup_logging
from common.db import connect


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m analysis")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()
    setup_logging(args.verbose)

    conn = connect()
    report = run(conn)
    conn.close()
    report.save(REPORTS_DIR / "sparsity_report.md", REPORTS_DIR / "sparsity_stats.json")
    print(f"Đã ghi {REPORTS_DIR / 'sparsity_report.md'}")


if __name__ == "__main__":
    main()
