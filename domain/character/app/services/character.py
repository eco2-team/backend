from datetime import datetime
from uuid import uuid4

from app.schemas.character import (
    CharacterAnalysisRequest,
    CharacterHistoryEntry,
    CharacterProfile,
)


class CharacterService:
    async def analyze(self, payload: CharacterAnalysisRequest) -> CharacterProfile:
        score = 0.8 + (payload.mood_score or 0) * 0.1
        return CharacterProfile(
            id=str(uuid4()),
            name="Eco Guardian",
            description="Advocates for sustainable living and recycling awareness.",
            compatibility_score=min(score, 1.0),
            traits=payload.preferences or ["recycler", "educator"],
        )

    async def history(self, user_id: str) -> list[CharacterHistoryEntry]:
        now = datetime.utcnow()
        return [
            CharacterHistoryEntry(
                id=str(uuid4()),
                character_id=str(uuid4()),
                timestamp=now,
                context={"user_id": user_id, "action": "completed-cleanup"},
            )
        ]

    async def catalog(self) -> list[CharacterProfile]:
        return [
            CharacterProfile(
                id="catalog-guardian",
                name="Guardian",
                description="Protects nature and educates neighbors.",
                compatibility_score=0.93,
                traits=["educator", "community-builder"],
            ),
            CharacterProfile(
                id="catalog-strategist",
                name="Strategist",
                description="Optimizes recycling routes and logistics.",
                compatibility_score=0.85,
                traits=["analyst", "planner"],
            ),
        ]

    async def metrics(self) -> dict:
        return {
            "analyzed_users": 128,
            "catalog_size": 5,
            "history_entries": 56,
        }
