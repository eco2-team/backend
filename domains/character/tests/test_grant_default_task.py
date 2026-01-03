"""Grant Default Character Task Tests."""

from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest


class TestGrantDefaultCharacterTask:
    """grant_default_character_task 테스트."""

    @pytest.fixture(autouse=True)
    def setup_celery_eager(self):
        """Celery eager mode 설정 (동기 실행)."""
        from domains.character.celery_app import celery_app

        celery_app.conf.task_always_eager = True
        celery_app.conf.task_eager_propagates = True
        yield
        celery_app.conf.task_always_eager = False

    @pytest.fixture
    def mock_default_character(self):
        """기본 캐릭터 mock."""
        return {
            "id": uuid4(),
            "code": "char-eco",
            "name": "이코",
            "type": "기본",
            "dialog": "안녕! 나는 이코야!",
        }

    def test_grant_default_character_success(self, mock_default_character):
        """기본 캐릭터 지급 성공."""
        from domains.character.tasks.grant_default import grant_default_character_task

        user_id = str(uuid4())

        with (
            patch(
                "domains.character.tasks.grant_default._get_default_character",
                return_value=mock_default_character,
            ),
            patch(
                "domains.character.tasks.grant_default._save_to_users_db",
                return_value={"inserted": True, "skipped": False},
            ) as mock_save,
        ):
            result = grant_default_character_task(user_id)

            assert result["success"] is True
            assert result["inserted"] is True
            mock_save.assert_called_once()

    def test_grant_default_character_already_exists(self, mock_default_character):
        """이미 캐릭터가 있는 경우 (ON CONFLICT DO NOTHING)."""
        from domains.character.tasks.grant_default import grant_default_character_task

        user_id = str(uuid4())

        with (
            patch(
                "domains.character.tasks.grant_default._get_default_character",
                return_value=mock_default_character,
            ),
            patch(
                "domains.character.tasks.grant_default._save_to_users_db",
                return_value={"inserted": False, "skipped": True},
            ),
        ):
            result = grant_default_character_task(user_id)

            assert result["success"] is True
            assert result["skipped"] is True

    def test_grant_default_character_not_found(self):
        """기본 캐릭터가 없는 경우."""
        from domains.character.tasks.grant_default import grant_default_character_task

        user_id = str(uuid4())

        with patch(
            "domains.character.tasks.grant_default._get_default_character",
            return_value=None,
        ):
            result = grant_default_character_task(user_id)

            assert result["success"] is False
            assert result["error"] == "default_character_not_found"


class TestGetCharactersQueryWithDefaultPublisher:
    """GetCharactersQuery 기본 캐릭터 발행 테스트."""

    @pytest.mark.asyncio
    async def test_publishes_event_when_empty_list(self):
        """빈 목록일 때 이벤트 발행."""
        from unittest.mock import AsyncMock

        from apps.users.application.character.queries import GetCharactersQuery
        from apps.users.setup.config import Settings

        # Mock gateway (빈 리스트 반환)
        mock_gateway = MagicMock()
        mock_gateway.list_by_user_id = AsyncMock(return_value=[])

        # Mock publisher
        mock_publisher = MagicMock()

        # Mock settings
        mock_settings = Settings(
            default_character_id="00000000-0000-0000-0000-000000000001",
            default_character_code="char-eco",
            default_character_name="이코",
            default_character_type="기본",
            default_character_dialog="안녕! 나는 이코야!",
        )

        query = GetCharactersQuery(
            character_gateway=mock_gateway,
            default_publisher=mock_publisher,
            settings=mock_settings,
        )

        user_id = uuid4()
        result = await query.execute(user_id)

        # 이벤트 발행 확인
        mock_publisher.publish.assert_called_once_with(user_id)

        # 기본 캐릭터 반환 확인
        assert len(result) == 1
        assert result[0].character_name == "이코"

    @pytest.mark.asyncio
    async def test_no_event_when_has_characters(self):
        """캐릭터가 있으면 이벤트 발행 안 함."""
        from datetime import datetime, timezone
        from unittest.mock import AsyncMock

        from apps.users.application.character.queries import GetCharactersQuery
        from apps.users.domain.entities.user_character import (
            CharacterStatus,
            UserCharacter,
        )

        # Mock gateway (캐릭터 있음)
        mock_char = UserCharacter(
            id=uuid4(),
            user_id=uuid4(),
            character_id=uuid4(),
            character_code="char-eco",
            character_name="이코",
            character_type="기본",
            character_dialog="안녕!",
            source="default-onboard",
            status=CharacterStatus.OWNED,
            acquired_at=datetime.now(timezone.utc),
        )
        mock_gateway = MagicMock()
        mock_gateway.list_by_user_id = AsyncMock(return_value=[mock_char])

        # Mock publisher
        mock_publisher = MagicMock()

        query = GetCharactersQuery(
            character_gateway=mock_gateway,
            default_publisher=mock_publisher,
        )

        user_id = uuid4()
        result = await query.execute(user_id)

        # 이벤트 발행 안 됨
        mock_publisher.publish.assert_not_called()

        # 기존 캐릭터 반환
        assert len(result) == 1
