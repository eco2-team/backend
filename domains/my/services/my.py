from __future__ import annotations

from typing import Sequence
from uuid import UUID

import re

from fastapi import Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from domains.my.database.session import get_db_session
from domains.my.models import AuthUserSocialAccount, User
from domains.my.repositories import UserRepository, UserSocialAccountRepository
from domains.my.schemas import UserProfile, UserUpdate


class MyService:
    def __init__(self, session: AsyncSession = Depends(get_db_session)):
        self.session = session
        self.repo = UserRepository(session)
        self.social_repo = UserSocialAccountRepository(session)

    async def get_current_user(
        self, auth_user_id: UUID, provider: str | None = None
    ) -> UserProfile:
        user, accounts = await self._get_or_create_user_with_accounts(auth_user_id)
        return self._to_profile(user, accounts, preferred_provider=provider)

    async def update_current_user(
        self,
        auth_user_id: UUID,
        payload: UserUpdate,
        provider: str | None = None,
    ) -> UserProfile:
        user = await self._get_user_by_auth_id(auth_user_id)
        updated = await self._apply_update(user, payload)
        accounts = await self.social_repo.list_by_user_id(auth_user_id)
        return self._to_profile(updated, accounts, preferred_provider=provider)

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

    async def _get_user_by_auth_id(self, auth_user_id: UUID) -> User:
        user = await self.repo.get_by_auth_user_id(auth_user_id)
        if user is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
        return user

    async def _get_or_create_user_with_accounts(
        self, auth_user_id: UUID
    ) -> tuple[User, Sequence[AuthUserSocialAccount]]:
        user = await self.repo.get_by_auth_user_id(auth_user_id)
        accounts = await self.social_repo.list_by_user_id(auth_user_id)
        if user is None:
            user = await self.repo.create_from_auth(auth_user_id, accounts)
            await self.session.commit()
        return user, accounts

    async def _apply_update(self, user: User, payload: UserUpdate) -> User:
        update_data = payload.model_dump(exclude_unset=True)
        if not update_data:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="No changes provided",
            )
        phone_value = update_data.get("phone_number")
        if phone_value is not None:
            normalized_phone = self._normalize_phone_number(phone_value)
            update_data["phone_number"] = normalized_phone

        updated = await self.repo.update_user(user, update_data)
        if "phone_number" in update_data:
            await self.repo.update_auth_user_phone(
                user.auth_user_id, update_data.get("phone_number")
            )
        await self.session.commit()
        return updated

    def _to_profile(
        self,
        user: User,
        accounts: Sequence[AuthUserSocialAccount],
        *,
        preferred_provider: str | None = None,
    ) -> UserProfile:
        account = self._select_social_account(accounts, preferred_provider)
        username = self._resolve_username(user, account)
        nickname = self._resolve_nickname(user, account, username)
        provider = account.provider if account else (preferred_provider or "unknown")
        return UserProfile(
            username=username,
            nickname=nickname,
            phone_number=self._format_phone_number(user.phone_number),
            provider=provider,
            last_login_at=account.last_login_at if account else None,
        )

    @staticmethod
    def _select_social_account(
        accounts: Sequence[AuthUserSocialAccount],
        preferred_provider: str | None,
    ) -> AuthUserSocialAccount | None:
        if not accounts:
            return None
        if preferred_provider:
            for account in accounts:
                if account.provider == preferred_provider:
                    return account
        return accounts[0]

    @staticmethod
    def _resolve_username(user: User, account: AuthUserSocialAccount | None) -> str:
        candidates = [
            getattr(user, "name", None),
            user.username,
        ]
        for raw in candidates:
            value = MyService._clean_text(raw)
            if value:
                return value
        return "사용자"

    @staticmethod
    def _resolve_nickname(
        user: User,
        account: AuthUserSocialAccount | None,
        fallback: str,
    ) -> str:
        candidates = [
            getattr(user, "nickname", None),
            user.username,
            getattr(user, "name", None),
            fallback,
        ]
        for raw in candidates:
            value = MyService._clean_text(raw)
            if value:
                return value
        return fallback

    @staticmethod
    def _clean_text(value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        return stripped or None

    @staticmethod
    def _format_phone_number(value: str | None) -> str | None:
        if not value:
            return None

        digits = re.sub(r"\D+", "", value)
        if digits.startswith("82") and len(digits) >= 11:
            digits = "0" + digits[2:]

        if len(digits) == 11 and digits.startswith("010"):
            return f"{digits[:3]}-{digits[3:7]}-{digits[7:]}"
        if len(digits) == 10:
            return f"{digits[:3]}-{digits[3:6]}-{digits[6:]}"

        return value

    @staticmethod
    def _normalize_phone_number(value: str) -> str:
        digits = re.sub(r"\D+", "", value or "")
        if digits.startswith("82") and len(digits) >= 11:
            digits = "0" + digits[2:]

        if len(digits) == 11 and digits.startswith("010"):
            return f"{digits[:3]}-{digits[3:7]}-{digits[7:]}"
        if len(digits) == 10 and digits.startswith("01"):
            return f"{digits[:3]}-{digits[3:6]}-{digits[6:]}"

        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Invalid phone number format",
        )
