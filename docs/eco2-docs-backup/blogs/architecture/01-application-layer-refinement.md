# Application 계층 고도화: Auth & Users 도메인 리팩토링

Clean Architecture 초안을 바탕으로 Application 계층을 정제한 과정을 기록합니다.

---

## 1. 문제 정의

### AS-IS 구조

```
apps/auth/application/
├── common/
│   ├── dto/           ← 모든 DTO
│   ├── exceptions/    ← 모든 예외
│   └── ports/         ← 모든 Port (14개 파일)
├── commands/          ← 기능 구분 없이 모든 Command
└── queries/           ← 기능 구분 없이 모든 Query
```

### 문제점

| 문제 | 설명 |
|------|------|
| **common 비대화** | 14개의 Port가 common에 혼재. 기능별 응집도 낮음 |
| **기능 파악 불가** | `blacklist_event_publisher.py`가 token 관련인지 폴더 구조로 알 수 없음 |
| **Service 역할 모호** | Service가 Port를 직접 호출하여 UseCase와 책임 중복 |
| **Query/Command 패턴 불일치** | Query만 Service를 경유, Command는 Port 직접 호출 |

---

## 2. 설계 원칙

### 2.1 구성 요소별 역할

| 구성 요소 | 역할 | 책임 |
|----------|------|------|
| **Port** | 외부 시스템 인터페이스 | Infrastructure 계층과의 계약 정의 |
| **Service** | 도메인 로직 캡슐화 | 순수 비즈니스 로직 또는 외부 시스템 Facade |
| **Command** | Write UseCase | 상태 변경 오케스트레이션 |
| **Query** | Read UseCase | 조회 오케스트레이션 |

### 2.2 Port 호출 원칙

```
원칙: UseCase(Command/Query)가 Port를 직접 호출한다.
이유: 트랜잭션 경계, flush, retry, 멱등성 등 애플리케이션 제어 흐름을 UseCase가 관장
```

**허용되는 예외: Facade Service**

Service가 여러 Port를 조합하여 하나의 개념을 캡슐화하는 경우에만 Port 보유를 허용한다.

| 판단 기준 | Facade | 일반 Service |
|----------|--------|-------------|
| 여러 Port를 조합하여 하나의 개념을 형성하는가? | O | X |
| 조합이 분리되면 의미가 소실되는가? | O | X |
| UseCase가 세부 구현을 알아야 하는가? | X | O |

---

## 3. 폴더 구조 설계

### 3.1 기능별 폴더 분리

**AS-IS:**
```
common/ports/
├── blacklist_event_publisher.py  ← token 관련
├── state_store.py                ← oauth 관련
├── token_service.py              ← token 관련
├── user_query_gateway.py         ← users 관련
└── ... (14개 파일)
```

**TO-BE:**
```
oauth/ports/      ← OAuth 인증 관련 Port
token/ports/      ← 토큰 관리 관련 Port
users/ports/      ← 사용자 관리 관련 Port
audit/ports/      ← 감사 로그 관련 Port
common/ports/     ← 트랜잭션 등 진짜 공통 Port만
```

### 3.2 폴더 구조로 기능 역할 표현

기능별 폴더를 펼쳤을 때, 해당 기능이 **어떤 책임을 가지는지** 즉시 파악할 수 있어야 한다.

#### oauth 폴더 구조

```
oauth/
├── commands/
│   ├── authorize.py         ← OAuth 인증 URL 생성
│   └── callback.py          ← OAuth 콜백 처리
├── dto/
│   └── oauth.py             ← OAuthAuthorizeRequest, OAuthCallbackResponse 등
├── exceptions/
│   └── oauth.py             ← InvalidStateError, OAuthProviderError
├── ports/
│   ├── provider_gateway.py  ← OAuth 프로바이더 통신
│   └── state_store.py       ← CSRF state 저장/검증
└── services/
    └── oauth_flow_service.py  ← OAuth 플로우 Facade
```

**읽어낼 수 있는 정보:**

