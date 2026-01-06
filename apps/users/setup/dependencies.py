"""Dependency injection setup."""

from __future__ import annotations

from functools import lru_cache
from typing import Annotated

from celery import Celery
from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

# Character domain
from apps.users.application.character.ports import DefaultCharacterPublisher
from apps.users.application.character.queries import (
    CheckCharacterOwnershipQuery,
    GetCharactersQuery,
)

# Identity domain (gRPC)
from apps.users.application.identity.commands import (
    GetOrCreateFromOAuthCommand,
    UpdateLoginTimeCommand,
)
from apps.users.application.identity.queries import GetUserQuery

# Profile domain
from apps.users.application.profile.commands import (
    DeleteUserInteractor,
    UpdateProfileInteractor,
)
from apps.users.application.profile.queries import GetProfileQuery
from apps.users.application.profile.services import ProfileBuilder
from apps.users.domain.services import UserService
from apps.users.infrastructure.messaging import CeleryDefaultCharacterPublisher
from apps.users.infrastructure.persistence_postgres.adapters import (
    SqlaIdentityCommandGateway,
    SqlaIdentityQueryGateway,
    SqlaSocialAccountQueryGateway,
    SqlaTransactionManager,
    SqlaUsersCharacterQueryGateway,
    SqlaUsersCommandGateway,
    SqlaUsersQueryGateway,
)
from apps.users.infrastructure.persistence_postgres.session import get_db_session
from apps.users.setup.config import get_settings

# Type alias for dependency injection
SessionDep = Annotated[AsyncSession, Depends(get_db_session)]


@lru_cache
def get_celery_app() -> Celery:
    """Celery 앱 인스턴스를 반환합니다."""
    settings = get_settings()
    return Celery(
        "users",
        broker=settings.celery_broker_url,
    )


def get_default_character_publisher() -> DefaultCharacterPublisher:
    """DefaultCharacterPublisher 인스턴스를 반환합니다."""
    return CeleryDefaultCharacterPublisher(get_celery_app())


# Domain Services
def get_user_service() -> UserService:
    """UserService 인스턴스를 반환합니다."""
    return UserService()


# Application Services
def get_profile_builder(
    user_service: UserService = Depends(get_user_service),
) -> ProfileBuilder:
    """ProfileBuilder 인스턴스를 반환합니다."""
    return ProfileBuilder(user_service)


# Queries
def get_get_profile_query(
    session: SessionDep,
    profile_builder: ProfileBuilder = Depends(get_profile_builder),
) -> GetProfileQuery:
    """GetProfileQuery 인스턴스를 반환합니다."""
    return GetProfileQuery(
        profile_gateway=SqlaUsersQueryGateway(session),
        social_account_gateway=SqlaSocialAccountQueryGateway(session),
        profile_builder=profile_builder,
    )


def get_get_characters_query(
    session: SessionDep,
    default_publisher: DefaultCharacterPublisher = Depends(get_default_character_publisher),
) -> GetCharactersQuery:
    """GetCharactersQuery 인스턴스를 반환합니다."""
    return GetCharactersQuery(
        character_gateway=SqlaUsersCharacterQueryGateway(session),
        default_publisher=default_publisher,
        settings=get_settings(),
    )


def get_check_character_ownership_query(
    session: SessionDep,
) -> CheckCharacterOwnershipQuery:
    """CheckCharacterOwnershipQuery 인스턴스를 반환합니다."""
    return CheckCharacterOwnershipQuery(
        character_gateway=SqlaUsersCharacterQueryGateway(session),
    )


# Commands
def get_update_profile_interactor(
    session: SessionDep,
    user_service: UserService = Depends(get_user_service),
    profile_builder: ProfileBuilder = Depends(get_profile_builder),
) -> UpdateProfileInteractor:
    """UpdateProfileInteractor 인스턴스를 반환합니다."""
    return UpdateProfileInteractor(
        profile_query=SqlaUsersQueryGateway(session),
        profile_command=SqlaUsersCommandGateway(session),
        social_account_gateway=SqlaSocialAccountQueryGateway(session),
        transaction_manager=SqlaTransactionManager(session),
        user_service=user_service,
        profile_builder=profile_builder,
    )


def get_delete_user_interactor(session: SessionDep) -> DeleteUserInteractor:
    """DeleteUserInteractor 인스턴스를 반환합니다."""
    return DeleteUserInteractor(
        profile_query=SqlaUsersQueryGateway(session),
        profile_command=SqlaUsersCommandGateway(session),
        transaction_manager=SqlaTransactionManager(session),
    )


# =========================================================================
# gRPC Server Factory Functions (Manual DI without FastAPI Depends)
# =========================================================================


class GrpcUseCaseFactory:
    """gRPC 서버용 UseCase 팩토리.

    gRPC 서버는 FastAPI Depends를 사용하지 않으므로,
    세션 팩토리를 통해 매 요청마다 UseCase를 생성합니다.
    """

    def __init__(self, session_factory) -> None:
        """
        Args:
            session_factory: async_sessionmaker 인스턴스
        """
        self._session_factory = session_factory

    def create_get_or_create_from_oauth_command(
        self,
        session: AsyncSession,
    ) -> GetOrCreateFromOAuthCommand:
        """GetOrCreateFromOAuthCommand 인스턴스를 생성합니다."""
        return GetOrCreateFromOAuthCommand(
            query_gateway=SqlaIdentityQueryGateway(session),
            command_gateway=SqlaIdentityCommandGateway(session),
            transaction_manager=SqlaTransactionManager(session),
        )

    def create_get_user_query(
        self,
        session: AsyncSession,
    ) -> GetUserQuery:
        """GetUserQuery 인스턴스를 생성합니다."""
        return GetUserQuery(
            query_gateway=SqlaUsersQueryGateway(session),
        )

    def create_update_login_time_command(
        self,
        session: AsyncSession,
    ) -> UpdateLoginTimeCommand:
        """UpdateLoginTimeCommand 인스턴스를 생성합니다."""
        return UpdateLoginTimeCommand(
            command_gateway=SqlaIdentityCommandGateway(session),
            transaction_manager=SqlaTransactionManager(session),
        )
