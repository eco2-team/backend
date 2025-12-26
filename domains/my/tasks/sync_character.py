"""
My Domain - User Character Sync Task (Batch)

유저 캐릭터 소유권을 my.user_characters 테이블에 배치 저장합니다.
scan 도메인에서 scan.reward가 직접 이 task를 호출합니다.

배치 처리로 DB 효율성 향상:
- flush_every: 50개 모이면 flush
- flush_interval: 5초마다 flush
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Any
from uuid import UUID

from celery_batches import Batches

from domains.my.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(
    base=Batches,
    name="my.save_character",
    queue="my.reward",
    flush_every=50,  # 50개 모이면 flush
    flush_interval=5,  # 5초마다 flush
    acks_late=True,
    max_retries=5,
)
def save_my_character_task(requests: list) -> dict[str, Any]:
    """my.user_characters 배치 저장.

    Bulk UPSERT로 DB 효율성 향상.
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
            if len(args) >= 7:
                kwargs = {
                    "user_id": args[0],
                    "character_id": args[1],
                    "character_code": args[2],
                    "character_name": args[3],
                    "character_type": args[4],
                    "character_dialog": args[5],
                    "source": args[6],
                }
        if kwargs:
            batch_data.append(kwargs)

    if not batch_data:
        return {"processed": 0}

    logger.info(
        "Save my character batch started",
        extra={"batch_size": len(batch_data)},
    )

    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            result = loop.run_until_complete(_save_my_character_batch_async(batch_data))
        finally:
            loop.close()

        logger.info(
            "Save my character batch completed",
            extra={"batch_size": len(batch_data), **result},
        )
        return result

    except Exception:
        logger.exception(
            "Save my character batch failed",
            extra={"batch_size": len(batch_data)},
        )
        raise


async def _save_my_character_batch_async(
    batch_data: list[dict[str, Any]],
) -> dict[str, Any]:
    """my.user_characters BULK INSERT.

    INSERT INTO ... VALUES (...), (...), ...
    ON CONFLICT (user_id, character_id) DO NOTHING

    Idempotent: 이미 소유한 캐릭터는 무시 (성능 최적화).
    """
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
    from sqlalchemy.orm import sessionmaker

    from domains._shared.database.config import get_worker_db_pool_settings

    # my 도메인 DB URL (환경변수에서)
    my_db_url = os.getenv(
        "MY_DATABASE_URL",
        "postgresql+asyncpg://postgres:postgres@localhost:5432/my",
    )
    pool_settings = get_worker_db_pool_settings()
    engine = create_async_engine(
        my_db_url,
        **pool_settings.get_engine_kwargs(),
    )
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
        # Bulk UPSERT
        values = []
        params = {}
        for i, data in enumerate(batch_data):
            values.append(
                f"(:user_id_{i}, :character_id_{i}, :character_code_{i}, "
                f":character_name_{i}, :character_type_{i}, :character_dialog_{i}, "
                f":source_{i}, :status_{i}, NOW(), NOW())"
            )
            params[f"user_id_{i}"] = UUID(data["user_id"])
            params[f"character_id_{i}"] = UUID(data["character_id"])
            params[f"character_code_{i}"] = data.get("character_code", "")
            params[f"character_name_{i}"] = data.get("character_name", "")
            params[f"character_type_{i}"] = data.get("character_type")
            params[f"character_dialog_{i}"] = data.get("character_dialog")
            params[f"source_{i}"] = data.get("source", "scan")
            params[f"status_{i}"] = "owned"  # 기본값: 소유 상태

        if not values:
            return {"processed": 0, "inserted": 0}

        sql = text(
            f"""
            INSERT INTO user_profile.user_characters
                (user_id, character_id, character_code, character_name,
                 character_type, character_dialog, source, status, acquired_at, updated_at)
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
