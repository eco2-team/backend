"""CatalogService.

Entity를 DTO로 변환하는 등 Catalog 관련 순수 애플리케이션 로직을 담당합니다.
"""

from typing import Sequence

from character.application.catalog.dto import CatalogItem
from character.domain.entities import Character


class CatalogService:
    """카탈로그 서비스."""

    def build_catalog_items(self, characters: Sequence[Character]) -> tuple[CatalogItem, ...]:
        """Character 엔티티 목록을 CatalogItem DTO 목록으로 변환합니다.

        정책:
        - dialog가 없으면 description을 사용
        - 둘 다 없으면 빈 문자열

        Args:
            characters: 캐릭터 엔티티 목록

        Returns:
            CatalogItem 튜플
        """
        return tuple(
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
