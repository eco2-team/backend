from __future__ import annotations

import argparse
import asyncio
import csv
import os
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable
from uuid import NAMESPACE_URL, uuid5

from sqlalchemy import func
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from domains.character.database.base import Base
from domains.character.models.character import Character

DATA_DIR = Path(__file__).resolve().parents[1] / "data"
DEFAULT_CSV_PATH = DATA_DIR / "character_catalog.csv"
DEFAULT_RARITY = "common"
RARITY_OVERRIDES = {"이코": "legendary"}
MANUAL_CODE_OVERRIDES = {
    "페이피": "char-paepy",
    "팩토리": "char-factory",
    "페티": "char-petty",
    "메탈리": "char-metally",
    "비니": "char-bini",
    "글래시": "char-glassy",
    "코튼": "char-cotton",
    "플리": "char-plea",
    "일랙": "char-elec",
    "배리": "char-battery",
    "라이티": "char-lighty",
    "폼이": "char-foamy",
    "이코": "char-eco",
}
TOKEN_SPLIT_PATTERN = re.compile(r"[,\n/]+")


@dataclass(frozen=True)
class CatalogEntry:
    name: str
    type_label: str
    dialogue: str

    @property
    def material_types(self) -> list[str]:
        normalized = self.type_label.replace("·", ",")
        return [token.strip() for token in TOKEN_SPLIT_PATTERN.split(normalized) if token.strip()]

    @property
    def metadata(self) -> dict:
        return {
            "typeLabel": self.type_label,
            "materialTypes": self.material_types,
            "dialogue": self.dialogue,
        }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Import static character catalog from CSV into Postgres",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--csv-path",
        type=Path,
        default=DEFAULT_CSV_PATH,
        help="Path to catalog CSV (name,type,dialog columns)",
    )
    parser.add_argument(
        "--database-url",
        help="Override CHARACTER_DATABASE_URL or DATABASE_URL env variables",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=50,
        help="Rows per insert batch",
    )
    return parser.parse_args()


def resolve_database_url(cli_value: str | None) -> str:
    if cli_value:
        return cli_value
    env_value = os.getenv("CHARACTER_DATABASE_URL") or os.getenv("DATABASE_URL")
    if not env_value:
        raise SystemExit("Set CHARACTER_DATABASE_URL or DATABASE_URL")
    return env_value


def load_catalog(csv_path: Path) -> list[CatalogEntry]:
    if not csv_path.exists():
        raise SystemExit(f"CSV file not found: {csv_path}")

    entries: list[CatalogEntry] = []
    with csv_path.open("r", encoding="utf-8-sig", newline="") as file_obj:
        reader = csv.DictReader(file_obj)
        required = {"name", "type", "dialog"}
        if reader.fieldnames is None or not required.issubset(set(reader.fieldnames)):
            raise SystemExit(f"CSV must contain columns: {', '.join(sorted(required))}")

        for idx, row in enumerate(reader, start=1):
            name = (row.get("name") or "").strip()
            type_label = (row.get("type") or "").strip()
            dialogue = (row.get("dialog") or "").strip()
            if not name or not type_label or not dialogue:
                print(f"Skipping row {idx} due to empty fields")
                continue
            entries.append(CatalogEntry(name=name, type_label=type_label, dialogue=dialogue))
    return entries


def _slugify(text: str) -> str:
    normalized = (
        unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii").lower()
    )
    normalized = re.sub(r"[^a-z0-9]+", "-", normalized).strip("-")
    if normalized:
        return normalized
    return uuid5(NAMESPACE_URL, text).hex[:12]


def build_code(name: str) -> str:
    manual = MANUAL_CODE_OVERRIDES.get(name)
    if manual:
        return manual
    return f"char-{_slugify(name)}"


def build_payload(entry: CatalogEntry) -> dict:
    rarity = RARITY_OVERRIDES.get(entry.name, DEFAULT_RARITY)
    description = f"{entry.name}는 {entry.type_label} 배출을 도와요."
    return {
        "code": build_code(entry.name),
        "name": entry.name,
        "description": description,
        "rarity": rarity,
        "element": None,
        "thumbnail_url": None,
        "metadata": entry.metadata,
    }


def batched(iterable: Iterable[dict], batch_size: int) -> Iterable[list[dict]]:
    batch: list[dict] = []
    for item in iterable:
        batch.append(item)
        if len(batch) >= batch_size:
            yield batch
            batch = []
    if batch:
        yield batch


async def ensure_tables(engine: AsyncEngine) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def upsert_batch(engine: AsyncEngine, batch: list[dict]) -> None:
    table = Character.__table__
    stmt = insert(table).values(batch)
    update_columns = {
        "name": stmt.excluded.name,
        "description": stmt.excluded.description,
        "rarity": stmt.excluded.rarity,
        "metadata": stmt.excluded.metadata,
        "element": stmt.excluded.element,
        "thumbnail_url": stmt.excluded.thumbnail_url,
        "updated_at": func.now(),
    }
    async with engine.begin() as conn:
        await conn.execute(
            stmt.on_conflict_do_update(
                index_elements=[table.c.code],
                set_=update_columns,
            )
        )


async def main() -> None:
    args = parse_args()
    database_url = resolve_database_url(args.database_url)

    entries = load_catalog(args.csv_path.resolve())
    if not entries:
        print("No valid catalog rows found")
        return

    engine = create_async_engine(database_url, echo=False, pool_pre_ping=True)
    await ensure_tables(engine)

    payloads = [build_payload(entry) for entry in entries]
    total = 0
    for batch in batched(payloads, args.batch_size):
        await upsert_batch(engine, batch)
        total += len(batch)
    await engine.dispose()
    print(f"Upserted {total} character rows into database")


if __name__ == "__main__":
    asyncio.run(main())
