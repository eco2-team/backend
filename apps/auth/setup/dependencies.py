"""Dependency Injection Setup.

FastAPI Depends를 사용한 의존성 주입 설정입니다.

Architecture:
    - Infrastructure Dependencies: DB, Redis, RabbitMQ
    - Gateway Dependencies: SQLAlchemy/Redis Adapters
    - Service Dependencies: Application Services (연주자)
    - Use Case Dependencies: Interactors (지휘자)
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
# Gateway Dependencies (Adapters / Ports 구현체)
# ============================================================


async def get_users_command_gateway(
    session: "AsyncSession" = Depends(get_db_session),
):
    """UsersCommandGateway 제공자."""
    from apps.auth.infrastructure.persistence_postgres.adapters import SqlaUsersCommandGateway

    return SqlaUsersCommandGateway(session)


async def get_users_query_gateway(
    session: "AsyncSession" = Depends(get_db_session),
):
    """UsersQueryGateway 제공자."""
    from apps.auth.infrastructure.persistence_postgres.adapters import SqlaUsersQueryGateway

    return SqlaUsersQueryGateway(session)


async def get_social_account_gateway(
    session: "AsyncSession" = Depends(get_db_session),
):
    """SocialAccountQueryGateway 제공자."""
    from apps.auth.infrastructure.persistence_postgres.adapters import (
        SqlaSocialAccountQueryGateway,
    )

    return SqlaSocialAccountQueryGateway(session)


async def get_login_audit_gateway(
    session: "AsyncSession" = Depends(get_db_session),
):
    """LoginAuditGateway 제공자."""
    from apps.auth.infrastructure.persistence_postgres.adapters import SqlaLoginAuditGateway

    return SqlaLoginAuditGateway(session)


async def get_flusher(
    session: "AsyncSession" = Depends(get_db_session),
):
    """Flusher 제공자."""
    from apps.auth.infrastructure.persistence_postgres.adapters import SqlaFlusher

    return SqlaFlusher(session)


async def get_transaction_manager(
    session: "AsyncSession" = Depends(get_db_session),
):
    """TransactionManager 제공자."""
    from apps.auth.infrastructure.persistence_postgres.adapters import SqlaTransactionManager

    return SqlaTransactionManager(session)


# Deprecated aliases for backward compatibility
get_user_command_gateway = get_users_command_gateway
get_user_query_gateway = get_users_query_gateway


# ============================================================
# OAuth Domain - Redis Gateway Dependencies
# ============================================================


def get_oauth_state_store(
    redis: "aioredis.Redis" = Depends(get_oauth_state_redis),
):
    """OAuthStateStore 제공자 (OAuth 상태용 Redis)."""
    from apps.auth.infrastructure.persistence_redis import RedisStateStore

    return RedisStateStore(redis)


# ============================================================
# Token Domain - Redis Gateway Dependencies
# ============================================================


def get_token_blacklist_store(
    redis: "aioredis.Redis" = Depends(get_blacklist_redis),
):
    """TokenBlacklistStore 제공자 (블랙리스트용 Redis)."""
    from apps.auth.infrastructure.persistence_redis import RedisTokenBlacklist

    return RedisTokenBlacklist(redis)


def get_token_session_store(
    redis: "aioredis.Redis" = Depends(get_blacklist_redis),
):
    """TokenSessionStore 제공자 (블랙리스트용 Redis)."""
    from apps.auth.infrastructure.persistence_redis import RedisUsersTokenStore

    return RedisUsersTokenStore(redis)


# Deprecated aliases
get_state_store = get_oauth_state_store
get_token_blacklist = get_token_blacklist_store
get_user_token_store = get_token_session_store


# ============================================================
# Auth Domain - Messaging Dependencies
# ============================================================


_blacklist_event_publisher = None


async def get_blacklist_event_publisher(settings: Settings = Depends(get_settings)):
    """BlacklistEventPublisher 제공자 (RabbitMQ).

    Note:
        Singleton 패턴으로 연결을 재사용합니다.
        AMQP_URL이 설정되지 않은 경우 None을 반환합니다.
    """
    global _blacklist_event_publisher

    if settings.amqp_url is None:
        # AMQP 미설정 시 None 반환 (로컬 개발 환경 등)
        return None

    if _blacklist_event_publisher is None:
        from apps.auth.infrastructure.messaging import RabbitMQBlacklistEventPublisher

        _blacklist_event_publisher = RabbitMQBlacklistEventPublisher(settings.amqp_url)
        await _blacklist_event_publisher.connect()

    return _blacklist_event_publisher


# ============================================================
# Token Domain - Token Issuer
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


# ============================================================
# OAuth Domain - OAuth Provider
# ============================================================


def get_oauth_provider_registry(settings: Settings = Depends(get_settings)):
    """OAuth ProviderRegistry 제공자."""
    from apps.auth.infrastructure.oauth import ProviderRegistry

    return ProviderRegistry(settings)


def get_oauth_provider_gateway(
    registry=Depends(get_oauth_provider_registry),
    settings: Settings = Depends(get_settings),
):
    """OAuthProviderGateway 제공자."""
    from apps.auth.infrastructure.oauth import OAuthClientImpl

    return OAuthClientImpl(registry, timeout_seconds=settings.oauth_client_timeout_seconds)


# ============================================================
# User Domain - User Gateway Dependencies
# ============================================================


def get_users_id_generator():
    """UsersIdGenerator 제공자."""
    from apps.auth.infrastructure.common.adapters import UuidUsersIdGenerator

    return UuidUsersIdGenerator()


# Deprecated alias
get_user_id_generator = get_users_id_generator


def get_user_service(
    user_id_generator=Depends(get_users_id_generator),
):
    """UserService 제공자 (deprecated - use UsersManagementGateway)."""
    from apps.auth.domain.services import UserService

    return UserService(user_id_generator)


def get_users_management_gateway(settings: Settings = Depends(get_settings)):
    """UsersManagementGateway 제공자 (gRPC 클라이언트).

    users 도메인과 gRPC 통신을 위한 어댑터입니다.
    """
    from apps.auth.infrastructure.grpc.client import UsersGrpcClient
    from apps.auth.infrastructure.grpc.adapters import UsersManagementGatewayGrpc

    client = UsersGrpcClient(settings)
    return UsersManagementGatewayGrpc(client)


# Deprecated alias
get_user_management_gateway = get_users_management_gateway


# ============================================================
# Application Services (연주자 🎻)
# ============================================================


def get_oauth_flow_service(
    state_store=Depends(get_oauth_state_store),
    provider_gateway=Depends(get_oauth_provider_gateway),
):
    """OAuthFlowService 제공자.

    OAuth 인증 플로우 관련 비즈니스 로직을 캡슐화합니다.
    """
    from apps.auth.application.oauth.services import OAuthFlowService

    return OAuthFlowService(
        state_store=state_store,
        provider_gateway=provider_gateway,
    )


def get_token_service(
    issuer=Depends(get_token_issuer),
    session_store=Depends(get_token_session_store),
    blacklist_store=Depends(get_token_blacklist_store),
):
    """TokenService 제공자.

    토큰 발급 및 세션 관리 비즈니스 로직을 캡슐화합니다.
    """
    from apps.auth.application.token.services import TokenService

    return TokenService(
        issuer=issuer,
        session_store=session_store,
        blacklist_store=blacklist_store,
    )


def get_login_audit_service():
    """LoginAuditService 제공자.

    로그인 감사 엔티티 팩토리입니다 (순수 로직, Port 없음).
    """
    from apps.auth.application.audit.services import LoginAuditService

    return LoginAuditService()


# ============================================================
# Use Case Dependencies (지휘자 🎼)
# ============================================================


async def get_oauth_authorize_interactor(
    oauth_service=Depends(get_oauth_flow_service),
):
    """OAuthAuthorizeInteractor 제공자.

    OAuth 인증 URL 생성 유스케이스입니다.
    """
    from apps.auth.application.oauth.commands import OAuthAuthorizeInteractor

    return OAuthAuthorizeInteractor(oauth_service=oauth_service)


async def get_oauth_callback_interactor(
    # Services (연주자)
    oauth_service=Depends(get_oauth_flow_service),
    token_service=Depends(get_token_service),
    audit_service=Depends(get_login_audit_service),
    # Ports (인프라)
    user_management=Depends(get_users_management_gateway),
    audit_gateway=Depends(get_login_audit_gateway),
    flusher=Depends(get_flusher),
    transaction_manager=Depends(get_transaction_manager),
):
    """OAuthCallbackInteractor 제공자.

    OAuth 콜백 처리 유스케이스입니다.
    gRPC를 통해 users 도메인과 통신합니다.
    """
    from apps.auth.application.oauth.commands import OAuthCallbackInteractor

    return OAuthCallbackInteractor(
        oauth_service=oauth_service,
        token_service=token_service,
        audit_service=audit_service,
        user_management=user_management,
        audit_gateway=audit_gateway,
        flusher=flusher,
        transaction_manager=transaction_manager,
    )


async def get_logout_interactor(
    # Services (연주자)
    token_service=Depends(get_token_service),
    # Ports (인프라)
    blacklist_publisher=Depends(get_blacklist_event_publisher),
    transaction_manager=Depends(get_transaction_manager),
):
    """LogoutInteractor 제공자.

    로그아웃 유스케이스입니다.
    """
    from apps.auth.application.token.commands import LogoutInteractor

    return LogoutInteractor(
        token_service=token_service,
        blacklist_publisher=blacklist_publisher,
        transaction_manager=transaction_manager,
    )


async def get_refresh_tokens_interactor(
    # Services (연주자)
    token_service=Depends(get_token_service),
    # Ports (인프라)
    user_query_gateway=Depends(get_users_query_gateway),
    blacklist_publisher=Depends(get_blacklist_event_publisher),
    transaction_manager=Depends(get_transaction_manager),
):
    """RefreshTokensInteractor 제공자.

    토큰 갱신 유스케이스입니다.
    """
    from apps.auth.application.token.commands import RefreshTokensInteractor

    return RefreshTokensInteractor(
        token_service=token_service,
        user_query_gateway=user_query_gateway,
        blacklist_publisher=blacklist_publisher,
        transaction_manager=transaction_manager,
    )


async def get_validate_token_service(
    token_service=Depends(get_token_service),
    user_query_gateway=Depends(get_users_query_gateway),
):
    """ValidateTokenQueryService 제공자.

    토큰 검증 쿼리 서비스입니다.
    """
    from apps.auth.application.token.queries import ValidateTokenQueryService

    return ValidateTokenQueryService(
        token_service=token_service,
        user_query_gateway=user_query_gateway,
    )
