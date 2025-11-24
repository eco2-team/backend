from __future__ import annotations

import argparse
import asyncio
import csv
import os
import unicodedata
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

from sqlalchemy import (
    BigInteger,
    Column,
    DateTime,
    Float,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine


DEFAULT_CSV_BASENAME = "제로웨이스트 지도 데이터.csv"


def _resolve_default_csv() -> Path:
    base_dir = Path(__file__).resolve().parent.parent
    primary = base_dir / DEFAULT_CSV_BASENAME
    if primary.exists():
        return primary

    # macOS에서 NFD로 저장된 경우를 대비해 정규화된 파일명을 탐색
    decomposed = base_dir / unicodedata.normalize("NFD", DEFAULT_CSV_BASENAME)
    if decomposed.exists():
        return decomposed

    for candidate in base_dir.glob("*.csv"):
        normalized = unicodedata.normalize("NFC", candidate.name)
        if "제로웨이스트" in normalized and "지도" in normalized:
            return candidate

    raise FileNotFoundError(
        f"CSV file not found under {base_dir}. "
        "Ensure the dataset CSV is present next to Dockerfile."
    )


DEFAULT_CSV_PATH = _resolve_default_csv()
metadata = MetaData()

zero_waste_table = Table(
    "location_zero_waste_sites",
    metadata,
    Column("seq", BigInteger, primary_key=True),
    Column("folder_id", BigInteger, nullable=False),
    Column("favorite_type", String(16)),
    Column("color", Integer),
    Column("memo", Text),
    Column("display1", Text),
    Column("display2", Text),
    Column("x", Float),
    Column("y", Float),
    Column("lon", Float),
    Column("lat", Float),
    Column("place_key", String(64)),
    Column("created_at", DateTime(timezone=True)),
    Column("updated_at", DateTime(timezone=True)),
    schema="location",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Import Zero Waste map CSV into Postgres",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--csv-path",
        type=Path,
        default=DEFAULT_CSV_PATH,
        help="Path to the CSV file exported from the zero-waste map",
    )
    parser.add_argument(
        "--database-url",
        help="Override DATABASE_URL (defaults to LOCATION_DATABASE_URL or DATABASE_URL env)",
    )
    parser.add_argument("--batch-size", type=int, default=200, help="Rows per insert batch")
    return parser.parse_args()


def _clean_numeric(value: str | None, *, cast: type[float | int]) -> float | int | None:
    if value is None:
        return None
    stripped = value.strip()
    if not stripped:
        return None
    try:
        return cast(stripped)
    except ValueError:
        return None


def _clean_datetime(value: str | None) -> datetime | None:
    if value is None:
        return None
    stripped = value.strip()
    if not stripped:
        return None
    # Some rows have single-digit hours, pad manually.
    if " " in stripped:
        date_part, time_part = stripped.split(" ", 1)
        hour_part = time_part.split(":", 1)[0]
        if len(hour_part) == 1:
            stripped = f"{date_part} 0{time_part}"
    try:
        return datetime.strptime(stripped, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return None


def transform_row(row: dict[str, str]) -> dict[str, Any]:
    return {
        "folder_id": _clean_numeric(row.get("folderId"), cast=int),
        "seq": _clean_numeric(row.get("seq"), cast=int),
        "favorite_type": (row.get("favoriteType") or "").strip() or None,
        "color": _clean_numeric(row.get("color"), cast=int),
        "memo": (row.get("memo") or "").strip() or None,
        "display1": (row.get("display1") or "").strip() or None,
        "display2": (row.get("display2") or "").strip() or None,
        "x": _clean_numeric(row.get("x"), cast=float),
        "y": _clean_numeric(row.get("y"), cast=float),
        "lon": _clean_numeric(row.get("lon"), cast=float),
        "lat": _clean_numeric(row.get("lat"), cast=float),
        "place_key": (row.get("key") or "").strip() or None,
        "created_at": _clean_datetime(row.get("createdAt")),
        "updated_at": _clean_datetime(row.get("updatedAt")),
    }


async def ensure_schema(engine: AsyncEngine) -> None:
    async with engine.begin() as conn:
        exists = await conn.scalar(
            text(
                "SELECT 1 FROM information_schema.schemata "
                "WHERE schema_name = :schema_name"
            ),
            {"schema_name": "location"},
        )
        if exists:
            print("ℹ️  Schema 'location' already exists; skipping creation.")
        else:
            print("📦 Creating schema 'location' ...")
            await conn.execute(text("CREATE SCHEMA IF NOT EXISTS location"))


async def ensure_table(engine: AsyncEngine) -> None:
    await ensure_schema(engine)
    async with engine.begin() as conn:
        await conn.run_sync(metadata.create_all, tables=[zero_waste_table])


async def upsert_batch(engine: AsyncEngine, batch: list[dict[str, Any]]) -> None:
    if not batch:
        return
    stmt = insert(zero_waste_table).values(batch)
    update_columns = {
        column.name: getattr(stmt.excluded, column.name)
        for column in zero_waste_table.columns
        if column.name != "seq"
    }
    async with engine.begin() as conn:
        await conn.execute(stmt.on_conflict_do_update(index_elements=[zero_waste_table.c.seq], set_=update_columns))


def resolve_database_url(cli_value: str | None) -> str:
    if cli_value:
        return cli_value
    env_value = os.getenv("LOCATION_DATABASE_URL") or os.getenv("DATABASE_URL")
    if not env_value:
        raise SystemExit("Set LOCATION_DATABASE_URL or DATABASE_URL (postgresql+asyncpg://...)")
    return env_value


async def import_csv(engine: AsyncEngine, csv_path: Path, batch_size: int) -> int:
    total = 0
    pending: list[dict[str, Any]] = []
    with csv_path.open("r", encoding="utf-8-sig", newline="") as file_obj:
        reader: Iterable[dict[str, str]] = csv.DictReader(file_obj)
        for row in reader:
            mapped = transform_row(row)
            if mapped["seq"] is None or mapped["folder_id"] is None:
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

    print(f"Imported {total_rows} rows from {csv_path} into location_zero_waste_sites")


if __name__ == "__main__":
    asyncio.run(main())

