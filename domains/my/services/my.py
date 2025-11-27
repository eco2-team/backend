from __future__ import annotations

from typing import Sequence
from uuid import UUID

from fastapi import Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from domains.my.database.session import get_db_session
from domains.my.models import AuthUserSocialAccount, User
from domains.my.repositories import UserRepository, UserSocialAccountRepository
from domains.my.schemas import SocialAccountProfile, UserProfile, UserUpdate


class MyService:
    def __init__(self, session: AsyncSession = Depends(get_db_session)):
        self.session = session
        self.repo = UserRepository(session)
        self.social_repo = UserSocialAccountRepository(session)

    async def get_user(self, user_id: int) -> UserProfile:
        user = await self._get_user_or_404(user_id)
        accounts = await self.social_repo.list_by_user_id(user.auth_user_id)
        return self._to_profile(user, accounts)

    async def get_current_user(self, auth_user_id: UUID) -> UserProfile:
        user = await self._get_user_by_auth_id(auth_user_id)
        accounts = await self.social_repo.list_by_user_id(auth_user_id)
        return self._to_profile(user, accounts)

    async def update_user(self, user_id: int, payload: UserUpdate) -> UserProfile:
        user = await self._get_user_or_404(user_id)
        updated = await self._apply_update(user, payload)
        accounts = await self.social_repo.list_by_user_id(user.auth_user_id)
        return self._to_profile(updated, accounts)

    async def update_current_user(self, auth_user_id: UUID, payload: UserUpdate) -> UserProfile:
        user = await self._get_user_by_auth_id(auth_user_id)
        updated = await self._apply_update(user, payload)
        accounts = await self.social_repo.list_by_user_id(auth_user_id)
        return self._to_profile(updated, accounts)

    async def update_profile_image(
        self,
        auth_user_id: UUID,
        profile_image_url: str | None,
    ) -> UserProfile:
        user = await self._get_user_by_auth_id(auth_user_id)
        payload = UserUpdate(profile_image_url=profile_image_url)
        updated = await self._apply_update(user, payload)
        accounts = await self.social_repo.list_by_user_id(auth_user_id)
        return self._to_profile(updated, accounts)

    async def delete_user(self, user_id: int) -> None:
        await self._get_user_or_404(user_id)
        await self.repo.delete_user(user_id)
        await self.session.commit()

    async def delete_current_user(self, auth_user_id: UUID) -> None:
        user = await self._get_user_by_auth_id(auth_user_id)
        await self.repo.delete_user(user.id)
        await self.session.commit()

    async def metrics(self) -> dict:
        base_metrics = await self.repo.metrics()
        provider_counts = await self.social_repo.count_by_provider()
        return {
            **base_metrics,
            "by_provider": provider_counts,
        }

    async def _get_user_or_404(self, user_id: int) -> User:
        user = await self.repo.get_user(user_id)
        if user is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
        return user

    async def _get_user_by_auth_id(self, auth_user_id: UUID) -> User:
        user = await self.repo.get_by_auth_user_id(auth_user_id)
        if user is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
        return user

    async def _apply_update(self, user: User, payload: UserUpdate) -> User:
        update_data = payload.model_dump(exclude_unset=True)
        if not update_data:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="No changes provided",
            )
        updated = await self.repo.update_user(user, update_data)
        await self.session.commit()
        return updated

    def _to_profile(
        self,
        user: User,
        accounts: Sequence[AuthUserSocialAccount],
    ) -> UserProfile:
        social_accounts = [self._to_social_account_schema(account) for account in accounts]
        primary = social_accounts[0] if social_accounts else None
        return UserProfile(
            id=int(user.id),
            auth_user_id=user.auth_user_id,
            username=user.username,
            name=user.name,
            profile_image_url=user.profile_image_url,
            created_at=user.created_at,
            primary_provider=primary.provider if primary else None,
            primary_email=primary.email if primary else None,
            social_accounts=social_accounts,
        )

    @staticmethod
    def _to_social_account_schema(account: AuthUserSocialAccount) -> SocialAccountProfile:
        return SocialAccountProfile(
            provider=account.provider,
            provider_user_id=account.provider_user_id,
            email=account.email,
            username=account.username,
            nickname=account.nickname,
            profile_image_url=account.profile_image_url,
            last_login_at=account.last_login_at,
        )
