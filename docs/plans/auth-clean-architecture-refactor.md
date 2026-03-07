# Auth 도메인 Clean Architecture 리팩토링 계획

> 작성일: 2025-12-31
> 참조: `docs/foundations/16-fastapi-clean-example-analysis.md`

---

## 1. 개요

### 1.1 목표

현재 `domains/auth/` 구조를 Clean Architecture 원칙에 따라 `apps/auth/`로 리팩토링합니다.

### 1.2 주요 변경사항

| 항목 | 현재 | 목표 |
|------|------|------|
| 루트 경로 | `domains/auth/` | `apps/auth/` |
| 아키텍처 | 혼합된 레이어드 | Clean Architecture |
| 의존성 방향 | 양방향 | 단방향 (안쪽으로만) |
| ORM 결합 | Entity = ORM 모델 | Entity/ORM 분리 |

---

## 2. 현재 기능 분석

### 2.1 AuthService 메서드 → Use Case 매핑

| 현재 메서드 | 목표 Use Case | 타입 | 파일 |
|------------|--------------|------|------|
| `authorize()` | OAuthAuthorizeInteractor | Command | `commands/oauth_authorize.py` |
| `login_with_provider()` | OAuthCallbackInteractor | Command | `commands/oauth_callback.py` |
| `refresh_session()` | RefreshTokensInteractor | Command | `commands/refresh_tokens.py` |
| `logout()` | LogoutInteractor | Command | `commands/logout.py` |
| `get_current_user()` | ValidateTokenQueryService | Query | `queries/validate_token.py` |

### 2.2 현재 서비스 → 목표 위치

| 현재 서비스 | 목표 위치 | 역할 |
|------------|----------|------|
| `TokenService` | `application/common/ports/token_service.py` (Port) | 인터페이스 |
| `TokenService` | `infrastructure/security/jwt_token_service.py` (Adapter) | 구현체 |
| `OAuthStateStore` | `application/common/ports/state_store.py` (Port) | 인터페이스 |
| `OAuthStateStore` | `infrastructure/persistence_redis/state_store_redis.py` (Adapter) | 구현체 |
| `TokenBlacklist` | `application/common/ports/token_blacklist.py` (Port) | 인터페이스 |
| `TokenBlacklist` | `infrastructure/persistence_redis/token_blacklist_redis.py` (Adapter) | 구현체 |
| `UserTokenStore` | `application/common/ports/user_token_store.py` (Port) | 인터페이스 |
| `UserTokenStore` | `infrastructure/persistence_redis/user_token_store_redis.py` (Adapter) | 구현체 |
| `ProviderRegistry` | `infrastructure/oauth/registry.py` | OAuth 프로바이더 관리 |

### 2.3 현재 Repository → 목표 Gateway

| 현재 Repository | 목표 Port | 목표 Adapter |
|----------------|----------|-------------|
| `UserRepository` | `UserCommandGateway` | `user_data_mapper_sqla.py` |
| `UserRepository` | `UserQueryGateway` | `user_reader_sqla.py` |
| `LoginAuditRepository` | `LoginAuditGateway` | `login_audit_mapper_sqla.py` |

---

## 3. 목표 폴더 구조

