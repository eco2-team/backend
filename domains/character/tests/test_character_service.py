"""Tests for CharacterService business logic.

These tests mock the database layer to test service logic in isolation.

Note:
    _build_match_reason, _resolve_match_label 테스트는
    test_evaluators.py의 ScanRewardEvaluator 테스트로 이동됨.
"""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

# 상수 직접 정의 (테스트 독립성)
DEFAULT_CHARACTER_NAME = "이코"
RECYCLABLE_WASTE_CATEGORY = "재활용폐기물"
REWARD_SOURCE_SCAN = "scan-reward"


# Mock database session module before importing CharacterService
@pytest.fixture(autouse=True)
def mock_db_session():
    """Mock database session for all tests."""
    with patch("domains.character.services.character.get_db_session"):
        yield


class TestCatalog:
    """Tests for catalog method."""

    @pytest.fixture
    def mock_session(self):
        return AsyncMock()

    @pytest.fixture
    def service(self, mock_session):
        from domains.character.services.character import CharacterService

        service = CharacterService.__new__(CharacterService)
        service.session = mock_session
        service.character_repo = MagicMock()
        service.ownership_repo = MagicMock()
        return service

    @pytest.mark.asyncio
    async def test_catalog_returns_profiles(self, service):
        """캐릭터 목록이 있을 때 프로필 리스트 반환."""
        mock_character = MagicMock()
        mock_character.name = "이코"
        mock_character.type_label = "기본"
        mock_character.dialog = "안녕!"
        mock_character.description = None
        mock_character.match_label = "플라스틱"

        service.character_repo.list_all = AsyncMock(return_value=[mock_character])

        result = await service.catalog()

        assert len(result) == 1
        assert result[0].name == "이코"
        assert result[0].type == "기본"
        assert result[0].dialog == "안녕!"

    @pytest.mark.asyncio
    async def test_catalog_empty_raises_error(self, service):
        """캐릭터가 없을 때 CatalogEmptyError 발생."""
        from domains.character.exceptions import CatalogEmptyError

        service.character_repo.list_all = AsyncMock(return_value=[])

        with pytest.raises(CatalogEmptyError):
            await service.catalog()


class TestGetDefaultCharacter:
    """Tests for get_default_character method."""

    @pytest.fixture
    def mock_session(self):
        return AsyncMock()

    @pytest.fixture
    def service(self, mock_session):
        from domains.character.services.character import CharacterService

        service = CharacterService.__new__(CharacterService)
        service.session = mock_session
        service.character_repo = MagicMock()
        service.ownership_repo = MagicMock()
        return service

    @pytest.mark.asyncio
    async def test_returns_default_character(self, service):
        """기본 캐릭터 반환."""
        mock_character = MagicMock()
        mock_character.name = DEFAULT_CHARACTER_NAME

        service.character_repo.get_by_name = AsyncMock(return_value=mock_character)

        result = await service.get_default_character()

        assert result == mock_character
        service.character_repo.get_by_name.assert_called_once_with(DEFAULT_CHARACTER_NAME)


class TestMetrics:
    """Tests for metrics method."""

    @pytest.fixture
    def mock_session(self):
        return AsyncMock()

    @pytest.fixture
    def service(self, mock_session):
        from domains.character.services.character import CharacterService

        service = CharacterService.__new__(CharacterService)
        service.session = mock_session
        service.character_repo = MagicMock()
        service.ownership_repo = MagicMock()
        return service

    @pytest.mark.asyncio
    async def test_returns_catalog_size(self, service):
        """카탈로그 크기 반환."""
        mock_characters = [MagicMock(), MagicMock(), MagicMock()]
        service.character_repo.list_all = AsyncMock(return_value=mock_characters)

        result = await service.metrics()

        assert result == {"catalog_size": 3}

    @pytest.mark.asyncio
    async def test_returns_none_when_not_found(self, service):
        """기본 캐릭터가 없을 때 None 반환."""
        service.character_repo.get_by_name = AsyncMock(return_value=None)

        result = await service.get_default_character()

        assert result is None


