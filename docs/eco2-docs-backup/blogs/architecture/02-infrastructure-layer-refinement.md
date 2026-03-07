# Clean Architecture #8: Infrastructure Layer 정제

> Application Layer 정제에 이어 Infrastructure 계층을 기술 단위로 분리하고, 하드코딩된 값을 상수화하며, gRPC의 배치를 재정의한 과정을 기록합니다.

---

## 1. 계층별 분류 철학

Application Layer와 Infrastructure Layer는 서로 다른 기준으로 폴더를 분류한다.

### 1.1 Application Layer: 기능(Feature) 기준

```
application/
├── oauth/          ← "OAuth 인증"이라는 비즈니스 기능
├── token/          ← "토큰 관리"라는 비즈니스 기능
├── users/          ← "사용자 관리"라는 비즈니스 기능
└── audit/          ← "감사 로그"라는 비즈니스 기능
```

| 관점           | 설명                                                              |
| -------------- | ----------------------------------------------------------------- |
| **분류 기준**  | 비즈니스 기능(Feature), 도메인 개념                               |
| **질문**       | "이 시스템은 **무엇을** 하는가?"                                  |
| **가시성**     | 폴더 구조만으로 시스템의 비즈니스 역량 파악                       |
| **응집 단위**  | 하나의 기능에 필요한 Port, Service, Command, Query, DTO, Exception |

**폴더 구조가 드러내는 정보:**

```
token/
├── commands/    ← Write 연산 존재 (logout, refresh)
├── queries/     ← Read 연산 존재 (validate)
├── ports/       ← 4개의 외부 의존성 (issuer, blacklist, session, event)
└── services/    ← Facade 존재 (복잡한 조합 캡슐화)
```

→ `commands/`와 `queries/` 유무로 Read/Write 특성 즉시 파악

### 1.2 Infrastructure Layer: 기술(Technology) 기준

```
infrastructure/
├── persistence_postgres/   ← PostgreSQL 기술
├── persistence_redis/      ← Redis 기술
├── grpc/                   ← gRPC 프로토콜
├── messaging/              ← RabbitMQ 메시징
├── oauth/                  ← OAuth 프로토콜/HTTP
└── security/               ← JWT/암호화
```

| 관점           | 설명                                                              |
| -------------- | ----------------------------------------------------------------- |
| **분류 기준**  | 기술 스택, 통신 방식, 외부 시스템                                 |
| **질문**       | "이 시스템은 **어떻게** 외부와 연결되는가?"                       |
| **가시성**     | 폴더 구조만으로 기술 스택 파악                                    |
| **응집 단위**  | 동일 기술을 사용하는 어댑터, 매핑, 클라이언트, 상수               |

**폴더 구조가 드러내는 정보:**

```
persistence_postgres/
├── adapters/    ← Port 구현체들 (6개 Gateway)
├── mappings/    ← ORM 매핑 정의
├── session.py   ← 커넥션 관리
└── registry.py  ← 매퍼 등록
```

→ PostgreSQL과 관련된 모든 관심사가 한 곳에 집중

### 1.3 분류 철학 비교

| 관점               | Application Layer       | Infrastructure Layer           |
| ------------------ | ----------------------- | ------------------------------ |
| **분류 축**        | 기능(What)              | 기술(How)                      |
| **폴더 이름**      | 비즈니스 용어           | 기술 스택 이름                 |
| **변경 이유**      | 비즈니스 요구사항 변경  | 기술 스택 교체/추가            |
| **의존 방향**      | Port(인터페이스) 정의   | Port 구현체 제공               |
| **테스트 전략**    | Mock Port로 단위 테스트 | 실제 인프라로 통합 테스트      |

### 1.4 왜 다른 기준을 사용하는가?

**Application Layer는 "안정적인 비즈니스 개념"을 중심으로:**

- 비즈니스 로직은 기술보다 천천히 변한다
- "OAuth 인증"이라는 개념은 HTTP→gRPC로 바뀌어도 유지된다
- 기능 단위 응집으로 **변경 영향 범위 최소화**

