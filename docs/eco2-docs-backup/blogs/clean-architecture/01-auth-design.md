# 이코에코(Eco²) Clean Architecture #1: Auth - 설계

## 배경

이코에코(Eco²)는 환경 보호 활동을 장려하는 플랫폼이다. 사용자 인증 시스템은 OAuth2.0 기반 소셜 로그인(Google, Kakao, Naver)을 지원하며, JWT 토큰 기반 세션 관리를 한다.

기존 `domains/auth/` 구조는 빠른 MVP 개발에 적합했지만, 기능이 복잡해지면서 테스트와 유지보수가 어려워졌다.

---

## 기존 구조의 문제점

### 폴더 구조

```
domains/auth/
├── application/
│   └── services/
│       └── auth.py          # ~800줄, 모든 로직 집중
├── infrastructure/
│   ├── messaging/
│   │   └── redis_outbox.py
│   └── repositories/
│       └── user.py
├── models/
│   └── user.py
└── routers/
    └── auth.py
```

### 문제 1: God Object

```python
class AuthService:
    def __init__(
        self,
        session: AsyncSession = Depends(get_db_session),
        token_service: TokenService = Depends(TokenService),
        state_store: OAuthStateStore = Depends(OAuthStateStore),
        blacklist: TokenBlacklist = Depends(TokenBlacklist),
        token_store: UserTokenStore = Depends(UserTokenStore),
        settings: Settings = Depends(get_settings),
    ):
        self.session = session
        self.token_service = token_service
        self.state_store = state_store
        self.blacklist = blacklist
        self.user_token_store = token_store
        self.settings = settings
        self.providers = ProviderRegistry(settings)  # 내부 생성
        self.user_repo = UserRepository(session)     # 내부 생성
        self.login_audit_repo = LoginAuditRepository(session)
```

한 클래스에 OAuth 인증, 토큰 관리, 사용자 관리, 로그인 감사 등 모든 책임이 집중되어 있다.

### 문제 2: 테스트 불가능한 구조

```python
# ❌ 테스트하려면 실제 DB/Redis가 필요
def test_login():
    service = AuthService()  # Depends()가 실제 인프라에 연결
    # Mock 주입 불가
```

- `Depends()`로 구현체 직접 주입 → Mock 교체 불가
- 생성자 내부에서 객체 생성 → 의존성 숨김
- 단위 테스트 작성 시 통합 테스트 환경 필요

### 문제 3: 레이어 경계 불명확

```
┌─────────────────────────────────────────┐
│  AuthService                            │
│  ├── HTTP 요청 파싱                     │
│  ├── 비즈니스 로직 처리                 │
│  ├── DB 쿼리 실행                       │
│  ├── Redis 캐시 관리                    │
│  └── 외부 API 호출 (OAuth Provider)     │
└─────────────────────────────────────────┘
```

모든 레이어가 하나의 클래스에 섞여 있어 변경의 영향 범위를 예측하기 어렵다.

---

## Clean Architecture 핵심 개념

### 의존성 규칙

```
┌─────────────────────────────────────────────────────┐
│                    Frameworks                       │
│  ┌─────────────────────────────────────────────┐   │
│  │              Interface Adapters              │   │
│  │  ┌─────────────────────────────────────┐   │   │
│  │  │          Application Layer           │   │   │
│  │  │  ┌─────────────────────────────┐   │   │   │
│  │  │  │       Domain Layer          │   │   │   │
│  │  │  │   (Entities, Value Objects) │   │   │   │
│  │  │  └─────────────────────────────┘   │   │   │
│  │  └─────────────────────────────────────┘   │   │
│  └─────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────┘
            ← 의존성 방향 (바깥 → 안쪽)
```

**핵심**: 안쪽 레이어는 바깥쪽 레이어를 알지 못한다.

### 의존성 역전 원칙 (DIP)

```
❌ 기존:
┌─────────────┐      ┌─────────────┐
│  Service    │ ───→ │ Repository  │ (구현체)
└─────────────┘      └─────────────┘

✅ 목표:
┌─────────────┐      ┌─────────────┐      ┌─────────────┐
│  Service    │ ───→ │    Port     │ ←─── │  Adapter    │
└─────────────┘      │ (Interface) │      │ (구현체)    │
                     └─────────────┘      └─────────────┘
```

고수준 모듈(Service)이 저수준 모듈(Repository)에 직접 의존하지 않고, 추상(인터페이스)에 의존한다.

### Port & Adapter (Hexagonal Architecture)

