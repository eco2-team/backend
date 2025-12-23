"""
My Domain - User Character Sync Task

유저 캐릭터 소유권을 my.user_characters 테이블에 저장합니다.
scan 도메인에서 scan.reward가 직접 이 task를 호출합니다.
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Any
from uuid import UUID

from domains._shared.celery.base_task import BaseTask
from domains.my.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(
    bind=True,
    base=BaseTask,
    name="my.save_character",
    queue="my.reward",
    max_retries=5,
    soft_time_limit=30,
    time_limit=60,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=300,
    retry_jitter=True,
)
def save_my_character_task(
    self: BaseTask,
    user_id: str,
    character_id: str,
    character_code: str,
    character_name: str,
    character_type: str | None,
    character_dialog: str | None,
    source: str,
) -> dict[str, Any]:
    """my.user_characters 저장 (gRPC 대신 직접 INSERT).

    Idempotent: upsert 로직 (이미 소유한 경우 상태 업데이트).
    """
    log_ctx = {
        "user_id": user_id,
        "character_id": character_id,
        "character_name": character_name,
        "source": source,
        "celery_task_id": self.request.id,
    }
    logger.info("Save my character task started", extra=log_ctx)

    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            result = loop.run_until_complete(
                _save_my_character_async(
                    user_id=user_id,
                    character_id=character_id,
                    character_code=character_code,
                    character_name=character_name,
                    character_type=character_type,
                    character_dialog=character_dialog,
                    source=source,
                )
            )
        finally:
            loop.close()

        logger.info("Save my character completed", extra={**log_ctx, **result})
        return result

    except Exception:
        logger.exception("Save my character failed", extra=log_ctx)
        raise


async def _save_my_character_async(
    user_id: str,
    character_id: str,
    character_code: str,
    character_name: str,
    character_type: str | None,
    character_dialog: str | None,
    source: str,
) -> dict[str, Any]:
    """my.user_characters INSERT (직접 DB 접근)."""
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
    from sqlalchemy.orm import sessionmaker

    from domains.my.repositories.user_character_repository import UserCharacterRepository

    # my 도메인 DB URL (환경변수에서)
    my_db_url = os.getenv(
        "MY_DATABASE_URL",
        "postgresql+asyncpg://postgres:postgres@localhost:5432/my",
    )
    engine = create_async_engine(my_db_url, echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
        repo = UserCharacterRepository(session)

        # upsert: 이미 소유한 경우 상태 업데이트
        user_char = await repo.grant_character(
            user_id=UUID(user_id),
            character_id=UUID(character_id),
            character_code=character_code,
            character_name=character_name,
            character_type=character_type,
            character_dialog=character_dialog,
            source=source,
        )
        await session.commit()

        return {
            "saved": True,
            "user_character_id": str(user_char.id),
        }
