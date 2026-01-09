"""Reward Character Event Task.

reward.events (Fanout) Exchange로 브로드캐스트된 이벤트를 처리합니다.
character.save_ownership 큐에서 수신합니다.

Fanout 패턴: scan.reward → reward.events (fanout) → character.save_ownership 큐
                                                  → users.save_character 큐

모든 바인딩 큐에 동일 메시지가 복제됩니다.

Note: character-worker는 gevent pool 사용 → asyncio 대신 동기 DB 사용.
"""

import logging
from typing import Any
from uuid import UUID

from celery_batches import Batches

from character_worker.setup.celery import celery_app
from character_worker.setup.database import sync_session_factory

logger = logging.getLogger(__name__)


@celery_app.task(
    base=Batches,
    name="reward.character",
    queue="character.save_ownership",  # Binding: reward.character → character.save_ownership
    flush_every=50,
    flush_interval=5,
    acks_late=True,
    max_retries=5,
)
def reward_character_task(requests: list) -> dict[str, Any]:
    """reward.character 이벤트 처리 (character DB 저장).

    Celery Batches로 배치 처리합니다.
    ON CONFLICT DO NOTHING으로 멱등성을 보장합니다.

    이벤트 페이로드:
        - user_id: 사용자 ID
        - character_id: 캐릭터 ID
        - character_code: 캐릭터 코드
        - character_name: 캐릭터 이름 (unused in character-worker)
        - character_type: 캐릭터 타입 (unused in character-worker)
        - source: 획득 소스 (scan)

    Args:
        requests: Celery SimpleRequest 목록

    Returns:
        처리 결과 {"processed": int, "inserted": int}
    """
    if not requests:
        return {"processed": 0, "inserted": 0}

    # 이벤트 데이터 추출
    batch_data = []
    for req in requests:
        try:
            kwargs = req.kwargs or {}
            if kwargs.get("character_code"):
                batch_data.append(kwargs)
        except Exception as e:
            logger.warning(
                "Invalid reward.character event data",
                extra={"error": str(e)},
            )

    if not batch_data:
        return {"processed": 0, "inserted": 0}

    logger.info(
        "reward.character batch started (character-worker)",
        extra={"batch_size": len(batch_data)},
    )

    try:
        result = _save_ownership_batch_sync(batch_data)

        logger.info(
            "reward.character batch completed (character-worker)",
            extra={"batch_size": len(batch_data), **result},
        )
        return result

    except Exception:
        logger.exception(
            "reward.character batch failed (character-worker)",
            extra={"batch_size": len(batch_data)},
        )
        raise


def _generate_ownership_id(user_id: str, character_code: str) -> UUID:
    """Deterministic UUID 생성 (멱등성 보장).

    동일한 (user_id, character_code) 쌍은 항상 동일한 id 생성.
    """
    from uuid import NAMESPACE_DNS, uuid5

    return uuid5(NAMESPACE_DNS, f"ownership:{user_id}:{character_code}")


def _save_ownership_batch_sync(
    batch_data: list[dict[str, Any]],
) -> dict[str, Any]:
    """character.character_ownerships BULK UPSERT (동기 버전).

    INSERT INTO ... VALUES (...), (...), ... ON CONFLICT DO NOTHING
    (user_id, character_code) 기준 멱등성.

    Note: gevent pool 호환을 위해 동기 DB 세션 사용.
    """
    from sqlalchemy import text

    with sync_session_factory() as session:
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

        result = session.execute(sql, params)
        session.commit()

        return {
            "processed": len(batch_data),
            "inserted": result.rowcount,
        }
