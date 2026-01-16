"""Feedback Evaluator Service Tests.

RAG 품질 평가 서비스 테스트.

리팩토링 후:
- FeedbackEvaluatorService는 순수 비즈니스 로직만 담당
- evaluate_by_rules: Rule 기반 평가 (sync)
- should_use_fallback: Fallback 필요 여부 (sync)
- needs_llm_evaluation: LLM 평가 필요 여부 (sync)
"""

import pytest

from chat_worker.application.dto.feedback_result import FeedbackResult
from chat_worker.application.services.feedback_evaluator import FeedbackEvaluatorService
from chat_worker.domain.enums import FallbackReason, FeedbackQuality


class TestFeedbackResult:
    """FeedbackResult DTO 테스트."""

    def test_from_score_excellent(self) -> None:
        """0.9+ 점수는 EXCELLENT."""
        result = FeedbackResult.from_score(0.95)
        assert result.quality == FeedbackQuality.EXCELLENT
        assert result.needs_fallback is False

    def test_from_score_good(self) -> None:
        """0.7-0.9 점수는 GOOD."""
        result = FeedbackResult.from_score(0.8)
        assert result.quality == FeedbackQuality.GOOD
        assert result.needs_fallback is False

    def test_from_score_partial(self) -> None:
        """0.4-0.7 점수는 PARTIAL."""
        result = FeedbackResult.from_score(0.5)
        assert result.quality == FeedbackQuality.PARTIAL
        assert result.needs_fallback is False

    def test_from_score_poor(self) -> None:
        """0.2-0.4 점수는 POOR."""
        result = FeedbackResult.from_score(0.3)
        assert result.quality == FeedbackQuality.POOR
        assert result.needs_fallback is True
        assert result.fallback_reason == FallbackReason.RAG_LOW_QUALITY

    def test_from_score_none(self) -> None:
        """0-0.2 점수는 NONE."""
        result = FeedbackResult.from_score(0.1)
        assert result.quality == FeedbackQuality.NONE
        assert result.needs_fallback is True
        # 0.1은 0 이상이므로 RAG_LOW_QUALITY
        assert result.fallback_reason == FallbackReason.RAG_LOW_QUALITY

    def test_from_score_zero(self) -> None:
        """0점은 RAG_NO_RESULT."""
        result = FeedbackResult.from_score(0.05)
        assert result.quality == FeedbackQuality.NONE
        assert result.needs_fallback is True
        assert result.fallback_reason == FallbackReason.RAG_NO_RESULT

    def test_no_result_factory(self) -> None:
        """no_result 팩토리 메서드."""
        result = FeedbackResult.no_result()
        assert result.quality == FeedbackQuality.NONE
        assert result.score == 0.0
        assert result.needs_fallback is True
        assert result.fallback_reason == FallbackReason.RAG_NO_RESULT

    def test_excellent_factory(self) -> None:
        """excellent 팩토리 메서드."""
        result = FeedbackResult.excellent()
        assert result.quality == FeedbackQuality.EXCELLENT
        assert result.score >= 0.9
        assert result.needs_fallback is False

    def test_to_dict(self) -> None:
        """to_dict 변환."""
        result = FeedbackResult.from_score(0.75, ["suggestion1"], {"key": "value"})
        d = result.to_dict()

        assert d["quality"] == "good"
        assert d["score"] == 0.75
        assert d["needs_fallback"] is False
        assert d["suggestions"] == ["suggestion1"]
        assert d["metadata"] == {"key": "value"}


class TestFeedbackQuality:
    """FeedbackQuality Enum 테스트."""

    def test_needs_fallback_poor(self) -> None:
        """POOR는 Fallback 필요."""
        assert FeedbackQuality.POOR.needs_fallback() is True

    def test_needs_fallback_none(self) -> None:
        """NONE은 Fallback 필요."""
        assert FeedbackQuality.NONE.needs_fallback() is True

    def test_needs_fallback_good(self) -> None:
        """GOOD은 Fallback 불필요."""
        assert FeedbackQuality.GOOD.needs_fallback() is False

    def test_needs_enhancement_partial(self) -> None:
        """PARTIAL은 Enhancement 필요."""
        assert FeedbackQuality.PARTIAL.needs_enhancement() is True

    def test_needs_enhancement_excellent(self) -> None:
        """EXCELLENT은 Enhancement 불필요."""
        assert FeedbackQuality.EXCELLENT.needs_enhancement() is False


