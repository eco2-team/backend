import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

SERVICE_ROOT = Path(__file__).resolve().parents[1]
if str(SERVICE_ROOT) not in sys.path:
    sys.path.append(str(SERVICE_ROOT))

from app.database.models.user_character import UserCharacter  # noqa: E402
from app.repositories.user_character import UserCharacterRepository  # noqa: E402


class DummySession:
    def __init__(self):
        self.add = MagicMock()
        self.flush = AsyncMock()


def test_create_user_character_unlocks_existing():
    session = DummySession()
    user_id = uuid4()
    repo = UserCharacterRepository(session=session, current_user=SimpleNamespace(user_id=user_id))

    existing = UserCharacter(
        user_id=user_id,
        character_id=uuid4(),
        is_locked=True,
        classification_count=5,
        affection_score=2,
    )
    repo.get_user_character = AsyncMock(return_value=existing)

    result = asyncio.run(
        repo.create_user_character(character_id=existing.character_id, is_locked=False)
    )

    assert result is existing
    assert result.is_locked is False
    assert result.affection_score == 3
    session.add.assert_not_called()
    session.flush.assert_not_awaited()


def test_create_user_character_creates_new_instance():
    session = DummySession()
    user_id = uuid4()
    repo = UserCharacterRepository(session=session, current_user=SimpleNamespace(user_id=user_id))
    repo.get_user_character = AsyncMock(return_value=None)

    character_id = uuid4()
    result = asyncio.run(repo.create_user_character(character_id=character_id, is_locked=False))

    assert result.user_id == user_id
    assert result.character_id == character_id
    assert result.is_locked is False
    assert result.affection_score == 1
    assert result.classification_count == 1
    session.add.assert_called_once_with(result)
    session.flush.assert_awaited_once()
