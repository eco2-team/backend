"""EvaluateRewardCommand.

리워드 평가 Command입니다.
"""

import logging

from character.application.reward.dto import RewardRequest, RewardResult
from character.application.reward.ports import CharacterMatcher, OwnershipChecker
from character.application.reward.services.reward_policy_service import (
    RewardPolicyService,
)

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
        policy_service: RewardPolicyService,
    ) -> None:
        """Initialize.

        Args:
            matcher: 캐릭터 매처
            ownership_checker: 소유권 확인기
            policy_service: 리워드 정책 서비스
        """
        self._matcher = matcher
        self._ownership_checker = ownership_checker
        self._policy_service = policy_service

    async def execute(self, request: RewardRequest) -> RewardResult:
        """리워드를 평가합니다.

        Args:
            request: 리워드 요청

        Returns:
            리워드 결과
        """
        # 1. 정책 확인 (Service 위임)
        if not self._policy_service.should_evaluate(request):
            logger.info(
                "Reward conditions not met: disposal_rules=%s, insufficiencies=%s",
                request.disposal_rules_present,
                request.insufficiencies_present,
            )
            return RewardResult(
                received=False,
                already_owned=False,
                match_reason="Conditions not met",
            )

        # 2. 매칭 라벨 추출 (Service 위임)
        match_label = self._policy_service.determine_match_label(request)
        character = await self._matcher.match_by_label(match_label)

        if character is None:
            logger.info("No character matched for label=%s, using default", match_label)
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
