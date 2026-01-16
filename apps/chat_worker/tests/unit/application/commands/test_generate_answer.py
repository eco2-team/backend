"""GenerateAnswerCommand Unit Tests."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from chat_worker.application.commands.generate_answer_command import (
    GenerateAnswerCommand,
    GenerateAnswerInput,
    GenerateAnswerOutput,
)


class TestGenerateAnswerInput:
    """GenerateAnswerInput DTO 테스트."""

    def test_create_with_required_fields(self) -> None:
        """필수 필드로 생성."""
        input_dto = GenerateAnswerInput(
            job_id="job-123",
            message="플라스틱 어떻게 버려?",
            intent="waste",
        )

        assert input_dto.job_id == "job-123"
        assert input_dto.message == "플라스틱 어떻게 버려?"
        assert input_dto.intent == "waste"
        assert input_dto.additional_intents == []
        assert input_dto.has_multi_intent is False

    def test_create_with_all_fields(self) -> None:
        """모든 필드로 생성."""
        input_dto = GenerateAnswerInput(
            job_id="job-123",
            message="플라스틱 버리면 캐릭터도?",
            intent="waste",
            additional_intents=["character"],
            has_multi_intent=True,
            classification={"category": "plastic"},
            disposal_rules={"method": "recycle"},
            character_context={"name": "재활이"},
            location_context={"name": "센터"},
            web_search_results={"results": []},
            recyclable_price_context="고철 500원/kg",
            bulk_waste_context="소파 5000원",
            weather_context="맑음",
            collection_point_context="의류수거함 3개",
            conversation_history=[{"role": "user", "content": "hi"}],
            conversation_summary="이전 대화 요약",
        )

        assert input_dto.has_multi_intent is True
        assert input_dto.additional_intents == ["character"]
        assert input_dto.recyclable_price_context == "고철 500원/kg"


class TestGenerateAnswerOutput:
    """GenerateAnswerOutput DTO 테스트."""

    def test_create_basic(self) -> None:
        """기본 출력 생성."""
        output = GenerateAnswerOutput(answer="플라스틱은 재활용 가능합니다.")

        assert output.answer == "플라스틱은 재활용 가능합니다."
        assert output.cache_hit is False
        assert output.events == []

    def test_create_with_cache_hit(self) -> None:
        """캐시 히트 출력."""
        output = GenerateAnswerOutput(
            answer="캐시된 답변",
            cache_hit=True,
            events=["cache_hit"],
        )

        assert output.cache_hit is True
        assert "cache_hit" in output.events


class TestGenerateAnswerCommand:
    """GenerateAnswerCommand 테스트."""

    @pytest.fixture
    def mock_llm(self) -> AsyncMock:
        """LLM 클라이언트 Mock."""
        llm = AsyncMock()

        async def mock_stream(prompt: str, system_prompt: str):
            for token in ["플라스", "틱은 ", "재활용 ", "가능해요."]:
                yield token

        llm.generate_stream = mock_stream
        return llm

    @pytest.fixture
    def mock_prompt_builder(self) -> MagicMock:
        """프롬프트 빌더 Mock."""
        builder = MagicMock()
        builder.build = MagicMock(return_value="system prompt")
        builder.build_multi = MagicMock(return_value="multi-intent system prompt")
        return builder

    @pytest.fixture
    def mock_cache(self) -> AsyncMock:
        """캐시 Mock."""
        cache = AsyncMock()
        cache.get = AsyncMock(return_value=None)
        cache.set = AsyncMock()
        return cache

    @pytest.fixture
    def command(
        self,
        mock_llm: AsyncMock,
        mock_prompt_builder: MagicMock,
        mock_cache: AsyncMock,
    ) -> GenerateAnswerCommand:
        """Command 인스턴스."""
        return GenerateAnswerCommand(
            llm=mock_llm,
            prompt_builder=mock_prompt_builder,
            cache=mock_cache,
        )

    @pytest.mark.anyio
    async def test_execute_streaming(
        self,
        command: GenerateAnswerCommand,
    ) -> None:
        """스트리밍 답변 생성."""
        input_dto = GenerateAnswerInput(
            job_id="job-123",
            message="플라스틱 버리는 법",
            intent="waste",
        )

        tokens = []
        async for token in command.execute(input_dto):
            tokens.append(token)

        assert len(tokens) == 4
        assert "".join(tokens) == "플라스틱은 재활용 가능해요."

    @pytest.mark.anyio
    async def test_execute_full(
        self,
        command: GenerateAnswerCommand,
    ) -> None:
        """전체 답변 생성."""
        input_dto = GenerateAnswerInput(
            job_id="job-123",
            message="플라스틱 버리는 법",
            intent="waste",
        )

        result = await command.execute_full(input_dto)

        assert result.answer == "플라스틱은 재활용 가능해요."
        assert result.cache_hit is False
        assert "llm_called" in result.events
        assert "answer_generated" in result.events

    @pytest.mark.anyio
    async def test_execute_full_cache_hit(
        self,
        command: GenerateAnswerCommand,
        mock_cache: AsyncMock,
    ) -> None:
        """캐시 히트 시 캐시된 답변 반환."""
        mock_cache.get = AsyncMock(return_value="캐시된 답변입니다.")

        input_dto = GenerateAnswerInput(
            job_id="job-123",
            message="안녕",
            intent="general",  # cacheable intent
        )

        result = await command.execute_full(input_dto)

        assert result.answer == "캐시된 답변입니다."
        assert result.cache_hit is True
        assert "cache_hit" in result.events

    @pytest.mark.anyio
    async def test_execute_full_llm_error(
        self,
        mock_prompt_builder: MagicMock,
        mock_cache: AsyncMock,
    ) -> None:
        """LLM 에러 시 에러 메시지 반환."""
        mock_llm = AsyncMock()

        async def error_stream(prompt: str, system_prompt: str):
            raise Exception("LLM Error")
            yield  # type: ignore

        mock_llm.generate_stream = error_stream

        command = GenerateAnswerCommand(
            llm=mock_llm,
            prompt_builder=mock_prompt_builder,
            cache=mock_cache,
        )

        input_dto = GenerateAnswerInput(
            job_id="job-123",
            message="테스트",
            intent="waste",
        )

        result = await command.execute_full(input_dto)

        assert "문제가 생겼어요" in result.answer
        assert "llm_error" in result.events

    @pytest.mark.anyio
    async def test_execute_with_context(
        self,
        command: GenerateAnswerCommand,
        mock_prompt_builder: MagicMock,
    ) -> None:
        """컨텍스트와 함께 답변 생성."""
        input_dto = GenerateAnswerInput(
            job_id="job-123",
            message="플라스틱 버리는 법",
            intent="waste",
            classification={"category": "plastic", "confidence": 0.9},
            disposal_rules={"data": {"method": "분리배출", "bin": "플라스틱"}},
        )

        result = await command.execute_full(input_dto)

        assert result.answer == "플라스틱은 재활용 가능해요."
        mock_prompt_builder.build.assert_called_with("waste")

    @pytest.mark.anyio
    async def test_execute_multi_intent(
        self,
        command: GenerateAnswerCommand,
        mock_prompt_builder: MagicMock,
    ) -> None:
        """Multi-Intent 답변 생성."""
        input_dto = GenerateAnswerInput(
            job_id="job-123",
            message="플라스틱 버리면 캐릭터 뭐야?",
            intent="waste",
            additional_intents=["character"],
            has_multi_intent=True,
        )

        result = await command.execute_full(input_dto)

        mock_prompt_builder.build_multi.assert_called_with(["waste", "character"])

    @pytest.mark.anyio
    async def test_cacheable_intent_only(
        self,
        command: GenerateAnswerCommand,
        mock_cache: AsyncMock,
    ) -> None:
        """general/greeting만 캐시 가능."""
        # waste는 캐시 불가
        input_dto = GenerateAnswerInput(
            job_id="job-123",
            message="플라스틱",
            intent="waste",
        )

        await command.execute_full(input_dto)

        # waste intent는 캐시에 저장 안함
        mock_cache.set.assert_not_called()

    @pytest.mark.anyio
    async def test_cacheable_without_context(
        self,
        command: GenerateAnswerCommand,
        mock_cache: AsyncMock,
    ) -> None:
        """컨텍스트 없는 general만 캐시."""
        input_dto = GenerateAnswerInput(
            job_id="job-123",
            message="안녕",
            intent="general",
        )

        await command.execute_full(input_dto)

        # general + no context → 캐시 저장
        mock_cache.set.assert_called_once()

    @pytest.mark.anyio
    async def test_not_cacheable_with_context(
        self,
        command: GenerateAnswerCommand,
        mock_cache: AsyncMock,
    ) -> None:
        """컨텍스트 있으면 캐시 안함."""
        input_dto = GenerateAnswerInput(
            job_id="job-123",
            message="안녕",
            intent="general",
            classification={"some": "data"},  # 컨텍스트 있음
        )

        await command.execute_full(input_dto)

        # 컨텍스트가 있으면 캐시 안함
        mock_cache.set.assert_not_called()

    @pytest.mark.anyio
    async def test_no_cache_port(
        self,
        mock_llm: AsyncMock,
        mock_prompt_builder: MagicMock,
    ) -> None:
        """캐시 Port 없이 동작."""
        command = GenerateAnswerCommand(
            llm=mock_llm,
            prompt_builder=mock_prompt_builder,
            cache=None,  # 캐시 없음
        )

        input_dto = GenerateAnswerInput(
            job_id="job-123",
            message="안녕",
            intent="general",
        )

        result = await command.execute_full(input_dto)

        assert result.answer == "플라스틱은 재활용 가능해요."
        assert "cache_hit" not in result.events
