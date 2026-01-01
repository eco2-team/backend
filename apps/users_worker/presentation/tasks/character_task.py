"""Character Save Task.

유저 캐릭터 소유권을 users.user_characters 테이블에 배치 저장합니다.
scan 도메인에서 scan.reward가 이 task를 호출합니다.

배치 처리로 DB 효율성 향상:
- flush_every: 50개 모이면 flush
- flush_interval: 5초마다 flush
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from celery_batches import Batches

from apps.users_worker.setup.celery import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(
    base=Batches,
    name="users.save_character",
    queue="users.character",
    flush_every=50,
    flush_interval=5,
    acks_late=True,
    max_retries=5,
)
def save_characters_task(requests: list) -> dict[str, Any]:
    """users.user_characters 배치 저장.

    Celery Batches가 메시지를 배치로 모아서 호출합니다.

    Args:
        requests: Celery SimpleRequest 목록

    Returns:
        처리 결과 (processed, upserted)
    """
    if not requests:
        return {"processed": 0, "upserted": 0, "status": "success"}

    # SimpleRequest에서 kwargs 추출
    batch_data = []
    for req in requests:
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
        return {"processed": 0, "upserted": 0, "status": "success"}

    logger.info(
        "Save characters batch started",
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
            "Save characters batch completed",
            extra={"batch_size": len(batch_data), **result},
        )
        return result

    except Exception:
        logger.exception(
            "Save characters batch failed",
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
    from apps.users_worker.application.character.dto.event import CharacterEvent
    from apps.users_worker.setup.dependencies import Container

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
            # Celery retry
            raise RuntimeError(f"Retryable error: {result.message}")
        else:
            # DROP - 로깅만 하고 종료
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
