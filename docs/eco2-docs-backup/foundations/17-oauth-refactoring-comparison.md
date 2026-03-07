# OAuth2.0 리팩토링 비교 분석

> 기존 구현(`domains/auth/`)과 Clean Architecture 리팩토링(`apps/auth/`) 비교

## 1. 아키텍처 개요

### 1.1 기존 구조 (Layered + Service)

```mermaid
%%{init: {'theme': 'base', 'themeVariables': { 'primaryColor': '#ff6b6b', 'secondaryColor': '#4ecdc4'}}}%%
graph TB
    subgraph "Presentation Layer"
        C[Controller<br/>auth.py]
    end
    
    subgraph "Application Layer"
        S[AuthService<br/>거대한 서비스 클래스]
        TS[TokenService]
        SS[StateStore]
        TB[TokenBlacklist]
    end
    
    subgraph "Infrastructure Layer"
        PR[ProviderRegistry]
        UR[UserRepository]
        LAR[LoginAuditRepository]
        DB[(PostgreSQL)]
        RD[(Redis)]
    end
    
    C -->|"Depends(AuthService)"| S
    S -->|직접 생성| PR
    S -->|직접 생성| UR
    S -->|직접 생성| LAR
    S -->|직접 주입| TS
    S -->|직접 주입| SS
    S -->|직접 주입| TB
    UR --> DB
    LAR --> DB
    SS --> RD
    TB --> RD
    
    style S fill:#ff6b6b,color:#fff
    style C fill:#4ecdc4
```

**설명:**
- `AuthService`가 모든 비즈니스 로직을 담당 (God Class)
- Repository를 `__init__`에서 직접 생성
- Infrastructure 의존성이 Application Layer에 직접 노출

---

### 1.2 리팩토링 구조 (Clean Architecture)

```mermaid
%%{init: {'theme': 'base', 'themeVariables': { 'primaryColor': '#45b7d1', 'secondaryColor': '#96ceb4'}}}%%
graph TB
    subgraph "Presentation Layer"
        C[Controller<br/>authorize.py, callback.py]
        DEP[dependencies.py<br/>DI 팩토리]
    end
    
    subgraph "Application Layer"
        UC1[OAuthAuthorizeInteractor]
        UC2[OAuthCallbackInteractor]
        UC3[LogoutInteractor]
        UC4[RefreshTokensInteractor]
        
        subgraph "Ports (Interfaces)"
            P1[StateStore]
            P2[OAuthClientService]
            P3[UserCommandGateway]
            P4[UserQueryGateway]
            P5[TokenService]
            P6[Flusher]
            P7[TransactionManager]
        end
    end
    
    subgraph "Domain Layer"
        DS[UserService<br/>도메인 서비스]
        E[User Entity]
        VO[UserId, TokenPayload]
    end
    
    subgraph "Infrastructure Layer"
        A1[RedisStateStore]
        A2[OAuthClientImpl]
        A3[SqlaUserDataMapper]
        A4[SqlaUserReader]
        A5[JwtTokenService]
        A6[SqlaFlusher]
        A7[SqlaTransactionManager]
        DB[(PostgreSQL)]
        RD[(Redis)]
    end
    
    C -->|"Depends(get_*)"| DEP
    DEP -->|조립| UC1
    DEP -->|조립| UC2
    
    UC1 -.->|uses| P1
    UC1 -.->|uses| P2
    UC2 -.->|uses| P3
    UC2 -.->|uses| P4
    UC2 -.->|uses| P5
    UC2 -.->|uses| DS
    
    A1 -->|implements| P1
    A2 -->|implements| P2
    A3 -->|implements| P3
    A4 -->|implements| P4
    A5 -->|implements| P5
    
    A3 --> DB
    A4 --> DB
    A1 --> RD
    
    DS --> E
    DS --> VO
    
    style UC1 fill:#45b7d1,color:#fff
    style UC2 fill:#45b7d1,color:#fff
    style P1 fill:#96ceb4
    style P2 fill:#96ceb4
    style P3 fill:#96ceb4
    style P4 fill:#96ceb4
    style DS fill:#ffeaa7
```

