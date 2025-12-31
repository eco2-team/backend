"""Dependency injection setup."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from apps.users.application.commands import DeleteUserInteractor, UpdateProfileInteractor
from apps.users.application.common.services import ProfileBuilder
from apps.users.application.queries import (
    CheckCharacterOwnershipQuery,
    GetCharactersQuery,
    GetProfileQuery,
)
from apps.users.domain.services import UserService
from apps.users.infrastructure.persistence_postgres.adapters import (
    SqlaSocialAccountQueryGateway,
    SqlaTransactionManager,
    SqlaUserCharacterQueryGateway,
    SqlaUserCommandGateway,
    SqlaUserQueryGateway,
)
from apps.users.infrastructure.persistence_postgres.session import get_db_session

# Type alias for dependency injection
SessionDep = Annotated[AsyncSession, Depends(get_db_session)]


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
        user_query_gateway=SqlaUserQueryGateway(session),
        user_command_gateway=SqlaUserCommandGateway(session),
        social_account_gateway=SqlaSocialAccountQueryGateway(session),
        profile_builder=profile_builder,
    )


def get_get_characters_query(session: SessionDep) -> GetCharactersQuery:
    """GetCharactersQuery 인스턴스를 반환합니다."""
    return GetCharactersQuery(
        character_gateway=SqlaUserCharacterQueryGateway(session),
    )


def get_check_character_ownership_query(
    session: SessionDep,
) -> CheckCharacterOwnershipQuery:
    """CheckCharacterOwnershipQuery 인스턴스를 반환합니다."""
    return CheckCharacterOwnershipQuery(
        character_gateway=SqlaUserCharacterQueryGateway(session),
    )


# Commands
def get_update_profile_interactor(
    session: SessionDep,
    user_service: UserService = Depends(get_user_service),
    profile_builder: ProfileBuilder = Depends(get_profile_builder),
) -> UpdateProfileInteractor:
    """UpdateProfileInteractor 인스턴스를 반환합니다."""
    return UpdateProfileInteractor(
        user_query_gateway=SqlaUserQueryGateway(session),
        user_command_gateway=SqlaUserCommandGateway(session),
        social_account_gateway=SqlaSocialAccountQueryGateway(session),
        transaction_manager=SqlaTransactionManager(session),
        user_service=user_service,
        profile_builder=profile_builder,
    )


def get_delete_user_interactor(session: SessionDep) -> DeleteUserInteractor:
    """DeleteUserInteractor 인스턴스를 반환합니다."""
    return DeleteUserInteractor(
        user_query_gateway=SqlaUserQueryGateway(session),
        user_command_gateway=SqlaUserCommandGateway(session),
        transaction_manager=SqlaTransactionManager(session),
    )