class TestEvaluateReward:
    """Tests for evaluate_reward method."""

    @pytest.fixture
    def mock_session(self):
        return AsyncMock()

    @pytest.fixture
    def service(self, mock_session):
        from domains.character.services.character import CharacterService

        service = CharacterService.__new__(CharacterService)
        service.session = mock_session
        service.character_repo = MagicMock()
        service.ownership_repo = MagicMock()
        # 기본적으로 빈 캐릭터 목록 반환
        service.character_repo.list_all = AsyncMock(return_value=[])
        return service

    @pytest.mark.asyncio
    async def test_returns_no_match_when_no_evaluator(self, service):
        """등록된 evaluator가 없을 때 빈 응답 반환."""
        from domains.character.schemas.reward import (
            CharacterRewardRequest,
            CharacterRewardSource,
            ClassificationSummary,
        )

        payload = CharacterRewardRequest(
            source=CharacterRewardSource.SCAN,
            user_id=uuid4(),
            task_id="task-123",
            classification=ClassificationSummary(
                major_category=RECYCLABLE_WASTE_CATEGORY,
                middle_category="플라스틱",
            ),
            disposal_rules_present=True,
            insufficiencies_present=False,
        )

        with patch(
            "domains.character.services.character.get_evaluator",
            return_value=None,
        ):
            result = await service.evaluate_reward(payload)

        assert result.received is False
        assert result.already_owned is False
        assert result.name is None

    @pytest.mark.asyncio
    async def test_skips_when_not_recyclable(self, service):
        """재활용폐기물이 아닐 때 skip."""
        from domains.character.schemas.reward import (
            CharacterRewardRequest,
            CharacterRewardSource,
            ClassificationSummary,
        )

        payload = CharacterRewardRequest(
            source=CharacterRewardSource.SCAN,
            user_id=uuid4(),
            task_id="task-123",
            classification=ClassificationSummary(
                major_category="일반폐기물",
                middle_category="음식물",
            ),
            disposal_rules_present=True,
            insufficiencies_present=False,
        )

        result = await service.evaluate_reward(payload)

        assert result.received is False
        assert result.already_owned is False
        assert result.name is None

    @pytest.mark.asyncio
    async def test_skips_when_insufficiencies_present(self, service):
        """부족한 정보가 있을 때 skip."""
        from domains.character.schemas.reward import (
            CharacterRewardRequest,
            CharacterRewardSource,
            ClassificationSummary,
        )

        payload = CharacterRewardRequest(
            source=CharacterRewardSource.SCAN,
            user_id=uuid4(),
            task_id="task-123",
            classification=ClassificationSummary(
                major_category=RECYCLABLE_WASTE_CATEGORY,
                middle_category="플라스틱",
            ),
            disposal_rules_present=True,
            insufficiencies_present=True,
        )

        result = await service.evaluate_reward(payload)

        assert result.received is False

    @pytest.mark.asyncio
    async def test_skips_when_no_disposal_rules(self, service):
        """분리배출 규칙이 없을 때 skip."""
        from domains.character.schemas.reward import (
            CharacterRewardRequest,
            CharacterRewardSource,
            ClassificationSummary,
        )

        payload = CharacterRewardRequest(
            source=CharacterRewardSource.SCAN,
            user_id=uuid4(),
            task_id="task-123",
            classification=ClassificationSummary(
                major_category=RECYCLABLE_WASTE_CATEGORY,
                middle_category="플라스틱",
            ),
            disposal_rules_present=False,
            insufficiencies_present=False,
        )

        result = await service.evaluate_reward(payload)

        assert result.received is False

    @pytest.mark.asyncio
    async def test_no_match_when_no_characters(self, service):
        """매칭되는 캐릭터가 없을 때."""
        from domains.character.schemas.reward import (
            CharacterRewardRequest,
            CharacterRewardSource,
            ClassificationSummary,
        )

        payload = CharacterRewardRequest(
            source=CharacterRewardSource.SCAN,
            user_id=uuid4(),
            task_id="task-123",
            classification=ClassificationSummary(
                major_category=RECYCLABLE_WASTE_CATEGORY,
                middle_category="플라스틱",
            ),
            disposal_rules_present=True,
            insufficiencies_present=False,
        )

        # 빈 목록 반환 (매칭 없음)
        service.character_repo.list_all = AsyncMock(return_value=[])

        result = await service.evaluate_reward(payload)

        assert result.received is False
        assert result.name is None

    @pytest.mark.asyncio
    async def test_grants_reward_when_conditions_met(self, service):
        """조건 충족 시 리워드 지급."""
        from domains.character.schemas.reward import (
            CharacterRewardRequest,
            CharacterRewardSource,
            ClassificationSummary,
        )

        user_id = uuid4()
        mock_character = MagicMock()
        mock_character.id = uuid4()
        mock_character.name = "플라봇"
        mock_character.type_label = "플라스틱"
        mock_character.dialog = "플라스틱을 분리해줘서 고마워!"
        mock_character.description = None
        mock_character.match_label = "플라스틱"
        mock_character.code = "PLASTIC001"

        payload = CharacterRewardRequest(
            source=CharacterRewardSource.SCAN,
            user_id=user_id,
            task_id="task-123",
            classification=ClassificationSummary(
                major_category=RECYCLABLE_WASTE_CATEGORY,
                middle_category="플라스틱",
            ),
            disposal_rules_present=True,
            insufficiencies_present=False,
        )

        # list_all이 전체 캐릭터 반환, Evaluator가 필터링
        service.character_repo.list_all = AsyncMock(return_value=[mock_character])
        service.ownership_repo.get_by_user_and_character = AsyncMock(return_value=None)
        service._grant_and_sync = AsyncMock()

        result = await service.evaluate_reward(payload)

        assert result.received is True
        assert result.name == "플라봇"
        assert result.dialog == "플라스틱을 분리해줘서 고마워!"
        service._grant_and_sync.assert_called_once()

    @pytest.mark.asyncio
    async def test_already_owned_when_exists(self, service):
        """이미 소유한 캐릭터일 때."""
        from domains.character.schemas.reward import (
            CharacterRewardRequest,
            CharacterRewardSource,
            ClassificationSummary,
        )

        user_id = uuid4()
        mock_character = MagicMock()
        mock_character.id = uuid4()
        mock_character.name = "플라봇"
        mock_character.type_label = "플라스틱"
        mock_character.dialog = "플라스틱을 분리해줘서 고마워!"
        mock_character.description = None
        mock_character.match_label = "플라스틱"

        mock_ownership = MagicMock()

        payload = CharacterRewardRequest(
            source=CharacterRewardSource.SCAN,
            user_id=user_id,
            task_id="task-123",
            classification=ClassificationSummary(
                major_category=RECYCLABLE_WASTE_CATEGORY,
                middle_category="플라스틱",
            ),
            disposal_rules_present=True,
            insufficiencies_present=False,
        )

        # list_all이 전체 캐릭터 반환
        service.character_repo.list_all = AsyncMock(return_value=[mock_character])
        service.ownership_repo.get_by_user_and_character = AsyncMock(return_value=mock_ownership)

        result = await service.evaluate_reward(payload)

        assert result.received is False
        assert result.already_owned is True
        assert result.name == "플라봇"


