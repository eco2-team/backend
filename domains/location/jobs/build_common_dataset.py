from __future__ import annotations

import argparse
import csv
import json
import unicodedata
from pathlib import Path
from typing import Iterable


DATA_DIR = Path(__file__).resolve().parents[1] / "data"
ZERO_WASTE_FILENAME = "제로웨이스트 지도 데이터.csv"
KECO_FILENAME = "keco_recycle_compensation_sites.csv"

COMMON_FIELD_ORDER = [
    "source",
    "source_pk",
    "positnSn",
    "positnNm",
    "positnRgnNm",
    "positnLotnoAddr",
    "positnRdnmAddr",
    "positnPstnAddExpln",
    "positnPstnLat",
    "positnPstnLot",
    "positnIntdcCn",
    "positnCnvncFcltSrvcExpln",
    "prkMthdExpln",
    "monSalsHrExplnCn",
    "tuesSalsHrExplnCn",
    "wedSalsHrExplnCn",
    "thurSalsHrExplnCn",
    "friSalsHrExplnCn",
    "satSalsHrExplnCn",
    "sunSalsHrExplnCn",
    "lhldySalsHrExplnCn",
    "lhldyDyoffCn",
    "tmprLhldyCn",
    "dyoffBgndeCn",
    "dyoffEnddtCn",
    "dyoffRsnExpln",
    "bscTelnoCn",
    "rprsTelnoCn",
    "telnoExpln",
    "indivTelnoCn",
    "lnkgHmpgUrlAddr",
    "indivRelSrchListCn",
    "comRelSrwrdListCn",
    "clctItemCn",
    "etcMttrCn",
    "source_metadata",
]


def resolve_zero_waste_csv() -> Path:
    primary = DATA_DIR / ZERO_WASTE_FILENAME
    if primary.exists():
        return primary
    decomposed = DATA_DIR / unicodedata.normalize("NFD", ZERO_WASTE_FILENAME)
    if decomposed.exists():
        return decomposed
    raise FileNotFoundError(f"Zero-waste CSV not found under {DATA_DIR}")


def resolve_keco_csv() -> Path:
    candidate = DATA_DIR / KECO_FILENAME
    if candidate.exists():
        return candidate
    raise FileNotFoundError(f"KECO CSV not found under {DATA_DIR}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build unified dataset based on KECO schema",
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
        "--output-csv",
        type=Path,
        default=DATA_DIR / "location_common_dataset.csv",
        help="Output path for normalized dataset",
    )
    return parser.parse_args()


def read_csv(path: Path) -> Iterable[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as file_obj:
        yield from csv.DictReader(file_obj)


def clean_str(value: str | None) -> str:
    return (value or "").strip()


def clean_float(value: str | None) -> float | None:
    text = clean_str(value)
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def normalize_record(record: dict[str, object]) -> dict[str, str]:
    normalized: dict[str, str] = {}
    for field in COMMON_FIELD_ORDER:
        value = record.get(field)
        if value is None:
            normalized[field] = ""
        elif isinstance(value, float):
            normalized[field] = f"{value:.8f}".rstrip("0").rstrip(".")
        else:
            normalized[field] = str(value)
    return normalized


def map_keco_row(row: dict[str, str]) -> dict[str, object]:
    lat = clean_float(row.get("positnPstnLat"))
    lon = clean_float(row.get("positnPstnLot"))
    normalized_row = {key: clean_str(value) for key, value in row.items()}
    source_metadata = json.dumps(
        {key: (value if value is not None else "") for key, value in row.items()},
        ensure_ascii=False,
    )
    normalized_row.update(
        {
            "source": "keco",
            "source_pk": normalized_row.get("positnSn"),
            "positnPstnLat": lat,
            "positnPstnLot": lon,
            "source_metadata": source_metadata,
        }
    )
    return normalized_row


def map_zero_waste_row(row: dict[str, str]) -> dict[str, object]:
    seq = clean_str(row.get("seq"))
    display1 = clean_str(row.get("display1"))
    display2 = clean_str(row.get("display2"))
    memo = clean_str(row.get("memo"))
    address = display2 or display1
    lat = clean_float(row.get("lat"))
    lon = clean_float(row.get("lon"))

    source_metadata = json.dumps(
        {
            "folderId": clean_str(row.get("folderId")),
            "favoriteType": clean_str(row.get("favoriteType")),
            "color": clean_str(row.get("color")),
            "memo": memo,
            "display1": display1,
            "display2": display2,
            "x": clean_str(row.get("x")),
            "y": clean_str(row.get("y")),
            "lon": lon,
            "lat": lat,
            "key": clean_str(row.get("key")),
            "createdAt": clean_str(row.get("createdAt")),
            "updatedAt": clean_str(row.get("updatedAt")),
        },
        ensure_ascii=False,
    )

    return {
        "source": "zerowaste",
        "source_pk": seq,
        "positnSn": seq,
        "positnNm": display1 or display2 or memo or "Zero Waste Spot",
        "positnRgnNm": "",
        "positnLotnoAddr": address,
        "positnRdnmAddr": address,
        "positnPstnAddExpln": memo,
        "positnPstnLat": lat,
        "positnPstnLot": lon,
        "positnIntdcCn": memo,
        "positnCnvncFcltSrvcExpln": clean_str(row.get("favoriteType")),
        "prkMthdExpln": "",
        "monSalsHrExplnCn": "",
        "tuesSalsHrExplnCn": "",
        "wedSalsHrExplnCn": "",
        "thurSalsHrExplnCn": "",
        "friSalsHrExplnCn": "",
        "satSalsHrExplnCn": "",
        "sunSalsHrExplnCn": "",
        "lhldySalsHrExplnCn": "",
        "lhldyDyoffCn": "",
        "tmprLhldyCn": "",
        "dyoffBgndeCn": "",
        "dyoffEnddtCn": "",
        "dyoffRsnExpln": "",
        "bscTelnoCn": "",
        "rprsTelnoCn": "",
        "telnoExpln": "",
        "indivTelnoCn": "",
        "lnkgHmpgUrlAddr": "",
        "indivRelSrchListCn": "",
        "comRelSrwrdListCn": "",
        "clctItemCn": memo,
        "etcMttrCn": memo,
        "source_metadata": source_metadata,
    }


def build_dataset(args: argparse.Namespace) -> list[dict[str, str]]:
    records: list[dict[str, str]] = []

    for row in read_csv(args.keco_csv):
        records.append(normalize_record(map_keco_row(row)))

    for row in read_csv(args.zero_waste_csv):
        records.append(normalize_record(map_zero_waste_row(row)))

    return records


def write_csv(rows: list[dict[str, str]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as file_obj:
        writer = csv.DictWriter(file_obj, fieldnames=COMMON_FIELD_ORDER)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    args = parse_args()
    dataset = build_dataset(args)
    write_csv(dataset, args.output_csv)
    print(f"Wrote {len(dataset)} rows to {args.output_csv}")


if __name__ == "__main__":
    main()
