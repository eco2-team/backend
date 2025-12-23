"""
Character Match Task

캐릭터 매칭 전용 Celery Task (character.match 큐)
- 로컬 캐시에서 캐릭터 목록 조회
- evaluator로 매칭
- DB 저장 없이 결과만 반환

scan.reward에서 동기 호출하여 결과를 받습니다.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any
from uuid import UUID

from domains._shared.celery.base_task import BaseTask
from domains.character.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(
    bind=True,
    base=BaseTask,
    name="character.match",
    queue="character.match",  # 빠른 응답용 전용 큐
    max_retries=2,
    soft_time_limit=10,
    time_limit=15,
)
def match_character_task(
    self: BaseTask,
    user_id: str,
    classification_result: dict[str, Any],
    disposal_rules_present: bool,
) -> dict[str, Any]:
    """캐릭터 매칭 수행 (DB 저장 없음, 로컬 캐시 사용).

    Args:
        user_id: 사용자 ID
        classification_result: 분류 결과 (classification, situation_tags 포함)
        disposal_rules_present: 배출 규칙 존재 여부

    Returns:
        매칭 결과:
        - received: 매칭 성공 여부
        - already_owned: 이미 보유 여부
        - character_id, name, dialog 등
    """
    log_ctx = {
        "user_id": user_id,
        "celery_task_id": self.request.id,
        "stage": "character.match",
    }
    logger.info("Character match task started", extra=log_ctx)

    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            result = loop.run_until_complete(
                _match_character_async(
                    user_id=user_id,
                    classification_result=classification_result,
                    disposal_rules_present=disposal_rules_present,
                )
            )
        finally:
            loop.close()

        logger.info(
            "Character match completed",
            extra={
                **log_ctx,
                "received": result.get("received") if result else False,
                "character_name": result.get("name") if result else None,
            },
        )
        return result

    except Exception:
        logger.exception("Character match failed", extra=log_ctx)
        return {"received": False, "reason": "error"}


async def _match_character_async(
    user_id: str,
    classification_result: dict[str, Any],
    disposal_rules_present: bool,
) -> dict[str, Any]:
    """캐릭터 매칭 (로컬 캐시 우선, DB fallback).

    Flow:
        1. 로컬 캐시에서 캐릭터 목록 조회
        2. 캐시 비어있으면 DB fallback
        3. evaluator로 매칭
        4. 소유권 체크 (DB)
        5. 결과 반환
    """
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
    from sqlalchemy.orm import sessionmaker

    from domains._shared.cache import get_character_cache
    from domains.character.core.config import get_settings
    from domains.character.repositories.character_repository import CharacterRepository
    from domains.character.repositories.ownership_repository import (
        CharacterOwnershipRepository,
    )
    from domains.character.schemas.reward import (
        CharacterRewardRequest,
        CharacterRewardSource,
        ClassificationSummary,
    )
    from domains.character.services.evaluators import get_evaluator

    settings = get_settings()
    engine = create_async_engine(settings.database_url, echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    classification = classification_result.get("classification", {})
    situation_tags = classification_result.get("situation_tags", [])

    # 1. 로컬 캐시에서 캐릭터 목록 조회
    cache = get_character_cache()
    characters = cache.list_all()

    if not characters:
        # 2. 캐시가 비어있으면 DB fallback
        logger.warning("Character cache empty, falling back to DB")
        async with async_session() as session:
            character_repo = CharacterRepository(session)
            characters = await character_repo.list_all()

    if not characters:
        return {"received": False, "reason": "no_characters"}

    # 3. Evaluator로 매칭
    evaluator = get_evaluator(CharacterRewardSource.SCAN)
    if evaluator is None:
        return {"received": False, "reason": "no_evaluator"}

    request = CharacterRewardRequest(
        source=CharacterRewardSource.SCAN,
        user_id=UUID(user_id),
        task_id="",
        classification=ClassificationSummary(
            major_category=classification.get("major_category", ""),
            middle_category=classification.get("middle_category", ""),
            minor_category=classification.get("minor_category"),
        ),
        situation_tags=situation_tags,
        disposal_rules_present=disposal_rules_present,
        insufficiencies_present=False,
    )

    eval_result = evaluator.evaluate(request, characters)

    if not eval_result.should_evaluate or not eval_result.matches:
        return {"received": False, "reason": "no_match"}

    matched_character = eval_result.matches[0]

    # 4. 소유권 체크 (DB)
    async with async_session() as session:
        ownership_repo = CharacterOwnershipRepository(session)
        existing = await ownership_repo.get_by_user_and_character(
            user_id=UUID(user_id), character_id=matched_character.id
        )

    # 5. 결과 반환 (DB 저장은 하지 않음)
    return {
        "received": not existing,
        "already_owned": existing is not None,
        "character_id": str(matched_character.id),
        "character_code": matched_character.code,
        "name": matched_character.name,
        "dialog": matched_character.dialog,
        "match_reason": eval_result.match_reason,
        "character_type": matched_character.type_label,
        "type": str(matched_character.type_label or "").strip(),
    }