**설명:**
- Use Case별 Interactor 클래스 (단일 책임)
- Port(Protocol)를 통한 의존성 역전
- Infrastructure → Application 방향으로만 의존
- `dependencies.py`에서 명시적 DI 조립

---

## 2. OAuth Authorize 플로우 비교

### 2.1 기존 구현

```mermaid
sequenceDiagram
    autonumber
    participant Client
    participant Controller as auth.py
    participant Service as AuthService
    participant StateStore as OAuthStateStore
    participant Provider as ProviderRegistry
    participant Redis
    
    Note over Client,Redis: 기존: Controller → Service (직접 의존)
    
    Client->>Controller: GET /google
    Controller->>Service: Depends(AuthService) 자동 주입
    
    Note right of Service: AuthService.__init__()에서<br/>ProviderRegistry 직접 생성
    
    Service->>Service: _get_provider("google")
    Service->>Provider: providers.get("google")
    
    Service->>StateStore: create_state(provider, redirect_uri, ...)
    StateStore->>Redis: SETEX oauth:state:{state}
    Redis-->>StateStore: OK
    StateStore-->>Service: (state, code_verifier, code_challenge, expires_at)
    
    Service->>Provider: build_authorization_url(state, code_challenge, ...)
    Provider-->>Service: authorization_url
    
    Service-->>Controller: AuthorizationResponse
    Controller-->>Client: 200 OK + authorization_url
```

**특징:**
- `AuthService`가 `ProviderRegistry`를 직접 생성 (`self.providers = ProviderRegistry(settings)`)
- `StateStore`가 state 생성 + code_verifier + code_challenge 모두 처리
- Controller에서 `Depends(AuthService)` 자동 주입 (암시적)

---

### 2.2 리팩토링 구현

```mermaid
sequenceDiagram
    autonumber
    participant Client
    participant Controller as authorize.py
    participant DI as dependencies.py
    participant Interactor as OAuthAuthorizeInteractor
    participant StateStore as StateStore (Port)
    participant OAuthClient as OAuthClientService (Port)
    participant RedisAdapter as RedisStateStore
    participant OAuthAdapter as OAuthClientImpl
    participant Redis
    
    Note over Client,Redis: 리팩토링: Controller → DI Factory → Interactor → Ports
    
    Client->>Controller: GET /{provider}/authorize
    Controller->>DI: Depends(get_oauth_authorize_interactor)
    
    Note right of DI: 명시적 의존성 조립
    DI->>DI: get_state_store() → RedisStateStore
    DI->>DI: get_oauth_client() → OAuthClientImpl
    DI-->>Controller: OAuthAuthorizeInteractor 인스턴스
    
    Controller->>Interactor: execute(OAuthAuthorizeRequest)
    
    Note right of Interactor: Interactor는 Port만 알고 있음<br/>(구현체 모름)
    
    Interactor->>Interactor: state = secrets.token_urlsafe(32)
    Interactor->>Interactor: code_verifier = secrets.token_urlsafe(64)
    
    Interactor->>StateStore: save(state, OAuthState, ttl=600)
    StateStore->>RedisAdapter: (Port 구현체 호출)
    RedisAdapter->>Redis: SETEX oauth:state:{state}
    Redis-->>RedisAdapter: OK
    RedisAdapter-->>Interactor: None
    
    Interactor->>OAuthClient: get_authorization_url(provider, redirect_uri, state, code_verifier)
    OAuthClient->>OAuthAdapter: (Port 구현체 호출)
    OAuthAdapter->>OAuthAdapter: _compute_code_challenge(code_verifier)
    OAuthAdapter-->>Interactor: authorization_url
    
    Interactor-->>Controller: OAuthAuthorizeResponse
    Controller-->>Client: 200 OK + authorization_url
```

**특징:**
- `dependencies.py`에서 명시적으로 의존성 조립
- Interactor는 `StateStore`, `OAuthClientService` **Port(Protocol)**만 의존
- state/code_verifier 생성 로직이 Interactor로 이동 (Application Layer 책임)

---

## 3. OAuth Callback 플로우 비교

### 3.1 기존 구현

