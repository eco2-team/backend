"""CDN Character Asset Loader.

CDN에서 캐릭터 참조 이미지를 로드하는 구현체.

아키텍처:
- S3: dev-sesacthon-dev-images/character/{code}.png
- CDN: https://images.dev.growbin.app/character/{code}.png

캐싱 전략:
- 메모리 캐시 (LRU): 자주 사용되는 이미지 캐싱
- 캐시 TTL: 1시간 (이미지는 잘 변하지 않음)
"""

from __future__ import annotations

import asyncio
import logging
from functools import lru_cache
from typing import ClassVar

import httpx

from chat_worker.application.ports.character_asset import (
    CharacterAsset,
    CharacterAssetLoadError,
    CharacterAssetPort,
)

logger = logging.getLogger(__name__)


class CDNCharacterAssetLoader(CharacterAssetPort):
    """CDN 기반 캐릭터 에셋 로더.

    S3/CloudFront CDN에서 캐릭터 이미지를 로드합니다.

    Attributes:
        cdn_base_url: CDN 베이스 URL
        prefix: S3 prefix (기본 "character")
        timeout: HTTP 요청 타임아웃
    """

    # 지원되는 캐릭터 코드 목록
    # S3에 업로드된 이미지와 동기화 필요
    AVAILABLE_CODES: ClassVar[list[str]] = [
        "battery",
        "clothes",
        "foodwaste",
        "glass",
        "lighting",
        "metal",
        "monitor",
        "paper",
        "paper_products",
        "pet",
        "plastic",
        "sofa",
        "styrofoam",
        "tissue",
        "vinyl",
    ]

    # 캐릭터 코드 → 폐기물 카테고리 매핑
    # CharacterService의 waste_category와 연결
    CODE_TO_CATEGORY: ClassVar[dict[str, list[str]]] = {
        "battery": ["배터리", "건전지", "폐건전지"],
        "clothes": ["의류", "옷", "헌옷"],
        "foodwaste": ["음식물", "음식물쓰레기", "음쓰"],
        "glass": ["유리", "유리병", "빈병"],
        "lighting": ["조명", "형광등", "폐형광등", "전구"],
        "metal": ["금속", "캔", "철", "고철", "알루미늄"],
        "monitor": ["모니터", "전자제품", "가전", "폐가전"],
        "paper": ["종이", "신문지", "책"],
        "paper_products": ["종이팩", "우유팩", "종이컵"],
        "pet": ["페트", "페트병", "PET"],
        "plastic": ["플라스틱", "PP", "PE", "플라"],
        "sofa": ["소파", "대형폐기물", "가구", "침대", "매트리스"],
        "styrofoam": ["스티로폼", "완충재", "발포"],
        "tissue": ["휴지", "화장지", "종이타월"],
        "vinyl": ["비닐", "봉투", "비닐봉지", "랩"],
    }

    def __init__(
        self,
        cdn_base_url: str = "https://images.dev.growbin.app",
        prefix: str = "character",
        timeout: float = 10.0,
        cache_enabled: bool = True,
    ):
        """초기화.

        Args:
            cdn_base_url: CDN 베이스 URL
            prefix: S3 object prefix
            timeout: HTTP 요청 타임아웃 (초)
            cache_enabled: 메모리 캐시 사용 여부
        """
        self._cdn_base_url = cdn_base_url.rstrip("/")
        self._prefix = prefix
        self._timeout = timeout
        self._cache_enabled = cache_enabled
        self._cache: dict[str, bytes] = {}
        self._cache_lock = asyncio.Lock()

    def _build_url(self, code: str) -> str:
        """CDN URL 생성."""
        return f"{self._cdn_base_url}/{self._prefix}/{code}.png"

    async def get_asset(self, character_code: str) -> CharacterAsset | None:
        """캐릭터 코드로 에셋 조회 (바이트 포함).

        Args:
            character_code: 캐릭터 코드

        Returns:
            CharacterAsset (image_bytes 포함) 또는 None
        """
        code = character_code.lower()
        if code not in self.AVAILABLE_CODES:
            logger.debug("Unknown character code: %s", code)
            return None

        url = self._build_url(code)

        # 캐시 확인
        if self._cache_enabled and code in self._cache:
            logger.debug("Cache hit for character: %s", code)
            return CharacterAsset(
                code=code,
                image_url=url,
                image_bytes=self._cache[code],
            )

        # CDN에서 로드
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.get(url)
                response.raise_for_status()
                image_bytes = response.content

            # 캐시 저장
            if self._cache_enabled:
                async with self._cache_lock:
                    self._cache[code] = image_bytes

            logger.info(
                "Loaded character asset: %s (%d bytes)",
                code,
                len(image_bytes),
            )

            return CharacterAsset(
                code=code,
                image_url=url,
                image_bytes=image_bytes,
            )

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                logger.warning("Character asset not found: %s", code)
                return None
            logger.error("HTTP error loading character asset %s: %s", code, e)
            raise CharacterAssetLoadError(code, e) from e

        except Exception as e:
            logger.error("Failed to load character asset %s: %s", code, e)
            raise CharacterAssetLoadError(code, e) from e

    async def get_asset_url(self, character_code: str) -> str | None:
        """캐릭터 코드로 CDN URL만 조회.

        Args:
            character_code: 캐릭터 코드

        Returns:
            CDN URL 또는 None
        """
        code = character_code.lower()
        if code not in self.AVAILABLE_CODES:
            return None
        return self._build_url(code)

    async def list_available_codes(self) -> list[str]:
        """사용 가능한 모든 캐릭터 코드 목록."""
        return list(self.AVAILABLE_CODES)

    def get_code_for_category(self, waste_category: str) -> str | None:
        """폐기물 카테고리에서 캐릭터 코드 조회.

        Args:
            waste_category: 폐기물 카테고리명

        Returns:
            매칭된 캐릭터 코드 또는 None

        Examples:
            >>> loader.get_code_for_category("페트병")
            'pet'
            >>> loader.get_code_for_category("플라스틱")
            'plastic'
        """
        category_lower = waste_category.lower()

        for code, categories in self.CODE_TO_CATEGORY.items():
            for cat in categories:
                if cat.lower() in category_lower or category_lower in cat.lower():
                    return code

        return None

    async def get_asset_for_category(self, waste_category: str) -> CharacterAsset | None:
        """폐기물 카테고리로 에셋 조회.

        Args:
            waste_category: 폐기물 카테고리명

        Returns:
            CharacterAsset 또는 None
        """
        code = self.get_code_for_category(waste_category)
        if not code:
            return None
        return await self.get_asset(code)

    def clear_cache(self) -> None:
        """캐시 초기화."""
        self._cache.clear()
        logger.info("Character asset cache cleared")


@lru_cache(maxsize=1)
def get_character_asset_loader() -> CDNCharacterAssetLoader:
    """CharacterAssetLoader 싱글톤."""
    return CDNCharacterAssetLoader()