```
                    ┌─────────────────────────────┐
                    │      Application Core       │
   Driving          │  ┌─────────────────────┐   │          Driven
   Adapters         │  │                     │   │          Adapters
                    │  │   Domain + UseCase  │   │
┌─────────┐   Port  │  │                     │   │  Port   ┌─────────┐
│  HTTP   │ ──────→ │  └─────────────────────┘   │ ←────── │   DB    │
│Controller│        │                             │         │ Adapter │
└─────────┘         └─────────────────────────────┘         └─────────┘
```

| 개념 | 역할 | 위치 | 예시 |
|------|------|------|------|
| **Port** | 인터페이스 (what) | Application 경계 | `UserCommandGateway` |
| **Driving Adapter** | 외부 → 내부 | Presentation | HTTP Controller |
| **Driven Adapter** | 내부 → 외부 | Infrastructure | `SqlaUserDataMapper` |

### CQRS (Command Query Responsibility Segregation)

| 유형 | 역할 | 특징 | 네이밍 |
|------|------|------|--------|
| **Command** | 상태 변경 | Write, Side Effect | `~Interactor` |
| **Query** | 조회 | Read Only | `~QueryService` |

장점:
- 읽기/쓰기 최적화를 독립적으로 수행 가능
- 단일 책임 원칙 준수
- 테스트 용이성 향상

---

## 레퍼런스 분석: fastapi-clean-example