class TestApplyRewardRaceCondition:
    """Tests for race condition handling in _apply_reward."""

    @pytest.fixture
    def mock_session(self):
        return AsyncMock()

    @pytest.fixture
    def service(self, mock_session):
        from domains.character.services.character import CharacterService

        service = CharacterService.__new__(CharacterService)
        service.session = mock_session
        service.character_repo = MagicMock()
        service.ownership_repo = MagicMock()
        service.character_repo.list_all = AsyncMock(return_value=[])
        return service

    @pytest.mark.asyncio
    async def test_integrity_error_returns_already_owned(self, service):
        """IntegrityError 발생 시 already_owned=True 반환."""
        from sqlalchemy.exc import IntegrityError

        user_id = uuid4()
        mock_character = MagicMock()
        mock_character.id = uuid4()
        mock_character.name = "플라봇"
        mock_character.type_label = "플라스틱"
        mock_character.dialog = "플라스틱!"
        mock_character.description = None
        mock_character.match_label = "플라스틱"

        service.ownership_repo.get_by_user_and_character = AsyncMock(return_value=None)
        service._grant_and_sync = AsyncMock(side_effect=IntegrityError("duplicate", {}, None))

        result = await service._apply_reward(user_id, [mock_character], source_label="scan-reward")

        profile, already_owned, failure = result
        assert profile.name == "플라봇"
        assert already_owned is True
        assert failure is None
        service.session.rollback.assert_called_once()


class TestCreateForTest:
    """Tests for create_for_test factory method."""

    @pytest.fixture
    def mock_session(self):
        return AsyncMock()

    def test_creates_service_with_default_repos(self, mock_session):
        """기본 repository로 서비스 생성."""
        from domains.character.services.character import CharacterService

        service = CharacterService.create_for_test(session=mock_session)

        assert service.session == mock_session
        assert service.character_repo is not None
        assert service.ownership_repo is not None

    def test_creates_service_with_custom_repos(self, mock_session):
        """커스텀 repository로 서비스 생성."""
        from domains.character.services.character import CharacterService

        mock_char_repo = MagicMock()
        mock_owner_repo = MagicMock()

        service = CharacterService.create_for_test(
            session=mock_session,
            character_repo=mock_char_repo,
            ownership_repo=mock_owner_repo,
        )

        assert service.character_repo == mock_char_repo
        assert service.ownership_repo == mock_owner_repo


class TestGrantAndSync:
    """Tests for _grant_and_sync method."""

    @pytest.fixture
    def mock_session(self):
        session = AsyncMock()
        session.commit = AsyncMock()
        return session

    @pytest.fixture
    def service(self, mock_session):
        from domains.character.services.character import CharacterService

        service = CharacterService.create_for_test(session=mock_session)
        service.ownership_repo = MagicMock()
        service.ownership_repo.insert_owned = AsyncMock()
        return service

    @pytest.mark.asyncio
    async def test_grant_and_sync_inserts_ownership(self, service, mock_session):
        """ownership 삽입 후 commit 호출."""
        user_id = uuid4()
        mock_character = MagicMock()
        mock_character.id = uuid4()
        mock_character.name = "테스트"
        mock_character.code = "TEST001"
        mock_character.type_label = "기본"
        mock_character.dialog = "안녕!"

        await service._grant_and_sync(
            user_id=user_id, character=mock_character, source="test-source"
        )

        # ownership 저장 및 commit
        service.ownership_repo.insert_owned.assert_called_once()
        mock_session.commit.assert_called_once()
