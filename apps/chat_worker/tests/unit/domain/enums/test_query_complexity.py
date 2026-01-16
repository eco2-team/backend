"""QueryComplexity Enum Unit Tests."""

import pytest

from chat_worker.domain.enums.query_complexity import QueryComplexity


class TestQueryComplexity:
    """QueryComplexity Enum 테스트."""

    def test_complexity_values(self) -> None:
        """복잡도 값 확인."""
        assert QueryComplexity.SIMPLE.value == "simple"
        assert QueryComplexity.COMPLEX.value == "complex"

    def test_from_bool_simple(self) -> None:
        """False -> SIMPLE."""
        result = QueryComplexity.from_bool(False)
        assert result == QueryComplexity.SIMPLE

    def test_from_bool_complex(self) -> None:
        """True -> COMPLEX."""
        result = QueryComplexity.from_bool(True)
        assert result == QueryComplexity.COMPLEX

    def test_from_string_valid_simple(self) -> None:
        """'simple' 문자열에서 생성."""
        assert QueryComplexity.from_string("simple") == QueryComplexity.SIMPLE

    def test_from_string_valid_complex(self) -> None:
        """'complex' 문자열에서 생성."""
        assert QueryComplexity.from_string("complex") == QueryComplexity.COMPLEX

    def test_from_string_case_insensitive(self) -> None:
        """대소문자 구분 없이 변환."""
        assert QueryComplexity.from_string("SIMPLE") == QueryComplexity.SIMPLE
        assert QueryComplexity.from_string("Simple") == QueryComplexity.SIMPLE
        assert QueryComplexity.from_string("COMPLEX") == QueryComplexity.COMPLEX
        assert QueryComplexity.from_string("Complex") == QueryComplexity.COMPLEX

    def test_from_string_invalid_returns_simple(self) -> None:
        """유효하지 않은 문자열은 SIMPLE 반환."""
        assert QueryComplexity.from_string("invalid") == QueryComplexity.SIMPLE
        assert QueryComplexity.from_string("unknown") == QueryComplexity.SIMPLE
        assert QueryComplexity.from_string("") == QueryComplexity.SIMPLE

    def test_complexity_is_string_enum(self) -> None:
        """QueryComplexity는 str 기반 Enum."""
        assert isinstance(QueryComplexity.SIMPLE.value, str)
        assert QueryComplexity.SIMPLE.value == "simple"

    def test_complexity_comparison(self) -> None:
        """복잡도 비교."""
        assert QueryComplexity.SIMPLE == QueryComplexity.SIMPLE
        assert QueryComplexity.SIMPLE != QueryComplexity.COMPLEX
        assert QueryComplexity.SIMPLE == "simple"

    def test_complexity_count(self) -> None:
        """총 복잡도 수 확인."""
        all_complexities = list(QueryComplexity)
        assert len(all_complexities) == 2
