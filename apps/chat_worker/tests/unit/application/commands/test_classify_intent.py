"""ClassifyIntentCommand Unit Tests."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from chat_worker.application.commands.classify_intent_command import (
    ClassifyIntentCommand,
    ClassifyIntentInput,
    ClassifyIntentOutput,
)
from chat_worker.application.services.intent_classifier_service import (
    IntentClassificationSchema,
)


class TestClassifyIntentInput:
    """ClassifyIntentInput DTO 테스트."""

    def test_create_with_required_fields(self) -> None:
        """필수 필드로 생성."""
        input_dto = ClassifyIntentInput(
            job_id="job-123",
            message="플라스틱 어떻게 버려?",
        )

        assert input_dto.job_id == "job-123"
        assert input_dto.message == "플라스틱 어떻게 버려?"
        assert input_dto.conversation_history is None
        assert input_dto.previous_intents is None

    def test_create_with_all_fields(self) -> None:
        """모든 필드로 생성."""
        input_dto = ClassifyIntentInput(
            job_id="job-123",
            message="캐릭터도 알려줘",
            conversation_history=[{"role": "user", "content": "안녕"}],
            previous_intents=["waste"],
        )

        assert input_dto.conversation_history is not None
        assert input_dto.previous_intents == ["waste"]


class TestClassifyIntentOutput:
    """ClassifyIntentOutput DTO 테스트."""

    def test_create_with_required_fields(self) -> None:
        """필수 필드로 생성."""
        output = ClassifyIntentOutput(
            intent="waste",
            confidence=0.9,
            is_complex=False,
        )

        assert output.intent == "waste"
        assert output.confidence == 0.9
        assert output.is_complex is False
        assert output.has_multi_intent is False
        assert output.additional_intents == []
        assert output.decomposed_queries == []
        assert output.events == []

    def test_create_multi_intent(self) -> None:
        """Multi-Intent 출력."""
        output = ClassifyIntentOutput(
            intent="waste",
            confidence=0.85,
            is_complex=True,
            has_multi_intent=True,
            additional_intents=["character", "location"],
            decomposed_queries=[
                "플라스틱 버리는 법",
                "캐릭터 뭐야?",
                "근처 재활용센터",
            ],
            events=["multi_intent_detected"],
        )

        assert output.has_multi_intent is True
        assert len(output.additional_intents) == 2
        assert len(output.decomposed_queries) == 3


class TestClassifyIntentCommand:
    """ClassifyIntentCommand 테스트."""

    @pytest.fixture
    def mock_llm(self) -> AsyncMock:
        """LLM 클라이언트 Mock."""
        llm = AsyncMock()
        llm.generate_structured = AsyncMock(
            return_value=IntentClassificationSchema(
                intent="waste",
                confidence=0.9,
                reasoning="분리배출 방법 문의",
            )
        )
        return llm

    @pytest.fixture
    def mock_prompt_loader(self) -> MagicMock:
        """프롬프트 로더 Mock."""
        loader = MagicMock()
        loader.load = MagicMock(return_value="prompt_template")
        return loader

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
        mock_prompt_loader: MagicMock,
        mock_cache: AsyncMock,
    ) -> ClassifyIntentCommand:
        """Command 인스턴스."""
        return ClassifyIntentCommand(
            llm=mock_llm,
            prompt_loader=mock_prompt_loader,
            cache=mock_cache,
            enable_multi_intent=False,  # 단순 테스트
        )

    @pytest.mark.anyio
    async def test_execute_simple_intent(
        self,
        command: ClassifyIntentCommand,
        mock_llm: AsyncMock,
    ) -> None:
        """단순 의도 분류."""
        mock_llm.generate_structured = AsyncMock(
            return_value=IntentClassificationSchema(
                intent="waste",
                confidence=0.9,
                reasoning="분리배출 방법 문의",
            )
        )

        input_dto = ClassifyIntentInput(
            job_id="job-123",
            message="플라스틱 어떻게 버려?",
        )

        result = await command.execute(input_dto)

        assert result.intent == "waste"
        assert result.confidence > 0
        assert "llm_structured_called" in result.events

    @pytest.mark.anyio
    async def test_execute_cache_hit(
        self,
        command: ClassifyIntentCommand,
        mock_cache: AsyncMock,
        mock_llm: AsyncMock,
    ) -> None:
        """캐시 히트 시 LLM 호출 안함."""
        mock_cache.get = AsyncMock(
            return_value={
                "intent": "character",
                "confidence": 0.95,
                "is_complex": False,
            }
        )

        input_dto = ClassifyIntentInput(
            job_id="job-123",
            message="캐릭터 뭐야?",
        )

        result = await command.execute(input_dto)

        assert result.intent == "character"
        assert result.confidence == 0.95
        assert "cache_hit" in result.events
        mock_llm.generate_structured.assert_not_called()

    @pytest.mark.anyio
    async def test_execute_llm_error_fallback(
        self,
        command: ClassifyIntentCommand,
        mock_llm: AsyncMock,
    ) -> None:
        """LLM 에러 시 general fallback."""
        mock_llm.generate_structured = AsyncMock(side_effect=Exception("LLM Error"))

        input_dto = ClassifyIntentInput(
            job_id="job-123",
            message="테스트 메시지",
        )

        result = await command.execute(input_dto)

        assert result.intent == "general"
        assert result.confidence == 0.0
        assert "llm_error" in result.events

    @pytest.mark.anyio
    async def test_execute_cache_error_continues(
        self,
        command: ClassifyIntentCommand,
        mock_cache: AsyncMock,
        mock_llm: AsyncMock,
    ) -> None:
        """캐시 에러 시에도 계속 진행."""
        mock_cache.get = AsyncMock(side_effect=Exception("Redis Error"))
        mock_llm.generate_structured = AsyncMock(
            return_value=IntentClassificationSchema(
                intent="location",
                confidence=0.88,
                reasoning="재활용센터 위치 검색",
            )
        )

        input_dto = ClassifyIntentInput(
            job_id="job-123",
            message="근처 재활용센터",
        )

        result = await command.execute(input_dto)

        assert result.intent == "location"
        assert "cache_error" in result.events
        mock_llm.generate_structured.assert_called_once()

    @pytest.mark.anyio
    async def test_execute_with_previous_intents(
        self,
        mock_llm: AsyncMock,
        mock_prompt_loader: MagicMock,
    ) -> None:
        """이전 의도 기반 분류 (Chain-of-Intent)."""
        mock_llm.generate_structured = AsyncMock(
            return_value=IntentClassificationSchema(
                intent="character",
                confidence=0.85,
                reasoning="캐릭터 정보 요청",
            )
        )

        command = ClassifyIntentCommand(
            llm=mock_llm,
            prompt_loader=mock_prompt_loader,
            cache=None,
            enable_multi_intent=False,
        )

        input_dto = ClassifyIntentInput(
            job_id="job-123",
            message="그 캐릭터 알려줘",
            previous_intents=["waste"],
        )

        result = await command.execute(input_dto)

        assert result.intent == "character"
        # Chain-of-Intent 시 캐시 사용 안함
        assert "cache_hit" not in result.events

    @pytest.mark.anyio
    async def test_execute_saves_to_cache(
        self,
        command: ClassifyIntentCommand,
        mock_cache: AsyncMock,
        mock_llm: AsyncMock,
    ) -> None:
        """분류 결과 캐시에 저장."""
        mock_llm.generate_structured = AsyncMock(
            return_value=IntentClassificationSchema(
                intent="bulk_waste",
                confidence=0.92,
                reasoning="대형폐기물 처리 문의",
            )
        )

        input_dto = ClassifyIntentInput(
            job_id="job-123",
            message="소파 버리는 법",
        )

        result = await command.execute(input_dto)

        assert result.intent == "bulk_waste"
        mock_cache.set.assert_called_once()
        assert "cache_saved" in result.events


class TestClassifyIntentCommandMultiIntent:
    """Multi-Intent 처리 테스트."""

    @pytest.fixture
    def mock_llm(self) -> AsyncMock:
        """LLM 클라이언트 Mock."""
        llm = AsyncMock()
        return llm

    @pytest.fixture
    def mock_prompt_loader(self) -> MagicMock:
        """프롬프트 로더 Mock."""
        loader = MagicMock()
        loader.load = MagicMock(return_value="prompt_template")
        return loader

    @pytest.fixture
    def command_multi(
        self,
        mock_llm: AsyncMock,
        mock_prompt_loader: MagicMock,
    ) -> ClassifyIntentCommand:
        """Multi-Intent 활성화된 Command."""
        return ClassifyIntentCommand(
            llm=mock_llm,
            prompt_loader=mock_prompt_loader,
            cache=None,
            enable_multi_intent=True,
        )

    @pytest.mark.anyio
    async def test_single_intent_shortcut(
        self,
        command_multi: ClassifyIntentCommand,
        mock_llm: AsyncMock,
    ) -> None:
        """단순 메시지는 Multi-Intent 우회."""
        mock_llm.generate_structured = AsyncMock(
            return_value=IntentClassificationSchema(
                intent="waste",
                confidence=0.85,
                reasoning="폐기물 관련 질문",
            )
        )

        input_dto = ClassifyIntentInput(
            job_id="job-123",
            message="플라스틱",  # 짧은 메시지
        )

        result = await command_multi.execute(input_dto)

        # Multi-Intent 감지 없이 바로 분류
        assert result.intent == "waste"
        assert "multi_intent_candidate" not in result.events