**Infrastructure Layer는 "교체 가능한 기술 구현"을 중심으로:**

- Redis→Memcached 전환 시 `persistence_redis/` 폴더만 교체
- PostgreSQL→MySQL 전환 시 `persistence_postgres/` 폴더만 교체
- 기술 단위 응집으로 **기술 교체 용이성 확보**

```
[Application]                    [Infrastructure]
    │                                   │
    │  기능별 Port 인터페이스 정의      │  기술별 Adapter 구현 제공
    │       oauth/ports/                │       persistence_redis/adapters/
    │       token/ports/                │       persistence_postgres/adapters/
    │       users/ports/                │       grpc/adapters/
    │                                   │
    ▼                                   ▼
   "무엇을 할 것인가"              "어떻게 구현할 것인가"
```

---

## 2. 문제 정의

### 2.1 AS-IS 구조 (Auth)

```
apps/auth/infrastructure/
├── adapters/                  ← 기술 무관하게 어댑터 혼재
│   ├── flusher_sqla.py
│   ├── user_reader_sqla.py
│   └── users_management_grpc_adapter.py
├── grpc/
│   ├── client.py
│   └── users_pb2.py
├── oauth/
│   └── providers/*.py
├── persistence_postgres/
│   └── mappings/*.py
├── persistence_redis/
│   └── state_store_redis.py   ← 어댑터가 기술 폴더 최상위에 혼재
└── security/
    └── jwt_token_service.py
```

### 2.2 AS-IS 구조 (Users)

```
apps/users/infrastructure/
├── grpc/                      ← gRPC 서버가 infrastructure에 위치
│   ├── server.py
│   └── servicers/
│       └── users_servicer.py  ← DB 직접 접근하는 Fat Servicer
└── persistence_postgres/
    └── adapters/
        └── user_gateway_sqla.py  ← 단수형 네이밍
```

### 2.3 문제점

| 문제                     | 설명                                                              |
| ------------------------ | ----------------------------------------------------------------- |
| **어댑터 배치 불일치**   | 일부는 최상위 `adapters/`, 일부는 기술별 폴더 내 위치              |
| **하드코딩된 상수**      | Redis key prefix, schema 이름이 코드 전체에 산재                  |
| **gRPC 서버 위치 모호**  | 전달 계층(delivery)인 gRPC 서버가 infrastructure에 위치           |
| **Fat Servicer**         | gRPC servicer가 DB 직접 접근, 트랜잭션 관리까지 수행              |
| **네이밍 불일치**        | `user_` vs `users_` 혼용                                          |

---

## 3. 설계 원칙

### 3.1 기술별 폴더 내 역할 분리

```
persistence_postgres/
├── adapters/      ← Port 구현체 (Gateway 어댑터)
├── mappings/      ← ORM 매핑 정의
├── constants.py   ← 스키마/테이블 상수
├── session.py     ← 커넥션/세션 팩토리
└── registry.py    ← 매퍼 등록 (Imperative Mapping)
```

### 3.2 어댑터 명명 규칙

```
패턴: {도메인}_{port_역할}_{기술}.py

예시:
  users_query_gateway_sqla.py      ← users 도메인, 조회 게이트웨이, SQLAlchemy
  users_management_gateway_grpc.py ← users 도메인, 관리 게이트웨이, gRPC
  token_blacklist_redis.py         ← token 도메인, 블랙리스트, Redis
```

### 3.3 gRPC 배치 원칙

| 역할           | 위치               | 이유                                        |
| -------------- | ------------------ | ------------------------------------------- |
| gRPC **서버**  | `presentation/`    | HTTP와 동등한 전달 계층 (delivery mechanism) |
| gRPC **클라이언트** | `infrastructure/`  | 외부 서비스 호출은 infrastructure 관심사    |

### 3.4 Thin Adapter 패턴 (gRPC Servicer)

```
gRPC Servicer의 책임:
  1. Request → DTO 변환
  2. UseCase.execute(dto) 호출
  3. Result → Protobuf 응답 변환
  4. 예외 → gRPC status 매핑

금지:
  - DB 직접 접근
  - 트랜잭션 관리
  - 비즈니스 로직
```

