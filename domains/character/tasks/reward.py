"""
Character Reward Tasks

캐릭터 보상 저장 관련 Celery Tasks
- save_ownership_task: character DB 저장 (character.reward 큐)

Note: scan_reward_task는 scan 도메인에서 처리 (domains/scan/tasks/reward.py)
      scan.reward에서 직접 이 task를 호출합니다.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any
from uuid import UUID

from domains._shared.celery.base_task import BaseTask
from domains.character.celery_app import celery_app

logger = logging.getLogger(__name__)


# ============================================================
# Save Ownership Task - character DB 저장
# ============================================================


@celery_app.task(
    bind=True,
    base=BaseTask,
    name="character.save_ownership",
    queue="character.reward",
    max_retries=5,
    soft_time_limit=30,
    time_limit=60,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=300,
    retry_jitter=True,
)
def save_ownership_task(
    self: BaseTask,
    user_id: str,
    character_id: str,
    source: str,
) -> dict[str, Any]:
    """character.character_ownerships 저장.

    Idempotent: 이미 소유한 경우 skip.
    """
    log_ctx = {
        "user_id": user_id,
        "character_id": character_id,
        "source": source,
        "celery_task_id": self.request.id,
    }
    logger.info("Save ownership task started", extra=log_ctx)

    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            result = loop.run_until_complete(
                _save_ownership_async(
                    user_id=user_id,
                    character_id=character_id,
                    source=source,
                )
            )
        finally:
            loop.close()

        logger.info("Save ownership completed", extra={**log_ctx, **result})
        return result

    except Exception:
        logger.exception("Save ownership failed", extra=log_ctx)
        raise


async def _save_ownership_async(
    user_id: str,
    character_id: str,
    source: str,
) -> dict[str, Any]:
    """character.character_ownerships INSERT."""
    from sqlalchemy.exc import IntegrityError
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
    from sqlalchemy.orm import sessionmaker

    from domains.character.core.config import get_settings
    from domains.character.repositories.character_repository import CharacterRepository
    from domains.character.repositories.ownership_repository import CharacterOwnershipRepository

    settings = get_settings()
    engine = create_async_engine(settings.database_url, echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
        character_repo = CharacterRepository(session)
        ownership_repo = CharacterOwnershipRepository(session)

        character = await character_repo.get_by_id(UUID(character_id))
        if not character:
            return {"saved": False, "reason": "character_not_found"}

        existing = await ownership_repo.get_by_user_and_character(
            user_id=UUID(user_id), character_id=UUID(character_id)
        )
        if existing:
            return {"saved": False, "reason": "already_owned"}

        try:
            await ownership_repo.insert_owned(
                user_id=UUID(user_id),
                character=character,
                source=source,
            )
            await session.commit()
            return {"saved": True}
        except IntegrityError:
            await session.rollback()
            return {"saved": False, "reason": "concurrent_insert"}
