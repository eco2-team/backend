"""
Character Match Task

캐릭터 매칭 전용 Celery Task (character.match 큐)
- 로컬 캐시에서만 캐릭터 목록 조회 (DB 조회 없음)
- evaluator로 매칭
- 소유권 체크 없음 (클라이언트가 판단)
- 매칭 결과만 반환

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
    """캐릭터 매칭 수행 (캐시 전용, DB 조회 없음).

    Args:
        user_id: 사용자 ID
        classification_result: 분류 결과 (classification, situation_tags 포함)
        disposal_rules_present: 배출 규칙 존재 여부

    Returns:
        매칭 성공 시:
        - name, dialog, match_reason, type: 클라이언트 표시용
        - character_id, character_code: 저장 task 발행용 (내부)
        매칭 실패 시: None
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
                "matched": result is not None,
                "character_name": result.get("name") if result else None,
            },
        )
        return result

    except Exception:
        logger.exception("Character match failed", extra=log_ctx)
        return None


async def _match_character_async(
    user_id: str,
    classification_result: dict[str, Any],
    disposal_rules_present: bool,
) -> dict[str, Any] | None:
    """캐릭터 매칭 (캐시 전용, DB 조회 없음).

    Flow:
        1. 로컬 캐시에서 캐릭터 목록 조회 (DB fallback 없음)
        2. evaluator로 매칭
        3. 결과 반환 (소유권 체크 없음 - 클라이언트가 판단)
    """
    from domains._shared.cache import get_character_cache
    from domains.character.schemas.reward import (
        CharacterRewardRequest,
        CharacterRewardSource,
        ClassificationSummary,
    )
    from domains.character.services.evaluators import get_evaluator

    classification = classification_result.get("classification", {})
    situation_tags = classification_result.get("situation_tags", [])

    # 1. 로컬 캐시에서 캐릭터 목록 조회 (DB fallback 없음)
    cache = get_character_cache()
    characters = cache.list_all()

    if not characters:
        logger.warning("Character cache empty, cannot perform match")
        return None

    # 2. Evaluator로 매칭
    evaluator = get_evaluator(CharacterRewardSource.SCAN)
    if evaluator is None:
        logger.error("No evaluator found for SCAN source")
        return None

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
        return None

    matched_character = eval_result.matches[0]

    # 3. 결과 반환 (소유권 체크 없음 - 클라이언트가 판단)
    return {
        # 클라이언트 표시용
        "name": matched_character.name,
        "dialog": matched_character.dialog,
        "match_reason": eval_result.match_reason,
        "type": matched_character.type_label,
        # 저장 task 발행용 (내부)
        "character_id": str(matched_character.id),
        "character_code": matched_character.code,
    }
