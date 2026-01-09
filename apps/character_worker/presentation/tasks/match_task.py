"""Match Character Task.

character.match 큐를 처리하는 Celery 태스크입니다.

domains/character/tasks/match.py와 동일한 인터페이스를 유지합니다.
"""

import logging
from typing import Any

from character_worker.application.match import MatchCharacterCommand
from character_worker.application.match.dto import MatchRequest
from character_worker.infrastructure.cache import get_character_cache
from character_worker.setup.celery import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(
    name="character.match",
    bind=True,
    queue="character.match",
    max_retries=2,
    soft_time_limit=10,
    time_limit=15,
)
def match_character_task(
    self,
    user_id: str,
    classification_result: dict[str, Any],
    disposal_rules_present: bool,
) -> dict[str, Any] | None:
    """캐릭터 매칭 태스크.

    로컬 캐시를 사용하여 캐릭터를 매칭합니다.
    동기 호출을 위한 태스크입니다 (scan.reward에서 .get() 호출).

    Args:
        user_id: 사용자 ID
        classification_result: 분류 결과 (classification 포함)
        disposal_rules_present: 배출 규칙 존재 여부 (unused, 호환성 유지)

    Returns:
        매칭 성공 시:
        - name, dialog, match_reason, type: 클라이언트 표시용
        - character_id, character_code: 저장 task 발행용 (내부)
        - received: True (매칭됨)
        매칭 실패 시: None
    """
    log_ctx = {
        "user_id": user_id,
        "celery_task_id": self.request.id,
        "stage": "character.match",
    }
    logger.info("Character match task started", extra=log_ctx)

    cache = get_character_cache()

    if not cache.is_loaded():
        logger.warning(
            "Character cache not loaded, attempting lazy load",
            extra={**log_ctx, "cache_id": id(cache)},
        )
        # Lazy loading: 캐시가 없으면 로드 시도
        try:
            from character_worker.setup.celery import _init_character_cache

            _init_character_cache()
        except Exception as e:
            logger.error(f"Failed to lazy load character cache: {e}", extra=log_ctx)
            return None

        if not cache.is_loaded():
            logger.error("Character cache still not loaded after lazy load", extra=log_ctx)
            return None

    # classification_result에서 middle_category 추출
    classification = classification_result.get("classification", {})
    middle = (classification.get("middle_category") or "").strip()
    minor = (classification.get("minor_category") or "").strip()

    if not middle:
        logger.info("No middle_category, skip matching", extra=log_ctx)
        return None

    # 매칭 수행
    from uuid import UUID as UUIDType

    command = MatchCharacterCommand(cache)
    request = MatchRequest(
        task_id=self.request.id or "",
        user_id=UUIDType(user_id) if user_id else UUIDType(int=0),
        middle_category=middle,
    )

    result = command.execute(request)

    if not result.success:
        logger.info(
            "No character matched",
            extra={**log_ctx, "middle_category": middle},
        )
        return None

    # match_reason 생성: "무색페트병>무색페트병(물병)" 형식
    match_reason = f"{middle}>{minor}" if minor else middle

    response = {
        # 클라이언트 표시용
        "name": result.character_name,
        "dialog": result.dialog,
        "match_reason": match_reason,
        "type": result.character_type,
        # 저장 task 발행용 (내부)
        "character_id": str(result.character_id) if result.character_id else None,
        "character_code": result.character_code,
        "received": True,
    }

    logger.info(
        "Character match completed",
        extra={
            **log_ctx,
            "matched": True,
            "character_name": result.character_name,
            "match_label": middle,
        },
    )
    return response
