"""
Sync to My Domain Celery Task

character 도메인에서 캐릭터 소유권 저장 후
my 도메인으로 비동기 동기화하는 Task
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from domains._shared.celery.base_task import BaseTask
from domains.character.consumers.reward import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(
    bind=True,
    base=BaseTask,
    name="character.sync_to_my",
    queue="my.sync",
    max_retries=5,  # 동기화는 중요하므로 재시도 횟수 증가
    soft_time_limit=15,
    time_limit=30,
    autoretry_for=(Exception,),
    retry_backoff=True,  # Exponential backoff
    retry_backoff_max=60,  # 최대 60초
    retry_jitter=True,
)
def sync_to_my_task(
    self: BaseTask,
    user_id: str,
    character_id: str,
    character_code: str,
    character_name: str,
    character_type: str | None,
    character_dialog: str | None,
    source: str,
) -> dict[str, Any]:
    """my 도메인으로 캐릭터 소유권 동기화.

    character.character_ownerships에 저장된 후 호출됩니다.
    gRPC로 my.UserCharacterService.GrantCharacter를 호출합니다.

    Args:
        user_id: 사용자 UUID 문자열
        character_id: 캐릭터 UUID 문자열
        character_code: 캐릭터 코드
        character_name: 캐릭터 이름
        character_type: 캐릭터 타입 (nullable)
        character_dialog: 캐릭터 대사 (nullable)
        source: 소유권 획득 소스 (e.g., "scan-reward")

    Returns:
        동기화 결과
    """
    import asyncio

    log_ctx = {
        "user_id": user_id,
        "character_id": character_id,
        "character_name": character_name,
        "source": source,
        "celery_task_id": self.request.id,
    }
    logger.info("Sync to my domain task started", extra=log_ctx)

    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            success, already_owned = loop.run_until_complete(
                _sync_grpc(
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

        result = {
            "success": success,
            "already_owned": already_owned,
            "user_id": user_id,
            "character_id": character_id,
        }

        logger.info(
            "Sync to my domain task completed",
            extra={**log_ctx, "success": success, "already_owned": already_owned},
        )
        return result

    except Exception as exc:
        logger.exception("Sync to my domain task failed", extra=log_ctx)
        raise self.retry(exc=exc)


async def _sync_grpc(
    user_id: str,
    character_id: str,
    character_code: str,
    character_name: str,
    character_type: str | None,
    character_dialog: str | None,
    source: str,
) -> tuple[bool, bool]:
    """gRPC로 my 도메인에 캐릭터 소유권 동기화."""
    from domains.character.rpc.my_client import get_my_client
    from domains.character.schemas.catalog import GrantCharacterRequest

    client = get_my_client()
    grant_request = GrantCharacterRequest(
        user_id=UUID(user_id),
        character_id=UUID(character_id),
        character_code=character_code,
        character_name=character_name,
        character_type=character_type,
        character_dialog=character_dialog,
        source=source,
    )
    return await client.grant_character(grant_request)
