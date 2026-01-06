"""HTTP Controller 테스트.

HTTP Controller는 외부 클라이언트(프론트엔드, 모바일)와의 인터페이스입니다.
이 테스트는 요청/응답 변환, 레거시 호환성을 검증합니다.
"""

from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from character.application.catalog.dto import CatalogItem, CatalogResult
from character.application.reward.dto import RewardResult
from character.presentation.http.controllers.catalog import (
    router as catalog_router,
)
from character.presentation.http.controllers.reward import router as reward_router
from character.setup.dependencies import (
    get_catalog_query,
    get_evaluate_reward_command,
)

pytestmark = pytest.mark.asyncio


@pytest.fixture
def mock_catalog_query() -> AsyncMock:
    """Mock GetCatalogQuery."""
    return AsyncMock()


@pytest.fixture
def mock_evaluate_command() -> AsyncMock:
    """Mock EvaluateRewardCommand."""
    return AsyncMock()


def create_test_app(
    catalog_query: AsyncMock | None = None,
    evaluate_command: AsyncMock | None = None,
) -> FastAPI:
    """테스트용 FastAPI 앱 (의존성 오버라이드 포함)."""
    app = FastAPI()
    app.include_router(catalog_router)
    app.include_router(reward_router)

    # Dependency overrides
    if catalog_query:
        app.dependency_overrides[get_catalog_query] = lambda: catalog_query
    if evaluate_command:
        app.dependency_overrides[get_evaluate_reward_command] = lambda: evaluate_command

    return app


class TestCatalogController:
    """GET /character/catalog 테스트.

    검증 포인트:
    1. 정상 응답 형식
    2. 빈 카탈로그 처리
    3. 필드 strip 처리
    """

    async def test_returns_character_list(self, mock_catalog_query: AsyncMock) -> None:
        """정상 카탈로그 반환.

        검증:
        - list[CharacterProfile] 형식으로 반환
        - 각 캐릭터의 name, type, dialog, match 필드 포함

        이유:
        프론트엔드는 이 응답을 캐릭터 도감에 표시합니다.
        필드 형식이 맞아야 UI가 정상 동작합니다.
        """
        mock_catalog_query.execute.return_value = CatalogResult(
            items=(
                CatalogItem(
                    code="char-eco",
                    name="이코",
                    type_label="기본",
                    dialog="안녕! 나는 이코야!",
                    match_label=None,
                    description="기본 캐릭터",
                ),
                CatalogItem(
                    code="char-pet",
                    name="페트",
                    type_label="재활용",
                    dialog="안녕! 나는 페트야!",
                    match_label="무색페트병",
                    description="페트병 캐릭터",
                ),
            ),
            total=2,
        )

        app = create_test_app(catalog_query=mock_catalog_query)
        client = TestClient(app)
        response = client.get("/character/catalog")

        assert response.status_code == 200
        data = response.json()

        assert len(data) == 2

        # 첫 번째 캐릭터 검증
        eco = data[0]
        assert eco["name"] == "이코"
        assert eco["type"] == "기본"
        assert eco["dialog"] == "안녕! 나는 이코야!"
        assert eco["match"] is None  # 기본 캐릭터는 match 없음

        # 두 번째 캐릭터 검증
        pet = data[1]
        assert pet["name"] == "페트"
        assert pet["match"] == "무색페트병"

    async def test_empty_catalog(self, mock_catalog_query: AsyncMock) -> None:
        """빈 카탈로그 반환.

        검증:
        - 캐릭터가 없으면 빈 배열 반환

        이유:
        초기 상태나 설정 오류 시에도 에러 없이 응답해야 합니다.
        """
        mock_catalog_query.execute.return_value = CatalogResult(items=(), total=0)

        app = create_test_app(catalog_query=mock_catalog_query)
        client = TestClient(app)
        response = client.get("/character/catalog")

        assert response.status_code == 200
        assert response.json() == []

    async def test_strips_whitespace(self, mock_catalog_query: AsyncMock) -> None:
        """공백 제거 처리.

        검증:
        - type_label, dialog, match_label의 앞뒤 공백 제거

        이유:
        데이터 입력 시 실수로 추가된 공백이 UI에 표시되면 안 됩니다.
        """
        mock_catalog_query.execute.return_value = CatalogResult(
            items=(
                CatalogItem(
                    code="char-eco",
                    name="이코",
                    type_label="  기본  ",  # 공백 포함
                    dialog="  안녕!  ",  # 공백 포함
                    match_label="  라벨  ",  # 공백 포함
                    description="기본 캐릭터",
                ),
            ),
            total=1,
        )

        app = create_test_app(catalog_query=mock_catalog_query)
        client = TestClient(app)
        response = client.get("/character/catalog")

        data = response.json()
        assert data[0]["type"] == "기본"  # 공백 제거됨
        assert data[0]["dialog"] == "안녕!"
        assert data[0]["match"] == "라벨"