```
apps/auth/
│
├── domain/                                    # 🔵 Domain Layer (순수 Python)
│   ├── __init__.py
│   │
│   ├── entities/
│   │   ├── __init__.py
│   │   ├── base.py                            # Entity[T] 베이스
│   │   ├── user.py                            # User 엔티티
│   │   ├── user_social_account.py             # UserSocialAccount
│   │   └── login_audit.py                     # LoginAudit
│   │
│   ├── value_objects/
│   │   ├── __init__.py
│   │   ├── base.py                            # ValueObject 베이스
│   │   ├── user_id.py                         # UserId
│   │   ├── email.py                           # Email
│   │   ├── provider_user_id.py                # ProviderUserId
│   │   └── token_payload.py                   # TokenPayload
│   │
│   ├── enums/
│   │   ├── __init__.py
│   │   ├── oauth_provider.py                  # OAuthProvider
│   │   └── token_type.py                      # TokenType
│   │
│   ├── ports/
│   │   ├── __init__.py
│   │   ├── token_generator.py                 # TokenGenerator Protocol
│   │   └── user_id_generator.py               # UserIdGenerator Protocol
│   │
│   ├── services/
│   │   ├── __init__.py
│   │   └── user_service.py                    # 사용자 생성, 소셜 계정 연동
│   │
│   └── exceptions/
│       ├── __init__.py
│       ├── base.py                            # DomainError
│       ├── user.py                            # UserNotFoundError
│       └── auth.py                            # InvalidTokenError
│
├── application/                               # 🟢 Application Layer
│   ├── __init__.py
│   │
│   ├── commands/
│   │   ├── __init__.py
│   │   ├── oauth_authorize.py                 # OAuthAuthorizeInteractor
│   │   ├── oauth_callback.py                  # OAuthCallbackInteractor
│   │   ├── logout.py                          # LogoutInteractor
│   │   ├── refresh_tokens.py                  # RefreshTokensInteractor
│   │   └── revoke_all_tokens.py               # RevokeAllTokensInteractor
│   │
│   ├── queries/
│   │   ├── __init__.py
│   │   └── validate_token.py                  # ValidateTokenQueryService
│   │
│   └── common/
│       ├── __init__.py
│       │
│       ├── ports/
│       │   ├── __init__.py
│       │   ├── user_command_gateway.py
│       │   ├── user_query_gateway.py
│       │   ├── social_account_gateway.py
│       │   ├── login_audit_gateway.py
│       │   ├── token_service.py
│       │   ├── state_store.py
│       │   ├── token_blacklist.py
│       │   ├── user_token_store.py
│       │   ├── outbox_gateway.py
│       │   ├── flusher.py
│       │   └── transaction_manager.py
│       │
│       ├── services/
│       │   ├── __init__.py
│       │   └── oauth_client.py
│       │
│       ├── dto/
│       │   ├── __init__.py
│       │   ├── auth.py
│       │   └── token.py
│       │
│       └── exceptions/
│           ├── __init__.py
│           ├── base.py
│           └── auth.py
│
├── infrastructure/                            # 🟠 Infrastructure Layer
│   ├── __init__.py
│   │
│   ├── adapters/
│   │   ├── __init__.py
│   │   ├── user_data_mapper_sqla.py
│   │   ├── user_reader_sqla.py
│   │   ├── social_account_mapper_sqla.py
│   │   ├── login_audit_mapper_sqla.py
│   │   ├── main_flusher_sqla.py
│   │   ├── main_transaction_manager_sqla.py
│   │   ├── user_id_generator_uuid.py
│   │   └── types.py
│   │
│   ├── persistence_postgres/
│   │   ├── __init__.py
│   │   ├── session.py
│   │   ├── registry.py
│   │   └── mappings/
│   │       ├── __init__.py
│   │       ├── all.py
│   │       ├── user.py
│   │       ├── user_social_account.py
│   │       └── login_audit.py
│   │
│   ├── persistence_redis/
│   │   ├── __init__.py
│   │   ├── client.py
│   │   ├── state_store_redis.py
│   │   ├── token_blacklist_redis.py
│   │   ├── user_token_store_redis.py
│   │   └── outbox_redis.py
│   │
│   ├── security/
│   │   ├── __init__.py
│   │   ├── jwt_token_service.py
│   │   └── jwt_processor.py
│   │
│   ├── oauth/
│   │   ├── __init__.py
│   │   ├── base.py
│   │   ├── google.py
│   │   ├── kakao.py
│   │   ├── naver.py
│   │   └── registry.py
│   │
│   └── exceptions/
│       ├── __init__.py
│       ├── base.py
│       ├── gateway.py
│       └── oauth.py
│
├── presentation/                              # 🔴 Presentation Layer
│   ├── __init__.py
│   │
│   └── http/
│       ├── __init__.py
│       │
│       ├── controllers/
│       │   ├── __init__.py
│       │   │
│       │   ├── auth/
│       │   │   ├── __init__.py
│       │   │   ├── authorize.py
│       │   │   ├── callback.py
│       │   │   ├── logout.py
│       │   │   ├── refresh.py
│       │   │   ├── revoke.py
│       │   │   └── router.py
│       │   │
│       │   ├── general/
│       │   │   ├── __init__.py
│       │   │   ├── health.py
│       │   │   ├── metrics.py
│       │   │   └── router.py
│       │   │
│       │   ├── api_v1_router.py
│       │   └── root_router.py
│       │
│       ├── auth/
│       │   ├── __init__.py
│       │   ├── cookie_params.py
│       │   ├── dependencies.py
│       │   └── middleware.py
│       │
│       ├── errors/
│       │   ├── __init__.py
│       │   ├── handlers.py
│       │   └── translators.py
│       │
│       └── schemas/
│           ├── __init__.py
│           ├── auth.py
│           └── common.py
│
├── setup/                                     # 🟣 Setup Layer
│   ├── __init__.py
│   ├── config/
│   │   ├── __init__.py
│   │   ├── settings.py
│   │   ├── database.py
│   │   ├── redis.py
│   │   ├── security.py
│   │   └── oauth.py
│   ├── dependencies.py
│   ├── logging.py
│   ├── tracing.py
│   └── constants.py
│
├── workers/                                   # ⚙️ Workers
│   ├── __init__.py
│   └── consumers/
│       └── blacklist_relay.py
│
├── tests/
│   ├── __init__.py
│   ├── conftest.py
│   ├── unit/
│   │   ├── domain/
│   │   ├── application/
│   │   └── factories/
│   └── integration/
│
├── main.py
├── Dockerfile
├── Dockerfile.relay
├── requirements.txt
└── README.md
```