```mermaid
sequenceDiagram
    autonumber
    participant Client
    participant Controller as auth.py
    participant Service as AuthService
    participant StateStore
    participant Provider
    participant httpx as httpx.AsyncClient
    participant UserRepo as UserRepository
    participant TokenService
    participant DB as PostgreSQL
    participant Redis
    
    Note over Client,Redis: 기존: AuthService가 모든 것을 직접 처리
    
    Client->>Controller: GET /google/callback?code=xxx&state=yyy
    Controller->>Service: Depends(AuthService)
    
    Service->>StateStore: consume_state(state)
    StateStore->>Redis: GET + DEL oauth:state:{state}
    Redis-->>Service: state_data
    
    Note right of Service: ❌ httpx 직접 사용<br/>(Infrastructure 노출)
    Service->>httpx: async with httpx.AsyncClient()
    httpx->>Provider: exchange_code(code, code_verifier)
    Provider-->>httpx: tokens
    httpx->>Provider: fetch_profile(tokens)
    Provider-->>httpx: OAuthProfile
    httpx-->>Service: profile
    
    Note right of Service: ❌ Repository 직접 호출
    Service->>UserRepo: upsert_from_profile(profile)
    UserRepo->>DB: INSERT/UPDATE users
    DB-->>Service: user
    
    Service->>TokenService: issue_pair(user_id, provider)
    TokenService-->>Service: token_pair
    
    Note right of Service: ❌ session.commit() 직접 호출
    Service->>DB: session.commit()
    
    Service->>Service: _apply_session_cookies(response, token_pair)
    Service-->>Controller: User
    Controller-->>Client: 302 Redirect + Set-Cookie
```

**문제점:**
- `httpx.AsyncClient`를 Service에서 직접 생성 (Infrastructure 노출)
- `session.commit()` 직접 호출 (트랜잭션 관리 혼재)
- `UserRepository`를 `__init__`에서 직접 생성

---

### 3.2 리팩토링 구현

```mermaid
sequenceDiagram
    autonumber
    participant Client
    participant Controller as callback.py
    participant DI as dependencies.py
    participant Interactor as OAuthCallbackInteractor
    participant StateStore as StateStore (Port)
    participant OAuthClient as OAuthClientService (Port)
    participant UserQuery as UserQueryGateway (Port)
    participant UserCmd as UserCommandGateway (Port)
    participant UserSvc as UserService (Domain)
    participant TokenSvc as TokenService (Port)
    participant Flusher as Flusher (Port)
    participant TxMgr as TransactionManager (Port)
    participant DB as PostgreSQL
    participant Redis
    participant OAuth as OAuth Provider
    
    Note over Client,OAuth: 리팩토링: Interactor → Ports → Adapters
    
    Client->>Controller: GET /{provider}/callback?code=xxx&state=yyy
    Controller->>DI: Depends(get_oauth_callback_interactor)
    DI-->>Controller: OAuthCallbackInteractor (11개 의존성 주입)
    
    Controller->>Interactor: execute(OAuthCallbackRequest)
    
    rect rgb(255, 240, 240)
        Note right of Interactor: 1. State 검증
        Interactor->>StateStore: consume(state)
        StateStore-->>Interactor: OAuthState | None
    end
    
    rect rgb(240, 255, 240)
        Note right of Interactor: 2. OAuth 프로필 조회 (Port 통해)
        Interactor->>OAuthClient: fetch_profile(provider, code, state, code_verifier)
        OAuthClient->>OAuth: exchange_code + fetch_profile
        OAuth-->>OAuthClient: profile
        OAuthClient-->>Interactor: OAuthProfile
    end
    
    rect rgb(240, 240, 255)
        Note right of Interactor: 3. 사용자 조회/생성 (Gateway 통해)
        Interactor->>UserQuery: get_by_provider(provider, provider_user_id)
        UserQuery->>DB: SELECT
        DB-->>Interactor: User | None
        
        alt 신규 사용자
            Interactor->>UserSvc: create_user_from_oauth_profile(...)
            UserSvc-->>Interactor: (User, UserSocialAccount)
            Interactor->>UserCmd: add(user)
        end
    end
    
    rect rgb(255, 255, 240)
        Note right of Interactor: 4. 토큰 발급
        Interactor->>TokenSvc: issue_pair(user_id, provider)
        TokenSvc-->>Interactor: TokenPair
    end
    
    rect rgb(255, 240, 255)
        Note right of Interactor: 5. 트랜잭션 커밋 (Port 통해)
        Interactor->>Flusher: flush()
        Interactor->>TxMgr: commit()
        TxMgr->>DB: COMMIT
    end
    
    Interactor-->>Controller: OAuthCallbackResponse
    Controller->>Controller: set_auth_cookies(response, ...)
    Controller-->>Client: 200 OK + Set-Cookie
```

