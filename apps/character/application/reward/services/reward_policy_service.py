"""RewardPolicyService.

보상 지급 여부 판단 및 매칭 라벨 결정 등
포트 의존성 없는 순수 애플리케이션 로직을 담당합니다.
"""

from character.application.reward.dto import RewardRequest


class RewardPolicyService:
    """리워드 정책 서비스."""

    def should_evaluate(self, request: RewardRequest) -> bool:
        """보상 평가를 진행해야 하는지 판단합니다.

        정책:
        - 분리수거 규칙 정보가 있어야 함
        - 부적절한 항목이 없어야 함

        Args:
            request: 리워드 요청

        Returns:
            평가 진행 여부
        """
        return request.disposal_rules_present and not request.insufficiencies_present

    def determine_match_label(self, request: RewardRequest) -> str:
        """매칭에 사용할 라벨을 결정합니다.

        정책:
        - 분류 결과의 중분류(middle_category)를 사용

        Args:
            request: 리워드 요청

        Returns:
            매칭 라벨
        """
        return request.classification.middle_category