class TestFeedbackEvaluatorService:
    """FeedbackEvaluatorService 테스트.

    리팩토링 후 Service는 순수 비즈니스 로직만 담당.
    모든 메서드가 sync (Port 의존 없음).
    """

    @pytest.fixture
    def service(self) -> FeedbackEvaluatorService:
        """서비스 인스턴스."""
        return FeedbackEvaluatorService()

    def test_evaluate_no_result(self, service: FeedbackEvaluatorService) -> None:
        """결과 없음 평가."""
        result = service.evaluate_by_rules(
            query="플라스틱 분리수거",
            rag_results=None,
        )
        assert result.quality == FeedbackQuality.NONE
        assert result.needs_fallback is True

    def test_evaluate_empty_data(self, service: FeedbackEvaluatorService) -> None:
        """빈 데이터 평가."""
        result = service.evaluate_by_rules(
            query="플라스틱 분리수거",
            rag_results={"data": {}},
        )
        assert result.score < 0.3
        assert result.needs_fallback is True

    def test_evaluate_good_result(self, service: FeedbackEvaluatorService) -> None:
        """좋은 결과 평가."""
        result = service.evaluate_by_rules(
            query="플라스틱 분리수거",
            rag_results={
                "category": "재활용폐기물_플라스틱류",
                "data": {
                    "disposal_info": [
                        {"item": "페트병", "method": "라벨 제거 후 분리배출"},
                        {"item": "플라스틱 용기", "method": "세척 후 분리배출"},
                    ],
                    "examples": ["페트병", "플라스틱 용기"],
                },
            },
        )
        assert result.score >= 0.5
        assert result.quality in (FeedbackQuality.GOOD, FeedbackQuality.PARTIAL)

    def test_evaluate_keyword_matching(
        self, service: FeedbackEvaluatorService
    ) -> None:
        """키워드 매칭 점수."""
        result = service.evaluate_by_rules(
            query="페트병 분리수거",
            rag_results={
                "category": "재활용폐기물_플라스틱류",
                "data": {
                    "disposal_info": [{"item": "페트병", "method": "라벨 제거 후 배출"}],
                    "examples": ["페트병"],
                },
            },
        )
        # 키워드 매칭으로 점수 확인 (keyword_match_ratio 사용)
        assert result.metadata.get("keyword_match_ratio", 0) > 0

    def test_should_use_fallback_waste_intent(
        self, service: FeedbackEvaluatorService
    ) -> None:
        """waste intent에서 Fallback 필요 여부."""
        feedback = FeedbackResult.from_score(0.2)
        needs, reason = service.should_use_fallback(feedback, "waste")

        assert needs is True
        assert reason == FallbackReason.RAG_LOW_QUALITY

    def test_should_not_fallback_good_result(
        self, service: FeedbackEvaluatorService
    ) -> None:
        """좋은 결과는 Fallback 불필요."""
        feedback = FeedbackResult.from_score(0.8)
        needs, reason = service.should_use_fallback(feedback, "waste")

        assert needs is False
        assert reason is None

    def test_needs_llm_evaluation_for_partial(
        self, service: FeedbackEvaluatorService
    ) -> None:
        """PARTIAL 결과는 LLM 평가 필요."""
        result = FeedbackResult.from_score(0.5)  # PARTIAL
        assert service.needs_llm_evaluation(result) is True

    def test_no_llm_evaluation_for_good(
        self, service: FeedbackEvaluatorService
    ) -> None:
        """GOOD 결과는 LLM 평가 불필요."""
        result = FeedbackResult.from_score(0.8)  # GOOD
        assert service.needs_llm_evaluation(result) is False

    def test_no_llm_evaluation_for_excellent(
        self, service: FeedbackEvaluatorService
    ) -> None:
        """EXCELLENT 결과는 LLM 평가 불필요."""
        result = FeedbackResult.from_score(0.95)  # EXCELLENT
        assert service.needs_llm_evaluation(result) is False
