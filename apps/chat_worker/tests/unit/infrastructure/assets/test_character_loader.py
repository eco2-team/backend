"""CDN Character Asset Loader Tests."""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from chat_worker.application.ports.character_asset import (
    CharacterAsset,
    CharacterAssetLoadError,
)
from chat_worker.infrastructure.assets.character_loader import (
    CDNCharacterAssetLoader,
    get_character_asset_loader,
)


class TestCDNCharacterAssetLoader:
    """CDNCharacterAssetLoader 테스트."""

    def test_init_defaults(self):
        """기본값 초기화."""
        loader = CDNCharacterAssetLoader()
        assert loader._cdn_base_url == "https://images.dev.growbin.app"
        assert loader._prefix == "character"
        assert loader._timeout == 10.0
        assert loader._cache_enabled is True
        assert loader._cache == {}

    def test_init_custom(self):
        """커스텀 값 초기화."""
        loader = CDNCharacterAssetLoader(
            cdn_base_url="https://cdn.example.com/",
            prefix="assets",
            timeout=5.0,
            cache_enabled=False,
        )
        assert loader._cdn_base_url == "https://cdn.example.com"  # trailing slash stripped
        assert loader._prefix == "assets"
        assert loader._timeout == 5.0
        assert loader._cache_enabled is False

    def test_build_url(self):
        """URL 생성 테스트."""
        loader = CDNCharacterAssetLoader()
        url = loader._build_url("battery")
        assert url == "https://images.dev.growbin.app/character/battery.png"

    def test_available_codes(self):
        """지원 코드 목록."""
        codes = CDNCharacterAssetLoader.AVAILABLE_CODES
        assert "battery" in codes
        assert "pet" in codes
        assert "plastic" in codes
        assert "eco" in codes
        assert len(codes) == 13  # DB 13종과 동기화


class TestGetAsset:
    """get_asset() 테스트."""

    @pytest.mark.asyncio
    async def test_unknown_code_returns_none(self):
        """미등록 코드는 None 반환."""
        loader = CDNCharacterAssetLoader()
        result = await loader.get_asset("unknown")
        assert result is None

    @pytest.mark.asyncio
    async def test_case_insensitive(self):
        """대소문자 구분 없음."""
        loader = CDNCharacterAssetLoader(cache_enabled=False)

        with patch.object(loader, "_get_http_client") as mock_get_client:
            mock_response = MagicMock()
            mock_response.content = b"test_image_data"
            mock_response.raise_for_status = MagicMock()

            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_get_client.return_value = mock_client

            result = await loader.get_asset("BATTERY")
            assert result is not None
            assert result.code == "battery"

    @pytest.mark.asyncio
    async def test_cache_hit(self):
        """캐시 히트 시 HTTP 호출 없음."""
        loader = CDNCharacterAssetLoader()
        loader._cache["pet"] = b"cached_data"

        result = await loader.get_asset("pet")
        assert result is not None
        assert result.image_bytes == b"cached_data"
        assert result.code == "pet"

    @pytest.mark.asyncio
    async def test_cache_miss_fetches_from_cdn(self):
        """캐시 미스 시 CDN에서 fetch."""
        loader = CDNCharacterAssetLoader()

        with patch.object(loader, "_get_http_client") as mock_get_client:
            mock_response = MagicMock()
            mock_response.content = b"fetched_image"
            mock_response.raise_for_status = MagicMock()

            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_get_client.return_value = mock_client

            result = await loader.get_asset("battery")

            assert result is not None
            assert result.image_bytes == b"fetched_image"
            assert result.code == "battery"
            assert "battery" in loader._cache

    @pytest.mark.asyncio
    async def test_404_returns_none(self):
        """404 응답은 None 반환."""
        loader = CDNCharacterAssetLoader()

        with patch.object(loader, "_get_http_client") as mock_get_client:
            mock_response = MagicMock()
            mock_response.status_code = 404

            mock_client = AsyncMock()
            mock_client.get = AsyncMock(
                side_effect=httpx.HTTPStatusError(
                    "Not Found",
                    request=MagicMock(),
                    response=mock_response,
                )
            )
            mock_get_client.return_value = mock_client

            result = await loader.get_asset("battery")
            assert result is None

    @pytest.mark.asyncio
    async def test_http_error_raises(self):
        """HTTP 에러 (404 제외) 시 예외 발생."""
        loader = CDNCharacterAssetLoader()

        with patch.object(loader, "_get_http_client") as mock_get_client:
            mock_response = MagicMock()
            mock_response.status_code = 500

            mock_client = AsyncMock()
            mock_client.get = AsyncMock(
                side_effect=httpx.HTTPStatusError(
                    "Server Error",
                    request=MagicMock(),
                    response=mock_response,
                )
            )
            mock_get_client.return_value = mock_client

            with pytest.raises(CharacterAssetLoadError) as exc_info:
                await loader.get_asset("battery")
            assert exc_info.value.code == "battery"


