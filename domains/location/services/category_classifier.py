from dataclasses import dataclass

from domains.location.models import ZeroWasteSite
from domains.location.schemas.location import LocationCategory


@dataclass(frozen=True)
class CategoryPattern:
    category: LocationCategory
    keywords: tuple[str, ...]
    exclude_if_contains: tuple[str, ...] = ()


CATEGORY_PATTERNS: tuple[CategoryPattern, ...] = (
    CategoryPattern(
        LocationCategory.REFILL_ZERO,
        (
            "제로웨이스트",
            "리필",
            "무포장",
            "용기",
            "리필스테이션",
            "리필샵",
        ),
    ),
    CategoryPattern(
        LocationCategory.CAFE_BAKERY,
        (
            "카페",
            "커피",
            "tea",
            "베이커리",
            "브루어리",
        ),
    ),
    CategoryPattern(
        LocationCategory.VEGAN_DINING,
        (
            "비건",
            "vegan",
        ),
    ),
    CategoryPattern(
        LocationCategory.UPCYCLE_RECYCLE,
        (
            "되살림",
            "업사이클",
            "리사이클",
            "재활용",
            "수거",
            "리폼",
            "수선",
            "재사용",
        ),
    ),
    CategoryPattern(
        LocationCategory.BOOK_WORKSHOP,
        (
            "책방",
            "서점",
            "도서관",
            "공방",
            "스튜디오",
            "갤러리",
            "센터",
            "학교",
            "교육",
            "클래스",
            "워크샵",
            "아카데미",
        ),
    ),
    CategoryPattern(
        LocationCategory.MARKET_MART,
        (
            "마트",
            "마켓",
            "시장",
            "생협",
            "coop",
            "co-op",
            "한살림",
            "아이쿱",
            "하나로",
            "공동구매",
            "무인상점",
        ),
    ),
    CategoryPattern(
        LocationCategory.LODGING,
        (
            "숙소",
            "게스트하우스",
            "게하",
            "민박",
            "호텔",
            "펜션",
            "호스텔",
            " stay",
            " 스테이",
            "guesthouse",
            "guest house",
        ),
        exclude_if_contains=("스테이션",),
    ),
)


def classify_category(site: ZeroWasteSite) -> LocationCategory:
    text_parts = [
        value.lower()
        for value in (site.memo, site.display1, site.display2)
        if value
    ]
    text = " ".join(text_parts)
    if not text and site.favorite_type == "ADDRESS":
        return LocationCategory.ADDRESS_ONLY

    for pattern in CATEGORY_PATTERNS:
        if any(keyword in text for keyword in pattern.keywords):
            if any(exclusion in text for exclusion in pattern.exclude_if_contains):
                continue
            return pattern.category

    if site.favorite_type == "ADDRESS":
        return LocationCategory.ADDRESS_ONLY
    return LocationCategory.GENERAL

