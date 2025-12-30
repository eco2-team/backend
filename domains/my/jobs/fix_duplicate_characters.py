#!/usr/bin/env python3
"""중복 캐릭터 데이터 정리 및 UNIQUE 제약 변경 마이그레이션.

Bug Fix (2025-12-30):
- 문제: character_id 기준 UNIQUE 제약이 캐시 불일치로 인해 중복 저장 허용
- 원인: 캐시에서 잘못된 character_id가 전달되어 같은 캐릭터가 다른 ID로 중복 저장됨
- 수정: character_code 기준 UNIQUE 제약으로 변경

실행:
    python -m domains.my.jobs.fix_duplicate_characters

주의사항:
    1. 실행 전 반드시 백업하세요.
    2. 중복 데이터 중 가장 먼저 획득한 레코드만 유지됩니다.
    3. 멱등성 보장 - 여러 번 실행해도 안전합니다.
"""

import asyncio
import logging
import os
import sys

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


# Step 1: 중복 데이터 확인
CHECK_DUPLICATES_SQL = """
SELECT user_id, character_code, COUNT(*) as cnt
FROM user_profile.user_characters
GROUP BY user_id, character_code
HAVING COUNT(*) > 1
ORDER BY cnt DESC;
"""

# Step 2: 중복 중 최신 레코드 삭제 (가장 먼저 획득한 것만 유지)
DELETE_DUPLICATES_SQL = """
DELETE FROM user_profile.user_characters
WHERE id IN (
    SELECT id
    FROM (
        SELECT id,
               ROW_NUMBER() OVER (
                   PARTITION BY user_id, character_code
                   ORDER BY acquired_at ASC  -- 가장 오래된 것 유지
               ) as rn
        FROM user_profile.user_characters
    ) ranked
    WHERE rn > 1
);
"""

# Step 3: 기존 UNIQUE 제약 삭제 (존재하면)
DROP_OLD_CONSTRAINT_SQL = """
ALTER TABLE user_profile.user_characters
DROP CONSTRAINT IF EXISTS uq_user_character;
"""

# Step 4: 새 UNIQUE 제약 생성 (존재하지 않으면)
CREATE_NEW_CONSTRAINT_SQL = """
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'uq_user_character_code'
        AND conrelid = 'user_profile.user_characters'::regclass
    ) THEN
        ALTER TABLE user_profile.user_characters
        ADD CONSTRAINT uq_user_character_code UNIQUE (user_id, character_code);
    END IF;
END $$;
"""

# 검증 쿼리
VERIFY_CONSTRAINT_SQL = """
SELECT conname, contype
FROM pg_constraint
WHERE conrelid = 'user_profile.user_characters'::regclass
AND conname LIKE 'uq_user_character%';
"""


async def run_migration():
    """마이그레이션 실행."""
    db_url = os.getenv(
        "MY_DATABASE_URL",
        "postgresql+asyncpg://sesacthon:password@localhost:5432/ecoeco",
    )

    engine = create_async_engine(db_url, echo=False)

    async with engine.begin() as conn:
        # Step 1: 중복 확인
        logger.info("Step 1: Checking for duplicates...")
        result = await conn.execute(text(CHECK_DUPLICATES_SQL))
        duplicates = result.fetchall()

        if duplicates:
            logger.warning(f"Found {len(duplicates)} duplicate groups:")
            for row in duplicates[:10]:  # 처음 10개만 표시
                logger.warning(f"  user_id={row[0]}, character_code={row[1]}, count={row[2]}")
            if len(duplicates) > 10:
                logger.warning(f"  ... and {len(duplicates) - 10} more")
        else:
            logger.info("No duplicates found.")

        # Step 2: 중복 삭제
        if duplicates:
            logger.info("Step 2: Deleting duplicate records (keeping oldest)...")
            result = await conn.execute(text(DELETE_DUPLICATES_SQL))
            logger.info(f"Deleted {result.rowcount} duplicate records.")
        else:
            logger.info("Step 2: Skipped (no duplicates).")

        # Step 3: 기존 제약 삭제
        logger.info("Step 3: Dropping old constraint (uq_user_character)...")
        await conn.execute(text(DROP_OLD_CONSTRAINT_SQL))
        logger.info("Old constraint dropped (if existed).")

        # Step 4: 새 제약 생성
        logger.info("Step 4: Creating new constraint (uq_user_character_code)...")
        await conn.execute(text(CREATE_NEW_CONSTRAINT_SQL))
        logger.info("New constraint created (if not existed).")

        # 검증
        logger.info("Verifying constraints...")
        result = await conn.execute(text(VERIFY_CONSTRAINT_SQL))
        constraints = result.fetchall()
        for row in constraints:
            logger.info(f"  Constraint: {row[0]}, Type: {row[1]}")

        logger.info("✅ Migration completed successfully!")

    await engine.dispose()


def main():
    """메인 진입점."""
    print("=" * 60)
    print("중복 캐릭터 데이터 정리 및 UNIQUE 제약 변경")
    print("=" * 60)
    print()
    print("이 스크립트는 다음 작업을 수행합니다:")
    print("1. 중복된 (user_id, character_code) 조합 확인")
    print("2. 중복 레코드 삭제 (가장 오래된 것만 유지)")
    print("3. 기존 UNIQUE 제약 (user_id, character_id) 삭제")
    print("4. 새 UNIQUE 제약 (user_id, character_code) 생성")
    print()

    confirm = input("계속하시겠습니까? (yes/no): ").strip().lower()
    if confirm != "yes":
        print("취소되었습니다.")
        sys.exit(0)

    print()
    asyncio.run(run_migration())


if __name__ == "__main__":
    main()
