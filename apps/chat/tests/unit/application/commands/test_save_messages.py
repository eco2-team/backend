"""SaveMessagesCommand Unit Tests."""

from datetime import datetime
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from chat.application.chat.commands.save_messages import (
    MessageSaveInput,
    SaveMessagesCommand,
    SaveMessagesResult,
)


class TestMessageSaveInput:
    """MessageSaveInput DTO 테스트."""

    def test_input_required_fields(self) -> None:
        """필수 필드로 생성."""
        now = datetime.now()
        input_dto = MessageSaveInput(
            conversation_id=str(uuid4()),
            user_id=str(uuid4()),
            user_message="Hello",
            user_message_created_at=now,
            assistant_message="Hi there!",
            assistant_message_created_at=now,
        )

        assert input_dto.user_message == "Hello"
        assert input_dto.assistant_message == "Hi there!"
        assert input_dto.intent is None
        assert input_dto.metadata is None

    def test_input_with_all_fields(self) -> None:
        """모든 필드로 생성."""
        now = datetime.now()
        metadata = {"citations": ["source1"]}

        input_dto = MessageSaveInput(
            conversation_id=str(uuid4()),
            user_id=str(uuid4()),
            user_message="What is this?",
            user_message_created_at=now,
            assistant_message="This is...",
            assistant_message_created_at=now,
            intent="waste_classification",
            metadata=metadata,
        )

        assert input_dto.intent == "waste_classification"
        assert input_dto.metadata == metadata


class TestSaveMessagesResult:
    """SaveMessagesResult DTO 테스트."""

    def test_success_result(self) -> None:
        """성공 결과."""
        result = SaveMessagesResult(
            saved_count=10,
            updated_conversations=5,
            is_success=True,
        )

        assert result.saved_count == 10
        assert result.updated_conversations == 5
        assert result.is_success is True
        assert result.error is None

    def test_failure_result(self) -> None:
        """실패 결과."""
        result = SaveMessagesResult(
            saved_count=0,
            updated_conversations=0,
            is_success=False,
            error="Database connection failed",
        )

        assert result.is_success is False
        assert result.error == "Database connection failed"


