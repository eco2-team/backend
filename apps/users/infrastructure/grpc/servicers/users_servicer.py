"""UsersService gRPC Servicer.

OAuth 콜백에서 auth 도메인이 호출하는 사용자 관련 gRPC 서비스입니다.

통합 스키마 사용:
    - users.accounts
    - users.social_accounts

참고: https://rooftopsnow.tistory.com/127
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

import grpc

from apps.users.domain.entities.user import User
from apps.users.infrastructure.grpc import users_pb2, users_pb2_grpc
from apps.users.infrastructure.persistence_postgres.mappings.user_social_account import (
    UserSocialAccount,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


class UsersServicer(users_pb2_grpc.UsersServiceServicer):
    """Users gRPC Service 구현.

    users.accounts, users.social_accounts 테이블에 접근합니다.
    """

    def __init__(self, session_factory) -> None:
        """
        Args:
            session_factory: AsyncSession 팩토리 함수
        """
        self._session_factory = session_factory

    async def GetOrCreateFromOAuth(
        self,
        request: users_pb2.GetOrCreateFromOAuthRequest,
        context: grpc.aio.ServicerContext,
    ) -> users_pb2.GetOrCreateFromOAuthResponse:
        """OAuth 프로필로 사용자 조회 또는 생성."""
        try:
            async with self._session_factory() as session:
                # 1. 기존 사용자 조회 (provider + provider_user_id로)
                existing = await self._get_user_by_provider(
                    session,
                    request.provider,
                    request.provider_user_id,
                )

                if existing:
                    user, social_account = existing
                    logger.info(
                        "Found existing user via OAuth",
                        extra={
                            "user_id": str(user.id),
                            "provider": request.provider,
                        },
                    )
                    return users_pb2.GetOrCreateFromOAuthResponse(
                        user=self._user_to_proto(user),
                        social_account=self._social_account_to_proto(social_account),
                        is_new_user=False,
                    )

                # 2. 새 사용자 생성
                user, social_account = await self._create_user_from_oauth(
                    session,
                    provider=request.provider,
                    provider_user_id=request.provider_user_id,
                    email=request.email if request.HasField("email") else None,
                    nickname=request.nickname if request.HasField("nickname") else None,
                    profile_image_url=(
                        request.profile_image_url if request.HasField("profile_image_url") else None
                    ),
                )

                await session.commit()

                logger.info(
                    "Created new user via OAuth",
                    extra={
                        "user_id": str(user.id),
                        "provider": request.provider,
                    },
                )

                return users_pb2.GetOrCreateFromOAuthResponse(
                    user=self._user_to_proto(user),
                    social_account=self._social_account_to_proto(social_account),
                    is_new_user=True,
                )

        except ValueError as e:
            logger.error("Invalid argument in GetOrCreateFromOAuth", extra={"error": str(e)})
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, str(e))
        except Exception:
            logger.exception("Internal error in GetOrCreateFromOAuth")
            await context.abort(grpc.StatusCode.INTERNAL, "Internal server error")

    async def GetUser(
        self,
        request: users_pb2.GetUserRequest,
        context: grpc.aio.ServicerContext,
    ) -> users_pb2.GetUserResponse:
        """사용자 ID로 조회."""
        try:
            user_id = UUID(request.user_id)

            async with self._session_factory() as session:
                user = await self._get_user_by_id(session, user_id)

                if user is None:
                    return users_pb2.GetUserResponse()

                return users_pb2.GetUserResponse(user=self._user_to_proto(user))

        except ValueError as e:
            logger.error("Invalid user_id format", extra={"error": str(e)})
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, str(e))
        except Exception:
            logger.exception("Internal error in GetUser")
            await context.abort(grpc.StatusCode.INTERNAL, "Internal server error")

    async def UpdateLoginTime(
        self,
        request: users_pb2.UpdateLoginTimeRequest,
        context: grpc.aio.ServicerContext,
    ) -> users_pb2.UpdateLoginTimeResponse:
        """로그인 시간 업데이트."""
        try:
            user_id = UUID(request.user_id)

            async with self._session_factory() as session:
                success = await self._update_login_time(
                    session,
                    user_id=user_id,
                    provider=request.provider,
                    provider_user_id=request.provider_user_id,
                )
                await session.commit()

                return users_pb2.UpdateLoginTimeResponse(success=success)

        except ValueError as e:
            logger.error("Invalid argument in UpdateLoginTime", extra={"error": str(e)})
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, str(e))
        except Exception:
            logger.exception("Internal error in UpdateLoginTime")
            await context.abort(grpc.StatusCode.INTERNAL, "Internal server error")

    # =========================================================================
    # Private Methods - DB Operations (users 스키마 사용)
    # =========================================================================

    async def _get_user_by_provider(
        self,
        session: "AsyncSession",
        provider: str,
        provider_user_id: str,
    ) -> tuple[User, UserSocialAccount] | None:
        """Provider 정보로 사용자 조회."""
        from sqlalchemy import select

        from apps.users.infrastructure.persistence_postgres.mappings.user import accounts_table
        from apps.users.infrastructure.persistence_postgres.mappings.user_social_account import (
            social_accounts_table,
        )

        # 소셜 계정으로 사용자 조회
        stmt = (
            select(
                accounts_table,
                social_accounts_table,
            )
            .select_from(accounts_table)
            .join(
                social_accounts_table,
                accounts_table.c.id == social_accounts_table.c.user_id,
            )
            .where(
                social_accounts_table.c.provider == provider,
                social_accounts_table.c.provider_user_id == provider_user_id,
            )
        )

        result = await session.execute(stmt)
        row = result.first()

        if row is None:
            return None

        # Row를 User와 UserSocialAccount로 변환
        user = User(
            id=row.id,
            nickname=row.nickname,
            name=row.name,
            email=row.email,
            phone_number=row.phone_number,
            profile_image_url=row.profile_image_url,
            created_at=row.created_at,
            updated_at=row.updated_at,
            last_login_at=row.last_login_at,
        )

        social_account = UserSocialAccount(
            id=row[social_accounts_table.c.id],
            user_id=row[social_accounts_table.c.user_id],
            provider=row[social_accounts_table.c.provider],
            provider_user_id=row[social_accounts_table.c.provider_user_id],
            email=row[social_accounts_table.c.email],
            last_login_at=row[social_accounts_table.c.last_login_at],
            created_at=row[social_accounts_table.c.created_at],
            updated_at=row[social_accounts_table.c.updated_at],
        )

        return user, social_account

    async def _get_user_by_id(self, session: "AsyncSession", user_id: UUID) -> User | None:
        """ID로 사용자 조회."""
        from sqlalchemy import select

        from apps.users.infrastructure.persistence_postgres.mappings.user import accounts_table

        stmt = select(accounts_table).where(accounts_table.c.id == user_id)
        result = await session.execute(stmt)
        row = result.first()

        if row is None:
            return None

        return User(
            id=row.id,
            nickname=row.nickname,
            name=row.name,
            email=row.email,
            phone_number=row.phone_number,
            profile_image_url=row.profile_image_url,
            created_at=row.created_at,
            updated_at=row.updated_at,
            last_login_at=row.last_login_at,
        )

    async def _create_user_from_oauth(
        self,
        session: "AsyncSession",
        *,
        provider: str,
        provider_user_id: str,
        email: str | None,
        nickname: str | None,
        profile_image_url: str | None,
    ) -> tuple[User, UserSocialAccount]:
        """OAuth 프로필로 새 사용자 생성."""
        from sqlalchemy import insert

        from apps.users.infrastructure.persistence_postgres.mappings.user import accounts_table
        from apps.users.infrastructure.persistence_postgres.mappings.user_social_account import (
            social_accounts_table,
        )

        now = datetime.now(timezone.utc)
        user_id = uuid4()

        # User 생성
        user_values = {
            "id": user_id,
            "nickname": nickname,
            "name": None,
            "email": email,
            "phone_number": None,
            "profile_image_url": profile_image_url,
            "created_at": now,
            "updated_at": now,
            "last_login_at": now,
        }
        await session.execute(insert(accounts_table).values(**user_values))

        # SocialAccount 생성
        social_account_id = uuid4()
        social_values = {
            "id": social_account_id,
            "user_id": user_id,
            "provider": provider,
            "provider_user_id": provider_user_id,
            "email": email,
            "last_login_at": now,
            "created_at": now,
            "updated_at": now,
        }
        await session.execute(insert(social_accounts_table).values(**social_values))

        user = User(
            id=user_id,
            nickname=nickname,
            name=None,
            email=email,
            phone_number=None,
            profile_image_url=profile_image_url,
            created_at=now,
            updated_at=now,
            last_login_at=now,
        )

        social_account = UserSocialAccount(
            id=social_account_id,
            user_id=user_id,
            provider=provider,
            provider_user_id=provider_user_id,
            email=email,
            last_login_at=now,
            created_at=now,
            updated_at=now,
        )

        return user, social_account

    async def _update_login_time(
        self,
        session: "AsyncSession",
        *,
        user_id: UUID,
        provider: str,
        provider_user_id: str,
    ) -> bool:
        """로그인 시간 업데이트."""
        from sqlalchemy import update

        from apps.users.infrastructure.persistence_postgres.mappings.user import accounts_table
        from apps.users.infrastructure.persistence_postgres.mappings.user_social_account import (
            social_accounts_table,
        )

        now = datetime.now(timezone.utc)

        # User last_login_at 업데이트
        await session.execute(
            update(accounts_table)
            .where(accounts_table.c.id == user_id)
            .values(last_login_at=now, updated_at=now)
        )

        # SocialAccount last_login_at 업데이트
        await session.execute(
            update(social_accounts_table)
            .where(
                social_accounts_table.c.user_id == user_id,
                social_accounts_table.c.provider == provider,
                social_accounts_table.c.provider_user_id == provider_user_id,
            )
            .values(last_login_at=now, updated_at=now)
        )

        return True

    # =========================================================================
    # Private Methods - Protobuf Conversion
    # =========================================================================

    def _user_to_proto(self, user: User) -> users_pb2.UserInfo:
        """User → UserInfo protobuf."""
        return users_pb2.UserInfo(
            id=str(user.id),
            nickname=user.nickname or "",
            profile_image_url=user.profile_image_url or "",
            phone_number=user.phone_number or "",
            created_at=user.created_at.isoformat() if user.created_at else "",
            updated_at=user.updated_at.isoformat() if user.updated_at else "",
            last_login_at=user.last_login_at.isoformat() if user.last_login_at else "",
        )

    def _social_account_to_proto(
        self,
        account: UserSocialAccount,
    ) -> users_pb2.SocialAccountInfo:
        """UserSocialAccount → SocialAccountInfo protobuf."""
        return users_pb2.SocialAccountInfo(
            id=str(account.id),
            user_id=str(account.user_id),
            provider=account.provider,
            provider_user_id=account.provider_user_id,
            email=account.email or "",
            created_at=account.created_at.isoformat() if account.created_at else "",
            last_login_at=account.last_login_at.isoformat() if account.last_login_at else "",
        )