---

## 4. 기능 검증 매트릭스

### 4.1 엔드포인트 매핑

| Method | Endpoint | 현재 | 목표 |
|--------|----------|------|------|
| `GET` | `/{provider}/authorize` | `AuthService.authorize()` | `OAuthAuthorizeInteractor` |
| `GET` | `/{provider}/callback` | `AuthService.login_with_provider()` | `OAuthCallbackInteractor` |
| `POST` | `/logout` | `AuthService.logout()` | `LogoutInteractor` |
| `POST` | `/refresh` | `AuthService.refresh_session()` | `RefreshTokensInteractor` |
| `POST` | `/revoke` | (신규) | `RevokeAllTokensInteractor` |
| `GET` | `/health` | `health.py` | `general/health.py` |
| `GET` | `/metrics` | `metrics.py` | `general/metrics.py` |

### 4.2 기능 체크리스트

| 기능 | 현재 위치 | 목표 위치 | 상태 |
|------|----------|----------|------|
| OAuth 인증 URL 생성 | `AuthService.authorize()` | `commands/oauth_authorize.py` | ✅ |
| OAuth 콜백 (로그인/회원가입) | `AuthService.login_with_provider()` | `commands/oauth_callback.py` | ✅ |
| 토큰 갱신 | `AuthService.refresh_session()` | `commands/refresh_tokens.py` | ✅ |
| 로그아웃 | `AuthService.logout()` | `commands/logout.py` | ✅ |
| 토큰 검증 | `get_current_user dependency` | `queries/validate_token.py` | ✅ |
| JWT 발급/검증 | `TokenService` | `infrastructure/security/` | ✅ |
| OAuth 상태 관리 | `OAuthStateStore` | `persistence_redis/state_store_redis.py` | ✅ |
| 토큰 블랙리스트 | `TokenBlacklist` | `persistence_redis/token_blacklist_redis.py` | ✅ |
| 사용자 토큰 저장 | `UserTokenStore` | `persistence_redis/user_token_store_redis.py` | ✅ |
| Outbox 패턴 | `RedisOutbox` | `persistence_redis/outbox_redis.py` | ✅ |
| Blacklist Relay | `workers/blacklist_relay.py` | `workers/consumers/blacklist_relay.py` | ✅ |
| 사용자 생성/조회 | `UserRepository` | `adapters/user_*.py` | ✅ |
| 로그인 감사 | `LoginAuditRepository` | `adapters/login_audit_mapper_sqla.py` | ✅ |
| 쿠키 관리 | `AuthService._*_cookie*()` | `presentation/http/auth/cookie_params.py` | ✅ |

