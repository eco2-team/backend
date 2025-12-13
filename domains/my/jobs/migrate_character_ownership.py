#!/usr/bin/env python3
"""character.character_ownerships → my.user_characters 마이그레이션 스크립트.

이 스크립트는 character 도메인의 소유권 데이터를 my 도메인으로 이관합니다.

사용법:
    python -m domains.my.jobs.migrate_character_ownership

주의사항:
    1. 실행 전 my.user_characters 테이블이 생성되어 있어야 합니다.
    2. 멱등성을 보장하므로 여러 번 실행해도 안전합니다.
    3. 프로덕션 실행 전 반드시 백업하세요.
"""

from __future__ import annotations

import asyncio
import logging
import sys
from datetime import datetime, timezone

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from domains.my.core.config import get_settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)


MIGRATE_SQL = """
INSERT INTO user_profile.user_characters (
    id, user_id, character_id, character_code, character_name,
    source, status, acquired_at, updated_at
)
SELECT
    co.id,
    co.user_id,
    co.character_id,
    c.code,
    c.name,
    co.source,
    co.status::text,
    co.acquired_at,
    co.updated_at
FROM character.character_ownerships co
JOIN character.characters c ON co.character_id = c.id
ON CONFLICT (user_id, character_id) DO UPDATE SET
    character_code = EXCLUDED.character_code,
    character_name = EXCLUDED.character_name,
    source = COALESCE(EXCLUDED.source, user_profile.user_characters.source),
    status = EXCLUDED.status,
    updated_at = EXCLUDED.updated_at
"""

COUNT_SOURCE_SQL = "SELECT COUNT(*) FROM character.character_ownerships"
COUNT_TARGET_SQL = "SELECT COUNT(*) FROM user_profile.user_characters"


async def migrate() -> int:
    """마이그레이션 실행."""
    settings = get_settings()
    engine = create_async_engine(settings.database_url, echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    try:
        async with async_session() as session:
            # 1. 소스 데이터 개수 확인
            result = await session.execute(text(COUNT_SOURCE_SQL))
            source_count = result.scalar()
            logger.info(f"Source records (character.character_ownerships): {source_count}")

            if source_count == 0:
                logger.info("No records to migrate. Exiting.")
                return 0

            # 2. 마이그레이션 실행
            start = datetime.now(timezone.utc)
            logger.info("Starting migration...")

            await session.execute(text(MIGRATE_SQL))
            await session.commit()

            elapsed = (datetime.now(timezone.utc) - start).total_seconds()
            logger.info(f"Migration completed in {elapsed:.2f}s")

            # 3. 타겟 데이터 개수 확인
            result = await session.execute(text(COUNT_TARGET_SQL))
            target_count = result.scalar()
            logger.info(f"Target records (my.user_characters): {target_count}")

            if target_count >= source_count:
                logger.info("✅ Migration successful!")
            else:
                logger.warning(
                    f"⚠️ Record count mismatch: source={source_count}, target={target_count}"
                )

            return 0

    except Exception as e:
        logger.error(f"❌ Migration failed: {e}")
        return 1
    finally:
        await engine.dispose()


def main() -> None:
    """엔트리포인트."""
    sys.exit(asyncio.run(migrate()))


if __name__ == "__main__":
    main()
