from app.schemas.info import (
    FAQEntry,
    RecycleCategory,
    RecycleItem,
    RecycleSearchRequest,
    RegionalRule,
)


class InfoService:
    async def get_item(self, item_id: int) -> RecycleItem:
        return RecycleItem(
            id=item_id,
            name="페트병",
            category="플라스틱",
            subcategory="PET",
            disposal_method="내용물을 비우고 라벨 제거 후 압착",
            notes=["뚜껑과 라벨 분리", "잔여물 제거"],
            recyclable=True,
        )

    async def list_categories(self) -> list[RecycleCategory]:
        return [
            RecycleCategory(id=1, name="플라스틱", icon="🧴", item_count=42),
            RecycleCategory(id=2, name="종이", icon="📄", item_count=30),
            RecycleCategory(id=3, name="유리", icon="🍾", item_count=18),
        ]

    async def search(self, payload: RecycleSearchRequest) -> list[RecycleItem]:
        return [
            RecycleItem(
                id=1,
                name=payload.query,
                category="플라스틱",
                disposal_method="세척 후 투명 페트 전용 배출",
                notes=[],
                recyclable=True,
            )
        ]

    async def regional_rules(self, region: str) -> RegionalRule:
        return RegionalRule(
            region=region,
            rules=[
                "투명 페트병 별도 수거 요일 준수",
                "스티로폼은 금요일 배출",
            ],
        )

    async def faq(self, category: str | None, skip: int, limit: int) -> list[FAQEntry]:
        return [
            FAQEntry(
                id=1,
                question="페트병 라벨은 왜 제거해야 하나요?",
                answer="라벨 재질이 달라 분리해야 재활용 효율이 높아집니다.",
                category=category or "공통",
            )
        ][skip : skip + limit]

    async def metrics(self) -> dict:
        return {
            "items_indexed": 512,
            "faq_entries": 24,
            "last_sync_minutes_ago": 15,
        }