class TestRewardController:
    """POST /internal/characters/rewards 테스트.

    검증 포인트:
    1. 요청 검증 (필수 필드)
    2. 응답 형식
    3. 레거시 호환 필드 (type)
    """

    async def test_successful_reward(self, mock_evaluate_command: AsyncMock) -> None:
        """리워드 성공 응답.

        검증:
        - received=True일 때 캐릭터 정보 포함
        - character_type과 type 필드 모두 포함 (레거시 호환)

        이유:
        구버전 클라이언트는 'type' 필드를 사용하고,
        신버전은 'character_type'을 사용합니다.
        """
        mock_evaluate_command.execute.return_value = RewardResult(
            received=True,
            already_owned=False,
            character_code="char-pet",
            character_name="페트",
            character_type="재활용",
            dialog="안녕! 나는 페트야!",
            match_reason="Matched by 무색페트병",
        )

        app = create_test_app(evaluate_command=mock_evaluate_command)
        client = TestClient(app)
        response = client.post(
            "/internal/characters/rewards",
            json={
                "user_id": str(uuid4()),
                "source": "scan",
                "classification": {
                    "major_category": "재활용폐기물",
                    "middle_category": "무색페트병",
                },
                "disposal_rules_present": True,
                "insufficiencies_present": False,
            },
        )

        assert response.status_code == 200
        data = response.json()

        assert data["received"] is True
        assert data["already_owned"] is False
        assert data["name"] == "페트"
        assert data["dialog"] == "안녕! 나는 페트야!"
        # 레거시 호환
        assert data["character_type"] == "재활용"
        assert data["type"] == "재활용"  # 같은 값

    async def test_already_owned_response(self, mock_evaluate_command: AsyncMock) -> None:
        """이미 소유한 캐릭터 응답.

        검증:
        - already_owned=True 반환
        - 캐릭터 정보도 포함 (UI에서 표시용)

        이유:
        "이미 보유 중입니다" 메시지와 함께
        캐릭터 정보를 표시해야 합니다.
        """
        mock_evaluate_command.execute.return_value = RewardResult(
            received=False,
            already_owned=True,
            character_code="char-pet",
            character_name="페트",
            character_type="재활용",
            dialog="안녕! 나는 페트야!",
            match_reason="Matched by 무색페트병",
        )

        app = create_test_app(evaluate_command=mock_evaluate_command)
        client = TestClient(app)
        response = client.post(
            "/internal/characters/rewards",
            json={
                "user_id": str(uuid4()),
                "source": "scan",
                "classification": {
                    "major_category": "재활용폐기물",
                    "middle_category": "무색페트병",
                },
                "disposal_rules_present": True,
                "insufficiencies_present": False,
            },
        )

        data = response.json()
        assert data["received"] is False
        assert data["already_owned"] is True
        assert data["name"] == "페트"

    async def test_conditions_not_met_response(self, mock_evaluate_command: AsyncMock) -> None:
        """리워드 조건 미충족 응답.

        검증:
        - received=False, already_owned=False
        - 캐릭터 정보 없음 (null)

        이유:
        조건 미충족 시에는 캐릭터 정보가 없습니다.
        """
        mock_evaluate_command.execute.return_value = RewardResult(
            received=False,
            already_owned=False,
            character_code=None,
            character_name=None,
            character_type=None,
            dialog=None,
            match_reason="Reward conditions not met",
        )

        app = create_test_app(evaluate_command=mock_evaluate_command)
        client = TestClient(app)
        response = client.post(
            "/internal/characters/rewards",
            json={
                "user_id": str(uuid4()),
                "source": "scan",
                "classification": {
                    "major_category": "재활용폐기물",
                    "middle_category": "무색페트병",
                },
                "disposal_rules_present": False,  # 조건 미충족
                "insufficiencies_present": False,
            },
        )

        data = response.json()
        assert data["received"] is False
        assert data["already_owned"] is False
        assert data["name"] is None
        assert data["match_reason"] == "Reward conditions not met"

    async def test_invalid_request_returns_422(self, mock_evaluate_command: AsyncMock) -> None:
        """잘못된 요청 처리.

        검증:
        - 필수 필드 누락 시 422 Unprocessable Entity

        이유:
        클라이언트 오류를 명확하게 알려줘야 합니다.
        """
        app = create_test_app(evaluate_command=mock_evaluate_command)
        client = TestClient(app)
        response = client.post(
            "/internal/characters/rewards",
            json={
                # user_id 누락
                "source": "scan",
                "classification": {
                    "major_category": "재활용폐기물",
                    "middle_category": "무색페트병",
                },
            },
        )

        assert response.status_code == 422

    async def test_invalid_uuid_returns_422(self, mock_evaluate_command: AsyncMock) -> None:
        """잘못된 UUID 형식.

        검증:
        - 유효하지 않은 UUID 형식에 422 반환

        이유:
        UUID 형식 검증은 Pydantic이 처리합니다.
        """
        app = create_test_app(evaluate_command=mock_evaluate_command)
        client = TestClient(app)
        response = client.post(
            "/internal/characters/rewards",
            json={
                "user_id": "not-a-uuid",
                "source": "scan",
                "classification": {
                    "major_category": "재활용폐기물",
                    "middle_category": "무색페트병",
                },
                "disposal_rules_present": True,
                "insufficiencies_present": False,
            },
        )

        assert response.status_code == 422
