"""EvaluateRewardCommand 단위 테스트."""

from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from apps.character.application.reward.commands.evaluate_reward import (
    EvaluateRewardCommand,
)
from apps.character.application.reward.dto import (
    ClassificationSummary,
    RewardRequest,
)
from apps.character.application.reward.services.reward_policy_service import (
    RewardPolicyService,
)
from apps.character.domain.entities import Character
from apps.character.domain.enums import CharacterRewardSource

pytestmark = pytest.mark.asyncio


@pytest.fixture
def mock_matcher() -> AsyncMock:
    """CharacterMatcher mock."""
    matcher = AsyncMock()
    matcher.match_by_label = AsyncMock()
    matcher.get_default = AsyncMock()
    return matcher


@pytest.fixture
def mock_ownership_checker() -> AsyncMock:
    """OwnershipChecker mock."""
    checker = AsyncMock()
    checker.is_owned = AsyncMock(return_value=False)
    return checker


@pytest.fixture
def policy_service() -> RewardPolicyService:
    """RewardPolicyService 인스턴스."""
    return RewardPolicyService()


@pytest.fixture
def sample_character() -> Character:
    """테스트용 캐릭터."""
    return Character(
        id=uuid4(),
        code="char-pet",
        name="페트",
        type_label="재활용",
        dialog="안녕! 나는 페트야!",
        match_label="무색페트병",
        description="페트병 캐릭터",
    )


@pytest.fixture
def default_character() -> Character:
    """기본 캐릭터."""
    return Character(
        id=uuid4(),
        code="char-eco",
        name="이코",
        type_label="기본",
        dialog="안녕! 나는 이코야!",
        match_label=None,
        description="기본 캐릭터",
    )


class TestEvaluateRewardCommand:
    """EvaluateRewardCommand 테스트."""

    async def test_conditions_not_met_no_disposal_rules(
        self,
        mock_matcher: AsyncMock,
        mock_ownership_checker: AsyncMock,
        policy_service: RewardPolicyService,
    ) -> None:
        """disposal_rules가 없으면 리워드 미지급."""
        command = EvaluateRewardCommand(mock_matcher, mock_ownership_checker, policy_service)

        request = RewardRequest(
            user_id=uuid4(),
            source=CharacterRewardSource.SCAN,
            classification=ClassificationSummary(
                major_category="재활용폐기물",
                middle_category="무색페트병",
            ),
            disposal_rules_present=False,  # 조건 미충족
            insufficiencies_present=False,
        )

        result = await command.execute(request)

        assert result.received is False
        assert result.already_owned is False
        assert result.match_reason == "Conditions not met"
        mock_matcher.match_by_label.assert_not_called()

    async def test_conditions_not_met_has_insufficiencies(
        self,
        mock_matcher: AsyncMock,
        mock_ownership_checker: AsyncMock,
        policy_service: RewardPolicyService,
    ) -> None:
        """insufficiencies가 있으면 리워드 미지급."""
        command = EvaluateRewardCommand(mock_matcher, mock_ownership_checker, policy_service)

        request = RewardRequest(
            user_id=uuid4(),
            source=CharacterRewardSource.SCAN,
            classification=ClassificationSummary(
                major_category="재활용폐기물",
                middle_category="무색페트병",
            ),
            disposal_rules_present=True,
            insufficiencies_present=True,  # 조건 미충족
        )

        result = await command.execute(request)

        assert result.received is False
        assert result.already_owned is False
        assert result.match_reason == "Conditions not met"
        mock_matcher.match_by_label.assert_not_called()

    async def test_character_matched_and_not_owned(
        self,
        mock_matcher: AsyncMock,
        mock_ownership_checker: AsyncMock,
        policy_service: RewardPolicyService,
        sample_character: Character,
    ) -> None:
        """캐릭터 매칭 성공 + 미소유 = 리워드 지급."""
        mock_matcher.match_by_label.return_value = sample_character
        mock_ownership_checker.is_owned.return_value = False

        command = EvaluateRewardCommand(mock_matcher, mock_ownership_checker, policy_service)

        request = RewardRequest(
            user_id=uuid4(),
            source=CharacterRewardSource.SCAN,
            classification=ClassificationSummary(
                major_category="재활용폐기물",
                middle_category="무색페트병",
            ),
            disposal_rules_present=True,
            insufficiencies_present=False,
        )

        result = await command.execute(request)

        assert result.received is True
        assert result.already_owned is False
        assert result.character_code == "char-pet"
        assert result.character_name == "페트"
        assert "무색페트병" in result.match_reason

    async def test_character_already_owned(
        self,
        mock_matcher: AsyncMock,
        mock_ownership_checker: AsyncMock,
        policy_service: RewardPolicyService,
        sample_character: Character,
    ) -> None:
        """이미 소유한 캐릭터 = 리워드 미지급."""
        mock_matcher.match_by_label.return_value = sample_character
        mock_ownership_checker.is_owned.return_value = True  # 이미 소유

        command = EvaluateRewardCommand(mock_matcher, mock_ownership_checker, policy_service)

        request = RewardRequest(
            user_id=uuid4(),
            source=CharacterRewardSource.SCAN,
            classification=ClassificationSummary(
                major_category="재활용폐기물",
                middle_category="무색페트병",
            ),
            disposal_rules_present=True,
            insufficiencies_present=False,
        )

        result = await command.execute(request)

        assert result.received is False
        assert result.already_owned is True
        assert result.character_code == "char-pet"

    async def test_fallback_to_default_character(
        self,
        mock_matcher: AsyncMock,
        mock_ownership_checker: AsyncMock,
        policy_service: RewardPolicyService,
        default_character: Character,
    ) -> None:
        """매칭 실패 시 기본 캐릭터로 폴백."""
        mock_matcher.match_by_label.return_value = None  # 매칭 실패
        mock_matcher.get_default.return_value = default_character
        mock_ownership_checker.is_owned.return_value = False

        command = EvaluateRewardCommand(mock_matcher, mock_ownership_checker, policy_service)

        request = RewardRequest(
            user_id=uuid4(),
            source=CharacterRewardSource.SCAN,
            classification=ClassificationSummary(
                major_category="재활용폐기물",
                middle_category="알수없음",
            ),
            disposal_rules_present=True,
            insufficiencies_present=False,
        )

        result = await command.execute(request)

        assert result.received is True
        assert result.character_code == "char-eco"
        assert result.character_name == "이코"
        mock_matcher.get_default.assert_called_once()
