"""CachedCatalogReader 테스트.

캐시 레이어는 시스템 성능에 직접적인 영향을 미칩니다.
이 테스트는 캐시 히트/미스, 직렬화/역직렬화, TTL 동작을 검증합니다.
"""

import json
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from character.domain.entities import Character
from character.infrastructure.persistence_redis.cached_catalog_reader import (
    CACHE_KEY,
    CACHE_TTL,
    CachedCatalogReader,
)

pytestmark = pytest.mark.asyncio


@pytest.fixture
def mock_delegate() -> AsyncMock:
    """DB Reader mock."""
    return AsyncMock()


@pytest.fixture
def mock_redis() -> AsyncMock:
    """Redis client mock."""
    redis = AsyncMock()
    redis.get = AsyncMock(return_value=None)
    redis.setex = AsyncMock()
    return redis


@pytest.fixture
def sample_characters() -> list[Character]:
    """테스트용 캐릭터 목록."""
    return [
        Character(
            id=uuid4(),
            code="char-eco",
            name="이코",
            type_label="기본",
            dialog="안녕! 나는 이코야!",
            description="기본 캐릭터",
            match_label=None,
        ),
        Character(
            id=uuid4(),
            code="char-pet",
            name="페트",
            type_label="재활용",
            dialog="안녕! 나는 페트야!",
            description="페트병 캐릭터",
            match_label="무색페트병",
        ),
    ]


class TestCacheHitMiss:
    """캐시 히트/미스 동작 테스트.

    검증 포인트:
    1. 캐시 히트: Redis에서 바로 반환, DB 조회 없음
    2. 캐시 미스: DB 조회 후 캐시 저장
    """

    async def test_cache_hit_skips_db(
        self,
        mock_delegate: AsyncMock,
        mock_redis: AsyncMock,
        sample_characters: list[Character],
    ) -> None:
        """캐시 히트 시 DB 조회 생략.

        검증:
        - Redis에 데이터가 있으면 delegate.list_all()이 호출되지 않음
        - Redis에서 가져온 데이터가 올바르게 역직렬화됨

        이유:
        카탈로그는 자주 변경되지 않으므로 캐시 활용률이 높습니다.
        캐시 히트 시 DB 부하를 줄이는 것이 핵심 목적입니다.
        """
        # Given: Redis에 캐시된 데이터 존재
        cached_data = json.dumps(
            [
                {
                    "id": str(sample_characters[0].id),
                    "code": "char-eco",
                    "name": "이코",
                    "description": "기본 캐릭터",
                    "type_label": "기본",
                    "dialog": "안녕! 나는 이코야!",
                    "match_label": None,
                }
            ]
        )
        mock_redis.get.return_value = cached_data

        reader = CachedCatalogReader(mock_delegate, mock_redis)

        # When
        result = await reader.list_all()

        # Then
        assert len(result) == 1
        assert result[0].code == "char-eco"
        assert result[0].name == "이코"
        # DB 조회 없음
        mock_delegate.list_all.assert_not_called()
        # Redis setex도 호출 없음 (이미 캐시됨)
        mock_redis.setex.assert_not_called()

    async def test_cache_miss_fetches_from_db_and_caches(
        self,
        mock_delegate: AsyncMock,
        mock_redis: AsyncMock,
        sample_characters: list[Character],
    ) -> None:
        """캐시 미스 시 DB 조회 후 캐시 저장.

        검증:
        - Redis에 데이터가 없으면 delegate.list_all() 호출
        - 조회 결과가 Redis에 저장됨
        - TTL이 올바르게 설정됨

        이유:
        첫 요청이나 캐시 만료 후에는 DB에서 조회해야 합니다.
        조회 결과를 캐시하여 이후 요청을 빠르게 처리합니다.
        """
        # Given: 캐시 없음
        mock_redis.get.return_value = None
        mock_delegate.list_all.return_value = sample_characters

        reader = CachedCatalogReader(mock_delegate, mock_redis)

        # When
        result = await reader.list_all()

        # Then
        assert len(result) == 2
        # DB 조회됨
        mock_delegate.list_all.assert_called_once()
        # Redis에 캐시됨
        mock_redis.setex.assert_called_once()
        call_args = mock_redis.setex.call_args
        assert call_args[0][0] == CACHE_KEY
        assert call_args[0][1] == CACHE_TTL  # 1시간