---

## 5. 리팩토링 단계

### Phase 1: 기반 구조 생성

```bash
# 1.1 새 디렉토리 구조 생성
mkdir -p apps/auth/{domain,application,infrastructure,presentation,setup,workers,tests}

# 1.2 Domain Layer 기초
mkdir -p apps/auth/domain/{entities,value_objects,enums,ports,services,exceptions}

# 1.3 Application Layer 기초
mkdir -p apps/auth/application/{commands,queries,common}
mkdir -p apps/auth/application/common/{ports,services,dto,exceptions}

# 1.4 Infrastructure Layer 기초
mkdir -p apps/auth/infrastructure/{adapters,persistence_postgres,persistence_redis,security,oauth,exceptions}
mkdir -p apps/auth/infrastructure/persistence_postgres/mappings

# 1.5 Presentation Layer 기초
mkdir -p apps/auth/presentation/http/{controllers,auth,errors,schemas}
mkdir -p apps/auth/presentation/http/controllers/{auth,general}

# 1.6 Setup Layer 기초
mkdir -p apps/auth/setup/config

# 1.7 Workers
mkdir -p apps/auth/workers/consumers

# 1.8 Tests
mkdir -p apps/auth/tests/{unit,integration}
mkdir -p apps/auth/tests/unit/{domain,application,factories}
```

### Phase 2: Domain Layer 구현

| 순서 | 파일 | 내용 |
|-----|------|------|
| 2.1 | `domain/entities/base.py` | Entity 베이스 클래스 |
| 2.2 | `domain/value_objects/base.py` | ValueObject 베이스 클래스 |
| 2.3 | `domain/enums/*.py` | OAuthProvider, TokenType |
| 2.4 | `domain/value_objects/*.py` | UserId, Email, TokenPayload |
| 2.5 | `domain/entities/*.py` | User, UserSocialAccount, LoginAudit |
| 2.6 | `domain/exceptions/*.py` | DomainError, UserNotFoundError |
| 2.7 | `domain/ports/*.py` | TokenGenerator, UserIdGenerator |
| 2.8 | `domain/services/user_service.py` | 순수 도메인 로직 |

### Phase 3: Application Layer 구현

| 순서 | 파일 | 내용 |
|-----|------|------|
| 3.1 | `application/common/ports/*.py` | 모든 Port 인터페이스 정의 |
| 3.2 | `application/common/dto/*.py` | AuthorizeRequest, TokenPairDTO |
| 3.3 | `application/common/exceptions/*.py` | ApplicationError, AuthenticationError |
| 3.4 | `application/commands/oauth_authorize.py` | OAuthAuthorizeInteractor |
| 3.5 | `application/commands/oauth_callback.py` | OAuthCallbackInteractor |
| 3.6 | `application/commands/logout.py` | LogoutInteractor |
| 3.7 | `application/commands/refresh_tokens.py` | RefreshTokensInteractor |
| 3.8 | `application/queries/validate_token.py` | ValidateTokenQueryService |

### Phase 4: Infrastructure Layer 구현

| 순서 | 파일 | 내용 |
|-----|------|------|
| 4.1 | `infrastructure/persistence_postgres/session.py` | AsyncSession 설정 |
| 4.2 | `infrastructure/persistence_postgres/registry.py` | mapper_registry |
| 4.3 | `infrastructure/persistence_postgres/mappings/*.py` | ORM 매핑 |
| 4.4 | `infrastructure/adapters/user_*.py` | UserCommandGateway, UserQueryGateway 구현 |
| 4.5 | `infrastructure/persistence_redis/*.py` | Redis 기반 Port 구현 |
| 4.6 | `infrastructure/security/*.py` | JWT 토큰 서비스 |
| 4.7 | `infrastructure/oauth/*.py` | OAuth 프로바이더 |
| 4.8 | `infrastructure/adapters/main_*.py` | Flusher, TransactionManager |

