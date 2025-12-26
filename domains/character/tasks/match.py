"""
Character Match Task

캐릭터 매칭 전용 Celery Task (character.match 큐)
- 로컬 캐시에서만 캐릭터 목록 조회 (DB 조회 없음)
- middle_category 기반 단순 라벨 매칭
- 소유권 체크 없음 (클라이언트가 판단)
- 매칭 결과만 반환

scan.reward에서 동기 호출하여 결과를 받습니다.
"""

from __future__ import annotations

import logging
from typing import Any

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
) -> dict[str, Any] | None:
    """캐릭터 매칭 수행 (캐시 전용, 단순 라벨 매칭).

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
    from domains._shared.cache import get_character_cache

    log_ctx = {
        "user_id": user_id,
        "celery_task_id": self.request.id,
        "stage": "character.match",
    }
    logger.info("Character match task started", extra=log_ctx)

    try:
        # 1. 로컬 캐시에서 캐릭터 목록 조회
        cache = get_character_cache()
        characters = cache.get_all()

        logger.info(
            "Cache status",
            extra={
                **log_ctx,
                "cache_initialized": cache.is_initialized,
                "cache_count": cache.count(),
                "characters_len": len(characters),
            },
        )

        if not characters:
            logger.warning(
                "Character cache empty, cannot perform match",
                extra={
                    **log_ctx,
                    "cache_id": id(cache),
                    "cache_initialized": cache.is_initialized,
                },
            )
            return None

        # 2. 단순 라벨 매칭 (middle_category == match_label)
        classification = classification_result.get("classification", {})
        middle = (classification.get("middle_category") or "").strip()
        minor = (classification.get("minor_category") or "").strip()

        if not middle:
            logger.info("No middle_category, skip matching", extra=log_ctx)
            return None

        # 첫 번째 매칭 캐릭터 반환
        matched = next((c for c in characters if c.match_label == middle), None)

        if not matched:
            logger.info(
                "No character matched",
                extra={**log_ctx, "middle_category": middle},
            )
            return None

        # 3. match_reason 생성: "무색페트병>무색페트병(물병)" 형식
        match_reason = f"{middle}>{minor}" if minor else middle

        result = {
            # 클라이언트 표시용
            "name": matched.name,
            "dialog": matched.dialog,
            "match_reason": match_reason,
            "type": matched.type_label,
            # 저장 task 발행용 (내부)
            "character_id": str(matched.id),
            "character_code": matched.code,
            "received": True,
        }

        logger.info(
            "Character match completed",
            extra={
                **log_ctx,
                "matched": True,
                "character_name": matched.name,
                "match_label": middle,
            },
        )
        return result

    except Exception:
        logger.exception("Character match failed", extra=log_ctx)
        return None