---

## 4. Auth Infrastructure 정제

### 4.1 TO-BE 구조

```
apps/auth/infrastructure/
├── common/
│   └── adapters/
│       └── users_id_generator_uuid.py   ← 기술 무관 어댑터
│
├── grpc/                                 ← gRPC 클라이언트 (users 서비스 호출)
│   ├── adapters/
│   │   └── users_management_gateway_grpc.py
│   ├── client.py                         ← gRPC 채널/스텁 관리
│   └── schemas/
│       ├── users_pb2.py
│       └── users_pb2_grpc.py
│
├── messaging/
│   └── adapters/
│       └── blacklist_event_publisher_rabbitmq.py
│
├── oauth/
│   ├── client.py                         ← OAuthClientService 구현체
│   ├── providers/
│   │   ├── base.py
│   │   ├── google.py
│   │   ├── kakao.py
│   │   └── naver.py
│   └── registry.py                       ← Provider DI 레지스트리
│
├── persistence_postgres/
│   ├── adapters/
│   │   ├── flusher_sqla.py
│   │   ├── login_audit_gateway_sqla.py
│   │   ├── social_account_query_gateway_sqla.py
│   │   ├── transaction_manager_sqla.py
│   │   ├── users_command_gateway_sqla.py
│   │   └── users_query_gateway_sqla.py
│   ├── mappings/
│   │   ├── login_audit.py
│   │   ├── users_social_account.py
│   │   └── users.py
│   ├── registry.py
│   └── session.py
│
├── persistence_redis/
│   ├── adapters/
│   │   ├── state_store_redis.py
│   │   ├── token_blacklist_redis.py
│   │   └── users_token_store_redis.py
│   ├── client.py
│   └── constants.py                      ← Redis key prefix 상수
│
└── security/
    └── jwt_token_service.py
```

### 4.2 Redis 상수 파일

**AS-IS (하드코딩):**

```python
# state_store_redis.py
key = f"oauth:state:{state}"

# token_blacklist_redis.py
key = f"blacklist:{jti}"

# users_token_store_redis.py
user_key = f"user:tokens:{user_id}"
meta_key = f"token:meta:{jti}"
```

**TO-BE (상수화):**

```python
# constants.py
STATE_KEY_PREFIX = "oauth:state:"
BLACKLIST_KEY_PREFIX = "blacklist:"
USER_TOKENS_KEY_PREFIX = "user:tokens:"
TOKEN_META_KEY_PREFIX = "token:meta:"

# state_store_redis.py
from apps.auth.infrastructure.persistence_redis.constants import STATE_KEY_PREFIX

key = f"{STATE_KEY_PREFIX}{state}"
```

### 4.3 gRPC 클라이언트 구조

Auth 도메인의 gRPC는 **클라이언트** 역할:

```
grpc/
├── client.py                              ← gRPC 채널, 스텁, Circuit Breaker
├── adapters/
│   └── users_management_gateway_grpc.py   ← Port 구현체
└── schemas/
    ├── users_pb2.py                       ← Protobuf 정의
    └── users_pb2_grpc.py
```

**UsersManagementGatewayGrpc:**

```python
class UsersManagementGatewayGrpc(UsersManagementGateway):
    """gRPC를 통한 UsersManagementGateway 구현."""

    def __init__(self, client: UsersGrpcClient) -> None:
        self._client = client

    async def get_or_create_from_oauth(self, ...) -> OAuthUserResult | None:
        # gRPC 호출
        response = await self._client.get_or_create_from_oauth(...)
        
        # Response → Domain DTO 변환
        return OAuthUserResult(
            user_id=UUID(response.user.id),
            username=response.user.username or None,
            ...
        )
```

---

## 5. Users Infrastructure 정제

### 5.1 TO-BE 구조