### Phase 5: Presentation Layer 구현

| 순서 | 파일 | 내용 |
|-----|------|------|
| 5.1 | `presentation/http/schemas/*.py` | HTTP Request/Response 스키마 |
| 5.2 | `presentation/http/auth/*.py` | 쿠키, 의존성, 미들웨어 |
| 5.3 | `presentation/http/errors/*.py` | 에러 핸들러, 변환기 |
| 5.4 | `presentation/http/controllers/auth/*.py` | Auth 컨트롤러들 |
| 5.5 | `presentation/http/controllers/general/*.py` | Health, Metrics |
| 5.6 | `presentation/http/controllers/*_router.py` | 라우터 통합 |

### Phase 6: Setup & 통합

| 순서 | 파일 | 내용 |
|-----|------|------|
| 6.1 | `setup/config/*.py` | 설정 클래스들 |
| 6.2 | `setup/dependencies.py` | FastAPI DI 설정 |
| 6.3 | `setup/logging.py` | 로깅 설정 |
| 6.4 | `main.py` | FastAPI 앱 엔트리포인트 |
| 6.5 | `workers/consumers/blacklist_relay.py` | Worker 마이그레이션 |

### Phase 7: 테스트 & 검증

| 순서 | 작업 | 내용 |
|-----|------|------|
| 7.1 | Unit Tests | Domain, Application 레이어 테스트 |
| 7.2 | Integration Tests | 전체 플로우 테스트 |
| 7.3 | E2E Tests | 실제 OAuth 플로우 검증 |
| 7.4 | 기존 테스트 마이그레이션 | `tests/` 구조 업데이트 |

---

## 6. 주요 코드 변환 예시

### 6.1 현재 AuthService → 목표 OAuthCallbackInteractor

**현재:**
```python
# domains/auth/application/services/auth.py
class AuthService:
    def __init__(
        self,
        session: AsyncSession = Depends(get_db_session),
        token_service: TokenService = Depends(TokenService),
        ...
    ):
        self.session = session
        self.user_repo = UserRepository(session)
        
    async def login_with_provider(self, provider_name: str, payload: OAuthLoginRequest, ...):
        # 모든 로직이 한 곳에 혼합
        provider = self._get_provider(provider_name)
        tokens = await provider.exchange_code(...)
        profile = await provider.fetch_profile(...)
        user, _ = await self.user_repo.upsert_from_profile(profile)
        token_pair = self.token_service.issue_pair(...)
        await self.session.commit()
        self._apply_session_cookies(response, ...)
        return User.model_validate(user)
```