[ivan-borovets/fastapi-clean-example](https://github.com/ivan-borovets/fastapi-clean-example)를 레퍼런스로 삼았다.

### 폴더 구조

```
src/app/
├── domain/                    # 핵심 비즈니스 로직
│   ├── entities/              # Entity (식별자 있음)
│   ├── value_objects/         # Value Object (불변, 식별자 없음)
│   ├── ports/                 # Domain Port
│   └── services/              # Domain Service
├── application/               # Use Case
│   ├── commands/              # Command (상태 변경)
│   ├── queries/               # Query (조회)
│   └── common/
│       ├── ports/             # Application Port
│       └── dto/               # Data Transfer Object
├── infrastructure/            # 외부 시스템 구현
│   ├── adapters/              # Port 구현체
│   ├── persistence_sqla/      # SQLAlchemy 설정
│   └── auth/                  # 인증 관련
├── presentation/              # HTTP Controller
│   └── http/
│       ├── controllers/
│       ├── schemas/           # Pydantic Request/Response
│       └── errors/            # HTTP Error Handler
└── setup/                     # DI Container, Config
    └── ioc/                   # Dependency Injection
```

### Gateway vs Repository

예제에서는 Gateway 패턴을 사용한다.

| 패턴 | 특징 | 장점 | 단점 |
|------|------|------|------|
| **Repository** | 단일 인터페이스 (CRUD) | 단순함 | 읽기/쓰기 분리 어려움 |
| **Gateway** | Command/Query 분리 | CQRS 지원, 최적화 용이 | 인터페이스 증가 |

```python
# UserCommandGateway - 쓰기 연산
class UserCommandGateway(Protocol):
    async def save(self, user: User) -> None: ...
    async def update(self, user: User) -> None: ...

# UserQueryGateway - 읽기 연산  
class UserQueryGateway(Protocol):
    async def find_by_email(self, email: str) -> User | None: ...
    async def find_by_id(self, user_id: UserId) -> User | None: ...
```

### 3단계 Port 구조

```
┌─────────────────────────────────────────────────────────────────┐
│  Domain Layer                                                   │
│  └── ports/password_hasher.py                                  │
│       - 도메인 로직에서 필요한 추상화                           │
│       - 예: PasswordHasher (비밀번호 해싱은 도메인 규칙)       │
├─────────────────────────────────────────────────────────────────┤
│  Application Layer                                              │
│  └── common/ports/                                              │
│       ├── user_command_gateway.py                               │
│       ├── user_query_gateway.py                                 │
│       └── flusher.py                                            │
│       - Use Case에서 필요한 외부 시스템 추상화                  │
│       - 예: Gateway (데이터 영속화), Flusher (트랜잭션 커밋)   │
├─────────────────────────────────────────────────────────────────┤
│  Infrastructure Layer                                           │
│  └── auth/session/ports/gateway.py                              │
│       - 인프라 내부 추상화 (테스트, 교체 용이성)               │
│       - 예: AuthSessionGateway (세션 저장소 추상화)            │
└─────────────────────────────────────────────────────────────────┘
```

---

## 적용 설계

### 최종 폴더 구조 (apps/auth/)

```
apps/auth/
├── domain/                         # 핵심 비즈니스 로직
│   ├── entities/
│   │   ├── __init__.py
│   │   ├── base.py                 # Entity 기본 클래스
│   │   ├── user.py                 # User 엔티티
│   │   ├── user_social_account.py  # 소셜 계정 연결
│   │   └── login_audit.py          # 로그인 감사 로그
│   ├── value_objects/
│   │   ├── __init__.py
│   │   ├── base.py                 # ValueObject 기본 클래스
│   │   ├── user_id.py              # UserId (UUID 래핑)
│   │   ├── email.py                # Email (유효성 검증)
│   │   └── token_payload.py        # JWT Payload
│   ├── enums/
│   │   ├── oauth_provider.py       # Google, Kakao, Naver
│   │   └── token_type.py           # Access, Refresh
│   ├── ports/
│   │   └── user_id_generator.py    # Domain Port
│   ├── services/
│   │   └── user_service.py         # Domain Service
│   └── exceptions/
│       ├── base.py
│       ├── user.py
│       ├── auth.py
│       └── validation.py
│
├── application/                    # Use Case
│   ├── commands/
│   │   ├── oauth_authorize.py      # OAuth 인증 URL 생성
│   │   ├── oauth_callback.py       # OAuth 콜백 처리
│   │   ├── logout.py               # 로그아웃
│   │   └── refresh_tokens.py       # 토큰 갱신
│   ├── queries/
│   │   └── validate_token.py       # 토큰 검증
│   └── common/
│       ├── ports/                  # Application Port
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
│       ├── dto/
│       │   └── auth.py             # Request/Response DTO
│       ├── services/
│       │   └── oauth_client.py     # OAuth Client Port
│       └── exceptions/
│           ├── base.py
│           ├── auth.py
│           └── gateway.py
│
├── infrastructure/                 # 외부 시스템 구현
│   ├── persistence_postgres/
│   │   ├── session.py              # AsyncSession 팩토리
│   │   ├── registry.py             # SQLAlchemy Registry
│   │   └── mappings/               # ORM 매핑
│   │       ├── user.py
│   │       ├── user_social_account.py
│   │       └── login_audit.py
│   ├── persistence_redis/
│   │   ├── client.py               # Redis 클라이언트
│   │   ├── state_store_redis.py    # OAuth State 저장
│   │   ├── token_blacklist_redis.py
│   │   ├── user_token_store_redis.py
│   │   └── outbox_redis.py         # Outbox 패턴
│   ├── adapters/                   # Port 구현체
│   │   ├── user_data_mapper_sqla.py
│   │   ├── user_reader_sqla.py
│   │   ├── social_account_mapper_sqla.py
│   │   ├── login_audit_mapper_sqla.py
│   │   ├── flusher_sqla.py
│   │   ├── transaction_manager_sqla.py
│   │   └── user_id_generator_uuid.py
│   ├── security/
│   │   └── jwt_token_service.py    # JWT 생성/검증
│   └── oauth/
│       ├── base.py                 # OAuth Provider 추상
│       ├── google.py
│       ├── kakao.py
│       ├── naver.py
│       ├── registry.py             # Provider Registry
│       └── client.py               # OAuthClient 구현
│
├── presentation/                   # HTTP Interface
│   └── http/
│       ├── controllers/
│       │   ├── root_router.py
│       │   ├── api_v1_router.py
│       │   ├── auth/               # /api/v1/auth/*
│       │   │   ├── router.py
│       │   │   ├── authorize.py
│       │   │   ├── callback.py
│       │   │   ├── logout.py
│       │   │   └── refresh.py
│       │   └── general/            # /health, /metrics
│       │       ├── router.py
│       │       ├── health.py
│       │       └── metrics.py
│       ├── schemas/
│       │   ├── auth.py
│       │   └── common.py
│       ├── errors/
│       │   ├── handlers.py         # Exception → HTTP Response
│       │   └── translators.py
│       ├── auth/
│       │   ├── dependencies.py     # FastAPI Depends
│       │   └── cookie_params.py
│       └── utils/
│           └── redirect.py         # Frontend 리다이렉트 유틸
│
├── workers/                        # Background Workers
│   └── consumers/
│       └── blacklist_relay.py      # Redis → RabbitMQ Relay
│
├── setup/                          # 설정 및 DI
│   ├── config/
│   │   └── settings.py             # Pydantic Settings
│   ├── dependencies.py             # DI Provider
│   └── logging.py
│
├── tests/                          # 테스트
│   ├── conftest.py
│   ├── unit/
│   │   ├── domain/
│   │   ├── application/
│   │   └── infrastructure/
│   └── integration/
│
├── main.py                         # FastAPI App
├── Dockerfile
├── Dockerfile.relay
└── requirements.txt
```

### Port-Adapter 매핑 테이블

| Layer | Port (Interface) | Adapter (Implementation) | 역할 |
|-------|-----------------|-------------------------|------|
| Domain | `UserIdGenerator` | `UuidUserIdGenerator` | UUID 생성 |
| Application | `UserCommandGateway` | `SqlaUserDataMapper` | 사용자 저장/수정 |
| Application | `UserQueryGateway` | `SqlaUserReader` | 사용자 조회 |
| Application | `SocialAccountGateway` | `SqlaSocialAccountMapper` | 소셜 계정 관리 |
| Application | `LoginAuditGateway` | `SqlaLoginAuditMapper` | 로그인 감사 |
| Application | `TokenService` | `JwtTokenService` | JWT 생성/검증 |
| Application | `StateStore` | `RedisStateStore` | OAuth State 저장 |
| Application | `TokenBlacklist` | `RedisTokenBlacklist` | 토큰 블랙리스트 |
| Application | `UserTokenStore` | `RedisUserTokenStore` | 사용자별 토큰 관리 |
| Application | `OutboxGateway` | `RedisOutbox` | Outbox 패턴 |
| Application | `Flusher` | `SqlaFlusher` | 트랜잭션 Flush |
| Application | `OAuthClient` | `OAuthClientService` | OAuth Provider 통합 |

### 의존성 흐름도

```
┌─────────────────────────────────────────────────────────────────────┐
│                         Presentation Layer                          │
│  ┌─────────────┐     ┌─────────────┐     ┌─────────────┐           │
│  │   Router    │ ──→ │ Controller  │ ──→ │   Schema    │           │
│  └─────────────┘     └──────┬──────┘     └─────────────┘           │
│                             │ Depends()                             │
└─────────────────────────────┼───────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────────┐
│                        Application Layer                            │
│  ┌─────────────────────────┐     ┌─────────────────────────┐       │
│  │   Command (Interactor)  │     │   Query (QueryService)  │       │
│  └───────────┬─────────────┘     └───────────┬─────────────┘       │
│              │                               │                      │
│              ↓                               ↓                      │
│  ┌─────────────────────────────────────────────────────────┐       │
│  │                    Application Ports                     │       │
│  │  UserCommandGateway, TokenService, StateStore, ...      │       │
│  └─────────────────────────────────────────────────────────┘       │
└─────────────────────────────┬───────────────────────────────────────┘
                              │ implements
                              ↓
┌─────────────────────────────────────────────────────────────────────┐
│                        Domain Layer                                 │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐                 │
│  │   Entity    │  │ Value Object│  │Domain Service│                │
│  └─────────────┘  └─────────────┘  └──────┬──────┘                 │
│                                           │                         │
│  ┌─────────────────────────────────────────────────────────┐       │
│  │                    Domain Ports                          │       │
│  │                 UserIdGenerator                          │       │
│  └─────────────────────────────────────────────────────────┘       │
└─────────────────────────────────────────────────────────────────────┘
                              ↑ implements
┌─────────────────────────────┴───────────────────────────────────────┐
│                      Infrastructure Layer                           │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐                 │
│  │  SQLAlchemy │  │    Redis    │  │     JWT     │                 │
│  │  Adapters   │  │  Adapters   │  │   Service   │                 │
│  └─────────────┘  └─────────────┘  └─────────────┘                 │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 설계 원칙 적용

| 원칙 | 적용 내용 |
|------|----------|
| **SRP** | Command/Query 분리, 레이어별 책임 분리 |
| **OCP** | 새 Adapter 추가 시 기존 코드 수정 없음 (예: MySQL → PostgreSQL) |
| **LSP** | Port 구현체들은 동일한 계약 준수 |
| **ISP** | Gateway를 Command/Query로 분리, 필요한 인터페이스만 의존 |
| **DIP** | Port 인터페이스 정의, Adapter가 구현, 의존성 역전 |

---

## 기대 효과

### Before vs After

| 항목 | Before | After |
|------|--------|-------|
| **테스트** | 통합 테스트만 가능 | 단위 테스트 가능 |
| **의존성** | 구현체 직접 의존 | 인터페이스 의존 |
| **변경 영향** | 전체 파일 수정 | 해당 레이어만 |
| **코드 크기** | auth.py ~800줄 | 파일당 ~100줄 |
| **가독성** | 복잡한 메서드 | 단일 책임 메서드 |

### 트레이드오프

| 장점 | 단점 |
|------|------|
| 테스트 용이 | 파일/클래스 수 증가 |
| 변경 격리 | 초기 학습 곡선 |
| 명확한 경계 | 보일러플레이트 증가 |
| 교체 용이 | 간단한 기능도 레이어 필요 |

---

## 참고 자료

- [fastapi-clean-example](https://github.com/ivan-borovets/fastapi-clean-example)
- Robert C. Martin, "Clean Architecture" (2017)
- Alistair Cockburn, "Hexagonal Architecture" (2005)
- Vaughn Vernon, "Implementing Domain-Driven Design" (2013)
- Martin Fowler, "Patterns of Enterprise Application Architecture" (2002)
