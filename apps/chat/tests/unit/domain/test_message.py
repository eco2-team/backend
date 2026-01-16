"""Message Entity Unit Tests."""

from datetime import datetime
from uuid import UUID, uuid4

import pytest

from chat.domain.entities.message import Message


class TestMessageEntity:
    """Message 엔티티 테스트."""

    def test_message_creation_user_role(self) -> None:
        """user 역할로 메시지 생성."""
        chat_id = uuid4()
        message = Message(
            chat_id=chat_id,
            role="user",
            content="Hello",
        )

        assert message.chat_id == chat_id
        assert message.role == "user"
        assert message.content == "Hello"
        assert isinstance(message.id, UUID)
        assert message.intent is None
        assert message.metadata is None
        assert message.job_id is None
        assert isinstance(message.created_at, datetime)

    def test_message_creation_assistant_role(self) -> None:
        """assistant 역할로 메시지 생성."""
        chat_id = uuid4()
        message = Message(
            chat_id=chat_id,
            role="assistant",
            content="Hello, I'm here to help.",
        )

        assert message.role == "assistant"
        assert message.content == "Hello, I'm here to help."

    def test_message_invalid_role_raises_error(self) -> None:
        """잘못된 역할은 ValueError 발생."""
        chat_id = uuid4()

        with pytest.raises(ValueError) as exc_info:
            Message(
                chat_id=chat_id,
                role="admin",
                content="Test",
            )

        assert "Invalid role: admin" in str(exc_info.value)
        assert "Must be 'user' or 'assistant'" in str(exc_info.value)

    def test_message_invalid_role_system(self) -> None:
        """system 역할도 ValueError 발생."""
        with pytest.raises(ValueError):
            Message(
                chat_id=uuid4(),
                role="system",
                content="Test",
            )

    def test_message_with_all_fields(self) -> None:
        """모든 필드로 메시지 생성."""
        chat_id = uuid4()
        message_id = uuid4()
        job_id = uuid4()
        now = datetime.now()
        metadata = {"citations": ["source1"], "confidence": 0.95}

        message = Message(
            id=message_id,
            chat_id=chat_id,
            role="assistant",
            content="Response content",
            intent="waste_classification",
            metadata=metadata,
            job_id=job_id,
            created_at=now,
        )

        assert message.id == message_id
        assert message.chat_id == chat_id
        assert message.intent == "waste_classification"
        assert message.metadata == metadata
        assert message.job_id == job_id
        assert message.created_at == now


class TestMessageFactoryMethods:
    """Message 팩토리 메서드 테스트."""

    def test_user_message_factory(self) -> None:
        """user_message 팩토리 메서드."""
        chat_id = uuid4()
        message = Message.user_message(
            chat_id=chat_id,
            content="User question",
        )

        assert message.chat_id == chat_id
        assert message.role == "user"
        assert message.content == "User question"
        assert message.job_id is None
        assert message.intent is None
        assert message.metadata is None

    def test_user_message_with_job_id(self) -> None:
        """job_id가 있는 user_message."""
        chat_id = uuid4()
        job_id = uuid4()
        message = Message.user_message(
            chat_id=chat_id,
            content="Question",
            job_id=job_id,
        )

        assert message.job_id == job_id

    def test_assistant_message_factory(self) -> None:
        """assistant_message 팩토리 메서드."""
        chat_id = uuid4()
        message = Message.assistant_message(
            chat_id=chat_id,
            content="AI response",
        )

        assert message.chat_id == chat_id
        assert message.role == "assistant"
        assert message.content == "AI response"
        assert message.intent is None
        assert message.metadata is None

    def test_assistant_message_with_intent(self) -> None:
        """intent가 있는 assistant_message."""
        chat_id = uuid4()
        message = Message.assistant_message(
            chat_id=chat_id,
            content="Response",
            intent="general",
        )

        assert message.intent == "general"

    def test_assistant_message_with_metadata(self) -> None:
        """metadata가 있는 assistant_message."""
        chat_id = uuid4()
        metadata = {
            "node_results": {"rag": {"status": "success"}},
            "citations": ["doc1", "doc2"],
        }
        message = Message.assistant_message(
            chat_id=chat_id,
            content="Response",
            metadata=metadata,
        )

        assert message.metadata == metadata
        assert message.metadata["citations"] == ["doc1", "doc2"]

    def test_assistant_message_with_all_options(self) -> None:
        """모든 옵션이 있는 assistant_message."""
        chat_id = uuid4()
        job_id = uuid4()
        metadata = {"key": "value"}

        message = Message.assistant_message(
            chat_id=chat_id,
            content="Full response",
            intent="waste_disposal",
            metadata=metadata,
            job_id=job_id,
        )

        assert message.role == "assistant"
        assert message.content == "Full response"
        assert message.intent == "waste_disposal"
        assert message.metadata == metadata
        assert message.job_id == job_id


class TestMessageEdgeCases:
    """Message 엣지 케이스 테스트."""

    def test_empty_content(self) -> None:
        """빈 content 허용."""
        message = Message(
            chat_id=uuid4(),
            role="user",
            content="",
        )

        assert message.content == ""

    def test_very_long_content(self) -> None:
        """매우 긴 content."""
        long_content = "A" * 10000
        message = Message(
            chat_id=uuid4(),
            role="assistant",
            content=long_content,
        )

        assert len(message.content) == 10000

    def test_unicode_content(self) -> None:
        """유니코드 content."""
        message = Message(
            chat_id=uuid4(),
            role="user",
            content="안녕하세요 🌍 こんにちは",
        )

        assert "안녕하세요" in message.content
        assert "🌍" in message.content

    def test_empty_metadata_dict(self) -> None:
        """빈 metadata dict."""
        message = Message(
            chat_id=uuid4(),
            role="assistant",
            content="Response",
            metadata={},
        )

        assert message.metadata == {}

    def test_nested_metadata(self) -> None:
        """중첩된 metadata."""
        metadata = {
            "level1": {
                "level2": {
                    "value": [1, 2, 3],
                },
            },
        }
        message = Message(
            chat_id=uuid4(),
            role="assistant",
            content="Response",
            metadata=metadata,
        )

        assert message.metadata["level1"]["level2"]["value"] == [1, 2, 3]
