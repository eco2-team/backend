"""Tests for Reward Evaluators (Strategy Pattern).

평가 전략 로직의 단위 테스트.
"""

from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from domains.character.schemas.reward import (
    CharacterRewardRequest,
    CharacterRewardSource,
    ClassificationSummary,
)
from domains.character.services.evaluators import (
    ScanRewardEvaluator,
    get_evaluator,
)

# 상수 정의
RECYCLABLE_WASTE_CATEGORY = "재활용폐기물"
MATCH_REASON_UNDEFINED = "미정의"


class TestScanRewardEvaluatorShouldEvaluate:
    """ScanRewardEvaluator.should_evaluate 테스트."""

    @pytest.fixture
    def evaluator(self):
        return ScanRewardEvaluator()

    def test_returns_true_when_all_conditions_met(self, evaluator):
        """모든 조건 충족 시 True."""
        payload = CharacterRewardRequest(
            source=CharacterRewardSource.SCAN,
            user_id=uuid4(),
            task_id="test-123",
            classification=ClassificationSummary(
                major_category=RECYCLABLE_WASTE_CATEGORY,
                middle_category="플라스틱",
            ),
            disposal_rules_present=True,
            insufficiencies_present=False,
        )

        result = evaluator.should_evaluate(payload)
        assert result is True

    def test_returns_false_when_not_recyclable(self, evaluator):
        """재활용폐기물이 아닐 때 False."""
        payload = CharacterRewardRequest(
            source=CharacterRewardSource.SCAN,
            user_id=uuid4(),
            task_id="test-123",
            classification=ClassificationSummary(
                major_category="일반폐기물",
                middle_category="음식물",
            ),
            disposal_rules_present=True,
            insufficiencies_present=False,
        )

        result = evaluator.should_evaluate(payload)
        assert result is False

    def test_returns_false_when_insufficiencies_present(self, evaluator):
        """부족한 정보가 있을 때 False."""
        payload = CharacterRewardRequest(
            source=CharacterRewardSource.SCAN,
            user_id=uuid4(),
            task_id="test-123",
            classification=ClassificationSummary(
                major_category=RECYCLABLE_WASTE_CATEGORY,
                middle_category="플라스틱",
            ),
            disposal_rules_present=True,
            insufficiencies_present=True,
        )

        result = evaluator.should_evaluate(payload)
        assert result is False

    def test_returns_false_when_no_disposal_rules(self, evaluator):
        """분리배출 규칙이 없을 때 False."""
        payload = CharacterRewardRequest(
            source=CharacterRewardSource.SCAN,
            user_id=uuid4(),
            task_id="test-123",
            classification=ClassificationSummary(
                major_category=RECYCLABLE_WASTE_CATEGORY,
                middle_category="플라스틱",
            ),
            disposal_rules_present=False,
            insufficiencies_present=False,
        )

        result = evaluator.should_evaluate(payload)
        assert result is False


class TestScanRewardEvaluatorBuildMatchReason:
    """ScanRewardEvaluator.build_match_reason 테스트."""

    @pytest.fixture
    def evaluator(self):
        return ScanRewardEvaluator()

    def test_middle_and_minor(self, evaluator):
        """middle_category와 minor_category가 있을 때."""
        payload = CharacterRewardRequest(
            source=CharacterRewardSource.SCAN,
            user_id=uuid4(),
            task_id="test-123",
            classification=ClassificationSummary(
                major_category=RECYCLABLE_WASTE_CATEGORY,
                middle_category="플라스틱",
                minor_category="페트병",
            ),
            disposal_rules_present=True,
            insufficiencies_present=False,
        )

        result = evaluator.build_match_reason(payload)
        assert result == "플라스틱>페트병"

    def test_middle_only(self, evaluator):
        """middle_category만 있을 때."""
        payload = CharacterRewardRequest(
            source=CharacterRewardSource.SCAN,
            user_id=uuid4(),
            task_id="test-123",
            classification=ClassificationSummary(
                major_category=RECYCLABLE_WASTE_CATEGORY,
                middle_category="유리",
                minor_category=None,
            ),
            disposal_rules_present=True,
            insufficiencies_present=False,
        )

        result = evaluator.build_match_reason(payload)
        assert result == "유리"

    def test_major_only(self, evaluator):
        """major_category만 유효할 때."""
        payload = CharacterRewardRequest(
            source=CharacterRewardSource.SCAN,
            user_id=uuid4(),
            task_id="test-123",
            classification=ClassificationSummary(
                major_category="일반폐기물",
                middle_category=" ",  # 공백
                minor_category=None,
            ),
            disposal_rules_present=True,
            insufficiencies_present=False,
        )

        result = evaluator.build_match_reason(payload)
        assert result == "일반폐기물"

    def test_all_empty_returns_undefined(self, evaluator):
        """모든 카테고리가 공백일 때."""
        payload = CharacterRewardRequest(
            source=CharacterRewardSource.SCAN,
            user_id=uuid4(),
            task_id="test-123",
            classification=ClassificationSummary(
                major_category=" ",
                middle_category=" ",
                minor_category=None,
            ),
            disposal_rules_present=True,
            insufficiencies_present=False,
        )

        result = evaluator.build_match_reason(payload)
        assert result == MATCH_REASON_UNDEFINED