**개선점:**
- `OAuthClientService` Port가 httpx를 캡슐화
- `UserQueryGateway` / `UserCommandGateway`로 읽기/쓰기 분리 (CQRS)
- `Flusher` + `TransactionManager` Port로 트랜잭션 관리 추상화
- `UserService` (Domain Layer)에서 순수 도메인 로직만 처리

---

## 4. 파일 매핑 테이블

### 4.1 Controller Layer

| 기존 파일 | 리팩토링 파일 | 변경 내용 |
|----------|-------------|----------|
| `presentation/http/controllers/auth.py` (318줄) | `presentation/http/controllers/auth/authorize.py` | Provider별 분리 → 동적 라우팅 |
| ↑ | `presentation/http/controllers/auth/callback.py` | 콜백 로직 분리 |
| ↑ | `presentation/http/controllers/auth/logout.py` | 로그아웃 분리 |
| ↑ | `presentation/http/controllers/auth/refresh.py` | 토큰 갱신 분리 |

### 4.2 Application Layer

| 기존 파일 | 리팩토링 파일 | 변경 내용 |
|----------|-------------|----------|
| `application/services/auth.py` (320줄) | `application/commands/oauth_authorize.py` | authorize() → Interactor |
| ↑ | `application/commands/oauth_callback.py` | login_with_provider() → Interactor |
| ↑ | `application/commands/logout.py` | logout() → Interactor |
| ↑ | `application/commands/refresh_tokens.py` | refresh_session() → Interactor |
| ↑ | `application/queries/validate_token.py` | get_current_user() → QueryService |
| `application/services/state_service.py` | `application/common/ports/state_store.py` | 구현 → Port(인터페이스) |
| `application/services/token_service.py` | `application/common/ports/token_service.py` | 구현 → Port |
| `application/services/token_blacklist.py` | `application/common/ports/token_blacklist.py` | 구현 → Port |
| `application/services/providers/` | `infrastructure/oauth/` | Application → Infrastructure 이동 |

### 4.3 Infrastructure Layer

| 기존 파일 | 리팩토링 파일 | 변경 내용 |
|----------|-------------|----------|
| `infrastructure/repositories/user_repository.py` | `infrastructure/adapters/user_data_mapper_sqla.py` | Repository → Gateway Adapter |
| ↑ | `infrastructure/adapters/user_reader_sqla.py` | 읽기 전용 Adapter 분리 |
| `application/services/state_service.py` | `infrastructure/persistence_redis/state_store_redis.py` | Application → Infrastructure |
| `application/services/token_blacklist.py` | `infrastructure/persistence_redis/token_blacklist_redis.py` | Application → Infrastructure |
| (없음) | `infrastructure/adapters/flusher_sqla.py` | 신규: Flush 추상화 |
| (없음) | `infrastructure/adapters/transaction_manager_sqla.py` | 신규: 트랜잭션 추상화 |

### 4.4 Domain Layer

| 기존 파일 | 리팩토링 파일 | 변경 내용 |
|----------|-------------|----------|
| `domain/models/user.py` (ORM) | `domain/entities/user.py` (순수) | ORM 분리 |
| ↑ | `infrastructure/persistence_postgres/mappings/user.py` | ORM 매핑만 |
| (없음) | `domain/value_objects/user_id.py` | 신규: Value Object |
| (없음) | `domain/value_objects/token_payload.py` | 신규: Value Object |
| (없음) | `domain/services/user_service.py` | 신규: Domain Service |