class TestSerialization:
    """직렬화/역직렬화 테스트.

    검증 포인트:
    1. Character 엔티티가 JSON으로 올바르게 변환
    2. JSON이 Character 엔티티로 올바르게 복원
    3. Optional 필드 처리
    """

    async def test_serialize_preserves_all_fields(
        self,
        mock_delegate: AsyncMock,
        mock_redis: AsyncMock,
        sample_characters: list[Character],
    ) -> None:
        """직렬화 시 모든 필드 보존.

        검증:
        - id가 문자열로 변환됨
        - 모든 필드가 JSON에 포함됨

        이유:
        캐시된 데이터가 원본과 동일해야 합니다.
        필드 누락은 클라이언트 오류로 이어집니다.
        """
        mock_redis.get.return_value = None
        mock_delegate.list_all.return_value = sample_characters

        reader = CachedCatalogReader(mock_delegate, mock_redis)
        await reader.list_all()

        # setex에 전달된 JSON 검증
        cached_json = mock_redis.setex.call_args[0][2]
        cached_data = json.loads(cached_json)

        assert len(cached_data) == 2

        eco = cached_data[0]
        assert eco["id"] == str(sample_characters[0].id)
        assert eco["code"] == "char-eco"
        assert eco["name"] == "이코"
        assert eco["type_label"] == "기본"
        assert eco["dialog"] == "안녕! 나는 이코야!"
        assert eco["description"] == "기본 캐릭터"
        assert eco["match_label"] is None

    async def test_deserialize_handles_bytes(
        self,
        mock_delegate: AsyncMock,
        mock_redis: AsyncMock,
    ) -> None:
        """bytes 타입 역직렬화 처리.

        검증:
        - Redis에서 bytes로 반환해도 올바르게 처리

        이유:
        Redis 클라이언트 설정에 따라 str 또는 bytes로 반환됩니다.
        두 경우 모두 처리해야 합니다.
        """
        # Given: bytes 타입으로 반환
        cached_data = json.dumps(
            [
                {
                    "id": str(uuid4()),
                    "code": "char-eco",
                    "name": "이코",
                    "description": None,
                    "type_label": "기본",
                    "dialog": "안녕!",
                    "match_label": None,
                }
            ]
        ).encode("utf-8")
        mock_redis.get.return_value = cached_data

        reader = CachedCatalogReader(mock_delegate, mock_redis)

        # When
        result = await reader.list_all()

        # Then
        assert len(result) == 1
        assert result[0].name == "이코"

    async def test_deserialize_handles_missing_optional_fields(
        self,
        mock_delegate: AsyncMock,
        mock_redis: AsyncMock,
    ) -> None:
        """Optional 필드 누락 처리.

        검증:
        - description, match_label이 없어도 역직렬화 성공

        이유:
        캐시 스키마가 변경되거나 일부 캐릭터에 optional 필드가 없을 수 있습니다.
        """
        cached_data = json.dumps(
            [
                {
                    "id": str(uuid4()),
                    "code": "char-eco",
                    "name": "이코",
                    "type_label": "기본",
                    "dialog": "안녕!",
                    # description, match_label 없음
                }
            ]
        )
        mock_redis.get.return_value = cached_data

        reader = CachedCatalogReader(mock_delegate, mock_redis)

        result = await reader.list_all()

        assert len(result) == 1
        assert result[0].description is None
        assert result[0].match_label is None


class TestCacheKey:
    """캐시 키 테스트."""

    def test_cache_key_is_descriptive(self) -> None:
        """캐시 키가 명확한지 확인.

        검증:
        - 캐시 키가 도메인과 용도를 명확히 나타내는지

        이유:
        Redis에서 키를 모니터링하거나 수동으로 삭제할 때
        용도를 쉽게 파악할 수 있어야 합니다.
        """
        assert CACHE_KEY == "character:catalog"
        assert "character" in CACHE_KEY
        assert "catalog" in CACHE_KEY

    def test_cache_ttl_is_reasonable(self) -> None:
        """캐시 TTL이 적절한지 확인.

        검증:
        - 너무 짧지 않음 (성능)
        - 너무 길지 않음 (데이터 신선도)

        이유:
        카탈로그는 자주 변경되지 않지만 무한히 캐시하면
        새 캐릭터 추가 시 반영이 느려집니다.
        """
        assert CACHE_TTL == 3600  # 1시간
        assert CACHE_TTL >= 60  # 최소 1분
        assert CACHE_TTL <= 86400  # 최대 24시간