**목표:**
```python
# apps/auth/application/commands/oauth_callback.py
from dataclasses import dataclass
from typing import Protocol

@dataclass(frozen=True, slots=True)
class OAuthCallbackRequest:
    provider: str
    code: str
    state: str
    redirect_uri: str | None
    user_agent: str | None
    ip_address: str | None

@dataclass(frozen=True, slots=True)
class OAuthCallbackResponse:
    user_id: UUID
    access_token: str
    refresh_token: str
    access_expires_at: int
    refresh_expires_at: int

class OAuthCallbackInteractor:
    def __init__(
        self,
        user_service: UserService,                    # Domain Service
        user_command_gateway: UserCommandGateway,     # Port
        social_account_gateway: SocialAccountGateway, # Port
        login_audit_gateway: LoginAuditGateway,       # Port
        token_service: TokenService,                  # Port
        state_store: StateStore,                      # Port
        user_token_store: UserTokenStore,             # Port
        oauth_client: OAuthClientService,             # Application Service
        flusher: Flusher,                            # Port
        transaction_manager: TransactionManager,      # Port
    ) -> None:
        self._user_service = user_service
        self._user_command_gateway = user_command_gateway
        self._social_account_gateway = social_account_gateway
        self._login_audit_gateway = login_audit_gateway
        self._token_service = token_service
        self._state_store = state_store
        self._user_token_store = user_token_store
        self._oauth_client = oauth_client
        self._flusher = flusher
        self._transaction_manager = transaction_manager

    async def execute(self, request: OAuthCallbackRequest) -> OAuthCallbackResponse:
        """
        :raises AuthenticationError: 상태 검증 실패
        :raises OAuthProviderError: Provider API 오류
        :raises DataMapperError: DB 오류
        """
        # 1. 상태 검증
        state_data = await self._state_store.consume(request.state)
        if not state_data or state_data.provider != request.provider:
            raise AuthenticationError("Invalid or expired state")
        
        # 2. OAuth 토큰 교환 & 프로필 조회
        profile = await self._oauth_client.fetch_profile(
            provider=request.provider,
            code=request.code,
            state=request.state,
            redirect_uri=request.redirect_uri or state_data.redirect_uri,
            code_verifier=state_data.code_verifier,
        )
        
        # 3. 사용자 생성/조회
        user = await self._user_service.upsert_from_profile(
            profile=profile,
            user_gateway=self._user_command_gateway,
            social_account_gateway=self._social_account_gateway,
        )
        
        # 4. 토큰 발급
        token_pair = self._token_service.issue_pair(
            user_id=user.id_,
            provider=request.provider,
        )
        
        # 5. 토큰 저장
        await self._user_token_store.register(
            user_id=user.id_,
            jti=token_pair.refresh_jti,
            expires_at=token_pair.refresh_expires_at,
            device_id=state_data.device_id,
            user_agent=request.user_agent,
        )
        
        # 6. 로그인 감사
        self._login_audit_gateway.add(LoginAudit(
            user_id=user.id_,
            provider=request.provider,
            jti=token_pair.access_jti,
            ip_address=request.ip_address,
            user_agent=request.user_agent,
        ))
        
        # 7. 커밋
        await self._flusher.flush()
        await self._transaction_manager.commit()
        
        return OAuthCallbackResponse(
            user_id=user.id_.value,
            access_token=token_pair.access_token,
            refresh_token=token_pair.refresh_token,
            access_expires_at=token_pair.access_expires_at,
            refresh_expires_at=token_pair.refresh_expires_at,
        )
```

### 6.2 현재 User 모델 → Domain Entity + ORM 매핑 분리

**현재 (혼합):**
```python
# domains/auth/domain/models/user.py
from sqlalchemy.orm import Mapped, mapped_column
from domains.auth.infrastructure.database.base import Base

class User(Base):  # ORM과 결합
    __tablename__ = "users"
    id: Mapped[uuid.UUID] = mapped_column(...)
    username: Mapped[str] = mapped_column(...)
```

**목표 - Domain Entity (순수 Python):**
```python
# apps/auth/domain/entities/user.py
from apps.auth.domain.entities.base import Entity
from apps.auth.domain.value_objects.user_id import UserId
from apps.auth.domain.value_objects.email import Email

class User(Entity[UserId]):
    def __init__(
        self,
        *,
        id_: UserId,
        username: str | None,
        nickname: str | None,
        profile_image_url: str | None,
        phone_number: str | None,
        created_at: datetime,
        updated_at: datetime,
        last_login_at: datetime | None,
    ) -> None:
        super().__init__(id_=id_)
        self.username = username
        self.nickname = nickname
        self.profile_image_url = profile_image_url
        self.phone_number = phone_number
        self.created_at = created_at
        self.updated_at = updated_at
        self.last_login_at = last_login_at
```

**목표 - ORM 매핑 (Infrastructure):**
```python
# apps/auth/infrastructure/persistence_postgres/mappings/user.py
from sqlalchemy import Table, Column, String, DateTime
from sqlalchemy.dialects.postgresql import UUID

from apps.auth.infrastructure.persistence_postgres.registry import mapper_registry
from apps.auth.domain.entities.user import User
from apps.auth.domain.value_objects.user_id import UserId

users_table = Table(
    "users",
    mapper_registry.metadata,
    Column("id", UUID(as_uuid=True), primary_key=True),
    Column("username", String(120)),
    Column("nickname", String(120)),
    Column("profile_image_url", String(512)),
    Column("phone_number", String(32), index=True),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    Column("last_login_at", DateTime(timezone=True)),
    schema="auth",
)

def start_user_mapper() -> None:
    mapper_registry.map_imperatively(
        User,
        users_table,
        properties={
            "id_": users_table.c.id,
        },
    )
```

