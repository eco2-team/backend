from __future__ import annotations

import argparse
import asyncio
import csv
import gzip
from pathlib import Path
from typing import Any, Iterable

from sqlalchemy import (
    BigInteger,
    Column,
    Float,
    MetaData,
    String,
    Table,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

DATA_DIR = Path(__file__).resolve().parents[1] / "data"
DEFAULT_CSV_CANDIDATES = [
    "location_common_dataset.csv.gz",
    "location_common_dataset.csv",
]
metadata = MetaData()

normalized_table = Table(
    "location_normalized_sites",
    metadata,
    Column("positn_sn", BigInteger, primary_key=True),
    Column("source", String(32), nullable=False),
    Column("source_pk", String(128), nullable=False),
    Column("positn_nm", Text),
    Column("positn_rgn_nm", String(128)),
    Column("positn_lotno_addr", Text),
    Column("positn_rdnm_addr", Text),
    Column("positn_pstn_add_expln", Text),
    Column("positn_pstn_lat", Float),
    Column("positn_pstn_lot", Float),
    Column("positn_intdc_cn", Text),
    Column("positn_cnvnc_fclt_srvc_expln", Text),
    Column("prk_mthd_expln", Text),
    Column("mon_sals_hr_expln_cn", Text),
    Column("tues_sals_hr_expln_cn", Text),
    Column("wed_sals_hr_expln_cn", Text),
    Column("thur_sals_hr_expln_cn", Text),
    Column("fri_sals_hr_expln_cn", Text),
    Column("sat_sals_hr_expln_cn", Text),
    Column("sun_sals_hr_expln_cn", Text),
    Column("lhldy_sals_hr_expln_cn", Text),
    Column("lhldy_dyoff_cn", Text),
    Column("tmpr_lhldy_cn", Text),
    Column("dyoff_bgnde_cn", String(32)),
    Column("dyoff_enddt_cn", String(32)),
    Column("dyoff_rsn_expln", Text),
    Column("bsc_telno_cn", String(128)),
    Column("rprs_telno_cn", String(128)),
    Column("telno_expln", Text),
    Column("indiv_telno_cn", Text),
    Column("lnkg_hmpg_url_addr", Text),
    Column("indiv_rel_srch_list_cn", Text),
    Column("com_rel_srwrd_list_cn", Text),
    Column("clct_item_cn", Text),
    Column("etc_mttr_cn", Text),
    Column("source_metadata", Text),
    UniqueConstraint("source", "source_pk", name="uq_location_normalized_source"),
    schema="location",
)


def _resolve_default_csv() -> Path:
    for filename in DEFAULT_CSV_CANDIDATES:
        candidate = DATA_DIR / filename
        if candidate.exists():
            return candidate
    return DATA_DIR / DEFAULT_CSV_CANDIDATES[0]


def _open_csv(path: Path):
    if path.suffix == ".gz":
        return gzip.open(path, "rt", encoding="utf-8-sig", newline="")
    return path.open("r", encoding="utf-8-sig", newline="")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Import KECO-style normalized dataset CSV into Postgres",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--csv-path",
        type=Path,
        default=_resolve_default_csv(),
        help="Path to normalized dataset CSV",
    )
    parser.add_argument(
        "--database-url",
        help="Override LOCATION_DATABASE_URL or DATABASE_URL env variables",
    )
    parser.add_argument("--batch-size", type=int, default=200, help="Rows per insert batch")
    return parser.parse_args()


def _clean_str(value: str | None) -> str:
    return (value or "").strip()


def _clean_float(value: str | None) -> float | None:
    text_value = _clean_str(value)
    if not text_value:
        return None
    try:
        return float(text_value)
    except ValueError:
        return None


def _clean_int(value: str | None) -> int | None:
    text_value = _clean_str(value)
    if not text_value:
        return None
    try:
        return int(text_value)
    except ValueError:
        return None


