"""MatchCharacterCommand.

캐릭터 매칭 Command입니다.
"""

import logging

from apps.character_worker.application.match.dto import MatchRequest, MatchResult
from apps.character_worker.application.match.ports import CharacterCache

logger = logging.getLogger(__name__)


class MatchCharacterCommand:
    """캐릭터 매칭 Command.

    로컬 캐시를 사용하여 캐릭터를 매칭합니다.
    DB 접근 없이 메모리 캐시만 사용합니다.
    """

    def __init__(self, cache: CharacterCache) -> None:
        """Initialize.

        Args:
            cache: 캐릭터 캐시
        """
        self._cache = cache

    def execute(self, request: MatchRequest) -> MatchResult:
        """캐릭터를 매칭합니다.

        Args:
            request: 매칭 요청

        Returns:
            매칭 결과
        """
        # 1. 캐시에서 매칭 라벨로 캐릭터 찾기
        character = self._cache.get_by_match_label(request.middle_category)

        if character is not None:
            logger.debug(
                "Character matched",
                extra={
                    "task_id": request.task_id,
                    "user_id": str(request.user_id),
                    "label": request.middle_category,
                    "character_code": character.code,
                },
            )
            return MatchResult(
                success=True,
                character_id=character.id,
                character_code=character.code,
                character_name=character.name,
                character_type=character.type_label,
                dialog=character.dialog,
                is_default=False,
            )

        # 2. 매칭 실패 시 기본 캐릭터 반환
        default = self._cache.get_default()
        if default is None:
            logger.warning(
                "No default character in cache",
                extra={"task_id": request.task_id},
            )
            return MatchResult(success=False)

        logger.debug(
            "Using default character",
            extra={
                "task_id": request.task_id,
                "user_id": str(request.user_id),
                "label": request.middle_category,
                "character_code": default.code,
            },
        )
        return MatchResult(
            success=True,
            character_id=default.id,
            character_code=default.code,
            character_name=default.name,
            character_type=default.type_label,
            dialog=default.dialog,
            is_default=True,
        )
