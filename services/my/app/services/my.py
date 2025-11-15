from datetime import datetime

from app.schemas.my import ActivityEntry, UserPoints, UserProfile, UserUpdate


class MyService:
    async def get_user(self, user_id: int) -> UserProfile:
        return UserProfile(
            id=user_id,
            email="user@example.com",
            username="eco-user",
            avatar_url=None,
            points=1230,
            level=4,
            created_at=datetime.utcnow(),
        )

    async def update_user(self, user_id: int, payload: UserUpdate) -> UserProfile:
        current = await self.get_user(user_id)
        return current.copy(update=payload.dict(exclude_none=True))

    async def user_points(self, user_id: int) -> UserPoints:
        return UserPoints(
            user_id=user_id,
            total_points=1500,
            available_points=1200,
            used_points=300,
        )

    async def history(self, user_id: int, skip: int, limit: int) -> list[ActivityEntry]:
        base = ActivityEntry(
            id=1,
            user_id=user_id,
            action="waste_scan",
            points_earned=15,
            timestamp=datetime.utcnow(),
        )
        return [base][skip : skip + limit]

    async def delete_user(self, user_id: int) -> None:
        _ = user_id

    async def metrics(self) -> dict:
        return {
            "profiles": 240,
            "weekly_active_users": 82,
            "avg_points_per_user": 1340,
        }
