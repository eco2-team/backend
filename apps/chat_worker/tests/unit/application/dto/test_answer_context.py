"""AnswerContext and AnswerResult DTO Unit Tests."""

import pytest

from chat_worker.application.dto.answer_context import AnswerContext, AnswerResult


class TestAnswerContext:
    """AnswerContext DTO 테스트."""

    def test_create_empty(self) -> None:
        """빈 컨텍스트 생성."""
        context = AnswerContext()

        assert context.classification is None
        assert context.disposal_rules is None
        assert context.character_context is None
        assert context.location_context is None
        assert context.web_search_results is None
        assert context.recyclable_price_context is None
        assert context.bulk_waste_context is None
        assert context.weather_context is None
        assert context.collection_point_context is None
        assert context.user_input == ""
        assert context.conversation_history is None
        assert context.conversation_summary is None

    def test_create_with_all_fields(self) -> None:
        """모든 필드로 생성."""
        context = AnswerContext(
            classification={"category": "plastic"},
            disposal_rules={"method": "separate"},
            character_context={"name": "재활이"},
            location_context={"name": "서울 재활용센터"},
            web_search_results="최신 정책 정보...",
            recyclable_price_context="고철 kg당 500원",
            bulk_waste_context="소파 수수료 5,000원",
            weather_context="오늘 맑음, 분리배출 최적",
            collection_point_context="의류수거함 500m 내 3개",
            user_input="플라스틱 어떻게 버려?",
            conversation_history=[{"role": "user", "content": "안녕"}],
            conversation_summary="이전 대화 요약...",
        )

        assert context.classification == {"category": "plastic"}
        assert context.user_input == "플라스틱 어떻게 버려?"
        assert context.conversation_history is not None

    def test_has_context_empty(self) -> None:
        """빈 컨텍스트는 False."""
        context = AnswerContext()

        assert context.has_context() is False

    def test_has_context_with_classification(self) -> None:
        """classification 있으면 True."""
        context = AnswerContext(classification={"category": "plastic"})

        assert context.has_context() is True

    def test_has_context_with_disposal_rules(self) -> None:
        """disposal_rules 있으면 True."""
        context = AnswerContext(disposal_rules={"method": "recycle"})

        assert context.has_context() is True

    def test_has_context_with_conversation_history(self) -> None:
        """conversation_history 있으면 True."""
        context = AnswerContext(
            conversation_history=[{"role": "user", "content": "hi"}]
        )

        assert context.has_context() is True

    def test_to_prompt_context_empty(self) -> None:
        """빈 컨텍스트의 프롬프트."""
        context = AnswerContext()

        result = context.to_prompt_context()

        assert result == ""

    def test_to_prompt_context_with_user_input(self) -> None:
        """user_input 포함된 프롬프트."""
        context = AnswerContext(user_input="플라스틱 버리는 법")

        result = context.to_prompt_context()

        assert "## User Question" in result
        assert "플라스틱 버리는 법" in result

    def test_to_prompt_context_with_classification(self) -> None:
        """classification 포함된 프롬프트."""
        context = AnswerContext(
            classification={"category": "plastic", "confidence": 0.95}
        )

        result = context.to_prompt_context()

        assert "## Classification" in result
        assert '"category": "plastic"' in result

    def test_to_prompt_context_with_conversation_summary(self) -> None:
        """conversation_summary 포함된 프롬프트."""
        context = AnswerContext(
            conversation_summary="사용자가 플라스틱 분류에 관심 있음"
        )

        result = context.to_prompt_context()

        assert "## Previous Conversation Summary" in result
        assert "플라스틱 분류에 관심" in result

    def test_to_prompt_context_with_conversation_history(self) -> None:
        """conversation_history 포함된 프롬프트."""
        context = AnswerContext(
            conversation_history=[
                {"role": "user", "content": "안녕"},
                {"role": "assistant", "content": "반갑습니다!"},
            ]
        )

        result = context.to_prompt_context()

        assert "## Recent Conversation" in result
        assert "- User: 안녕" in result
        assert "- Assistant: 반갑습니다!" in result

    def test_to_prompt_context_with_web_search(self) -> None:
        """web_search_results 포함된 프롬프트."""
        context = AnswerContext(web_search_results="최신 재활용 정책...")

        result = context.to_prompt_context()

        assert "## Web Search Results" in result
        assert "최신 재활용 정책" in result

    def test_to_prompt_context_with_weather(self) -> None:
        """weather_context 포함된 프롬프트."""
        context = AnswerContext(weather_context="오늘 맑음, 분리배출 최적")

        result = context.to_prompt_context()

        assert "## Weather Info" in result
        assert "분리배출 최적" in result

    def test_to_prompt_context_with_bulk_waste(self) -> None:
        """bulk_waste_context 포함된 프롬프트."""
        context = AnswerContext(bulk_waste_context="소파: 5000원, 냉장고: 8000원")

        result = context.to_prompt_context()

        assert "## Bulk Waste Info" in result
        assert "소파: 5000원" in result

    def test_to_prompt_context_with_collection_point(self) -> None:
        """collection_point_context 포함된 프롬프트."""
        context = AnswerContext(collection_point_context="의류수거함 3개 발견")

        result = context.to_prompt_context()

        assert "## Collection Point Info" in result
        assert "의류수거함 3개" in result

    def test_to_prompt_context_full(self) -> None:
        """모든 필드가 있는 프롬프트."""
        context = AnswerContext(
            conversation_summary="요약",
            conversation_history=[{"role": "user", "content": "hi"}],
            classification={"cat": "plastic"},
            disposal_rules={"method": "recycle"},
            character_context={"name": "재활이"},
            location_context={"addr": "서울"},
            web_search_results="검색 결과",
            recyclable_price_context="시세 정보",
            bulk_waste_context="대형폐기물",
            weather_context="날씨 정보",
            collection_point_context="수거함 정보",
            user_input="질문",
        )

        result = context.to_prompt_context()

        # 모든 섹션 포함 확인
        assert "## Previous Conversation Summary" in result
        assert "## Recent Conversation" in result
        assert "## Classification" in result
        assert "## Disposal Rules" in result
        assert "## Character Info" in result
        assert "## Location Info" in result
        assert "## Web Search Results" in result
        assert "## Recyclable Price Info" in result
        assert "## Bulk Waste Info" in result
        assert "## Weather Info" in result
        assert "## Collection Point Info" in result
        assert "## User Question" in result