| 항목 | 판단 |
|------|------|
| `commands/` 존재, `queries/` 부재 | **Write 전용 기능** (OAuth는 인증 "수행"만 함) |
| `services/oauth_flow_service.py` | 복잡한 플로우를 캡슐화하는 Facade 존재 |
| `ports/provider_gateway.py` | 외부 OAuth 프로바이더와 통신 |
| `ports/state_store.py` | CSRF 방어용 state 관리 |
| `exceptions/oauth.py` | OAuth 특화 예외 (InvalidStateError 등) |

#### token 폴더 구조

```
token/
├── commands/
│   ├── logout.py            ← 로그아웃 (토큰 폐기)
│   └── refresh.py           ← 토큰 갱신
├── dto/
│   └── token.py             ← LogoutRequest, RefreshTokensResponse 등
├── exceptions/
│   └── auth.py              ← AuthenticationError
├── ports/
│   ├── issuer.py            ← JWT 발급/검증
│   ├── blacklist_store.py   ← 블랙리스트 조회
│   ├── session_store.py     ← 세션 저장/조회
│   └── blacklist_event_publisher.py  ← 블랙리스트 이벤트 발행
├── queries/
│   └── validate.py          ← 토큰 유효성 검증
└── services/
    └── token_service.py     ← 토큰 시스템 Facade
```

**읽어낼 수 있는 정보:**

| 항목 | 판단 |
|------|------|
| `commands/` + `queries/` 모두 존재 | **Read/Write 모두 수행** |
| `queries/validate.py` | 토큰 검증은 조회 성격 (상태 변경 없음) |
| `commands/logout.py`, `commands/refresh.py` | 토큰 폐기/갱신은 상태 변경 |
| `ports/blacklist_event_publisher.py` | 메시지 큐로 이벤트 발행 (비동기 처리) |
| `services/token_service.py` | issuer + session + blacklist 조합 Facade |

### 3.3 queries 유무로 Read/Write 판단

```
queries/ 존재 → Read UseCase 보유
queries/ 부재 → Write 전용 기능
```

| 도메인 | commands | queries | 판단 |
|--------|----------|---------|------|
| **oauth** | O | X | Write 전용 (인증 수행) |
| **token** | O | O | Read + Write (검증 + 폐기/갱신) |
| **audit** | X | X | 보조 기능 (Service만 제공) |
| **profile** (users) | O | O | Read + Write (조회 + 수정/삭제) |
| **character** (users) | X | O | Read 전용 (캐릭터 조회) |

---

## 4. Exceptions 분리

### AS-IS

```python
# common/exceptions/auth.py에 모든 예외 집중
class InvalidStateError(ApplicationError): ...      # oauth 관련
class OAuthProviderError(ApplicationError): ...     # oauth 관련
class AuthenticationError(ApplicationError): ...   # token 관련
class UserServiceUnavailableError(ApplicationError): ...  # users 관련
```

### TO-BE

```
oauth/exceptions/oauth.py      ← InvalidStateError, OAuthProviderError
token/exceptions/auth.py       ← AuthenticationError
users/exceptions/gateway.py    ← UserServiceUnavailableError
common/exceptions/base.py      ← ApplicationError (베이스만)
common/exceptions/gateway.py   ← GatewayError, DataMapperError (인프라 공통)
```

**원칙:** 예외는 발생 도메인에 위치시킨다. common에는 베이스 예외만 둔다.

---

## 5. Service 역할 정의

### 5.1 Facade Service (Port 보유 허용)

여러 Port를 조합하여 하나의 개념을 캡슐화하는 Service.

#### OAuthFlowService

```python
class OAuthFlowService:
    def __init__(self, state_store, provider_gateway):
        self._state_store = state_store
        self._provider_gateway = provider_gateway

    async def validate_and_fetch_profile(self, provider, code, state, ...):
        # 1. State 검증 및 소비 (Redis)
        state_data = await self._state_store.consume(state)
        if state_data is None:
            raise InvalidStateError()
        
        # 2. OAuth 프로바이더 통신 (External HTTP)
        profile = await self._provider_gateway.fetch_profile(...)
        
        # 3. 결과 반환
        return OAuthFlowResult(profile, state_data)
```