def transform_row(row: dict[str, str]) -> dict[str, Any]:
    return {
        "positn_sn": _clean_int(row.get("positnSn")),
        "source": _clean_str(row.get("source")),
        "source_pk": _clean_str(row.get("source_pk")),
        "positn_nm": _clean_str(row.get("positnNm")),
        "positn_rgn_nm": _clean_str(row.get("positnRgnNm")),
        "positn_lotno_addr": _clean_str(row.get("positnLotnoAddr")),
        "positn_rdnm_addr": _clean_str(row.get("positnRdnmAddr")),
        "positn_pstn_add_expln": _clean_str(row.get("positnPstnAddExpln")),
        "positn_pstn_lat": _clean_float(row.get("positnPstnLat")),
        "positn_pstn_lot": _clean_float(row.get("positnPstnLot")),
        "positn_intdc_cn": _clean_str(row.get("positnIntdcCn")),
        "positn_cnvnc_fclt_srvc_expln": _clean_str(row.get("positnCnvncFcltSrvcExpln")),
        "prk_mthd_expln": _clean_str(row.get("prkMthdExpln")),
        "mon_sals_hr_expln_cn": _clean_str(row.get("monSalsHrExplnCn")),
        "tues_sals_hr_expln_cn": _clean_str(row.get("tuesSalsHrExplnCn")),
        "wed_sals_hr_expln_cn": _clean_str(row.get("wedSalsHrExplnCn")),
        "thur_sals_hr_expln_cn": _clean_str(row.get("thurSalsHrExplnCn")),
        "fri_sals_hr_expln_cn": _clean_str(row.get("friSalsHrExplnCn")),
        "sat_sals_hr_expln_cn": _clean_str(row.get("satSalsHrExplnCn")),
        "sun_sals_hr_expln_cn": _clean_str(row.get("sunSalsHrExplnCn")),
        "lhldy_sals_hr_expln_cn": _clean_str(row.get("lhldySalsHrExplnCn")),
        "lhldy_dyoff_cn": _clean_str(row.get("lhldyDyoffCn")),
        "tmpr_lhldy_cn": _clean_str(row.get("tmprLhldyCn")),
        "dyoff_bgnde_cn": _clean_str(row.get("dyoffBgndeCn")),
        "dyoff_enddt_cn": _clean_str(row.get("dyoffEnddtCn")),
        "dyoff_rsn_expln": _clean_str(row.get("dyoffRsnExpln")),
        "bsc_telno_cn": _clean_str(row.get("bscTelnoCn")),
        "rprs_telno_cn": _clean_str(row.get("rprsTelnoCn")),
        "telno_expln": _clean_str(row.get("telnoExpln")),
        "indiv_telno_cn": _clean_str(row.get("indivTelnoCn")),
        "lnkg_hmpg_url_addr": _clean_str(row.get("lnkgHmpgUrlAddr")),
        "indiv_rel_srch_list_cn": _clean_str(row.get("indivRelSrchListCn")),
        "com_rel_srwrd_list_cn": _clean_str(row.get("comRelSrwrdListCn")),
        "clct_item_cn": _clean_str(row.get("clctItemCn")),
        "etc_mttr_cn": _clean_str(row.get("etcMttrCn")),
        "source_metadata": row.get("source_metadata") or "",
    }


async def ensure_schema(engine: AsyncEngine) -> None:
    async with engine.begin() as conn:
        exists = await conn.scalar(
            text("SELECT 1 FROM information_schema.schemata " "WHERE schema_name = :schema_name"),
            {"schema_name": "location"},
        )
        if not exists:
            await conn.execute(text("CREATE SCHEMA IF NOT EXISTS location"))


async def ensure_table(engine: AsyncEngine) -> None:
    await ensure_schema(engine)
    async with engine.begin() as conn:
        await conn.run_sync(metadata.create_all, tables=[normalized_table])


async def upsert_batch(engine: AsyncEngine, batch: list[dict[str, Any]]) -> None:
    if not batch:
        return
    stmt = insert(normalized_table).values(batch)
    update_columns = {
        column.name: getattr(stmt.excluded, column.name)
        for column in normalized_table.columns
        if column.name != "positn_sn"
    }
    async with engine.begin() as conn:
        await conn.execute(
            stmt.on_conflict_do_update(
                index_elements=[normalized_table.c.positn_sn], set_=update_columns
            )
        )


def resolve_database_url(cli_value: str | None) -> str:
    if cli_value:
        return cli_value
    import os

    env_value = os.getenv("LOCATION_DATABASE_URL") or os.getenv("DATABASE_URL")
    if not env_value:
        raise SystemExit("Set LOCATION_DATABASE_URL or DATABASE_URL")
    return env_value


async def import_csv(engine: AsyncEngine, csv_path: Path, batch_size: int) -> int:
    total = 0
    pending: list[dict[str, Any]] = []
    with _open_csv(csv_path) as file_obj:
        reader: Iterable[dict[str, str]] = csv.DictReader(file_obj)
        for row in reader:
            mapped = transform_row(row)
            if mapped["positn_sn"] is None or not mapped["source"] or not mapped["source_pk"]:
                continue
            pending.append(mapped)
            if len(pending) >= batch_size:
                await upsert_batch(engine, pending)
                total += len(pending)
                pending.clear()
    if pending:
        await upsert_batch(engine, pending)
        total += len(pending)
    return total


async def main() -> None:
    args = parse_args()
    csv_path = args.csv_path.resolve()
    if not csv_path.exists():
        raise SystemExit(f"CSV file not found: {csv_path}")

    database_url = resolve_database_url(args.database_url)
    engine = create_async_engine(database_url, echo=False, pool_pre_ping=True)

    await ensure_table(engine)
    total_rows = await import_csv(engine, csv_path, args.batch_size)
    await engine.dispose()
    print(f"Imported {total_rows} normalized rows from {csv_path}")


if __name__ == "__main__":
    asyncio.run(main())
