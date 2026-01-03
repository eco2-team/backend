"""GetCatalogQuery.

캐릭터 카탈로그 조회 Query입니다.
"""

from apps.character.application.catalog.dto import CatalogItem, CatalogResult
from apps.character.application.catalog.ports import CatalogReader


class GetCatalogQuery:
    """캐릭터 카탈로그 조회 Query.

    캐시를 활용하여 캐릭터 카탈로그를 조회합니다.
    """

    def __init__(self, reader: CatalogReader) -> None:
        """Initialize.

        Args:
            reader: 카탈로그 Reader
        """
        self._reader = reader

    async def execute(self) -> CatalogResult:
        """카탈로그를 조회합니다.

        Returns:
            카탈로그 결과
        """
        characters = await self._reader.list_all()

        items = tuple(
            CatalogItem(
                code=c.code,
                name=c.name,
                type_label=c.type_label,
                dialog=c.dialog or c.description or "",
                match_label=c.match_label,
                description=c.description,
            )
            for c in characters
        )

        return CatalogResult(items=items, total=len(items))
