"""Character Asset Port - 캐릭터 이미지 에셋 추상 인터페이스.

Clean Architecture:
- Application Layer에서 정의하는 추상 Port
- Infrastructure Layer에서 CDN/S3 구현체 제공

용도:
- Gemini 이미지 생성 시 캐릭터 참조 이미지 로드
- 캐릭터 스타일 일관성 유지를 위한 reference image 제공
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True)
class CharacterAsset:
    """캐릭터 에셋 DTO.

    Attributes:
        code: 캐릭터 코드 (예: battery, plastic, pet)
        image_url: CDN URL
        image_bytes: 이미지 바이트 (로드된 경우)
        mime_type: MIME 타입 (기본 image/png)
    """

    code: str
    image_url: str
    image_bytes: bytes | None = None
    mime_type: str = "image/png"


class CharacterAssetPort(ABC):
    """캐릭터 이미지 에셋 Port.

    캐릭터 코드를 기반으로 참조 이미지를 로드합니다.

    구현체:
    - CDNCharacterAssetLoader: CDN URL에서 이미지 fetch
    - LocalCharacterAssetLoader: 로컬 파일 시스템 (개발용)

    사용 예시:
    ```python
    asset = await loader.get_asset("battery")
    if asset and asset.image_bytes:
        # Gemini 이미지 생성에 reference로 사용
        contents.append({
            "mime_type": asset.mime_type,
            "data": base64.b64encode(asset.image_bytes).decode(),
        })
    ```
    """

    @abstractmethod
    async def get_asset(self, character_code: str) -> CharacterAsset | None:
        """캐릭터 코드로 에셋 조회.

        Args:
            character_code: 캐릭터 코드 (예: battery, plastic)

        Returns:
            CharacterAsset 또는 None (미존재)
        """
        pass

    @abstractmethod
    async def get_asset_url(self, character_code: str) -> str | None:
        """캐릭터 코드로 CDN URL만 조회 (바이트 로드 없음).

        Args:
            character_code: 캐릭터 코드

        Returns:
            CDN URL 또는 None
        """
        pass

    @abstractmethod
    async def list_available_codes(self) -> list[str]:
        """사용 가능한 모든 캐릭터 코드 목록.

        Returns:
            캐릭터 코드 목록
        """
        pass


class CharacterAssetNotFoundError(Exception):
    """캐릭터 에셋 미존재 예외."""

    def __init__(self, code: str):
        super().__init__(f"Character asset not found: {code}")
        self.code = code


class CharacterAssetLoadError(Exception):
    """캐릭터 에셋 로드 실패 예외."""

    def __init__(self, code: str, cause: Exception | None = None):
        super().__init__(f"Failed to load character asset: {code}")
        self.code = code
        self.cause = cause