class TestScanRewardEvaluatorMatchCharacters:
    """ScanRewardEvaluator.match_characters 테스트."""

    @pytest.fixture
    def evaluator(self):
        return ScanRewardEvaluator()

    @pytest.fixture
    def mock_characters(self):
        """테스트용 캐릭터 목록."""
        plastic_char = MagicMock()
        plastic_char.name = "플라봇"
        plastic_char.match_label = "플라스틱"

        glass_char = MagicMock()
        glass_char.name = "유리봇"
        glass_char.match_label = "유리"

        default_char = MagicMock()
        default_char.name = "이코"
        default_char.match_label = None

        return [plastic_char, glass_char, default_char]

    def test_matches_by_middle_category(self, evaluator, mock_characters):
        """middle_category로 캐릭터 매칭."""
        payload = CharacterRewardRequest(
            source=CharacterRewardSource.SCAN,
            user_id=uuid4(),
            task_id="test-123",
            classification=ClassificationSummary(
                major_category=RECYCLABLE_WASTE_CATEGORY,
                middle_category="플라스틱",
            ),
            disposal_rules_present=True,
            insufficiencies_present=False,
        )

        result = evaluator.match_characters(payload, mock_characters)

        assert len(result) == 1
        assert result[0].name == "플라봇"

    def test_returns_empty_when_no_match_label(self, evaluator, mock_characters):
        """match_label이 없으면 빈 리스트 반환."""
        payload = CharacterRewardRequest(
            source=CharacterRewardSource.SCAN,
            user_id=uuid4(),
            task_id="test-123",
            classification=ClassificationSummary(
                major_category=RECYCLABLE_WASTE_CATEGORY,
                middle_category=" ",  # 공백
            ),
            disposal_rules_present=True,
            insufficiencies_present=False,
        )

        result = evaluator.match_characters(payload, mock_characters)

        assert result == []

    def test_matches_glass_category(self, evaluator, mock_characters):
        """유리 카테고리 매칭."""
        payload = CharacterRewardRequest(
            source=CharacterRewardSource.SCAN,
            user_id=uuid4(),
            task_id="test-123",
            classification=ClassificationSummary(
                major_category=RECYCLABLE_WASTE_CATEGORY,
                middle_category="유리",
            ),
            disposal_rules_present=True,
            insufficiencies_present=False,
        )

        result = evaluator.match_characters(payload, mock_characters)

        assert len(result) == 1
        assert result[0].name == "유리봇"


class TestScanRewardEvaluatorSourceLabel:
    """ScanRewardEvaluator.source_label 테스트."""

    def test_source_label_is_scan_reward(self):
        """source_label이 'scan-reward'."""
        evaluator = ScanRewardEvaluator()
        assert evaluator.source_label == "scan-reward"


class TestEvaluatorRegistry:
    """Evaluator Registry 테스트."""

    def test_get_scan_evaluator(self):
        """SCAN evaluator 조회."""
        evaluator = get_evaluator(CharacterRewardSource.SCAN)
        assert evaluator is not None
        assert isinstance(evaluator, ScanRewardEvaluator)

    def test_get_unknown_source_returns_none(self):
        """등록되지 않은 소스는 None 반환."""
        from domains.character.services.evaluators.registry import _evaluators

        # _evaluators는 내부 구현이므로 존재하지 않는 키 테스트
        assert _evaluators.get("nonexistent") is None


class TestEvaluatorEvaluate:
    """Evaluator.evaluate (Template Method) 테스트."""

    @pytest.fixture
    def evaluator(self):
        return ScanRewardEvaluator()

    @pytest.fixture
    def mock_characters(self):
        """테스트용 캐릭터 목록."""
        plastic_char = MagicMock()
        plastic_char.name = "플라봇"
        plastic_char.match_label = "플라스틱"
        return [plastic_char]

    def test_evaluate_returns_should_not_evaluate(self, evaluator):
        """조건 미충족 시 should_evaluate=False."""
        payload = CharacterRewardRequest(
            source=CharacterRewardSource.SCAN,
            user_id=uuid4(),
            task_id="test-123",
            classification=ClassificationSummary(
                major_category="일반폐기물",
                middle_category="음식물",
            ),
            disposal_rules_present=True,
            insufficiencies_present=False,
        )

        result = evaluator.evaluate(payload, [])

        assert result.should_evaluate is False
        assert result.matches == []
        assert result.source_label == "scan-reward"  # 항상 source_label 포함

    def test_evaluate_returns_matches_with_source_label(self, evaluator, mock_characters):
        """조건 충족 시 매칭된 캐릭터와 source_label 반환."""
        payload = CharacterRewardRequest(
            source=CharacterRewardSource.SCAN,
            user_id=uuid4(),
            task_id="test-123",
            classification=ClassificationSummary(
                major_category=RECYCLABLE_WASTE_CATEGORY,
                middle_category="플라스틱",
            ),
            disposal_rules_present=True,
            insufficiencies_present=False,
        )

        result = evaluator.evaluate(payload, mock_characters)

        assert result.should_evaluate is True
        assert len(result.matches) == 1
        assert result.match_reason == "플라스틱"
        assert result.source_label == "scan-reward"  # Strategy에서 제공