**Facade 판단:**
- `state consume` + `provider 통신` + `profile fetch`가 "OAuth 인증"이라는 하나의 단위
- 분리 시 UseCase가 OAuth 프로토콜 세부사항을 알아야 함
- 캡슐화가 적절함

#### TokenService

```python
class TokenService:
    def __init__(self, issuer, session_store, blacklist_store):
        self._issuer = issuer
        self._session_store = session_store
        self._blacklist_store = blacklist_store

    async def issue_and_register(self, user_id, provider, ...):
        # 1. 토큰 발급
        token_pair = self._issuer.issue_pair(user_id=user_id, provider=provider)
        
        # 2. 세션 등록
        await self._session_store.register(user_id=user_id, jti=token_pair.refresh_jti, ...)
        
        return TokenIssuanceResult(...)

    async def is_blacklisted(self, jti):
        return await self._blacklist_store.contains(jti)
```

**Facade 판단:**
- `토큰 발급` + `세션 등록`이 항상 함께 수행되어야 함
- 블랙리스트 확인도 토큰 검증의 일부
- "토큰 관리"라는 개념으로 캡슐화

### 5.2 순수 Service (Port 미보유)

Port 없이 순수 비즈니스 로직만 수행하는 Service.

#### LoginAuditService

**AS-IS (문제):**
```python
class LoginAuditService:
    def __init__(self, audit_gateway):  # Port 의존
        self._audit_gateway = audit_gateway
    
    def record_login(self, user_id, provider, access_jti, ...):
        audit = LoginAudit(id=uuid4(), user_id=user_id, ...)
        self._audit_gateway.add(audit)  # Service가 Port 호출
        return audit
```

**TO-BE (개선):**
```python
class LoginAuditService:
    # Port 의존성 없음
    
    def create_login_audit(self, user_id, provider, access_jti, ...) -> LoginAudit:
        return LoginAudit(
            id=uuid4(),
            user_id=user_id,
            provider=provider,
            jti=access_jti,
            issued_at=datetime.now(timezone.utc),
            ...
        )
```

**UseCase에서 Port 직접 호출:**
```python
# OAuthCallbackInteractor
audit = self._audit_service.create_login_audit(...)
self._audit_gateway.add(audit)  # UseCase가 Port 호출
```

**판단:**
- 단일 Port만 사용 (조합 없음)
- 엔티티 생성과 저장은 논리적으로 분리 가능
- UseCase가 직접 제어해도 문제없음

#### ProfileBuilder

```python
class ProfileBuilder:
    def __init__(self, user_service: UserService):
        self._user_service = user_service  # Domain Service만 의존
    
    def build(self, user, accounts, current_provider) -> UserProfile:
        display_name = self._user_service.resolve_display_name(user)
        nickname = self._user_service.resolve_nickname(user, display_name)
        
        return UserProfile(
            display_name=display_name,
            nickname=nickname,
            ...
        )
```

**판단:**
- Port 의존 없음
- 순수 DTO 구성 로직
- 여러 UseCase에서 재사용 가능

### 5.3 삭제된 Service

Port만 호출하던 Service는 삭제하고 UseCase가 직접 Port를 호출하도록 변경.

| 삭제된 Service | 이유 |
|---------------|------|
| `ProfileQueryService` | Port 호출 + DTO 구성만 수행. UseCase와 책임 중복 |
| `CharacterQueryService` | Port 호출 + DTO 변환만 수행. UseCase와 책임 중복 |

---

## 6. Query 패턴 통일

### AS-IS (문제)

```python
# Query가 Service를 경유
class GetProfileQuery:
    def __init__(self, profile_service: ProfileQueryService):
        self._profile_service = profile_service
    
    async def execute(self, user_id, provider):
        return await self._profile_service.get_user_profile(user_id, provider)

# Service가 Port 호출 → UseCase와 책임 중복
class ProfileQueryService:
    def __init__(self, profile_gateway, social_account_gateway, profile_builder):
        ...
    
    async def get_user_profile(self, user_id, provider):
        user = await self._profile_gateway.get_by_id(user_id)
        accounts = await self._social_account_gateway.list_by_user_id(user_id)
        return self._profile_builder.build(user, accounts, provider)
```

### TO-BE (개선)

