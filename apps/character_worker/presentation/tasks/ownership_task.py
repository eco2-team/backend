"""Save Ownership Task.

character.save_ownership 큐를 처리하는 Celery 태스크입니다.
Celery Batches를 사용하여 배치 처리합니다.

domains/character/tasks/reward.py와 동일한 인터페이스를 유지합니다.
"""

import asyncio
import logging
from typing import Any
from uuid import UUID

from celery_batches import Batches

from character_worker.setup.celery import celery_app
from character_worker.setup.database import async_session_factory

logger = logging.getLogger(__name__)


@celery_app.task(
    base=Batches,
    name="character.save_ownership",
    queue="character.save_ownership",
    flush_every=50,
    flush_interval=5,
    acks_late=True,
    max_retries=5,
)
def save_ownership_task(requests: list) -> dict[str, Any]:
    """캐릭터 소유권 저장 태스크.

    Celery Batches로 배치 처리합니다.
    ON CONFLICT DO NOTHING으로 멱등성을 보장합니다.

    인터페이스 (kwargs 또는 positional args):
        - user_id: 사용자 ID
        - character_id: 캐릭터 ID
        - source: 획득 소스

    Args:
        requests: Celery SimpleRequest 목록

    Returns:
        처리 결과 {"processed": int, "inserted": int}
    """
    if not requests:
        return {"processed": 0}

    # 이벤트 추출 (character_code 필수)
    batch_data = []
    for req in requests:
        try:
            # kwargs 우선
            kwargs = req.kwargs or {}
            if not kwargs:
                # positional args인 경우
                args = req.args or ()
                if len(args) >= 4:
                    kwargs = {
                        "user_id": args[0],
                        "character_id": args[1],
                        "character_code": args[2],
                        "source": args[3],
                    }
                elif len(args) >= 3:
                    # Legacy: character_code 없는 경우 (호환성)
                    kwargs = {
                        "user_id": args[0],
                        "character_id": args[1],
                        "source": args[2],
                    }
            # character_code 필수 체크
            if kwargs and kwargs.get("character_code"):
                batch_data.append(kwargs)
        except (ValueError, IndexError) as e:
            logger.warning(
                "Invalid ownership event data",
                extra={"error": str(e), "args": getattr(req, "args", None)},
            )

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


def _generate_ownership_id(user_id: str, character_code: str) -> UUID:
    """Deterministic UUID 생성 (멱등성 보장).

    동일한 (user_id, character_code) 쌍은 항상 동일한 id 생성.
    users.user_characters와 동일한 기준 사용.
    """
    from uuid import NAMESPACE_DNS, uuid5

    return uuid5(NAMESPACE_DNS, f"ownership:{user_id}:{character_code}")


async def _save_ownership_batch_async(
    batch_data: list[dict[str, Any]],
) -> dict[str, Any]:
    """character.character_ownerships BULK UPSERT.

    INSERT INTO ... VALUES (...), (...), ... ON CONFLICT DO NOTHING
    (user_id, character_code) 기준 멱등성 - users.user_characters와 통일.
    """
    from sqlalchemy import text

    async with async_session_factory() as session:
        # Bulk INSERT with ON CONFLICT DO NOTHING
        values = []
        params = {}
        for i, data in enumerate(batch_data):
            user_id = data["user_id"]
            character_id = data["character_id"]
            character_code = data["character_code"]
            values.append(
                f"(:id_{i}, :user_id_{i}, :character_id_{i}, :character_code_{i}, :source_{i}, "
                f":status_{i}, NOW(), NOW())"
            )
            # Deterministic UUID: (user_id, character_code) 기준 멱등성
            params[f"id_{i}"] = _generate_ownership_id(user_id, character_code)
            params[f"user_id_{i}"] = UUID(user_id)
            params[f"character_id_{i}"] = UUID(character_id)
            params[f"character_code_{i}"] = character_code
            params[f"source_{i}"] = data.get("source", "scan")
            params[f"status_{i}"] = "owned"

        if not values:
            return {"processed": 0, "inserted": 0}

        sql = text(
            f"""
            INSERT INTO character.character_ownerships
                (id, user_id, character_id, character_code, source, status, acquired_at, updated_at)
            VALUES {", ".join(values)}
            ON CONFLICT (user_id, character_code) DO NOTHING
        """
        )

        result = await session.execute(sql, params)
        await session.commit()

        return {
            "processed": len(batch_data),
            "inserted": result.rowcount,
        }