---

## 7. 의존성 주입 설정

### 7.1 FastAPI Depends 기반 (Dishka 미사용)

```python
# apps/auth/setup/dependencies.py
from functools import lru_cache
from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from apps.auth.infrastructure.persistence_postgres.session import get_db_session
from apps.auth.infrastructure.persistence_redis.client import get_redis
from apps.auth.infrastructure.adapters.user_data_mapper_sqla import SqlaUserDataMapper
from apps.auth.infrastructure.security.jwt_token_service import JwtTokenService
from apps.auth.application.commands.oauth_callback import OAuthCallbackInteractor

# Gateway Providers
async def get_user_command_gateway(
    session: AsyncSession = Depends(get_db_session),
) -> UserCommandGateway:
    return SqlaUserDataMapper(session)

async def get_user_query_gateway(
    session: AsyncSession = Depends(get_db_session),
) -> UserQueryGateway:
    return SqlaUserReader(session)

# Service Providers
@lru_cache
def get_token_service() -> TokenService:
    return JwtTokenService(...)

# Use Case Providers
async def get_oauth_callback_interactor(
    user_command_gateway: UserCommandGateway = Depends(get_user_command_gateway),
    token_service: TokenService = Depends(get_token_service),
    ...
) -> OAuthCallbackInteractor:
    return OAuthCallbackInteractor(
        user_command_gateway=user_command_gateway,
        token_service=token_service,
        ...
    )
```

---

## 8. 마이그레이션 체크리스트

### Phase 1: 준비
- [ ] 새 디렉토리 구조 생성
- [ ] `__init__.py` 파일 생성
- [ ] 기본 베이스 클래스 작성 (Entity, ValueObject)

### Phase 2: Domain Layer
- [ ] `domain/enums/` 작성
- [ ] `domain/value_objects/` 작성
- [ ] `domain/entities/` 작성 (ORM 분리)
- [ ] `domain/exceptions/` 작성
- [ ] `domain/ports/` 작성
- [ ] `domain/services/user_service.py` 작성

### Phase 3: Application Layer
- [ ] `application/common/ports/` 작성
- [ ] `application/common/dto/` 작성
- [ ] `application/common/exceptions/` 작성
- [ ] `application/commands/oauth_authorize.py` 작성
- [ ] `application/commands/oauth_callback.py` 작성
- [ ] `application/commands/logout.py` 작성
- [ ] `application/commands/refresh_tokens.py` 작성
- [ ] `application/queries/validate_token.py` 작성

### Phase 4: Infrastructure Layer
- [ ] `infrastructure/persistence_postgres/` 작성
- [ ] `infrastructure/persistence_postgres/mappings/` 작성
- [ ] `infrastructure/adapters/` 작성
- [ ] `infrastructure/persistence_redis/` 작성
- [ ] `infrastructure/security/` 작성
- [ ] `infrastructure/oauth/` 작성

### Phase 5: Presentation Layer
- [ ] `presentation/http/schemas/` 작성
- [ ] `presentation/http/auth/` 작성
- [ ] `presentation/http/errors/` 작성
- [ ] `presentation/http/controllers/auth/` 작성
- [ ] `presentation/http/controllers/general/` 작성
- [ ] 라우터 통합

### Phase 6: Setup & 통합
- [ ] `setup/config/` 작성
- [ ] `setup/dependencies.py` 작성
- [ ] `main.py` 업데이트
- [ ] `workers/consumers/blacklist_relay.py` 마이그레이션

### Phase 7: 테스트 & 검증
- [ ] Unit 테스트 작성
- [ ] Integration 테스트 작성
- [ ] 기존 테스트 마이그레이션
- [ ] 로컬 E2E 테스트
- [ ] CI/CD 파이프라인 업데이트

### Phase 8: 정리
- [ ] 기존 `domains/auth/` 제거
- [ ] import 경로 전체 업데이트
- [ ] Dockerfile 업데이트
- [ ] K8s 매니페스트 업데이트

