"""Chat Entity Unit Tests."""

from datetime import datetime, timedelta
from uuid import UUID, uuid4

import pytest

from chat.domain.entities.chat import Chat


class TestChatEntity:
    """Chat 엔티티 테스트."""

    def test_chat_creation_with_defaults(self) -> None:
        """기본값으로 Chat 생성."""
        user_id = uuid4()
        chat = Chat(user_id=user_id)

        assert chat.user_id == user_id
        assert isinstance(chat.id, UUID)
        assert chat.title is None
        assert chat.preview is None
        assert chat.message_count == 0
        assert chat.last_message_at is None
        assert chat.is_deleted is False
        assert isinstance(chat.created_at, datetime)
        assert isinstance(chat.updated_at, datetime)

    def test_chat_creation_with_all_fields(self) -> None:
        """모든 필드로 Chat 생성."""
        user_id = uuid4()
        chat_id = uuid4()
        now = datetime.now()

        chat = Chat(
            id=chat_id,
            user_id=user_id,
            title="Test Chat",
            preview="Hello world",
            message_count=5,
            last_message_at=now,
            is_deleted=False,
            created_at=now,
            updated_at=now,
        )

        assert chat.id == chat_id
        assert chat.user_id == user_id
        assert chat.title == "Test Chat"
        assert chat.preview == "Hello world"
        assert chat.message_count == 5
        assert chat.last_message_at == now

    def test_update_on_new_message_increments_count(self) -> None:
        """새 메시지로 카운트 증가."""
        chat = Chat(user_id=uuid4(), message_count=0)
        chat.update_on_new_message("Test message")

        assert chat.message_count == 1

    def test_update_on_new_message_multiple_times(self) -> None:
        """여러 메시지 추가 시 카운트 증가."""
        chat = Chat(user_id=uuid4(), message_count=0)

        chat.update_on_new_message("First")
        chat.update_on_new_message("Second")
        chat.update_on_new_message("Third")

        assert chat.message_count == 3

    def test_update_on_new_message_sets_preview(self) -> None:
        """새 메시지로 preview 설정."""
        chat = Chat(user_id=uuid4())
        chat.update_on_new_message("New preview text")

        assert chat.preview == "New preview text"

    def test_update_on_new_message_truncates_long_preview(self) -> None:
        """100자 초과 preview 잘림."""
        chat = Chat(user_id=uuid4())
        long_message = "A" * 150

        chat.update_on_new_message(long_message)

        assert len(chat.preview) == 100
        assert chat.preview == "A" * 100

    def test_update_on_new_message_keeps_short_preview(self) -> None:
        """100자 이하 preview 유지."""
        chat = Chat(user_id=uuid4())
        short_message = "A" * 50

        chat.update_on_new_message(short_message)

        assert len(chat.preview) == 50
        assert chat.preview == short_message

    def test_update_on_new_message_exactly_100_chars(self) -> None:
        """정확히 100자 preview."""
        chat = Chat(user_id=uuid4())
        exact_message = "A" * 100

        chat.update_on_new_message(exact_message)

        assert len(chat.preview) == 100

    def test_update_on_new_message_updates_timestamps(self) -> None:
        """새 메시지로 타임스탬프 업데이트."""
        old_time = datetime.now() - timedelta(hours=1)
        chat = Chat(
            user_id=uuid4(),
            last_message_at=old_time,
            updated_at=old_time,
        )

        chat.update_on_new_message("New message")

        assert chat.last_message_at > old_time
        assert chat.updated_at > old_time

    def test_soft_delete_sets_is_deleted(self) -> None:
        """soft_delete로 is_deleted 설정."""
        chat = Chat(user_id=uuid4(), is_deleted=False)

        chat.soft_delete()

        assert chat.is_deleted is True

    def test_soft_delete_updates_timestamp(self) -> None:
        """soft_delete로 updated_at 업데이트."""
        old_time = datetime.now() - timedelta(hours=1)
        chat = Chat(user_id=uuid4(), updated_at=old_time)

        chat.soft_delete()

        assert chat.updated_at > old_time

    def test_soft_delete_idempotent(self) -> None:
        """soft_delete 여러 번 호출 가능."""
        chat = Chat(user_id=uuid4())

        chat.soft_delete()
        first_updated_at = chat.updated_at

        chat.soft_delete()

        assert chat.is_deleted is True
        assert chat.updated_at >= first_updated_at

    def test_chat_with_empty_preview(self) -> None:
        """빈 preview로 업데이트."""
        chat = Chat(user_id=uuid4(), preview="Old preview")
        chat.update_on_new_message("")

        assert chat.preview == ""
