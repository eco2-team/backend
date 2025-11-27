from fastapi import Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from domains.my.database.session import get_db_session
from domains.my.models import User
from domains.my.repositories import UserRepository
from domains.my.schemas import UserProfile, UserUpdate


class MyService:
    def __init__(self, session: AsyncSession = Depends(get_db_session)):
        self.session = session
        self.repo = UserRepository(session)

    async def get_user(self, user_id: int) -> UserProfile:
        user = await self._get_user_or_404(user_id)
        return self._to_profile(user)

    async def get_current_user(self, provider: str, provider_user_id: str) -> UserProfile:
        user = await self._get_user_by_identity(provider, provider_user_id)
        return self._to_profile(user)

    async def update_user(self, user_id: int, payload: UserUpdate) -> UserProfile:
        user = await self._get_user_or_404(user_id)
        return await self._apply_update(user, payload)

    async def update_current_user(
        self,
        provider: str,
        provider_user_id: str,
        payload: UserUpdate,
    ) -> UserProfile:
        user = await self._get_user_by_identity(provider, provider_user_id)
        return await self._apply_update(user, payload)

    async def update_profile_image(
        self,
        provider: str,
        provider_user_id: str,
        profile_image_url: str | None,
    ) -> UserProfile:
        user = await self._get_user_by_identity(provider, provider_user_id)
        payload = UserUpdate(profile_image_url=profile_image_url)
        return await self._apply_update(user, payload)

    async def delete_user(self, user_id: int) -> None:
        await self._get_user_or_404(user_id)
        await self.repo.delete_user(user_id)
        await self.session.commit()

    async def delete_current_user(self, provider: str, provider_user_id: str) -> None:
        user = await self._get_user_by_identity(provider, provider_user_id)
        await self.repo.delete_user(user.id)
        await self.session.commit()

    async def metrics(self) -> dict:
        return await self.repo.metrics()

    async def _get_user_or_404(self, user_id: int) -> User:
        user = await self.repo.get_user(user_id)
        if user is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
        return user

    async def _get_user_by_identity(self, provider: str, provider_user_id: str) -> User:
        user = await self.repo.get_by_provider_identity(provider, provider_user_id)
        if user is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
        return user

    async def _apply_update(self, user: User, payload: UserUpdate) -> UserProfile:
        update_data = payload.model_dump(exclude_unset=True)
        if not update_data:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="No changes provided",
            )
        updated = await self.repo.update_user(user, update_data)
        await self.session.commit()
        return self._to_profile(updated)

    @staticmethod
    def _to_profile(user: User) -> UserProfile:
        return UserProfile(
            id=int(user.id),
            provider=user.provider,
            provider_user_id=user.provider_user_id,
            email=user.email,
            username=user.username,
            name=user.name,
            profile_image_url=user.profile_image_url,
            created_at=user.created_at,
        )