---

## 5. 의존성 주입 비교

### 5.1 기존: 암시적 DI (FastAPI 자동)

```python
# domains/auth/application/services/auth.py
class AuthService:
    def __init__(
        self,
        session: AsyncSession = Depends(get_db_session),      # ❌ 인프라 직접
        token_service: TokenService = Depends(TokenService),  # ❌ 구현체 직접
        state_store: OAuthStateStore = Depends(OAuthStateStore),
        blacklist: TokenBlacklist = Depends(TokenBlacklist),
        settings: Settings = Depends(get_settings),
    ):
        self.providers = ProviderRegistry(settings)  # ❌ 직접 생성
        self.user_repo = UserRepository(session)     # ❌ 직접 생성
```

**문제:**
- `Depends(ClassName)` → 구현체에 직접 의존
- `ProviderRegistry`, `UserRepository` 직접 생성

---

### 5.2 리팩토링: 명시적 DI (Factory 패턴)

```python
# apps/auth/setup/dependencies.py

# 1. Infrastructure 의존성
async def get_state_store(redis = Depends(get_redis_client)):
    from apps.auth.infrastructure.persistence_redis import RedisStateStore
    return RedisStateStore(redis)  # Port 구현체 반환

def get_oauth_client(registry = Depends(get_oauth_provider_registry)):
    from apps.auth.infrastructure.oauth import OAuthClientImpl
    return OAuthClientImpl(registry)  # Port 구현체 반환

# 2. Use Case 조립
async def get_oauth_authorize_interactor(
    state_store = Depends(get_state_store),      # ✅ Port
    oauth_client = Depends(get_oauth_client),    # ✅ Port
):
    from apps.auth.application.commands import OAuthAuthorizeInteractor
    return OAuthAuthorizeInteractor(
        state_store=state_store,
        oauth_client=oauth_client,
    )

# 3. Controller에서 사용
@router.get("/{provider}/authorize")
async def authorize(
    provider: str,
    interactor: OAuthAuthorizeInteractor = Depends(get_oauth_authorize_interactor),  # ✅ 팩토리 명시
):
    ...
```

**개선:**
- `Depends(get_*_factory)` → 팩토리 함수 명시
- Interactor는 Port(Protocol)만 의존
- 테스트 시 Mock 주입 용이

---

## 6. 체크리스트

### ✅ 완료된 항목

| 기능 | 상태 | 파일 |
|------|------|------|
| OAuth Authorize | ✅ | `commands/oauth_authorize.py` |
| OAuth Callback | ✅ | `commands/oauth_callback.py` |
| Logout | ✅ | `commands/logout.py` |
| Refresh Tokens | ✅ | `commands/refresh_tokens.py` |
| Validate Token | ✅ | `queries/validate_token.py` |
| Google Provider | ✅ | `infrastructure/oauth/google.py` |
| Kakao Provider | ✅ | `infrastructure/oauth/kakao.py` |
| Naver Provider | ✅ | `infrastructure/oauth/naver.py` |
| JWT Token Service | ✅ | `infrastructure/security/jwt_token_service.py` |
| Redis State Store | ✅ | `infrastructure/persistence_redis/state_store_redis.py` |
| Redis Blacklist | ✅ | `infrastructure/persistence_redis/token_blacklist_redis.py` |

### ⚠️ 기존 기능 중 마이그레이션 필요

| 기능 | 기존 위치 | 필요 작업 |
|------|----------|----------|
| `_build_frontend_redirect_url()` | `presentation/http/controllers/auth.py:73-99` | Controller에 추가 |
| `X-Frontend-Origin` 헤더 처리 | `auth.py:65` | Controller에 추가 |
| `oauth_failure_redirect_url` | `auth.py:193-196` | Error Handler에 추가 |
| Provider별 라우터 (`/google`, `/kakao`) | `routers.py` | 동적 라우팅으로 통합됨 ✅ |

---

## 7. 참고

- **기존 코드**: `domains/auth/`
- **리팩토링 코드**: `apps/auth/`
- **관련 문서**: `docs/foundations/16-fastapi-clean-example-analysis.md`