```
apps/users/
├── infrastructure/                       ← 외부 시스템 구현체만
│   └── persistence_postgres/
│       ├── adapters/
│       │   ├── identity_gateway_sqla.py
│       │   ├── social_account_gateway_sqla.py
│       │   ├── transaction_manager_sqla.py
│       │   ├── users_character_gateway_sqla.py
│       │   └── users_gateway_sqla.py
│       ├── mappings/
│       │   ├── user.py
│       │   ├── user_character.py
│       │   └── user_social_account.py
│       ├── constants.py                  ← 스키마/테이블 상수
│       └── session.py
│
└── presentation/                         ← 전달 계층
    ├── grpc/                             ← gRPC 서버
    │   ├── server.py
    │   ├── servicers/
    │   │   └── users_servicer.py
    │   ├── users_pb2.py
    │   └── users_pb2_grpc.py
    └── http/
        ├── controllers/
        └── schemas/
```

### 5.2 PostgreSQL 상수 파일

```python
# constants.py
USERS_SCHEMA = "users"
AUTH_SCHEMA = "auth"  # cross-schema query용

ACCOUNTS_TABLE = "accounts"
SOCIAL_ACCOUNTS_TABLE = "social_accounts"
USER_CHARACTERS_TABLE = "user_characters"
```

```python
# mappings/user.py
from apps.users.infrastructure.persistence_postgres.constants import (
    USERS_SCHEMA,
    ACCOUNTS_TABLE,
)

users_table = Table(
    ACCOUNTS_TABLE,
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True),
    ...,
    schema=USERS_SCHEMA,
)
```

### 5.3 gRPC 서버 → Presentation 이동

**이유:**

| 관점                 | 설명                                                   |
| -------------------- | ------------------------------------------------------ |
| **일관성**           | HTTP controllers도 `presentation/http/`에 위치        |
| **가시성**           | 폴더 구조만으로 지원 프로토콜 파악 (HTTP, gRPC)       |
| **역할 명확화**      | gRPC 서버는 "전달 계층"이지 "외부 시스템 구현"이 아님 |

```
presentation/
├── grpc/      ← gRPC 프로토콜
└── http/      ← HTTP 프로토콜
```

### 5.4 Fat Servicer → Thin Adapter 리팩토링

**AS-IS (Fat Servicer):**

```python
class UsersServicer(users_pb2_grpc.UsersServiceServicer):
    def __init__(self, session_factory):
        self._session_factory = session_factory

    async def GetOrCreateFromOAuth(self, request, context):
        async with self._session_factory() as session:
            # DB 직접 쿼리
            result = await session.execute(
                select(User).where(...)
            )
            user = result.scalar_one_or_none()
            
            if user is None:
                # 직접 생성
                user = User(...)
                session.add(user)
                await session.commit()
            
            # Protobuf 변환
            return users_pb2.Response(...)
```

**TO-BE (Thin Adapter):**

```python
class UsersServicer(users_pb2_grpc.UsersServiceServicer):
    """Thin Adapter - UseCase 호출만 담당."""

    def __init__(
        self,
        session_factory,
        use_case_factory: "GrpcUseCaseFactory",
    ) -> None:
        self._session_factory = session_factory
        self._use_case_factory = use_case_factory

    async def GetOrCreateFromOAuth(self, request, context):
        try:
            # 1. Request → DTO 변환
            dto = OAuthUserRequest(
                provider=request.provider,
                provider_user_id=request.provider_user_id,
                email=request.email if request.HasField("email") else None,
                ...
            )

            # 2. 세션 생성 및 UseCase 실행
            async with self._session_factory() as session:
                command = self._use_case_factory.create_get_or_create_from_oauth_command(session)
                result = await command.execute(dto)
                await session.commit()

            # 3. Result → Protobuf 응답 변환
            return users_pb2.GetOrCreateFromOAuthResponse(
                user=self._result_to_user_proto(result),
                is_new_user=result.is_new_user,
            )

        except ValueError as e:
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, str(e))
        except Exception:
            await context.abort(grpc.StatusCode.INTERNAL, "Internal server error")
```

### 5.5 GrpcUseCaseFactory

gRPC는 FastAPI `Depends`를 사용할 수 없으므로 팩토리 패턴 적용:

