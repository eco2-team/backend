"""
Character Reward Tasks

캐릭터 보상 저장 관련 Celery Tasks
- save_ownership_batch: character DB 배치 저장 (character.reward 큐)

배치 처리로 DB 효율성 향상:
- flush_every: 50개 모이면 flush
- flush_interval: 5초마다 flush
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any
from uuid import UUID

from celery_batches import Batches

from domains.character.celery_app import celery_app

logger = logging.getLogger(__name__)


# ============================================================
# Save Ownership Batch Task - character DB 배치 저장
# ============================================================


@celery_app.task(
    base=Batches,
    name="character.save_ownership",
    queue="character.reward",
    flush_every=50,  # 50개 모이면 flush
    flush_interval=5,  # 5초마다 flush
    acks_late=True,
    max_retries=5,
)
def save_ownership_task(requests: list) -> dict[str, Any]:
    """character.character_ownerships 배치 저장.

    Bulk INSERT로 DB 효율성 향상.
    Idempotent: ON CONFLICT DO NOTHING.
    """
    if not requests:
        return {"processed": 0}

    batch_data = []
    for req in requests:
        # SimpleRequest에서 kwargs 추출
        kwargs = req.kwargs or {}
        if not kwargs:
            # positional args인 경우
            args = req.args or ()
            if len(args) >= 3:
                kwargs = {
                    "user_id": args[0],
                    "character_id": args[1],
                    "source": args[2],
                }
        if kwargs:
            batch_data.append(kwargs)

    if not batch_data:
        return {"processed": 0}

    logger.info(
        "Save ownership batch started",
        extra={"batch_size": len(batch_data)},
    )

    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            result = loop.run_until_complete(_save_ownership_batch_async(batch_data))
        finally:
            loop.close()

        logger.info(
            "Save ownership batch completed",
            extra={"batch_size": len(batch_data), **result},
        )
        return result

    except Exception:
        logger.exception(
            "Save ownership batch failed",
            extra={"batch_size": len(batch_data)},
        )
        raise


def _generate_ownership_id(user_id: str, character_id: str) -> UUID:
    """Deterministic UUID 생성 (멱등성 보장).

    동일한 (user_id, character_id) 쌍은 항상 동일한 id 생성.
    """
    from uuid import NAMESPACE_DNS, uuid5

    return uuid5(NAMESPACE_DNS, f"ownership:{user_id}:{character_id}")


async def _save_ownership_batch_async(
    batch_data: list[dict[str, Any]],
) -> dict[str, Any]:
    """character.character_ownerships BULK UPSERT.

    INSERT INTO ... VALUES (...), (...), ... ON CONFLICT DO NOTHING
    Deterministic UUID로 멱등성 보장.
    """
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
    from sqlalchemy.orm import sessionmaker

    from domains._shared.database.config import get_worker_db_pool_settings
    from domains.character.core.config import get_settings

    settings = get_settings()
    pool_settings = get_worker_db_pool_settings()
    engine = create_async_engine(
        settings.database_url,
        **pool_settings.get_engine_kwargs(),
    )
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
        # Bulk INSERT with ON CONFLICT DO NOTHING
        values = []
        params = {}
        for i, data in enumerate(batch_data):
            user_id = data["user_id"]
            character_id = data["character_id"]
            values.append(
                f"(:id_{i}, :user_id_{i}, :character_id_{i}, :source_{i}, "
                f":status_{i}, NOW(), NOW())"
            )
            # Deterministic UUID: 동일 입력 → 동일 id (멱등성)
            params[f"id_{i}"] = _generate_ownership_id(user_id, character_id)
            params[f"user_id_{i}"] = UUID(user_id)
            params[f"character_id_{i}"] = UUID(character_id)
            params[f"source_{i}"] = data.get("source", "scan")
            params[f"status_{i}"] = "owned"

        if not values:
            return {"processed": 0, "inserted": 0}

        sql = text(
            f"""
            INSERT INTO character.character_ownerships
                (id, user_id, character_id, source, status, acquired_at, updated_at)
            VALUES {", ".join(values)}
            ON CONFLICT (user_id, character_id) DO NOTHING
        """
        )

        result = await session.execute(sql, params)
        await session.commit()

        return {
            "processed": len(batch_data),
            "inserted": result.rowcount,
        }