class TestAnswerResult:
    """AnswerResult DTO 테스트."""

    def test_create_with_required_fields(self) -> None:
        """필수 필드로 생성."""
        result = AnswerResult(answer="플라스틱은 투명 페트병으로...")

        assert result.answer == "플라스틱은 투명 페트병으로..."
        assert result.token_count == 0
        assert result.model == ""
        assert result.context_used == []
        assert result.is_streamed is False

    def test_create_with_all_fields(self) -> None:
        """모든 필드로 생성."""
        result = AnswerResult(
            answer="답변 내용",
            token_count=150,
            model="gpt-4o",
            context_used=["classification", "disposal_rules"],
            is_streamed=True,
        )

        assert result.answer == "답변 내용"
        assert result.token_count == 150
        assert result.model == "gpt-4o"
        assert result.context_used == ["classification", "disposal_rules"]
        assert result.is_streamed is True

    def test_from_stream(self) -> None:
        """스트리밍 청크에서 생성."""
        chunks = ["플라스", "틱은 ", "재활용", " 가능합", "니다."]

        result = AnswerResult.from_stream(
            chunks=chunks,
            model="gpt-4o-mini",
            context_used=["rag"],
        )

        assert result.answer == "플라스틱은 재활용 가능합니다."
        assert result.model == "gpt-4o-mini"
        assert result.context_used == ["rag"]
        assert result.is_streamed is True

    def test_from_stream_empty(self) -> None:
        """빈 스트림에서 생성."""
        result = AnswerResult.from_stream(chunks=[])

        assert result.answer == ""
        assert result.is_streamed is True

    def test_from_stream_default_context(self) -> None:
        """context_used 기본값."""
        result = AnswerResult.from_stream(chunks=["test"])

        assert result.context_used == []

    def test_to_dict(self) -> None:
        """딕셔너리 변환."""
        result = AnswerResult(
            answer="답변",
            token_count=100,
            model="claude-3",
            context_used=["web_search"],
            is_streamed=False,
        )

        d = result.to_dict()

        assert d["answer"] == "답변"
        assert d["token_count"] == 100
        assert d["model"] == "claude-3"
        assert d["context_used"] == ["web_search"]
        assert d["is_streamed"] is False

    def test_empty_answer(self) -> None:
        """빈 답변."""
        result = AnswerResult(answer="")

        assert result.answer == ""
        assert result.to_dict()["answer"] == ""

    def test_large_token_count(self) -> None:
        """큰 토큰 수."""
        result = AnswerResult(answer="답변", token_count=100000)

        assert result.token_count == 100000
