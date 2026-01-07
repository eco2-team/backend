"""Reward Character Event Task.

reward.direct Exchange로 발행된 reward.character 이벤트를 처리합니다.
users.save_character 큐에서 수신합니다.

1:N 라우팅: scan.reward → reward.direct → character.save_ownership 큐
                                       → users.save_character 큐

각 Worker가 동일한 task 이름(reward.character)으로 자신만의 구현을 제공합니다.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from celery_batches import Batches

from users_worker.setup.celery import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(
    base=Batches,
    name="reward.character",
    queue="users.save_character",  # Binding: reward.character → users.save_character
    flush_every=50,
    flush_interval=5,
    acks_late=True,
    max_retries=5,
)
def reward_character_task(requests: list) -> dict[str, Any]:
    """reward.character 이벤트 처리 (users DB 저장).

    Celery Batches로 배치 처리합니다.
    ON CONFLICT DO UPDATE으로 멱등성을 보장합니다.

    이벤트 페이로드:
        - user_id: 사용자 ID
        - character_id: 캐릭터 ID
        - character_code: 캐릭터 코드
        - character_name: 캐릭터 이름
        - character_type: 캐릭터 타입
        - source: 획득 소스 (scan)

    Args:
        requests: Celery SimpleRequest 목록

    Returns:
        처리 결과 {"processed": int, "upserted": int}
    """
    if not requests:
        return {"processed": 0, "upserted": 0, "status": "success"}

    # 이벤트 데이터 추출
    batch_data = []
    for req in requests:
        try:
            kwargs = req.kwargs or {}
            if kwargs.get("user_id") and kwargs.get("character_id"):
                batch_data.append(kwargs)
        except Exception as e:
            logger.warning(
                "Invalid reward.character event data",
                extra={"error": str(e)},
            )

    if not batch_data:
        return {"processed": 0, "upserted": 0, "status": "success"}

    logger.info(
        "reward.character batch started (users-worker)",
        extra={"batch_size": len(batch_data)},
    )

    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            result = loop.run_until_complete(_process_batch_async(batch_data))
        finally:
            loop.close()

        logger.info(
            "reward.character batch completed (users-worker)",
            extra={"batch_size": len(batch_data), **result},
        )
        return result

    except Exception:
        logger.exception(
            "reward.character batch failed (users-worker)",
            extra={"batch_size": len(batch_data)},
        )
        raise


async def _process_batch_async(batch_data: list[dict[str, Any]]) -> dict[str, Any]:
    """배치 데이터를 비동기로 처리.

    Clean Architecture 흐름:
    1. DTO 변환 (CharacterEvent)
    2. Command 실행 (SaveCharactersCommand)
    3. 결과 반환

    Args:
        batch_data: 배치 데이터 목록

    Returns:
        처리 결과
    """
    from users_worker.application.character.dto.event import CharacterEvent
    from users_worker.setup.dependencies import Container

    # DI 컨테이너 초기화
    container = Container()
    await container.init()

    try:
        # 1. DTO 변환
        events = []
        for data in batch_data:
            try:
                event = CharacterEvent.from_dict(data)
                events.append(event)
            except ValueError as e:
                logger.warning(
                    "Invalid character event data",
                    extra={"error": str(e), "data": data},
                )

        if not events:
            return {"processed": 0, "upserted": 0, "status": "success"}

        # 2. Command 실행
        command = container.save_characters_command
        result = await command.execute(events)

        # 3. 결과 반환
        if result.is_success:
            return {
                "processed": result.processed,
                "upserted": result.upserted,
                "status": "success",
            }
        elif result.is_retryable:
            raise RuntimeError(f"Retryable error: {result.message}")
        else:
            logger.error(
                "Batch dropped",
                extra={"message": result.message, "batch_size": len(events)},
            )
            return {
                "processed": len(events),
                "upserted": 0,
                "status": "dropped",
                "message": result.message,
            }

    finally:
        await container.close()
