from __future__ import annotations

import argparse
from pathlib import Path

from domains.location.jobs.build_common_dataset import (
    build_dataset,
    resolve_keco_csv,
    resolve_zero_waste_csv,
    write_csv,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build normalized dataset CSV (saved to repo)",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--keco-csv",
        type=Path,
        default=resolve_keco_csv(),
        help="Path to KECO recycle compensation CSV",
    )
    parser.add_argument(
        "--zero-waste-csv",
        type=Path,
        default=resolve_zero_waste_csv(),
        help="Path to zero-waste map CSV",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "data" / "location_common_dataset.csv.gz",
        help="Output path (supports .csv or .csv.gz)",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    dataset = build_dataset(args)
    if not dataset:
        print("No records found; skipping write.")
        return

    output_path = args.output.resolve()
    write_csv(dataset, output_path)
    print(f"Wrote {len(dataset)} rows to {output_path}")


if __name__ == "__main__":
    main()
