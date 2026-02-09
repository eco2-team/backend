"""CalibrationSample Value Object Unit Tests."""

from __future__ import annotations

import pytest

from chat_worker.domain.exceptions.eval_exceptions import (
    InvalidCalibrationSampleError,
)
from chat_worker.domain.value_objects.calibration_sample import CalibrationSample


def _make_sample(**overrides) -> CalibrationSample:
    """기본 CalibrationSample 팩토리."""
    defaults = {
        "query": "페트병 분리배출 방법은?",
        "intent": "waste",
        "context": "환경부 분리배출 가이드",
        "reference_answer": "페트병은 내용물을 비우고 라벨을 제거한 뒤 배출합니다.",
        "human_scores": {
            "faithfulness": 5,
            "relevance": 4,
            "completeness": 4,
            "safety": 5,
            "communication": 4,
        },
        "annotator_agreement": 0.85,
    }
    defaults.update(overrides)
    return CalibrationSample(**defaults)


@pytest.mark.eval_unit
class TestCalibrationSample:
    """CalibrationSample Value Object 테스트."""

    def test_valid_creation(self) -> None:
        """유효한 값으로 CalibrationSample 생성."""
        sample = _make_sample()

        assert sample.query == "페트병 분리배출 방법은?"
        assert sample.intent == "waste"
        assert sample.context == "환경부 분리배출 가이드"
        assert sample.reference_answer == "페트병은 내용물을 비우고 라벨을 제거한 뒤 배출합니다."
        assert sample.human_scores["faithfulness"] == 5
        assert sample.annotator_agreement == 0.85

    def test_negative_agreement_raises(self) -> None:
        """음수 annotator_agreement는 도메인 예외 발생."""
        with pytest.raises(InvalidCalibrationSampleError, match="must be >= 0.0"):
            _make_sample(annotator_agreement=-0.1)

    def test_zero_agreement_valid(self) -> None:
        """annotator_agreement=0.0은 유효 (VO 허용 범위)."""
        sample = _make_sample(annotator_agreement=0.0)

        assert sample.annotator_agreement == 0.0

    def test_to_dict(self) -> None:
        """딕셔너리 변환 검증."""
        sample = _make_sample()

        d = sample.to_dict()

        assert d["query"] == "페트병 분리배출 방법은?"
        assert d["intent"] == "waste"
        assert d["context"] == "환경부 분리배출 가이드"
        assert d["reference_answer"] == "페트병은 내용물을 비우고 라벨을 제거한 뒤 배출합니다."
        assert d["human_scores"]["faithfulness"] == 5
        assert d["annotator_agreement"] == 0.85
        assert isinstance(d, dict)

    def test_from_dict(self) -> None:
        """딕셔너리에서 CalibrationSample 복원 (라운드트립)."""
        original = _make_sample()

        d = original.to_dict()
        restored = CalibrationSample.from_dict(d)

        assert restored.query == original.query
        assert restored.intent == original.intent
        assert restored.context == original.context
        assert restored.reference_answer == original.reference_answer
        assert restored.human_scores == original.human_scores
        assert restored.annotator_agreement == original.annotator_agreement

    def test_frozen(self) -> None:
        """불변성 테스트 (frozen dataclass)."""
        sample = _make_sample()

        with pytest.raises(AttributeError):
            sample.query = "변경 시도"  # type: ignore