```python
class GrpcUseCaseFactory:
    """gRPC 서버용 UseCase 팩토리."""

    def __init__(self, session_factory) -> None:
        self._session_factory = session_factory

    def create_get_or_create_from_oauth_command(
        self,
        session: AsyncSession,
    ) -> GetOrCreateFromOAuthCommand:
        return GetOrCreateFromOAuthCommand(
            query_gateway=SqlaIdentityQueryGateway(session),
            command_gateway=SqlaIdentityCommandGateway(session),
            transaction_manager=SqlaTransactionManager(session),
        )

    def create_get_user_query(
        self,
        session: AsyncSession,
    ) -> GetUserQuery:
        return GetUserQuery(
            query_gateway=SqlaUsersQueryGateway(session),
        )
```

---

## 6. gRPC 배치 비교

| 도메인 | gRPC 역할     | 위치              | 이유                           |
| ------ | ------------- | ----------------- | ------------------------------ |
| Auth   | **클라이언트** | `infrastructure/` | users 서비스 호출 (외부 의존성) |
| Users  | **서버**       | `presentation/`   | 요청 수신 (전달 계층)          |

---

## 7. 설정값 외부화

### 7.1 OAuth 클라이언트 타임아웃

**AS-IS:**

```python
async with httpx.AsyncClient(timeout=10.0) as client:
```

**TO-BE:**

```python
# settings.py
class Settings(BaseSettings):
    oauth_client_timeout_seconds: float = Field(default=10.0)

# client.py
class OAuthClientImpl:
    def __init__(self, registry, timeout_seconds: float) -> None:
        self._timeout = timeout_seconds

    async def fetch_profile(self, ...):
        async with httpx.AsyncClient(timeout=self._timeout) as client:
```

### 7.2 토큰 만료 시간

**AS-IS:**

```python
estimated_issued_at = current_time - timedelta(seconds=900)  # 하드코딩
```

**TO-BE:**

```python
estimated_issued_at = current_time - timedelta(
    seconds=self._issuer.access_token_expire_minutes * 60
)
```

---

## 8. 최종 구조 비교

### Auth Infrastructure

| 카테고리          | AS-IS                           | TO-BE                              |
| ----------------- | ------------------------------- | ---------------------------------- |
| 어댑터 위치       | 최상위 `adapters/` 혼재        | 기술별 `{tech}/adapters/`         |
| 상수              | 코드 내 하드코딩               | `constants.py` 중앙화             |
| gRPC              | `grpc/` (역할 불명확)          | `grpc/adapters/`, `grpc/client.py` |
| 네이밍            | `user_reader_sqla.py`          | `users_query_gateway_sqla.py`     |

### Users Infrastructure/Presentation

| 카테고리          | AS-IS                                | TO-BE                                  |
| ----------------- | ------------------------------------ | -------------------------------------- |
| gRPC 서버 위치    | `infrastructure/grpc/`               | `presentation/grpc/`                   |
| Servicer 패턴     | Fat Servicer (DB 직접 접근)         | Thin Adapter (UseCase 호출)           |
| DI 방식           | 없음                                 | GrpcUseCaseFactory                     |
| 네이밍            | `user_gateway_sqla.py`              | `users_gateway_sqla.py`               |

---

## 9. 요약

| 원칙                              | 적용                                              |
| --------------------------------- | ------------------------------------------------- |
| 어댑터는 기술별 폴더 내 배치      | `persistence_postgres/adapters/`, `grpc/adapters/` |
| 상수는 기술별 `constants.py`     | Redis key prefix, PostgreSQL schema              |
| gRPC 서버는 presentation          | `users/presentation/grpc/`                       |
| gRPC 클라이언트는 infrastructure  | `auth/infrastructure/grpc/`                      |
| Servicer는 Thin Adapter           | Request→DTO→UseCase→Result→Response             |
| 네이밍은 도메인 복수형            | `users_*`, `users.py`                            |
| 설정값은 Settings에서 주입        | `oauth_client_timeout_seconds`, 토큰 만료시간    |

