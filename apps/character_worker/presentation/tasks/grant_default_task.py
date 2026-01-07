"""Grant Default Character Task.

신규 사용자에게 기본 캐릭터(이코)를 지급합니다.
users API에서 캐릭터 목록이 빈 경우 이 태스크가 호출됩니다.

Flow:
    1. users API: 빈 리스트 감지 → character.grant_default 발행
    2. character_worker: 기본 캐릭터 정보 조회 (로컬 캐시 또는 DB)
    3. character_worker: users.user_characters에 저장
"""

import asyncio
import logging
from typing import Any
from uuid import UUID

from character_worker.infrastructure.cache import get_character_cache
from character_worker.setup.celery import celery_app
from character_worker.setup.config import get_settings

logger = logging.getLogger(__name__)

# 기본 캐릭터 소스
DEFAULT_CHARACTER_SOURCE = "default-onboard"


@celery_app.task(
    name="character.grant_default",
    bind=True,
    queue="character.grant_default",
    max_retries=3,
    soft_time_limit=30,
    time_limit=60,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=60,
)
def grant_default_character_task(self, user_id: str) -> dict[str, Any]:
    """기본 캐릭터(이코)를 사용자에게 지급합니다.

    Args:
        user_id: 사용자 ID

    Returns:
        처리 결과
    """
    log_ctx = {
        "user_id": user_id,
        "celery_task_id": self.request.id,
        "stage": "character.grant_default",
    }
    logger.info("Grant default character task started", extra=log_ctx)

    try:
        # 1. 기본 캐릭터 정보 조회
        default_char = _get_default_character()

        if default_char is None:
            logger.error("Default character not found", extra=log_ctx)
            return {"success": False, "error": "default_character_not_found"}

        # 2. users.user_characters에 저장 (비동기)
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            result = loop.run_until_complete(
                _save_to_users_db(
                    user_id=UUID(user_id),
                    character_id=default_char["id"],
                    character_code=default_char["code"],
                    character_name=default_char["name"],
                    character_type=default_char["type"],
                    character_dialog=default_char["dialog"],
                )
            )
        finally:
            loop.close()

        logger.info(
            "Grant default character completed",
            extra={
                **log_ctx,
                "character_name": default_char["name"],
                **result,
            },
        )
        return {"success": True, **result}

    except Exception:
        logger.exception("Grant default character failed", extra=log_ctx)
        raise


def _get_default_character() -> dict[str, Any] | None:
    """기본 캐릭터 정보를 조회합니다.

    우선순위:
    1. 로컬 캐시에서 조회
    2. DB에서 직접 조회 (캐시 미스 시)
    """
    settings = get_settings()
    cache = get_character_cache()

    # 1. 캐시에서 기본 캐릭터 조회
    default_char = cache.get_default()
    if default_char is not None:
        return {
            "id": default_char.id,
            "code": default_char.code,
            "name": default_char.name,
            "type": default_char.type_label,
            "dialog": default_char.dialog,
        }

    # 2. 캐시 미스 - DB에서 직접 조회
    logger.warning("Default character not in cache, querying DB")
    return _query_default_character_from_db(settings.default_character_code)


def _query_default_character_from_db(code: str) -> dict[str, Any] | None:
    """DB에서 기본 캐릭터를 조회합니다."""
    from sqlalchemy import text

    from character_worker.setup.database import sync_session_factory

    with sync_session_factory() as session:
        result = session.execute(
            text(
                """
                SELECT id, code, name, type_label, dialog
                FROM character.characters
                WHERE code = :code
                LIMIT 1
            """
            ),
            {"code": code},
        )
        row = result.fetchone()

        if row is None:
            return None

        return {
            "id": row.id,
            "code": row.code,
            "name": row.name,
            "type": row.type_label,
            "dialog": row.dialog,
        }


async def _save_to_users_db(
    user_id: UUID,
    character_id: UUID,
    character_code: str,
    character_name: str,
    character_type: str,
    character_dialog: str,
) -> dict[str, Any]:
    """users.user_characters 테이블에 저장합니다.

    ON CONFLICT DO NOTHING으로 중복 지급을 방지합니다.
    """
    from uuid import uuid4

    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import (
        AsyncSession,
        async_sessionmaker,
        create_async_engine,
    )

    from character_worker.setup.config import get_settings

    settings = get_settings()

    # users DB 연결
    engine = create_async_engine(
        settings.users_async_database_url,
        pool_size=5,
        max_overflow=10,
    )
    async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    try:
        async with async_session() as session:
            result = await session.execute(
                text(
                    """
                    INSERT INTO users.user_characters
                        (id, user_id, character_id, character_code, character_name,
                         character_type, character_dialog, source, status, acquired_at, updated_at)
                    VALUES
                        (:id, :user_id, :character_id, :character_code, :character_name,
                         :character_type, :character_dialog, :source, 'owned', NOW(), NOW())
                    ON CONFLICT (user_id, character_code) DO NOTHING
                """
                ),
                {
                    "id": uuid4(),
                    "user_id": user_id,
                    "character_id": character_id,
                    "character_code": character_code,
                    "character_name": character_name,
                    "character_type": character_type,
                    "character_dialog": character_dialog,
                    "source": DEFAULT_CHARACTER_SOURCE,
                },
            )
            await session.commit()

            inserted = result.rowcount > 0
            return {"inserted": inserted, "skipped": not inserted}
    finally:
        await engine.dispose()
