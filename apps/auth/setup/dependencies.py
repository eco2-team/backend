"""Dependency Injection Setup.

FastAPI Depends를 사용한 의존성 주입 설정입니다.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, AsyncGenerator

from fastapi import Depends

from apps.auth.setup.config import Settings, get_settings

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession
    import redis.asyncio as aioredis


# ============================================================
# Infrastructure Dependencies
# ============================================================


async def get_db_session() -> AsyncGenerator["AsyncSession", None]:
    """DB 세션 제공자."""
    from apps.auth.infrastructure.persistence_postgres.session import get_async_session

    async for session in get_async_session():
        yield session


def get_blacklist_redis() -> "aioredis.Redis":
    """토큰 블랙리스트용 Redis 클라이언트 제공자."""
    from apps.auth.infrastructure.persistence_redis.client import get_blacklist_redis

    return get_blacklist_redis()


def get_oauth_state_redis() -> "aioredis.Redis":
    """OAuth 상태 저장용 Redis 클라이언트 제공자."""
    from apps.auth.infrastructure.persistence_redis.client import get_oauth_state_redis

    return get_oauth_state_redis()


# ============================================================
# Gateway Dependencies (Adapters)
# ============================================================


async def get_user_command_gateway(
    session: "AsyncSession" = Depends(get_db_session),
):
    """UserCommandGateway 제공자."""
    from apps.auth.infrastructure.adapters import SqlaUserDataMapper

    return SqlaUserDataMapper(session)


async def get_user_query_gateway(
    session: "AsyncSession" = Depends(get_db_session),
):
    """UserQueryGateway 제공자."""
    from apps.auth.infrastructure.adapters import SqlaUserReader

    return SqlaUserReader(session)


async def get_social_account_gateway(
    session: "AsyncSession" = Depends(get_db_session),
):
    """SocialAccountGateway 제공자."""
    from apps.auth.infrastructure.adapters import SqlaSocialAccountMapper

    return SqlaSocialAccountMapper(session)


async def get_login_audit_gateway(
    session: "AsyncSession" = Depends(get_db_session),
):
    """LoginAuditGateway 제공자."""
    from apps.auth.infrastructure.adapters import SqlaLoginAuditMapper

    return SqlaLoginAuditMapper(session)


async def get_flusher(
    session: "AsyncSession" = Depends(get_db_session),
):
    """Flusher 제공자."""
    from apps.auth.infrastructure.adapters import SqlaFlusher

    return SqlaFlusher(session)


async def get_transaction_manager(
    session: "AsyncSession" = Depends(get_db_session),
):
    """TransactionManager 제공자."""
    from apps.auth.infrastructure.adapters import SqlaTransactionManager

    return SqlaTransactionManager(session)


# ============================================================
# Auth Domain - Redis Gateway Dependencies
# ============================================================


def get_oauth_state_store(
    redis: "aioredis.Redis" = Depends(get_oauth_state_redis),
):
    """OAuthStateStore 제공자 (OAuth 상태용 Redis)."""
    from apps.auth.infrastructure.persistence_redis import RedisStateStore

    return RedisStateStore(redis)


def get_token_blacklist_store(
    redis: "aioredis.Redis" = Depends(get_blacklist_redis),
):
    """TokenBlacklistStore 제공자 (블랙리스트용 Redis)."""
    from apps.auth.infrastructure.persistence_redis import RedisTokenBlacklist

    return RedisTokenBlacklist(redis)


def get_user_token_store(
    redis: "aioredis.Redis" = Depends(get_blacklist_redis),
):
    """UserTokenStore 제공자 (블랙리스트용 Redis)."""
    from apps.auth.infrastructure.persistence_redis import RedisUserTokenStore

    return RedisUserTokenStore(redis)


# Deprecated aliases
get_state_store = get_oauth_state_store
get_token_blacklist = get_token_blacklist_store


# ============================================================
# Auth Domain - Token & OAuth Dependencies
# ============================================================


def get_token_issuer(settings: Settings = Depends(get_settings)):
    """TokenIssuer 제공자."""
    from apps.auth.infrastructure.security import JwtTokenService

    return JwtTokenService(
        secret_key=settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
        issuer=settings.jwt_issuer,
        audience=settings.jwt_audience,
        access_token_expire_minutes=settings.access_token_exp_minutes,
        refresh_token_expire_minutes=settings.refresh_token_exp_minutes,
    )


def get_oauth_provider_registry(settings: Settings = Depends(get_settings)):
    """OAuth ProviderRegistry 제공자."""
    from apps.auth.infrastructure.oauth import ProviderRegistry

    return ProviderRegistry(settings)


def get_oauth_provider_gateway(registry=Depends(get_oauth_provider_registry)):
    """OAuthProviderGateway 제공자."""
    from apps.auth.infrastructure.oauth import OAuthClientImpl

    return OAuthClientImpl(registry)


# Deprecated aliases
get_token_service = get_token_issuer
get_oauth_client = get_oauth_provider_gateway


# ============================================================
# User Domain - User Gateway Dependencies
# ============================================================


def get_user_id_generator():
    """UserIdGenerator 제공자."""
    from apps.auth.infrastructure.adapters import UuidUserIdGenerator

    return UuidUserIdGenerator()


def get_user_service(
    user_id_generator=Depends(get_user_id_generator),
):
    """UserService 제공자 (deprecated - use UserManagementGateway)."""
    from apps.auth.domain.services import UserService

    return UserService(user_id_generator)


def get_user_management_gateway(settings: Settings = Depends(get_settings)):
    """UserManagementGateway 제공자 (gRPC 클라이언트).

    users 도메인과 gRPC 통신을 위한 어댑터입니다.
    """
    from apps.auth.infrastructure.grpc.users_client import UsersGrpcClient
    from apps.auth.infrastructure.grpc.user_management_adapter import (
        UserManagementGrpcAdapter,
    )

    client = UsersGrpcClient(settings)
    return UserManagementGrpcAdapter(client)


# Deprecated alias
get_user_management_service = get_user_management_gateway


# ============================================================
# Use Case Dependencies
# ============================================================


async def get_oauth_authorize_interactor(
    state_store=Depends(get_state_store),
    oauth_client=Depends(get_oauth_client),
):
    """OAuthAuthorizeInteractor 제공자."""
    from apps.auth.application.commands import OAuthAuthorizeInteractor

    return OAuthAuthorizeInteractor(
        state_store=state_store,
        oauth_client=oauth_client,
    )


async def get_oauth_callback_interactor(
    user_management=Depends(get_user_management_gateway),
    login_audit_gateway=Depends(get_login_audit_gateway),
    token_issuer=Depends(get_token_issuer),
    oauth_state_store=Depends(get_oauth_state_store),
    user_token_store=Depends(get_user_token_store),
    oauth_provider=Depends(get_oauth_provider_gateway),
    flusher=Depends(get_flusher),
    transaction_manager=Depends(get_transaction_manager),
):
    """OAuthCallbackInteractor 제공자.

    Phase 1: gRPC를 통해 users 도메인과 통신합니다.
    - UserManagementGateway (gRPC 어댑터)를 사용
    """
    from apps.auth.application.commands import OAuthCallbackInteractor

    return OAuthCallbackInteractor(
        user_management=user_management,
        login_audit_gateway=login_audit_gateway,
        token_issuer=token_issuer,
        oauth_state_store=oauth_state_store,
        user_token_store=user_token_store,
        oauth_provider=oauth_provider,
        flusher=flusher,
        transaction_manager=transaction_manager,
    )


async def get_logout_interactor(
    token_service=Depends(get_token_service),
    blacklist_publisher=Depends(get_blacklist_event_publisher),
    user_token_store=Depends(get_user_token_store),
    transaction_manager=Depends(get_transaction_manager),
):
    """LogoutInteractor 제공자."""
    from apps.auth.application.commands import LogoutInteractor

    return LogoutInteractor(
        token_service=token_service,
        blacklist_publisher=blacklist_publisher,
        user_token_store=user_token_store,
        transaction_manager=transaction_manager,
    )


async def get_refresh_tokens_interactor(
    token_service=Depends(get_token_service),
    token_blacklist=Depends(get_token_blacklist),
    blacklist_publisher=Depends(get_blacklist_event_publisher),
    user_token_store=Depends(get_user_token_store),
    user_query_gateway=Depends(get_user_query_gateway),
    transaction_manager=Depends(get_transaction_manager),
):
    """RefreshTokensInteractor 제공자."""
    from apps.auth.application.commands import RefreshTokensInteractor

    return RefreshTokensInteractor(
        token_service=token_service,
        token_blacklist=token_blacklist,
        blacklist_publisher=blacklist_publisher,
        user_token_store=user_token_store,
        user_query_gateway=user_query_gateway,
        transaction_manager=transaction_manager,
    )


async def get_validate_token_service(
    token_service=Depends(get_token_service),
    token_blacklist=Depends(get_token_blacklist),
    user_query_gateway=Depends(get_user_query_gateway),
):
    """ValidateTokenQueryService 제공자."""
    from apps.auth.application.queries import ValidateTokenQueryService

    return ValidateTokenQueryService(
        token_service=token_service,
        token_blacklist=token_blacklist,
        user_query_gateway=user_query_gateway,
    )
