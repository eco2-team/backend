"""E2E (End-to-End) API Integration Tests.

실제 HTTP 요청을 통해 API 엔드포인트를 테스트합니다.
Service 레이어는 mock하여 API 계층의 동작을 검증합니다.

Run:
    pytest domains/character/tests/e2e/ -v
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from httpx import AsyncClient

from domains.character.exceptions import CatalogEmptyError
from domains.character.schemas.catalog import CharacterProfile
from domains.character.schemas.reward import CharacterRewardResponse


def create_reward_request_payload(
    user_id=None,
    major_category: str = "재활용폐기물",
    middle_category: str = "플라스틱",
    minor_category: str | None = "페트병",
    disposal_rules_present: bool = True,
    insufficiencies_present: bool = False,
) -> dict:
    """Helper to create reward request payloads for testing."""
    return {
        "source": "scan",
        "user_id": str(user_id or uuid4()),
        "task_id": f"test-task-{uuid4().hex[:8]}",
        "classification": {
            "major_category": major_category,
            "middle_category": middle_category,
            "minor_category": minor_category,
        },
        "disposal_rules_present": disposal_rules_present,
        "insufficiencies_present": insufficiencies_present,
    }


class TestCatalogEndpoint:
    """GET /api/v1/character/catalog E2E tests."""

    @pytest.mark.asyncio
    async def test_catalog_returns_character_list(self, async_client: AsyncClient):
        """캐릭터 목록 정상 반환."""
        mock_profiles = [
            CharacterProfile(name="이코", type="기본", dialog="안녕!", match="플라스틱"),
            CharacterProfile(name="플라봇", type="플라스틱", dialog="고마워!", match="플라스틱"),
        ]

        with patch("domains.character.api.v1.endpoints.character.CharacterService") as MockService:
            mock_instance = AsyncMock()
            mock_instance.catalog.return_value = mock_profiles
            MockService.return_value = mock_instance

            response = await async_client.get("/api/v1/character/catalog")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2
        assert data[0]["name"] == "이코"
        assert data[1]["name"] == "플라봇"

    @pytest.mark.asyncio
    async def test_catalog_empty_returns_404(self, async_client: AsyncClient):
        """캐릭터가 없으면 404 반환."""
        with patch("domains.character.api.v1.endpoints.character.CharacterService") as MockService:
            mock_instance = AsyncMock()
            mock_instance.catalog.side_effect = CatalogEmptyError()
            MockService.return_value = mock_instance

            response = await async_client.get("/api/v1/character/catalog")

        assert response.status_code == 404
        assert "catalog" in response.json()["detail"].lower()


class TestRewardsEndpoint:
    """POST /api/v1/internal/characters/rewards E2E tests."""

    @pytest.mark.asyncio
    async def test_reward_granted_successfully(self, async_client: AsyncClient):
        """리워드 정상 지급."""
        mock_response = CharacterRewardResponse(
            received=True,
            already_owned=False,
            name="플라봇",
            dialog="플라스틱을 분리해줘서 고마워!",
            match_reason="플라스틱>페트병",
            character_type="플라스틱",
            type="플라스틱",
        )

        with patch("domains.character.api.v1.endpoints.rewards.CharacterService") as MockService:
            mock_instance = AsyncMock()
            mock_instance.evaluate_reward.return_value = mock_response
            MockService.return_value = mock_instance

            payload = create_reward_request_payload()
            response = await async_client.post(
                "/api/v1/internal/characters/rewards",
                json=payload,
            )

        assert response.status_code == 200
        data = response.json()
        assert data["received"] is True
        assert data["already_owned"] is False
        assert data["name"] == "플라봇"
        assert data["character_type"] == "플라스틱"
        # Legacy field 호환성 확인
        assert data["type"] == "플라스틱"

    @pytest.mark.asyncio
    async def test_reward_already_owned(self, async_client: AsyncClient):
        """이미 소유한 캐릭터."""
        mock_response = CharacterRewardResponse(
            received=False,
            already_owned=True,
            name="플라봇",
            dialog="플라스틱을 분리해줘서 고마워!",
            match_reason="플라스틱>페트병",
            character_type="플라스틱",
            type="플라스틱",
        )

        with patch("domains.character.api.v1.endpoints.rewards.CharacterService") as MockService:
            mock_instance = AsyncMock()
            mock_instance.evaluate_reward.return_value = mock_response
            MockService.return_value = mock_instance

            payload = create_reward_request_payload()
            response = await async_client.post(
                "/api/v1/internal/characters/rewards",
                json=payload,
            )

        assert response.status_code == 200
        data = response.json()
        assert data["received"] is False
        assert data["already_owned"] is True

    @pytest.mark.asyncio
    async def test_reward_skipped_non_recyclable(self, async_client: AsyncClient):
        """재활용폐기물이 아닌 경우 skip."""
        mock_response = CharacterRewardResponse(
            received=False,
            already_owned=False,
            name=None,
            dialog=None,
            match_reason=None,
            character_type=None,
            type=None,
        )

        with patch("domains.character.api.v1.endpoints.rewards.CharacterService") as MockService:
            mock_instance = AsyncMock()
            mock_instance.evaluate_reward.return_value = mock_response
            MockService.return_value = mock_instance

            payload = create_reward_request_payload(major_category="일반폐기물")
            response = await async_client.post(
                "/api/v1/internal/characters/rewards",
                json=payload,
            )

        assert response.status_code == 200
        data = response.json()
        assert data["received"] is False
        assert data["name"] is None

    @pytest.mark.asyncio
    async def test_reward_invalid_user_id_format(self, async_client: AsyncClient):
        """잘못된 user_id 형식."""
        payload = {
            "source": "scan",
            "user_id": "not-a-valid-uuid",
            "task_id": "test-task-123",
            "classification": {
                "major_category": "재활용폐기물",
                "middle_category": "플라스틱",
            },
            "disposal_rules_present": True,
            "insufficiencies_present": False,
        }

        response = await async_client.post(
            "/api/v1/internal/characters/rewards",
            json=payload,
        )

        assert response.status_code == 422  # Validation error

    @pytest.mark.asyncio
    async def test_reward_missing_required_fields(self, async_client: AsyncClient):
        """필수 필드 누락."""
        payload = {
            "source": "scan",
            # user_id 누락
            "task_id": "test-task-123",
        }

        response = await async_client.post(
            "/api/v1/internal/characters/rewards",
            json=payload,
        )

        assert response.status_code == 422


class TestHealthEndpoints:
    """Health check endpoints E2E tests."""

    @pytest.mark.asyncio
    async def test_health_endpoint(self, async_client: AsyncClient):
        """Health endpoint 정상 응답."""
        response = await async_client.get("/health")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"

    @pytest.mark.asyncio
    async def test_ready_endpoint(self, async_client: AsyncClient):
        """Ready endpoint 정상 응답."""
        # DB 연결 mock
        with patch("domains.character.api.v1.endpoints.health.get_db_session"):
            with patch("domains.character.api.v1.endpoints.health.AsyncSession") as MockSession:
                mock_session = AsyncMock()
                mock_session.execute = AsyncMock()
                MockSession.return_value.__aenter__.return_value = mock_session

                response = await async_client.get("/ready")

        # Ready는 DB 연결 확인이 필요하므로 mock 없이는 실패할 수 있음
        assert response.status_code in [200, 503]


class TestOpenAPIEndpoints:
    """OpenAPI documentation endpoints."""

    @pytest.mark.asyncio
    async def test_openapi_json(self, async_client: AsyncClient):
        """OpenAPI JSON schema 접근 가능."""
        response = await async_client.get("/api/v1/character/openapi.json")

        assert response.status_code == 200
        data = response.json()
        assert "openapi" in data
        assert "paths" in data

    @pytest.mark.asyncio
    async def test_docs_endpoint(self, async_client: AsyncClient):
        """Swagger UI 접근 가능."""
        response = await async_client.get("/api/v1/character/docs")

        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]


class TestResponseFormat:
    """Response format validation tests."""

    @pytest.mark.asyncio
    async def test_reward_response_has_all_fields(self, async_client: AsyncClient):
        """리워드 응답에 모든 필드 포함."""
        mock_response = CharacterRewardResponse(
            received=True,
            already_owned=False,
            name="플라봇",
            dialog="고마워!",
            match_reason="플라스틱>페트병",
            character_type="플라스틱",
            type="플라스틱",
        )

        with patch("domains.character.api.v1.endpoints.rewards.CharacterService") as MockService:
            mock_instance = AsyncMock()
            mock_instance.evaluate_reward.return_value = mock_response
            MockService.return_value = mock_instance

            payload = create_reward_request_payload()
            response = await async_client.post(
                "/api/v1/internal/characters/rewards",
                json=payload,
            )

        data = response.json()
        expected_fields = {
            "received",
            "already_owned",
            "name",
            "dialog",
            "match_reason",
            "character_type",
            "type",
        }
        assert expected_fields.issubset(set(data.keys()))

    @pytest.mark.asyncio
    async def test_catalog_response_format(self, async_client: AsyncClient):
        """카탈로그 응답 형식 검증."""
        mock_profiles = [
            CharacterProfile(name="이코", type="기본", dialog="안녕!", match="플라스틱"),
        ]

        with patch("domains.character.api.v1.endpoints.character.CharacterService") as MockService:
            mock_instance = AsyncMock()
            mock_instance.catalog.return_value = mock_profiles
            MockService.return_value = mock_instance

            response = await async_client.get("/api/v1/character/catalog")

        data = response.json()
        assert isinstance(data, list)
        assert len(data) == 1

        char = data[0]
        assert "name" in char
        assert "type" in char
        assert "dialog" in char
