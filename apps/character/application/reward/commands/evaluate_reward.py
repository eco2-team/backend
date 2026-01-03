"""EvaluateRewardCommand.

리워드 평가 Command입니다.
"""

import logging

from apps.character.application.reward.dto import RewardRequest, RewardResult
from apps.character.application.reward.ports import CharacterMatcher, OwnershipChecker

logger = logging.getLogger(__name__)


class EvaluateRewardCommand:
    """리워드 평가 Command.

    분류 결과를 기반으로 캐릭터 리워드를 평가합니다.
    소유권 확인은 하되, 저장은 별도 Worker에서 처리합니다.
    """

    def __init__(
        self,
        matcher: CharacterMatcher,
        ownership_checker: OwnershipChecker,
    ) -> None:
        """Initialize.

        Args:
            matcher: 캐릭터 매처
            ownership_checker: 소유권 확인기
        """
        self._matcher = matcher
        self._ownership_checker = ownership_checker

    async def execute(self, request: RewardRequest) -> RewardResult:
        """리워드를 평가합니다.

        Args:
            request: 리워드 요청

        Returns:
            리워드 결과
        """
        # 0. 리워드 조건 체크 (레거시 정합성)
        # - 분리수거 규칙이 있어야 함
        # - 부적절 항목이 없어야 함
        should_evaluate = (
            request.disposal_rules_present
            and not request.insufficiencies_present
        )

        if not should_evaluate:
            logger.info(
                "Reward conditions not met: disposal_rules=%s, insufficiencies=%s",
                request.disposal_rules_present,
                request.insufficiencies_present,
            )
            return RewardResult(
                received=False,
                already_owned=False,
                match_reason="Reward conditions not met",
            )

        # 1. 매칭 라벨로 캐릭터 찾기
        match_label = request.classification.middle_category
        character = await self._matcher.match_by_label(match_label)

        if character is None:
            logger.info(
                "No character matched for label=%s, using default", match_label
            )
            character = await self._matcher.get_default()

        # 2. 소유권 확인
        already_owned = await self._ownership_checker.is_owned(
            user_id=request.user_id,
            character_id=character.id,
        )

        # 3. 결과 반환 (저장은 Worker에서 처리)
        return RewardResult(
            received=not already_owned,
            already_owned=already_owned,
            character_code=character.code,
            character_name=character.name,
            character_type=character.type_label,
            dialog=character.dialog,
            match_reason=f"Matched by {match_label}",
        )
