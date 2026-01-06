"""GetCatalogQuery.

캐릭터 카탈로그 조회 Query입니다.
"""

from character.application.catalog.dto import CatalogResult
from character.application.catalog.ports import CatalogReader
from character.application.catalog.services.catalog_service import CatalogService


class GetCatalogQuery:
    """캐릭터 카탈로그 조회 Query.

    캐시를 활용하여 캐릭터 카탈로그를 조회합니다.
    """

    def __init__(self, reader: CatalogReader, service: CatalogService) -> None:
        """Initialize.

        Args:
            reader: 카탈로그 Reader
            service: 카탈로그 서비스
        """
        self._reader = reader
        self._service = service

    async def execute(self) -> CatalogResult:
        """카탈로그를 조회합니다.

        Returns:
            카탈로그 결과
        """
        # 1. Port를 통한 조회 (오케스트레이션)
        characters = await self._reader.list_all()

        # 2. Service를 통한 변환 (로직 위임)
        items = self._service.build_catalog_items(characters)

        return CatalogResult(items=items, total=len(items))
