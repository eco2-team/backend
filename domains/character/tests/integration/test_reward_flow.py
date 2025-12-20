"""Integration tests for reward evaluation flow.

실제 PostgreSQL을 사용하여 전체 리워드 지급 플로우를 테스트합니다.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from domains.character.schemas.reward import (
    CharacterRewardRequest,
    CharacterRewardSource,
    ClassificationSummary,
)


@pytest.mark.asyncio
class TestRewardEvaluationFlow:
    """리워드 평가 전체 플로우 통합 테스트."""

    async def test_grant_new_character(self, character_service, seed_characters):
        """새 캐릭터 지급 플로우."""
        user_id = uuid4()

        payload = CharacterRewardRequest(
            source=CharacterRewardSource.SCAN,
            user_id=user_id,
            task_id="test-task-001",
            classification=ClassificationSummary(
                major_category="재활용폐기물",
                middle_category="플라스틱",
                minor_category="페트병",
            ),
            disposal_rules_present=True,
            insufficiencies_present=False,
        )

        # gRPC 동기화는 mock (외부 서비스)
        with patch.object(character_service, "_sync_to_my_domain", new_callable=AsyncMock):
            response = await character_service.evaluate_reward(payload)

        assert response.received is True
        assert response.already_owned is False
        assert response.name == "플라봇"
        assert response.match_reason == "플라스틱>페트병"

    async def test_already_owned_character(self, character_service, seed_characters, db_session):
        """이미 소유한 캐릭터 재지급 시도."""
        user_id = uuid4()
        plastic_char = next(c for c in seed_characters if c.name == "플라봇")

        # 먼저 소유권 생성
        from domains.character.models.character import CharacterOwnership, CharacterOwnershipStatus

        ownership = CharacterOwnership(
            user_id=user_id,
            character_id=plastic_char.id,
            source="test",
            status=CharacterOwnershipStatus.OWNED,
        )
        db_session.add(ownership)
        await db_session.commit()

        payload = CharacterRewardRequest(
            source=CharacterRewardSource.SCAN,
            user_id=user_id,
            task_id="test-task-002",
            classification=ClassificationSummary(
                major_category="재활용폐기물",
                middle_category="플라스틱",
            ),
            disposal_rules_present=True,
            insufficiencies_present=False,
        )

        response = await character_service.evaluate_reward(payload)

        assert response.received is False
        assert response.already_owned is True
        assert response.name == "플라봇"

    async def test_skip_non_recyclable(self, character_service, seed_characters):
        """재활용폐기물이 아닌 경우 skip."""
        user_id = uuid4()

        payload = CharacterRewardRequest(
            source=CharacterRewardSource.SCAN,
            user_id=user_id,
            task_id="test-task-003",
            classification=ClassificationSummary(
                major_category="일반폐기물",
                middle_category="음식물",
            ),
            disposal_rules_present=True,
            insufficiencies_present=False,
        )

        response = await character_service.evaluate_reward(payload)

        assert response.received is False
        assert response.already_owned is False
        assert response.name is None

    async def test_no_match_character(self, character_service, seed_characters):
        """매칭되는 캐릭터가 없는 경우."""
        user_id = uuid4()

        payload = CharacterRewardRequest(
            source=CharacterRewardSource.SCAN,
            user_id=user_id,
            task_id="test-task-004",
            classification=ClassificationSummary(
                major_category="재활용폐기물",
                middle_category="종이",  # 종이 캐릭터 없음
            ),
            disposal_rules_present=True,
            insufficiencies_present=False,
        )

        response = await character_service.evaluate_reward(payload)

        assert response.received is False
        assert response.name is None


@pytest.mark.asyncio
class TestCatalogFlow:
    """카탈로그 조회 통합 테스트."""

    async def test_catalog_returns_all_characters(self, character_service, seed_characters):
        """모든 캐릭터 조회."""
        # 캐시 비활성화 상태에서 테스트
        with patch("domains.character.services.character.get_cached", return_value=None):
            with patch("domains.character.services.character.set_cached", return_value=True):
                catalog = await character_service.catalog()

        assert len(catalog) == 3
        names = {c.name for c in catalog}
        assert names == {"이코", "플라봇", "유리봇"}

    async def test_catalog_with_cache(self, character_service, seed_characters):
        """캐시된 카탈로그 조회."""
        cached_data = [{"name": "캐시캐릭터", "type": "테스트", "dialog": "캐시!", "match": None}]

        with patch("domains.character.services.character.get_cached", return_value=cached_data):
            catalog = await character_service.catalog()

        # 캐시 데이터 반환
        assert len(catalog) == 1
        assert catalog[0].name == "캐시캐릭터"


@pytest.mark.asyncio
class TestOwnershipPersistence:
    """소유권 영속성 테스트."""

    async def test_ownership_persisted_after_grant(
        self, character_service, seed_characters, db_session
    ):
        """캐릭터 지급 후 소유권이 DB에 저장되는지 확인."""
        user_id = uuid4()
        glass_char = next(c for c in seed_characters if c.name == "유리봇")

        payload = CharacterRewardRequest(
            source=CharacterRewardSource.SCAN,
            user_id=user_id,
            task_id="test-task-005",
            classification=ClassificationSummary(
                major_category="재활용폐기물",
                middle_category="유리",
            ),
            disposal_rules_present=True,
            insufficiencies_present=False,
        )

        with patch.object(character_service, "_sync_to_my_domain", new_callable=AsyncMock):
            response = await character_service.evaluate_reward(payload)

        assert response.received is True

        # DB에서 소유권 확인
        ownership = await character_service.ownership_repo.get_by_user_and_character(
            user_id=user_id, character_id=glass_char.id
        )

        assert ownership is not None
        assert ownership.source == "scan-reward"  # Strategy에서 제공된 source