---

## 9. 위험 요소 및 대응

| 위험 | 영향 | 대응 |
|------|------|------|
| ORM 매핑 분리 시 관계 매핑 복잡성 | 중 | Imperative Mapping 테스트 철저히 |
| 기존 API 호환성 | 상 | HTTP 스키마 동일하게 유지 |
| 테스트 커버리지 감소 | 중 | 단계별 테스트 작성 병행 |
| 배포 중 다운타임 | 상 | Blue-Green 배포 또는 Feature Flag |

---

## 10. 배포 전략 (Canary)

### 10.1 개요

리팩토링된 코드는 **Canary 배포**로 안전하게 검증합니다.

참조: `docs/blogs/deployment/01-canary-deployment-strategy.md`

### 10.2 배포 흐름

```
┌─────────────────────────────────────────────────────────────────────┐
│                         Canary 배포 아키텍처                          │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│   Client                                                             │
│     │                                                                │
│     ├─────────────────────────────────────────┐                     │
│     │  X-Canary: true                         │  (no header)        │
│     ▼                                         ▼                     │
│  ┌─────────────┐                        ┌─────────────┐             │
│  │  Istio      │                        │  Istio      │             │
│  │  Gateway    │                        │  Gateway    │             │
│  └──────┬──────┘                        └──────┬──────┘             │
│         │                                      │                     │
│         ▼ VirtualService                       ▼ VirtualService     │
│  ┌─────────────────┐                    ┌─────────────────┐         │
│  │ auth-api-canary │                    │   auth-api      │         │
│  │ (리팩토링 버전) │                    │   (Stable)      │         │
│  │ version: v2     │                    │   version: v1   │         │
│  └─────────────────┘                    └─────────────────┘         │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

### 10.3 Canary 이미지 태그

```yaml
# Stable 이미지 (현재)
image: docker.io/mng990/eco2:auth-api-dev-latest

# Canary 이미지 (리팩토링)
image: docker.io/mng990/eco2:auth-api-dev-canary
```

### 10.4 테스트 방법

```bash
# 1. Stable 버전 테스트 (기존 코드)
curl https://api.example.com/api/v1/auth/health

# 2. Canary 버전 테스트 (리팩토링 코드)
curl -H "X-Canary: true" https://api.example.com/api/v1/auth/health
```

### 10.5 배포 단계

| 단계 | 작업 | 검증 |
|------|------|------|
| 1 | 리팩토링 코드 → `canary` 브랜치 | 로컬 테스트 |
| 2 | CI/CD가 `auth-api-dev-canary` 이미지 빌드 | 이미지 푸시 확인 |
| 3 | ArgoCD가 `deployment-canary.yaml` 동기화 | Pod Running 확인 |
| 4 | `X-Canary: true` 헤더로 E2E 테스트 | 모든 엔드포인트 검증 |
| 5 | 성공 시 `canary` → `develop` 머지 | Stable 이미지 업데이트 |
| 6 | Canary Deployment 제거 또는 축소 | 리소스 정리 |

### 10.6 롤백

문제 발생 시 **즉시 롤백** 가능:

```bash
# Canary Pod 스케일 다운 (트래픽 차단)
kubectl scale deployment auth-api-canary -n auth --replicas=0

# 또는 Canary 헤더 없이 요청하면 자동으로 Stable로 라우팅
```

---

## 11. 향후 작업 (Phase 8+)

### libs/ 구조화
- [ ] `_shared/` → `libs/` 리네이밍
- [ ] `waste_pipeline/` → `apps/scan/` 이동
- [ ] Celery config 도메인별 분리
- [ ] `_base/` → `docker/` 이동

---

## 12. 참고 문서

- `docs/foundations/16-fastapi-clean-example-analysis.md` - 아키텍처 상세 분석
- `docs/foundations/15-dependency-injection-comparison.md` - DI 비교
- `docs/blogs/deployment/01-canary-deployment-strategy.md` - Canary 배포 전략
- [fastapi-clean-example](https://github.com/ivan-borovets/fastapi-clean-example) - 참조 프로젝트

