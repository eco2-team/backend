"""Tests for Redis Cache Layer."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestCacheOperations:
    """Cache get/set/invalidate 테스트."""

    @pytest.mark.asyncio
    async def test_get_cached_returns_none_when_disabled(self):
        """캐시 비활성화 시 None 반환."""
        with patch("domains.character.core.cache.get_settings") as mock_settings:
            mock_settings.return_value.cache_enabled = False

            from domains.character.core.cache import get_cached

            # Reset global client
            import domains.character.core.cache as cache_module

            cache_module._redis_client = None

            result = await get_cached("test:key")
            assert result is None

    @pytest.mark.asyncio
    async def test_get_cached_returns_data_on_hit(self):
        """캐시 히트 시 데이터 반환."""
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value='{"name": "이코"}')
        mock_redis.ping = AsyncMock()

        with patch("domains.character.core.cache.get_settings") as mock_settings:
            mock_settings.return_value.cache_enabled = True
            mock_settings.return_value.redis_url = "redis://localhost:6379/0"

            import domains.character.core.cache as cache_module

            cache_module._redis_client = mock_redis

            result = await cache_module.get_cached("test:key")
            assert result == {"name": "이코"}
            mock_redis.get.assert_called_once_with("test:key")

    @pytest.mark.asyncio
    async def test_get_cached_returns_none_on_miss(self):
        """캐시 미스 시 None 반환."""
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=None)
        mock_redis.ping = AsyncMock()

        with patch("domains.character.core.cache.get_settings") as mock_settings:
            mock_settings.return_value.cache_enabled = True
            mock_settings.return_value.redis_url = "redis://localhost:6379/0"

            import domains.character.core.cache as cache_module

            cache_module._redis_client = mock_redis

            result = await cache_module.get_cached("test:key")
            assert result is None

    @pytest.mark.asyncio
    async def test_set_cached_stores_data(self):
        """캐시에 데이터 저장."""
        mock_redis = AsyncMock()
        mock_redis.setex = AsyncMock()
        mock_redis.ping = AsyncMock()

        with patch("domains.character.core.cache.get_settings") as mock_settings:
            mock_settings.return_value.cache_enabled = True
            mock_settings.return_value.redis_url = "redis://localhost:6379/0"
            mock_settings.return_value.cache_ttl_seconds = 300

            import domains.character.core.cache as cache_module

            cache_module._redis_client = mock_redis

            result = await cache_module.set_cached("test:key", {"name": "이코"})
            assert result is True
            mock_redis.setex.assert_called_once()
            call_args = mock_redis.setex.call_args
            assert call_args[0][0] == "test:key"
            assert call_args[0][1] == 300

    @pytest.mark.asyncio
    async def test_invalidate_cache_deletes_key(self):
        """캐시 키 삭제."""
        mock_redis = AsyncMock()
        mock_redis.delete = AsyncMock()
        mock_redis.ping = AsyncMock()

        with patch("domains.character.core.cache.get_settings") as mock_settings:
            mock_settings.return_value.cache_enabled = True
            mock_settings.return_value.redis_url = "redis://localhost:6379/0"

            import domains.character.core.cache as cache_module

            cache_module._redis_client = mock_redis

            result = await cache_module.invalidate_cache("test:key")
            assert result is True
            mock_redis.delete.assert_called_once_with("test:key")


class TestCatalogCache:
    """CharacterService.catalog 캐시 통합 테스트."""

    @pytest.fixture
    def mock_session(self):
        return AsyncMock()

    @pytest.fixture
    def service(self, mock_session):
        with patch("domains.character.services.character.get_db_session"):
            from domains.character.services.character import CharacterService

            service = CharacterService.__new__(CharacterService)
            service.session = mock_session
            service.character_repo = MagicMock()
            service.ownership_repo = MagicMock()
            return service

    @pytest.mark.asyncio
    async def test_catalog_returns_cached_data(self, service):
        """캐시 히트 시 캐시된 데이터 반환."""
        cached_data = [{"name": "이코", "type": "기본", "dialog": "안녕!", "match": "플라스틱"}]

        with patch(
            "domains.character.services.character.get_cached",
            AsyncMock(return_value=cached_data),
        ):
            result = await service.catalog()

        assert len(result) == 1
        assert result[0].name == "이코"
        service.character_repo.list_all.assert_not_called()

    @pytest.mark.asyncio
    async def test_catalog_fetches_from_db_on_cache_miss(self, service):
        """캐시 미스 시 DB 조회 후 캐시 저장."""
        mock_character = MagicMock()
        mock_character.name = "이코"
        mock_character.type_label = "기본"
        mock_character.dialog = "안녕!"
        mock_character.description = None
        mock_character.match_label = "플라스틱"

        service.character_repo.list_all = AsyncMock(return_value=[mock_character])

        with (
            patch(
                "domains.character.services.character.get_cached",
                AsyncMock(return_value=None),
            ),
            patch(
                "domains.character.services.character.set_cached",
                AsyncMock(return_value=True),
            ) as mock_set,
        ):
            result = await service.catalog()

        assert len(result) == 1
        assert result[0].name == "이코"
        service.character_repo.list_all.assert_called_once()
        mock_set.assert_called_once()