class TestSaveMessagesCommand:
    """SaveMessagesCommand 유스케이스 테스트."""

    @pytest.fixture
    def mock_repository(self) -> AsyncMock:
        """ChatRepository Mock."""
        repo = AsyncMock()
        repo.bulk_create_messages = AsyncMock(return_value=10)
        repo.update_conversation_metadata = AsyncMock(return_value=True)
        return repo

    @pytest.fixture
    def command(self, mock_repository: AsyncMock) -> SaveMessagesCommand:
        """Command 인스턴스."""
        return SaveMessagesCommand(repository=mock_repository)

    def _create_input(
        self,
        conversation_id: str | None = None,
        user_message: str = "User message",
        assistant_message: str = "Assistant message",
    ) -> MessageSaveInput:
        """테스트용 MessageSaveInput 생성."""
        now = datetime.now()
        return MessageSaveInput(
            conversation_id=conversation_id or str(uuid4()),
            user_id=str(uuid4()),
            user_message=user_message,
            user_message_created_at=now,
            assistant_message=assistant_message,
            assistant_message_created_at=now,
        )

    @pytest.mark.asyncio
    async def test_execute_empty_events(
        self,
        command: SaveMessagesCommand,
        mock_repository: AsyncMock,
    ) -> None:
        """빈 이벤트 목록 처리."""
        result = await command.execute([])

        assert result.saved_count == 0
        assert result.updated_conversations == 0
        assert result.is_success is True
        mock_repository.bulk_create_messages.assert_not_called()

    @pytest.mark.asyncio
    async def test_execute_single_event(
        self,
        command: SaveMessagesCommand,
        mock_repository: AsyncMock,
    ) -> None:
        """단일 이벤트 처리."""
        mock_repository.bulk_create_messages = AsyncMock(return_value=2)

        events = [self._create_input()]
        result = await command.execute(events)

        assert result.is_success is True
        assert result.saved_count == 2  # user + assistant
        mock_repository.bulk_create_messages.assert_called_once()

    @pytest.mark.asyncio
    async def test_execute_multiple_events(
        self,
        command: SaveMessagesCommand,
        mock_repository: AsyncMock,
    ) -> None:
        """여러 이벤트 처리."""
        mock_repository.bulk_create_messages = AsyncMock(return_value=6)

        events = [
            self._create_input(),
            self._create_input(),
            self._create_input(),
        ]
        result = await command.execute(events)

        assert result.is_success is True
        assert result.saved_count == 6

    @pytest.mark.asyncio
    async def test_execute_updates_conversation_metadata(
        self,
        command: SaveMessagesCommand,
        mock_repository: AsyncMock,
    ) -> None:
        """Conversation 메타데이터 업데이트."""
        mock_repository.bulk_create_messages = AsyncMock(return_value=2)

        events = [self._create_input()]
        result = await command.execute(events)

        assert result.updated_conversations == 1
        mock_repository.update_conversation_metadata.assert_called_once()

    @pytest.mark.asyncio
    async def test_execute_multiple_events_same_conversation(
        self,
        command: SaveMessagesCommand,
        mock_repository: AsyncMock,
    ) -> None:
        """같은 Conversation의 여러 이벤트."""
        mock_repository.bulk_create_messages = AsyncMock(return_value=4)

        conv_id = str(uuid4())
        events = [
            self._create_input(conversation_id=conv_id),
            self._create_input(conversation_id=conv_id),
        ]
        result = await command.execute(events)

        assert result.is_success is True
        # 같은 conversation이므로 update는 1번만
        assert result.updated_conversations == 1

    @pytest.mark.asyncio
    async def test_execute_multiple_conversations(
        self,
        command: SaveMessagesCommand,
        mock_repository: AsyncMock,
    ) -> None:
        """다른 Conversation의 이벤트들."""
        mock_repository.bulk_create_messages = AsyncMock(return_value=6)

        events = [
            self._create_input(conversation_id=str(uuid4())),
            self._create_input(conversation_id=str(uuid4())),
            self._create_input(conversation_id=str(uuid4())),
        ]
        result = await command.execute(events)

        assert result.is_success is True
        assert result.updated_conversations == 3

    @pytest.mark.asyncio
    async def test_execute_bulk_create_failure(
        self,
        mock_repository: AsyncMock,
    ) -> None:
        """bulk_create 실패 시 에러 반환."""
        mock_repository.bulk_create_messages = AsyncMock(side_effect=Exception("Database error"))
        command = SaveMessagesCommand(repository=mock_repository)

        events = [self._create_input()]
        result = await command.execute(events)

        assert result.is_success is False
        assert result.saved_count == 0
        assert "Database error" in result.error

    @pytest.mark.asyncio
    async def test_execute_metadata_update_partial_failure(
        self,
        command: SaveMessagesCommand,
        mock_repository: AsyncMock,
    ) -> None:
        """메타데이터 업데이트 일부 실패."""
        mock_repository.bulk_create_messages = AsyncMock(return_value=4)
        # 첫 번째 성공, 두 번째 실패
        mock_repository.update_conversation_metadata = AsyncMock(
            side_effect=[True, Exception("Update failed")]
        )

        events = [
            self._create_input(conversation_id=str(uuid4())),
            self._create_input(conversation_id=str(uuid4())),
        ]
        result = await command.execute(events)

        # 메타데이터 실패해도 전체는 성공
        assert result.is_success is True
        assert result.saved_count == 4
        assert result.updated_conversations == 1  # 1개만 성공

    @pytest.mark.asyncio
    async def test_execute_creates_message_pairs(
        self,
        command: SaveMessagesCommand,
        mock_repository: AsyncMock,
    ) -> None:
        """user + assistant 메시지 쌍 생성."""
        captured_messages = []

        async def capture_messages(messages):
            captured_messages.extend(messages)
            return len(messages)

        mock_repository.bulk_create_messages = capture_messages

        events = [self._create_input()]
        await command.execute(events)

        assert len(captured_messages) == 2
        roles = [m.role for m in captured_messages]
        assert "user" in roles
        assert "assistant" in roles

    @pytest.mark.asyncio
    async def test_execute_with_intent_and_metadata(
        self,
        command: SaveMessagesCommand,
        mock_repository: AsyncMock,
    ) -> None:
        """intent와 metadata가 assistant 메시지에 포함."""
        captured_messages = []

        async def capture_messages(messages):
            captured_messages.extend(messages)
            return len(messages)

        mock_repository.bulk_create_messages = capture_messages

        now = datetime.now()
        event = MessageSaveInput(
            conversation_id=str(uuid4()),
            user_id=str(uuid4()),
            user_message="Question",
            user_message_created_at=now,
            assistant_message="Answer",
            assistant_message_created_at=now,
            intent="waste_classification",
            metadata={"key": "value"},
        )

        await command.execute([event])

        assistant_msg = next(m for m in captured_messages if m.role == "assistant")
        assert assistant_msg.intent == "waste_classification"
        assert assistant_msg.metadata == {"key": "value"}