```python
class GetProfileQuery:
    def __init__(
        self,
        # Ports (인프라)
        profile_gateway: ProfileQueryGateway,
        social_account_gateway: SocialAccountQueryGateway,
        # Services (순수 로직)
        profile_builder: ProfileBuilder,
    ):
        self._profile_gateway = profile_gateway
        self._social_account_gateway = social_account_gateway
        self._profile_builder = profile_builder

    async def execute(self, user_id: UUID, provider: str) -> UserProfile:
        # 1. UseCase가 직접 Port 호출
        user = await self._profile_gateway.get_by_id(user_id)
        if user is None:
            raise UserNotFoundError(user_id)
        
        # 2. UseCase가 직접 Port 호출
        accounts = await self._social_account_gateway.list_by_user_id(user_id)
        
        # 3. Service는 순수 로직만
        return self._profile_builder.build(user, accounts, provider)
```

**변경 사항:**
- ProfileQueryService 삭제
- Query가 직접 Port 호출
- ProfileBuilder는 순수 DTO 구성만 담당

---

## 7. 더미 코드 삭제

| 파일 | 삭제 이유 |
|------|----------|
| `common/ports/outbox_gateway.py` | auth_relay 서비스가 outbox 처리 담당. auth에서 미사용 |
| `infrastructure/persistence_redis/outbox_redis.py` | 위와 동일. 구현체도 미사용 |

---

## 8. 최종 구조

### Auth 도메인

```
apps/auth/application/
├── common/
│   ├── exceptions/
│   │   ├── base.py              ← ApplicationError
│   │   └── gateway.py           ← GatewayError, DataMapperError
│   ├── ports/
│   │   ├── flusher.py
│   │   └── transaction_manager.py
│   └── services/
│       └── oauth_client.py      ← Protocol
│
├── oauth/                        ← Write 전용 (queries/ 없음)
│   ├── commands/
│   │   ├── authorize.py
│   │   └── callback.py
│   ├── dto/
│   ├── exceptions/
│   ├── ports/
│   │   ├── provider_gateway.py
│   │   └── state_store.py
│   └── services/
│       └── oauth_flow_service.py  ← Facade
│
├── token/                        ← Read + Write (queries/ 존재)
│   ├── commands/
│   │   ├── logout.py
│   │   └── refresh.py
│   ├── dto/
│   ├── exceptions/
│   ├── ports/
│   │   ├── issuer.py
│   │   ├── blacklist_store.py
│   │   ├── session_store.py
│   │   └── blacklist_event_publisher.py
│   ├── queries/
│   │   └── validate.py
│   └── services/
│       └── token_service.py      ← Facade
│
├── users/
│   ├── exceptions/
│   └── ports/
│
└── audit/                        ← 보조 기능 (commands/, queries/ 없음)
    ├── ports/
    └── services/
        └── login_audit_service.py  ← 순수 엔티티 팩토리
```

### Users 도메인

```
apps/users/application/
├── common/
│   ├── exceptions/
│   │   └── base.py
│   └── ports/
│       └── transaction_manager.py
│
├── profile/                      ← Read + Write
│   ├── commands/
│   │   ├── update_profile.py
│   │   └── delete_user.py
│   ├── dto/
│   ├── exceptions/
│   ├── ports/
│   ├── queries/
│   │   └── get_profile.py
│   └── services/
│       └── profile_builder.py    ← 순수 DTO 구성
│
├── character/                    ← Read 전용 (commands/ 없음)
│   ├── dto/
│   ├── ports/
│   └── queries/
│       └── get_characters.py
│
└── identity/
    └── ports/
```

---

## 9. 요약

| 원칙 | 적용 |
|------|------|
| Port 호출은 UseCase가 직접 | Command/Query가 Port 호출, Service는 순수 로직만 |
| Facade Service만 Port 보유 | OAuthFlowService, TokenService |
| 순수 Service는 Port 미보유 | ProfileBuilder, LoginAuditService |
| 도메인별 폴더 분리 | oauth/, token/, users/, audit/ |
| common은 공통만 | Flusher, TransactionManager, ApplicationError |
| queries 유무로 Read/Write 판단 | queries/ 존재 시 Read UseCase 보유 |
