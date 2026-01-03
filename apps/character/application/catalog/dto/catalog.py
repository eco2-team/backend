"""Catalog DTOs."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class CatalogItem:
    """카탈로그 아이템.

    Attributes:
        code: 캐릭터 코드
        name: 캐릭터 이름
        type_label: 캐릭터 타입 라벨
        dialog: 캐릭터 대사
        match_label: 매칭 라벨
        description: 캐릭터 설명
    """

    code: str
    name: str
    type_label: str
    dialog: str
    match_label: str | None = None
    description: str | None = None


@dataclass(frozen=True, slots=True)
class CatalogResult:
    """카탈로그 조회 결과.

    Attributes:
        items: 카탈로그 아이템 목록
        total: 전체 개수
    """

    items: tuple[CatalogItem, ...]
    total: int