class TestGetAssetUrl:
    """get_asset_url() 테스트."""

    @pytest.mark.asyncio
    async def test_valid_code(self):
        """유효한 코드는 URL 반환."""
        loader = CDNCharacterAssetLoader()
        url = await loader.get_asset_url("pet")
        assert url == "https://images.dev.growbin.app/character/pet.png"

    @pytest.mark.asyncio
    async def test_invalid_code(self):
        """잘못된 코드는 None 반환."""
        loader = CDNCharacterAssetLoader()
        url = await loader.get_asset_url("invalid")
        assert url is None


class TestListAvailableCodes:
    """list_available_codes() 테스트."""

    @pytest.mark.asyncio
    async def test_returns_all_codes(self):
        """모든 코드 반환."""
        loader = CDNCharacterAssetLoader()
        codes = await loader.list_available_codes()
        assert "battery" in codes
        assert "pet" in codes
        assert "eco" in codes
        assert len(codes) == 13  # DB 13종과 동기화


class TestGetCodeForCategory:
    """get_code_for_category() 테스트."""

    def test_exact_match(self):
        """정확한 매칭."""
        loader = CDNCharacterAssetLoader()
        assert loader.get_code_for_category("배터리") == "battery"
        assert loader.get_code_for_category("페트병") == "pet"
        assert loader.get_code_for_category("플라스틱") == "plastic"

    def test_partial_match(self):
        """부분 매칭."""
        loader = CDNCharacterAssetLoader()
        assert loader.get_code_for_category("건전지 버리기") == "battery"
        assert loader.get_code_for_category("유리병 분리배출") == "glass"

    def test_case_insensitive(self):
        """대소문자 무시."""
        loader = CDNCharacterAssetLoader()
        assert loader.get_code_for_category("PET") == "pet"
        assert loader.get_code_for_category("pet") == "pet"

    def test_no_match(self):
        """매칭 없음."""
        loader = CDNCharacterAssetLoader()
        assert loader.get_code_for_category("자동차") is None


class TestGetAssetForCategory:
    """get_asset_for_category() 테스트."""

    @pytest.mark.asyncio
    async def test_valid_category(self):
        """유효한 카테고리로 에셋 조회."""
        loader = CDNCharacterAssetLoader()

        with patch.object(loader, "get_asset") as mock_get_asset:
            mock_asset = CharacterAsset(
                code="pet",
                image_url="https://example.com/pet.png",
                image_bytes=b"test",
            )
            mock_get_asset.return_value = mock_asset

            result = await loader.get_asset_for_category("페트병")

            assert result is not None
            assert result.code == "pet"
            mock_get_asset.assert_called_once_with("pet")

    @pytest.mark.asyncio
    async def test_invalid_category(self):
        """잘못된 카테고리."""
        loader = CDNCharacterAssetLoader()
        result = await loader.get_asset_for_category("자동차")
        assert result is None


class TestClearCache:
    """clear_cache() 테스트."""

    def test_clears_cache(self):
        """캐시 초기화."""
        loader = CDNCharacterAssetLoader()
        loader._cache["test"] = b"data"

        loader.clear_cache()

        assert loader._cache == {}


class TestHttpClientManagement:
    """HTTP 클라이언트 관리 테스트."""

    @pytest.mark.asyncio
    async def test_lazy_initialization(self):
        """lazy initialization."""
        loader = CDNCharacterAssetLoader()
        assert loader._http_client is None

        client = await loader._get_http_client()
        assert loader._http_client is not None
        assert client is loader._http_client

        # 재호출 시 동일 인스턴스
        client2 = await loader._get_http_client()
        assert client2 is client

        # cleanup
        await loader.close()

    @pytest.mark.asyncio
    async def test_close(self):
        """close() 호출 시 클라이언트 정리."""
        loader = CDNCharacterAssetLoader()
        await loader._get_http_client()
        assert loader._http_client is not None

        await loader.close()
        assert loader._http_client is None


class TestGetCharacterAssetLoader:
    """get_character_asset_loader() 싱글톤 테스트."""

    def test_singleton(self):
        """싱글톤 패턴."""
        # lru_cache 초기화
        get_character_asset_loader.cache_clear()

        loader1 = get_character_asset_loader()
        loader2 = get_character_asset_loader()
        assert loader1 is loader2
