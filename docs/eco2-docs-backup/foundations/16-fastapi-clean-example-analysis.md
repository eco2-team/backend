# FastAPI Clean Example 분석 보고서

> 참조: [ivan-borovets/fastapi-clean-example](https://github.com/ivan-borovets/fastapi-clean-example)
> 
> 작성일: 2025-12-30

---

## 근원 기술 (Foundational Concepts)

이 프로젝트에서 사용하는 아키텍처 패턴들의 원본 출처와 핵심 개념입니다.

### Clean Architecture

| 항목 | 내용 |
|------|------|
| **창시자** | Robert C. Martin ("Uncle Bob") |
| **발표** | 2012년 8월 블로그 → 2017년 책 출간 |
| **원본** | [The Clean Architecture](https://blog.cleancoder.com/uncle-bob/2012/08/13/the-clean-architecture.html) |
| **책** | *Clean Architecture: A Craftsman's Guide to Software Structure and Design* (2017) |

**핵심 원칙:**
- **의존성 규칙 (Dependency Rule)**: 의존성은 항상 안쪽(고수준)으로만 향한다
- **독립성**: Framework, UI, Database, 외부 에이전시로부터 독립적
- **동심원 구조**: Entities → Use Cases → Interface Adapters → Frameworks & Drivers

```
┌─────────────────────────────────────────────────────────────────┐
│                    Frameworks & Drivers                         │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │                  Interface Adapters                      │   │
│  │  ┌─────────────────────────────────────────────────┐    │   │
│  │  │                  Use Cases                       │    │   │
│  │  │  ┌─────────────────────────────────────────┐    │    │   │
│  │  │  │              Entities                    │    │    │   │
│  │  │  │       (Enterprise Business Rules)        │    │    │   │
│  │  │  └─────────────────────────────────────────┘    │    │   │
│  │  │        (Application Business Rules)              │    │   │
│  │  └─────────────────────────────────────────────────┘    │   │
│  │              (Controllers, Gateways, Presenters)         │   │
│  └─────────────────────────────────────────────────────────┘   │
│                    (Web, DB, Devices, UI, External)             │
└─────────────────────────────────────────────────────────────────┘
                              ▲
                              │ 의존성 방향: 항상 안쪽으로
```

---

### Hexagonal Architecture (Ports & Adapters)

| 항목 | 내용 |
|------|------|
| **창시자** | Alistair Cockburn |
| **발표** | 2005년 |
| **원본** | [Hexagonal Architecture](https://alistair.cockburn.us/hexagonal-architecture/) |
| **별명** | Ports and Adapters Pattern |

**핵심 개념:**
- **Port**: 애플리케이션이 외부와 통신하는 인터페이스 (추상)
- **Adapter**: Port의 구체적 구현 (기술 의존적)
- **Driving Adapters**: 애플리케이션을 호출하는 쪽 (HTTP Controller, CLI)
- **Driven Adapters**: 애플리케이션이 호출하는 쪽 (Database, External API)

```
                    Driving Side                 Driven Side
                    (Primary)                    (Secondary)
                        │                            │
                        ▼                            ▼
┌──────────────┐   ┌─────────┐   ┌──────────┐   ┌─────────┐   ┌──────────────┐
│ HTTP Request │──▶│  Port   │──▶│   App    │──▶│  Port   │──▶│   Database   │
│  (Adapter)   │   │(Driving)│   │  Core    │   │(Driven) │   │  (Adapter)   │
└──────────────┘   └─────────┘   └──────────┘   └─────────┘   └──────────────┘
```

---

### Domain-Driven Design (DDD)

| 항목 | 내용 |
|------|------|
| **창시자** | Eric Evans |
| **발표** | 2003년 |
| **책** | *Domain-Driven Design: Tackling Complexity in the Heart of Software* (Blue Book) |
| **보조** | *Implementing Domain-Driven Design* - Vaughn Vernon (2013, Red Book) |

**전술적 패턴 (Tactical Patterns):**

| 패턴 | 설명 | 예시 |
|------|------|------|
| **Entity** | 고유 식별자를 가진 객체, 생명주기 있음 | `User`, `Order` |
| **Value Object** | 식별자 없음, 불변, 속성으로만 동등성 판단 | `Username`, `Money` |
| **Aggregate** | 일관성 경계를 가진 Entity 클러스터 | `Order` + `OrderLine` |
| **Repository** | Aggregate의 영속성 추상화 | `UserRepository` |
| **Domain Service** | Entity에 속하지 않는 도메인 로직 | `TransferService` |
| **Domain Event** | 도메인에서 발생한 중요한 사건 | `UserCreated` |
| **Factory** | 복잡한 객체 생성 캡슐화 | `OrderFactory` |

---

### CQRS (Command Query Responsibility Segregation)

| 항목 | 내용 |
|------|------|
| **창시자** | Greg Young |
| **발표** | 2010년경 |
| **기원** | CQS (Command Query Separation) - Bertrand Meyer |
| **참고** | [CQRS - Martin Fowler](https://martinfowler.com/bliki/CQRS.html) |

**CQS vs CQRS:**

| CQS (메서드 수준) | CQRS (시스템 수준) |
|------------------|-------------------|
| 메서드는 Command 또는 Query | 모델을 Command/Query로 분리 |
| 같은 객체 내 분리 | 별도의 Read/Write 모델 |
| Bertrand Meyer (1988) | Greg Young (2010) |

```
┌────────────────────────────────────────────────────────────┐
│                        Client                              │
└─────────────────┬──────────────────────┬───────────────────┘
                  │                      │
                  ▼                      ▼
         ┌───────────────┐      ┌───────────────┐
         │   Command     │      │    Query      │
         │    Model      │      │    Model      │
         │  (Write DB)   │      │  (Read DB)    │
         └───────────────┘      └───────────────┘
                  │                      ▲
                  │    Event/Sync        │
                  └──────────────────────┘
```

---

### Patterns of Enterprise Application Architecture (PoEAA)

| 항목 | 내용 |
|------|------|
| **저자** | Martin Fowler |
| **발표** | 2002년 |
| **책** | *Patterns of Enterprise Application Architecture* |
| **카탈로그** | [martinfowler.com/eaaCatalog](https://martinfowler.com/eaaCatalog/) |

**이 프로젝트에서 사용하는 PoEAA 패턴:**

| 패턴 | 설명 | 프로젝트 적용 |
|------|------|--------------|
| **Repository** | 도메인 객체 컬렉션처럼 동작하는 매개체 | `UserCommandGateway` |
| **Data Mapper** | 객체와 DB 테이블 간 매핑 분리 | `SqlaUserDataMapper` |
| **Unit of Work** | 비즈니스 트랜잭션 동안의 변경 추적 | `Flusher` + `TransactionManager` |
| **Gateway** | 외부 시스템 접근을 캡슐화 | 모든 `*Gateway` 포트 |
| **Identity Map** | 같은 객체 중복 로딩 방지 | SQLAlchemy Session |

**Repository vs Gateway vs Data Mapper:**

```
┌─────────────────────────────────────────────────────────────────┐
│  Repository (DDD)                                               │
│  - 도메인 객체의 "컬렉션"처럼 동작                                │
│  - 도메인 언어로 표현 (findByUsername, save)                     │
│  - Aggregate Root 단위                                          │
├─────────────────────────────────────────────────────────────────┤
│  Gateway (PoEAA)                                                │
│  - 외부 시스템 접근의 "통로"                                     │
│  - 기술적 추상화 (데이터 흐름 관점)                              │
│  - 더 범용적 (DB, API, 메시지 큐 등)                            │
├─────────────────────────────────────────────────────────────────┤
│  Data Mapper (PoEAA)                                            │
│  - 객체와 DB 레코드 간 "변환"                                    │
│  - 영속성 무지(Persistence Ignorance) 달성                      │
│  - ORM이 이 역할 수행 (SQLAlchemy)                              │
└─────────────────────────────────────────────────────────────────┘
```

---

### SOLID Principles

| 항목 | 내용 |
|------|------|
| **창시자** | Robert C. Martin |
| **발표** | 2000년대 초반 |
| **출처** | *Agile Software Development, Principles, Patterns, and Practices* (2002) |

**이 프로젝트에서 중요한 원칙:**

| 원칙 | 설명 | 적용 |
|------|------|------|
| **S** - Single Responsibility | 클래스는 하나의 책임만 | Use Case별 Interactor 분리 |
| **O** - Open/Closed | 확장에 열림, 수정에 닫힘 | Port/Adapter 패턴 |
| **L** - Liskov Substitution | 하위 타입 대체 가능 | Protocol 기반 인터페이스 |
| **I** - Interface Segregation | 클라이언트별 인터페이스 분리 | Command/Query Gateway 분리 |
| **D** - Dependency Inversion | 추상에 의존, 구체에 비의존 | **핵심** - 모든 Port가 이 원칙 |

**Dependency Inversion Principle (DIP) 상세:**

```python
# ❌ 전통적 의존성 (고수준 → 저수준)
class UserService:
    def __init__(self):
        self.repo = PostgresUserRepository()  # 구체 클래스 의존

# ✅ 의존성 역전 (고수준 → 추상 ← 저수준)
class UserService:
    def __init__(self, repo: UserRepository):  # 추상(Protocol) 의존
        self.repo = repo

class PostgresUserRepository(UserRepository):  # 구체가 추상 구현
    ...
```

---

### Onion Architecture

| 항목 | 내용 |
|------|------|
| **창시자** | Jeffrey Palermo |
| **발표** | 2008년 |
| **관계** | Clean Architecture의 전신 중 하나 |
| **원본** | [The Onion Architecture](https://jeffreypalermo.com/2008/07/the-onion-architecture-part-1/) |

**Clean Architecture와의 비교:**

| Onion Architecture | Clean Architecture |
|-------------------|-------------------|
| Domain Model (중심) | Entities (중심) |
| Domain Services | Use Cases |
| Application Services | Interface Adapters |
| Infrastructure | Frameworks & Drivers |

---

### 아키텍처 진화 타임라인

```
1988  CQS (Bertrand Meyer)
      │
2002  PoEAA (Martin Fowler) - Repository, Data Mapper, Unit of Work, Gateway
      │
2003  DDD (Eric Evans) - Entity, Value Object, Aggregate, Repository
      │
2005  Hexagonal Architecture (Alistair Cockburn) - Ports & Adapters
      │
2008  Onion Architecture (Jeffrey Palermo)
      │
2010  CQRS (Greg Young)
      │
2012  Clean Architecture (Robert C. Martin) - 이전 개념들의 통합
      │
2017  Clean Architecture 책 출간
      │
2024  fastapi-clean-example - Python/FastAPI에 실전 적용
```

---

## 1. 프로젝트 개요

### 1.1 소개

FastAPI 기반 Clean Architecture 백엔드 예제 프로젝트로, 다음 특징을 갖습니다:

- **No Stateful Globals**: 의존성 주입(DI) 활용
- **Low Coupling**: 의존성 역전 원칙(DIP) 적용
- **Tactical DDD**: 도메인 주도 설계의 전술적 패턴
- **CQRS**: Command/Query 책임 분리
- **Proper UoW**: 올바른 Unit of Work 패턴 사용

### 1.2 기술 스택

- FastAPI
- SQLAlchemy (async)
- Dishka (DI Container)
- bcrypt (Password Hashing)
- JWT (Session-based Auth)

---

## 2. 폴더 구조

```
src/app/
├── domain/                                    # 🔵 Domain Layer
│   ├── entities/
│   │   └── user.py
│   ├── enums/
│   │   └── user_role.py
│   ├── exceptions/
│   │   └── user.py
│   ├── ports/                                # Domain Ports
│   │   ├── password_hasher.py
│   │   └── user_id_generator.py
│   ├── services/
│   │   └── user.py
│   └── value_objects/
│       ├── raw_password.py
│       ├── user_id.py
│       ├── user_password_hash.py
│       └── username.py
│
├── application/                              # 🟢 Application Layer
│   ├── commands/                             # Command Use Cases
│   │   ├── activate_user.py
│   │   ├── create_user.py
│   │   ├── deactivate_user.py
│   │   ├── grant_admin.py
│   │   ├── revoke_admin.py
│   │   └── set_user_password.py
│   ├── queries/                              # Query Use Cases
│   │   └── list_users.py
│   └── common/
│       ├── exceptions/
│       ├── ports/                            # Application Ports
│       │   ├── access_revoker.py
│       │   ├── flusher.py
│       │   ├── identity_provider.py
│       │   ├── transaction_manager.py
│       │   ├── user_command_gateway.py
│       │   └── user_query_gateway.py
│       ├── query_params/
│       └── services/
│
├── infrastructure/                           # 🟠 Infrastructure Layer
│   ├── adapters/                             # Port 구현체들
│   │   ├── main_flusher_sqla.py
│   │   ├── main_transaction_manager_sqla.py
│   │   ├── password_hasher_bcrypt.py
│   │   ├── user_data_mapper_sqla.py
│   │   ├── user_id_generator_uuid.py
│   │   └── user_reader_sqla.py
│   ├── auth/
│   │   └── session/
│   │       ├── ports/                        # Infrastructure 내부 Port
│   │       │   └── gateway.py
│   │       └── adapters/
│   ├── exceptions/
│   └── persistence_sqla/
│       └── mappings/
│
├── presentation/                             # 🟣 Presentation Layer
│   └── http/
│       ├── auth/
│       │   └── adapters/
│       ├── controllers/
│       └── dependencies/
│
└── setup/                                    # ⚙️ Setup
    ├── config/
    └── di/
```

---

## 3. 레이어별 역할

### 3.1 Domain Layer

**위치**: `domain/`

**역할**: 핵심 비즈니스 로직, 외부 의존성 없음

| 구성요소 | 설명 | 예시 |
|---------|------|------|
| `entities/` | 도메인 엔티티 | `User` |
| `value_objects/` | 값 객체 | `Username`, `UserId`, `RawPassword` |
| `services/` | 도메인 서비스 | `UserService` |
| `ports/` | 도메인 Port | `PasswordHasher`, `UserIdGenerator` |
| `enums/` | 열거형 | `UserRole` |
| `exceptions/` | 도메인 예외 | `UsernameAlreadyExistsError` |

### 3.2 Application Layer

**위치**: `application/`

**역할**: Use Case 구현, 비즈니스 흐름 조율

| 구성요소 | 설명 | 예시 |
|---------|------|------|
| `commands/` | 상태 변경 Use Case | `CreateUserInteractor` |
| `queries/` | 조회 Use Case | `ListUsersQueryService` |
| `common/ports/` | Application Port | `UserCommandGateway`, `Flusher` |
| `common/services/` | 공유 서비스 | `CurrentUserService` |

### 3.3 Infrastructure Layer

**위치**: `infrastructure/`

**역할**: Port 구현, 외부 시스템 연동

| 구성요소 | 설명 | 예시 |
|---------|------|------|
| `adapters/` | Port 구현체 | `SqlaUserDataMapper` |
| `persistence_sqla/` | SQLAlchemy 설정/매핑 | `users_table` |
| `auth/` | 인증 인프라 | 세션, JWT |
| `exceptions/` | 인프라 예외 | `DataMapperError` |

### 3.4 Presentation Layer

**위치**: `presentation/`

**역할**: HTTP 처리, 사용자 인터페이스

| 구성요소 | 설명 | 예시 |
|---------|------|------|
| `http/controllers/` | API 엔드포인트 | 라우터 |
| `http/dependencies/` | FastAPI 의존성 | Depends 함수 |
| `http/auth/adapters/` | HTTP 전송 어댑터 | `JwtCookieAuthSessionTransport` |

---

## 4. Port와 Adapter 매핑

### 4.1 Domain Ports

| Port (인터페이스) | Adapter (구현체) | 기술 |
|------------------|-----------------|------|
| `PasswordHasher` | `BcryptPasswordHasher` | bcrypt |
| `UserIdGenerator` | `UuidUserIdGenerator` | UUID |

### 4.2 Application Ports

| Port (인터페이스) | Adapter (구현체) | 기술 |
|------------------|-----------------|------|
| `UserCommandGateway` | `SqlaUserDataMapper` | SQLAlchemy |
| `UserQueryGateway` | `SqlaUserReader` | SQLAlchemy |
| `Flusher` | `SqlaMainFlusher` | SQLAlchemy |
| `TransactionManager` | `SqlaMainTransactionManager` | SQLAlchemy |
| `IdentityProvider` | - | - |
| `AccessRevoker` | - | - |

### 4.3 Infrastructure 내부 Ports

| Port (인터페이스) | Adapter (구현체) | 용도 |
|------------------|-----------------|------|
| `AuthSessionGateway` | SQLAlchemy 구현 | 세션 저장소 교체 용이 |

---

## 5. Use Case 패턴 (CQRS)

### 5.1 Command Use Case 구조

```python
# application/commands/create_user.py

@dataclass(frozen=True, slots=True, kw_only=True)
class CreateUserRequest:           # Input DTO
    username: str
    password: str
    role: UserRole

class CreateUserResponse(TypedDict):  # Output DTO
    id: UUID

class CreateUserInteractor:        # Use Case
    def __init__(
        self,
        current_user_service: CurrentUserService,
        user_service: UserService,
        user_command_gateway: UserCommandGateway,
        flusher: Flusher,
        transaction_manager: TransactionManager,
    ) -> None:
        self._current_user_service = current_user_service
        self._user_service = user_service
        self._user_command_gateway = user_command_gateway
        self._flusher = flusher
        self._transaction_manager = transaction_manager

    async def execute(self, request_data: CreateUserRequest) -> CreateUserResponse:
        # 인증/인가
        current_user = await self._current_user_service.get_current_user()
        authorize(CanManageRole(), context=RoleManagementContext(...))
        
        # 도메인 로직
        user = await self._user_service.create_user(...)
        self._user_command_gateway.add(user)
        
        # 영속성
        await self._flusher.flush()
        await self._transaction_manager.commit()
        
        return CreateUserResponse(id=user.id_.value)
```

### 5.2 Query Use Case 구조

```python
# application/queries/list_users.py

@dataclass(frozen=True, slots=True, kw_only=True)
class ListUsersRequest:
    limit: int
    offset: int
    sorting_field: str
    sorting_order: SortingOrder

class ListUsersQueryService:
    def __init__(
        self,
        current_user_service: CurrentUserService,
        user_query_gateway: UserQueryGateway,
    ) -> None:
        self._current_user_service = current_user_service
        self._user_query_gateway = user_query_gateway

    async def execute(self, request_data: ListUsersRequest) -> ListUsersQM:
        # 인증/인가
        current_user = await self._current_user_service.get_current_user()
        authorize(...)
        
        # 조회
        response = await self._user_query_gateway.read_all(
            pagination=OffsetPaginationParams(...),
            sorting=SortingParams(...),
        )
        return response
```

### 5.3 Command vs Query 비교

| 항목 | Command | Query |
|------|---------|-------|
| 클래스명 | `XxxInteractor` | `XxxQueryService` |
| 역할 | 상태 변경 | 조회만 |
| Gateway | `CommandGateway` | `QueryGateway` |
| 트랜잭션 | ✅ 필요 | ❌ 불필요 |
| 반환값 | ID 또는 void | DTO/QueryModel |

---

## 6. Gateway 패턴

### 6.1 Gateway vs Repository

이 프로젝트는 "Repository" 대신 "Gateway"라는 용어를 사용합니다.

| 용어 | 의미 | 장점 |
|------|------|------|
| `Repository` | 도메인 객체 컬렉션 (DDD) | 널리 알려짐 |
| `Gateway` | 외부 시스템 통로 | CQRS 분리 명확 |

### 6.2 Gateway 인터페이스

**UserCommandGateway** (쓰기용):
```python
class UserCommandGateway(Protocol):
    @abstractmethod
    def add(self, user: User) -> None: ...

    @abstractmethod
    async def read_by_id(
        self, user_id: UserId, for_update: bool = False
    ) -> User | None: ...

    @abstractmethod
    async def read_by_username(
        self, username: Username, for_update: bool = False
    ) -> User | None: ...
```

**UserQueryGateway** (읽기용):
```python
class UserQueryModel(TypedDict):
    id_: UUID
    username: str
    role: UserRole
    is_active: bool

class ListUsersQM(TypedDict):
    users: list[UserQueryModel]
    total: int

class UserQueryGateway(Protocol):
    @abstractmethod
    async def read_all(
        self, pagination: OffsetPaginationParams, sorting: SortingParams
    ) -> ListUsersQM: ...
```

### 6.3 Gateway 구현체

```python
# infrastructure/adapters/user_data_mapper_sqla.py

class SqlaUserDataMapper(UserCommandGateway):
    def __init__(self, session: MainAsyncSession) -> None:
        self._session = session

    def add(self, user: User) -> None:
        self._session.add(user)

    async def read_by_id(self, user_id: UserId, for_update: bool = False) -> User | None:
        stmt = select(User).where(User.id_ == user_id)
        if for_update:
            stmt = stmt.with_for_update()
        return (await self._session.execute(stmt)).scalar_one_or_none()
```

---

## 7. 명명 규칙

### 7.1 Port 명명

| 패턴 | 예시 | 설명 |
|------|------|------|
| `Xxx + Gateway` | `UserCommandGateway` | 데이터 접근 통로 |
| `Xxx + er` | `Flusher`, `PasswordHasher` | 동작 수행자 |
| `Xxx + Manager` | `TransactionManager` | 관리자 |
| `Xxx + Provider` | `IdentityProvider` | 제공자 |

### 7.2 Adapter 명명

| 패턴 | 예시 | 설명 |
|------|------|------|
| `기술 + Port역할` | `SqlaUserDataMapper` | SQLAlchemy 구현 |
| `기술 + Port이름` | `BcryptPasswordHasher` | bcrypt 구현 |
| `기술 + 역할` | `SqlaUserReader` | SQLAlchemy 읽기 |

### 7.3 Use Case 명명

| 패턴 | 예시 | 설명 |
|------|------|------|
| `동사 + 명사 + Interactor` | `CreateUserInteractor` | Command |
| `동사 + 명사 + QueryService` | `ListUsersQueryService` | Query |

---

## 8. Port의 3단계 구조

```
┌─────────────────────────────────────────────────────────────────┐
│  domain/ports/                                                  │
│  └── 도메인 개념 추상화                                          │
│      - PasswordHasher: 비밀번호 해싱 (도메인 관심사)             │
│      - UserIdGenerator: ID 생성 (도메인 관심사)                  │
├─────────────────────────────────────────────────────────────────┤
│  application/common/ports/                                      │
│  └── 레이어 간 경계 (Application → Infrastructure)              │
│      - UserCommandGateway: 사용자 쓰기                          │
│      - UserQueryGateway: 사용자 읽기                            │
│      - Flusher: 영속성 플러시                                   │
│      - TransactionManager: 트랜잭션 관리                        │
├─────────────────────────────────────────────────────────────────┤
│  infrastructure/.../ports/                                      │
│  └── 같은 레이어 내 교체 용이                                    │
│      - AuthSessionGateway: 세션 저장소 (테스트/구현 교체)        │
└─────────────────────────────────────────────────────────────────┘
```

---

## 9. 의존성 흐름

```
┌─────────────────────────────────────────────────────────────────┐
│                      Presentation Layer                         │
│  HTTP Controllers → Use Case 호출                               │
└──────────────────────────┬──────────────────────────────────────┘
                           │ depends on (interface)
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│                      Application Layer                          │
│  Use Cases → Domain Services + Ports 사용                       │
└──────────────────────────┬──────────────────────────────────────┘
                           │ depends on (interface)
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│                        Domain Layer                             │
│  Entities + Value Objects + Domain Ports                        │
└─────────────────────────────────────────────────────────────────┘
                           ▲
                           │ implements (DIP: 의존성 역전)
┌─────────────────────────────────────────────────────────────────┐
│                     Infrastructure Layer                        │
│  Adapters (SQLAlchemy, bcrypt, UUID 등) → Ports 구현            │
└─────────────────────────────────────────────────────────────────┘
```

---

## 10. 추가 개념

### 10.1 Python Protocol vs ABC

이 프로젝트는 **Protocol** (Structural Subtyping)을 사용합니다.

| 방식 | 특징 | 사용 |
|------|------|------|
| **ABC** (Abstract Base Class) | 명시적 상속 필요 (`class A(Base)`) | 전통적 방식 |
| **Protocol** (typing.Protocol) | 덕 타이핑, 상속 불필요 | **이 프로젝트** |

```python
# ABC 방식 (Nominal Typing)
from abc import ABC, abstractmethod

class UserRepository(ABC):
    @abstractmethod
    def get(self, id: int) -> User: ...

class SqlUserRepository(UserRepository):  # 명시적 상속 필수
    def get(self, id: int) -> User: ...

# Protocol 방식 (Structural Typing) - 이 프로젝트 방식
from typing import Protocol

class UserRepository(Protocol):
    def get(self, id: int) -> User: ...

class SqlUserRepository:  # 상속 없이도 호환!
    def get(self, id: int) -> User: ...
    
# 타입 체커가 구조적으로 검증
def use_repo(repo: UserRepository): ...
use_repo(SqlUserRepository())  # ✅ OK - 메서드 시그니처가 일치
```

**Protocol 선택 이유:**
- 더 유연한 결합
- 테스트 Mock 작성이 쉬움
- 런타임 오버헤드 없음

---

### 10.2 테스트 전략

Clean Architecture의 **핵심 장점은 테스트 용이성**입니다.

**레이어별 테스트:**

| 레이어 | 테스트 유형 | Mock 대상 |
|--------|-----------|----------|
| **Domain** | Unit Test | 없음 (순수 로직) |
| **Application** | Unit Test | Ports (Gateway, Flusher 등) |
| **Infrastructure** | Integration Test | 실제 DB/Redis |
| **Presentation** | E2E Test | 전체 또는 Use Case Mock |

```python
# Use Case 단위 테스트 예시
class MockUserCommandGateway:
    def __init__(self):
        self.users = []
    
    def add(self, user: User) -> None:
        self.users.append(user)
    
    async def read_by_username(self, username: Username) -> User | None:
        return next((u for u in self.users if u.username == username), None)

class MockFlusher:
    async def flush(self) -> None:
        pass  # 아무것도 안 함

class MockTransactionManager:
    async def commit(self) -> None:
        pass

async def test_create_user():
    # Arrange
    gateway = MockUserCommandGateway()
    interactor = CreateUserInteractor(
        user_service=UserService(...),
        user_command_gateway=gateway,
        flusher=MockFlusher(),
        transaction_manager=MockTransactionManager(),
    )
    
    # Act
    result = await interactor.execute(CreateUserRequest(
        username="testuser",
        password="password123",
        role=UserRole.USER,
    ))
    
    # Assert
    assert result["id"] is not None
    assert len(gateway.users) == 1
```

---

### 10.3 에러 핸들링 전략

**레이어별 예외 정의:**

```
┌─────────────────────────────────────────────────────────────────┐
│  Domain Exceptions                                              │
│  - UsernameAlreadyExistsError                                  │
│  - InvalidPasswordError                                        │
│  - 순수 비즈니스 규칙 위반                                       │
├─────────────────────────────────────────────────────────────────┤
│  Application Exceptions                                         │
│  - AuthenticationError                                         │
│  - AuthorizationError                                          │
│  - Use Case 실행 중 오류                                        │
├─────────────────────────────────────────────────────────────────┤
│  Infrastructure Exceptions                                      │
│  - DataMapperError (DB 오류)                                   │
│  - ReaderError (조회 오류)                                     │
│  - 기술적 오류                                                  │
├─────────────────────────────────────────────────────────────────┤
│  Presentation Layer                                             │
│  - 모든 예외를 HTTP 응답으로 변환                               │
│  - Domain/App 예외 → 4xx                                       │
│  - Infrastructure 예외 → 5xx                                   │
└─────────────────────────────────────────────────────────────────┘
```

**예외 변환 예시:**

```python
# presentation/http/exception_handlers.py

@app.exception_handler(UsernameAlreadyExistsError)
async def handle_username_exists(request, exc):
    return JSONResponse(
        status_code=409,  # Conflict
        content={"detail": str(exc)},
    )

@app.exception_handler(AuthenticationError)
async def handle_auth_error(request, exc):
    return JSONResponse(
        status_code=401,  # Unauthorized
        content={"detail": "Authentication required"},
    )

@app.exception_handler(DataMapperError)
async def handle_db_error(request, exc):
    logger.error(f"Database error: {exc}")
    return JSONResponse(
        status_code=500,  # Internal Server Error
        content={"detail": "Internal server error"},
    )
```

---

### 10.4 데이터 흐름 예시

**HTTP 요청 → DB 저장 전체 흐름:**

```
[Client]
    │
    │ POST /users {"username": "john", "password": "secret"}
    ▼
┌─────────────────────────────────────────────────────────────────┐
│  Presentation Layer                                             │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  Controller (router)                                     │   │
│  │  - Request 파싱 (Pydantic)                              │   │
│  │  - Use Case 호출                                        │   │
│  │  - Response 반환                                        │   │
│  └──────────────────────────┬──────────────────────────────┘   │
└─────────────────────────────┼───────────────────────────────────┘
                              │ CreateUserRequest
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  Application Layer                                              │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  CreateUserInteractor.execute()                          │   │
│  │  1. 인증/인가 확인                                       │   │
│  │  2. UserService.create_user() 호출                      │   │
│  │  3. UserCommandGateway.add(user)                        │   │
│  │  4. Flusher.flush()                                     │   │
│  │  5. TransactionManager.commit()                         │   │
│  └──────────────────────────┬──────────────────────────────┘   │
└─────────────────────────────┼───────────────────────────────────┘
                              │ User entity
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  Domain Layer                                                   │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  UserService.create_user()                               │   │
│  │  1. Username 값 객체 생성 (유효성 검증)                  │   │
│  │  2. PasswordHasher.hash() 호출 (Port)                   │   │
│  │  3. UserIdGenerator.generate() 호출 (Port)              │   │
│  │  4. User 엔티티 생성                                     │   │
│  └──────────────────────────┬──────────────────────────────┘   │
└─────────────────────────────┼───────────────────────────────────┘
                              │ Port 호출
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  Infrastructure Layer                                           │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  BcryptPasswordHasher.hash()  → bcrypt 라이브러리       │   │
│  │  UuidUserIdGenerator.generate() → uuid4()               │   │
│  │  SqlaUserDataMapper.add() → session.add()               │   │
│  │  SqlaMainFlusher.flush() → session.flush()              │   │
│  │  SqlaMainTransactionManager.commit() → session.commit() │   │
│  └──────────────────────────┬──────────────────────────────┘   │
└─────────────────────────────┼───────────────────────────────────┘
                              │ SQL
                              ▼
                         [PostgreSQL]
```

---

### 10.5 Trade-offs (장단점)

**장점:**

| 장점 | 설명 |
|------|------|
| **테스트 용이성** | 각 레이어 독립적 테스트 가능 |
| **유지보수성** | 변경 영향 범위 최소화 |
| **기술 교체 용이** | DB, Framework 교체가 비즈니스 로직에 영향 없음 |
| **관심사 분리** | 각 레이어의 책임이 명확 |
| **도메인 중심** | 비즈니스 로직이 기술에 오염되지 않음 |

**단점:**

| 단점 | 설명 | 완화 방안 |
|------|------|----------|
| **복잡성 증가** | 파일/클래스 수 증가 | 작은 프로젝트에는 과할 수 있음 |
| **보일러플레이트** | Port, Adapter, DTO 중복 | 코드 생성기 활용 |
| **학습 곡선** | 팀 전체가 이해해야 함 | 문서화, 예제 코드 |
| **초기 개발 속도** | 설정해야 할 것이 많음 | 템플릿 프로젝트 활용 |
| **과도한 추상화** | 단순한 CRUD에도 레이어 통과 | 필요시 단순화 |

**적용 기준:**

```
프로젝트 규모/복잡도
       │
       ├── 작은 프로젝트 (CRUD 위주)
       │   → 단순 레이어드 아키텍처로 충분
       │
       ├── 중간 규모 (복잡한 비즈니스 로직)
       │   → Clean Architecture 고려
       │
       └── 대규모 (마이크로서비스, 장기 운영)
           → Clean Architecture 강력 권장
```

---

### 10.6 DI 컨테이너 설정 (Dishka) - *예제 참고용*

> ⚠️ **Note**: 이 섹션은 예제 프로젝트의 Dishka 사용 방식을 참고용으로 기록한 것입니다. 우리 프로젝트에서는 FastAPI 기본 `Depends()` 패턴을 사용합니다.

fastapi-clean-example은 **Dishka**를 사용합니다:

```python
# setup/di/providers.py

from dishka import Provider, Scope, provide

class InfrastructureProvider(Provider):
    scope = Scope.REQUEST
    
    @provide
    async def get_session(self) -> AsyncSession:
        async with async_session_maker() as session:
            yield session
    
    @provide
    def get_user_command_gateway(
        self, session: AsyncSession
    ) -> UserCommandGateway:
        return SqlaUserDataMapper(session)
    
    @provide
    def get_flusher(self, session: AsyncSession) -> Flusher:
        return SqlaMainFlusher(session)

class ApplicationProvider(Provider):
    scope = Scope.REQUEST
    
    @provide
    def get_create_user_interactor(
        self,
        user_service: UserService,
        gateway: UserCommandGateway,
        flusher: Flusher,
        tx_manager: TransactionManager,
    ) -> CreateUserInteractor:
        return CreateUserInteractor(
            user_service=user_service,
            user_command_gateway=gateway,
            flusher=flusher,
            transaction_manager=tx_manager,
        )

# main.py
from dishka.integrations.fastapi import setup_dishka

container = make_async_container(
    InfrastructureProvider(),
    ApplicationProvider(),
)
setup_dishka(container, app)
```

**FastAPI 엔드포인트에서 사용:**

```python
from dishka.integrations.fastapi import FromDishka

@router.post("/users")
async def create_user(
    request: CreateUserHttpRequest,
    interactor: FromDishka[CreateUserInteractor],
):
    result = await interactor.execute(CreateUserRequest(
        username=request.username,
        password=request.password,
        role=request.role,
    ))
    return {"id": result["id"]}
```

---

### 10.7 Entity Generic (Python 3.12+)

예제 프로젝트는 Python 3.12+의 새로운 Generic 문법을 사용합니다:

```python
# src/app/domain/entities/base.py
from collections.abc import Hashable
from typing import Any, Self, cast

class Entity[T: Hashable]:  # ← Python 3.12+ Generic 문법
    """
    Base class for domain entities, defined by a unique identity (`id`).
    - `id`: Identity that remains constant throughout the entity's lifecycle.
    - Entities are mutable, but are compared solely by their `id`.
    """
    
    def __new__(cls, *_args: Any, **_kwargs: Any) -> Self:
        if cls is Entity:
            raise TypeError("Base Entity cannot be instantiated directly.")
        return object.__new__(cls)
    
    def __init__(self, *, id_: T) -> None:
        self.id_ = id_
    
    def __setattr__(self, name: str, value: Any) -> None:
        # Prevents modifying the `id` after it's set
        if name == "id_" and getattr(self, "id_", None) is not None:
            raise AttributeError("Changing entity ID is not permitted.")
        object.__setattr__(self, name, value)
    
    def __eq__(self, other: object) -> bool:
        # ID 기반 동등성
        return type(self) is type(other) and cast(Self, other).id_ == self.id_
    
    def __hash__(self) -> int:
        return hash((type(self), self.id_))
```

**주요 특징:**
- `Entity[T: Hashable]`: T는 Hashable을 상속해야 함
- `__new__`: Base Entity 직접 인스턴스화 방지
- `__setattr__`: ID 변경 불가 (불변성)
- `__eq__`, `__hash__`: ID 기반 동등성 및 해시

---

### 10.8 BcryptPasswordHasher 복잡한 DI 패턴

비밀번호 해싱은 CPU 집약적 작업이므로 **비동기 + 스레드풀 + 세마포어** 패턴을 사용합니다:

```python
# src/app/infrastructure/adapters/password_hasher_bcrypt.py
class BcryptPasswordHasher(PasswordHasher):
    def __init__(
        self,
        pepper: bytes,                           # 보안: 서버 측 비밀 키
        work_factor: int,                        # bcrypt 라운드 수 (12~14 권장)
        executor: HasherThreadPoolExecutor,      # CPU 작업용 스레드풀
        semaphore: HasherSemaphore,              # 동시 요청 제한
        semaphore_wait_timeout_s: float,         # 세마포어 타임아웃
    ) -> None:
        ...
    
    async def hash(self, raw_password: RawPassword) -> UserPasswordHash:
        async with self._permit():  # 세마포어 획득
            loop = asyncio.get_running_loop()
            return await loop.run_in_executor(
                self._executor,        # 스레드풀에서 실행
                self.hash_sync,        # 동기 해싱 함수
                raw_password,
            )
    
    @asynccontextmanager
    async def _permit(self) -> AsyncIterator[None]:
        """세마포어로 동시 해싱 요청 제한"""
        try:
            await asyncio.wait_for(
                self._semaphore.acquire(),
                timeout=self._semaphore_wait_timeout_s,
            )
        except TimeoutError as err:
            raise PasswordHasherBusyError from err
        try:
            yield
        finally:
            self._semaphore.release()
    
    def hash_sync(self, raw_password: RawPassword) -> UserPasswordHash:
        # OWASP 권장: Pre-hashing with pepper
        base64_hmac_peppered = self._add_pepper(raw_password, self._pepper)
        salt = bcrypt.gensalt(rounds=self._work_factor)
        return UserPasswordHash(bcrypt.hashpw(base64_hmac_peppered, salt))
```

**DI 설정 (setup/ioc/domain.py):**

```python
class DomainProvider(Provider):
    @provide
    def provide_password_hasher(
        self,
        security: SecuritySettings,
        executor: HasherThreadPoolExecutor,
        semaphore: HasherSemaphore,
    ) -> PasswordHasher:
        return BcryptPasswordHasher(
            pepper=security.password.pepper.encode(),
            work_factor=security.password.hasher_work_factor,
            executor=executor,
            semaphore=semaphore,
            semaphore_wait_timeout_s=security.password.hasher_semaphore_wait_timeout_s,
        )
```

**설계 이유:**
- **ThreadPoolExecutor**: bcrypt는 GIL을 해제하지 않아 스레드풀 필요
- **Semaphore**: 과도한 동시 해싱 요청 방지 (DoS 공격 대응)
- **Pepper**: DB 유출 시에도 비밀번호 보호 (OWASP 권장)

---

### 10.9 테스트 구조 및 Mock 전략

#### 테스트 디렉토리 구조

```
tests/app/
├── unit/
│   ├── domain/
│   │   ├── entities/
│   │   │   └── test_base.py
│   │   ├── services/
│   │   │   ├── conftest.py          # Mock fixture 정의
│   │   │   ├── mock_types.py        # Mock 타입 정의
│   │   │   └── test_user.py
│   │   └── value_objects/
│   │       └── test_username.py
│   ├── application/
│   │   └── authz_service/
│   │       └── test_permissions.py
│   ├── infrastructure/
│   │   └── test_password_hasher_bcrypt.py
│   ├── setup/
│   │   └── test_cfg_*.py
│   └── factories/                    # 테스트용 팩토리
│       ├── user_entity.py
│       ├── value_objects.py
│       └── named_entity.py
├── integration/
│   └── setup/
│       └── test_cfg_loader.py
└── performance/
    └── profile_password_hasher_bcrypt.py
```

#### conftest.py - Mock Fixture 패턴

```python
# tests/app/unit/domain/services/conftest.py
from unittest.mock import create_autospec
import pytest

@pytest.fixture
def user_id_generator() -> UserIdGeneratorMock:
    return cast(UserIdGeneratorMock, create_autospec(UserIdGenerator, instance=True))

@pytest.fixture
def password_hasher() -> PasswordHasherMock:
    return cast(PasswordHasherMock, create_autospec(PasswordHasher, instance=True))
```

#### 테스트 팩토리 패턴

```python
# tests/app/unit/factories/user_entity.py
def create_user(
    user_id: UserId | None = None,
    username: Username | None = None,
    password_hash: UserPasswordHash | None = None,
    role: UserRole = UserRole.USER,
    is_active: bool = True,
) -> User:
    return User(
        id_=user_id or create_user_id(),
        username=username or create_username(),
        password_hash=password_hash or create_password_hash(),
        role=role,
        is_active=is_active,
    )
```

#### 실제 테스트 예시

```python
# tests/app/unit/domain/services/test_user.py
@pytest.mark.asyncio
@pytest.mark.parametrize("role", [UserRole.USER, UserRole.ADMIN])
async def test_creates_active_user_with_hashed_password(
    role: UserRole,
    user_id_generator: UserIdGeneratorMock,
    password_hasher: PasswordHasherMock,
) -> None:
    # Arrange
    username = create_username()
    raw_password = create_raw_password()
    expected_id = create_user_id()
    expected_hash = create_password_hash()
    
    user_id_generator.generate.return_value = expected_id
    password_hasher.hash.return_value = expected_hash
    
    sut = UserService(user_id_generator, password_hasher)
    
    # Act
    result = await sut.create_user(username, raw_password, role)
    
    # Assert
    assert isinstance(result, User)
    assert result.id_ == expected_id
    assert result.password_hash == expected_hash
```

**테스트 전략:**
- **create_autospec**: Protocol의 스펙을 유지하면서 Mock 생성
- **Factory 패턴**: 테스트 데이터 생성 일관성
- **Parametrize**: 여러 케이스 효율적 테스트

---

### 10.10 Command 전체 의존성 목록

문서의 핵심 의존성 외에 각 Command의 전체 의존성입니다:

| Command | 전체 의존성 |
|---------|------------|
| **CreateUserInteractor** | `CurrentUserService`, `UserService`, `UserCommandGateway`, `Flusher`, `TransactionManager` |
| **ActivateUserInteractor** | `CurrentUserService`, `UserCommandGateway`, `UserService`, `Flusher`, `TransactionManager` |
| **DeactivateUserInteractor** | `CurrentUserService`, `UserCommandGateway`, `UserService`, `TransactionManager`, `AccessRevoker` |
| **SetUserPasswordInteractor** | `CurrentUserService`, `UserCommandGateway`, `UserService`, `Flusher`, `TransactionManager` |
| **GrantAdminInteractor** | `CurrentUserService`, `UserCommandGateway`, `UserService`, `Flusher`, `TransactionManager` |
| **RevokeAdminInteractor** | `CurrentUserService`, `UserCommandGateway`, `UserService`, `Flusher`, `TransactionManager` |

| Query | 전체 의존성 |
|-------|------------|
| **ListUsersQueryService** | `CurrentUserService`, `UserQueryGateway` |

**공통 패턴:**
- 모든 Command/Query는 `CurrentUserService`로 현재 사용자 조회
- Command는 `TransactionManager`로 트랜잭션 커밋
- 쓰기 작업은 `Flusher`로 변경사항 플러시
- 사용자 비활성화 시 `AccessRevoker`로 세션 삭제

---

### 10.11 Value Object 자기 검증 패턴

Value Object는 **생성 시점에 불변성을 검증**하여 도메인 무결성을 보장합니다.

#### ValueObject 베이스 클래스

```python
# src/app/domain/value_objects/base.py
from dataclasses import dataclass, fields
from typing import Any, Self

@dataclass(frozen=True, slots=True, repr=False)
class ValueObject:
    """
    Base class for immutable value objects (VO) in domain.
    - Defined by instance attributes only; these must be immutable.
    - For simple type tagging, consider `typing.NewType` instead.
    """
    
    def __new__(cls, *_args: Any, **_kwargs: Any) -> Self:
        if cls is ValueObject:
            raise TypeError("Base ValueObject cannot be instantiated directly.")
        if not fields(cls):
            raise TypeError(f"{cls.__name__} must have at least one field!")
        return object.__new__(cls)
    
    def __post_init__(self) -> None:
        """Hook for additional initialization and ensuring invariants."""
    
    def __repr__(self) -> str:
        """
        - 1 field: outputs value only
        - 2+ fields: outputs `name=value` format
        - All `repr=False`: outputs '<hidden>'
        """
        return f"{type(self).__name__}({self.__repr_value()})"
    
    def __repr_value(self) -> str:
        items = [f for f in fields(self) if f.repr]
        if not items:
            return "<hidden>"
        if len(items) == 1:
            return f"{getattr(self, items[0].name)!r}"
        return ", ".join(f"{f.name}={getattr(self, f.name)!r}" for f in items)
```

#### Username - 복잡한 검증 로직

```python
# src/app/domain/value_objects/username.py
import re
from dataclasses import dataclass
from typing import ClassVar, Final

@dataclass(frozen=True, slots=True, repr=False)
class Username(ValueObject):
    """raises DomainTypeError"""
    
    # 검증 규칙 상수
    MIN_LEN: ClassVar[Final[int]] = 5
    MAX_LEN: ClassVar[Final[int]] = 20
    
    # 정규식 패턴들
    PATTERN_START: ClassVar[Final[re.Pattern[str]]] = re.compile(
        r"^[a-zA-Z0-9]",  # 문자/숫자로 시작
    )
    PATTERN_ALLOWED_CHARS: ClassVar[Final[re.Pattern[str]]] = re.compile(
        r"[a-zA-Z0-9._-]*",  # 허용 문자: 문자, 숫자, ., -, _
    )
    PATTERN_NO_CONSECUTIVE_SPECIALS: ClassVar[Final[re.Pattern[str]]] = re.compile(
        r"^[a-zA-Z0-9]+([._-]?[a-zA-Z0-9]+)*[._-]?$",  # 연속 특수문자 금지
    )
    PATTERN_END: ClassVar[Final[re.Pattern[str]]] = re.compile(
        r".*[a-zA-Z0-9]$",  # 문자/숫자로 끝
    )
    
    value: str
    
    def __post_init__(self) -> None:
        """생성 시점에 모든 검증 수행"""
        self._validate_username_length(self.value)
        self._validate_username_pattern(self.value)
    
    def _validate_username_length(self, username_value: str) -> None:
        if len(username_value) < self.MIN_LEN or len(username_value) > self.MAX_LEN:
            raise DomainTypeError(
                f"Username must be between {self.MIN_LEN} and {self.MAX_LEN} characters."
            )
    
    def _validate_username_pattern(self, username_value: str) -> None:
        if not re.match(self.PATTERN_START, username_value):
            raise DomainTypeError(
                "Username must start with a letter or digit."
            )
        if not re.fullmatch(self.PATTERN_ALLOWED_CHARS, username_value):
            raise DomainTypeError(
                "Username can only contain letters, digits, dots, hyphens, and underscores."
            )
        if not re.fullmatch(self.PATTERN_NO_CONSECUTIVE_SPECIALS, username_value):
            raise DomainTypeError(
                "Username cannot contain consecutive special characters."
            )
        if not re.match(self.PATTERN_END, username_value):
            raise DomainTypeError(
                "Username must end with a letter or digit."
            )
```

#### RawPassword - 민감 데이터 처리

```python
# src/app/domain/value_objects/raw_password.py
from dataclasses import dataclass, field

@dataclass(frozen=True, slots=True, repr=False)
class RawPassword(ValueObject):
    """raises DomainTypeError"""
    
    MIN_LEN: ClassVar[Final[int]] = 6
    
    # repr=False로 로그 노출 방지
    value: bytes = field(init=False, repr=False)
    
    def __init__(self, value: str) -> None:
        """str 입력 → bytes 저장 (인코딩)"""
        self._validate_password_length(value)
        # frozen=True이지만 __init__에서는 object.__setattr__ 사용 가능
        object.__setattr__(self, "value", value.encode())
    
    def _validate_password_length(self, password_value: str) -> None:
        if len(password_value) < self.MIN_LEN:
            raise DomainTypeError(
                f"Password must be at least {self.MIN_LEN} characters long."
            )
```

#### 설계 원칙

| 원칙 | 구현 방법 |
|------|----------|
| **불변성 (Immutable)** | `@dataclass(frozen=True)` - 생성 후 변경 불가 |
| **자기 검증 (Self-Validating)** | `__post_init__` 또는 `__init__`에서 검증 |
| **즉시 실패 (Fail Fast)** | 잘못된 값은 생성 시점에 예외 발생 |
| **민감 데이터 보호** | `repr=False`로 로그 노출 방지 |
| **값 동등성** | 같은 값을 가지면 동일한 객체로 취급 |

#### 사용 예시

```python
# ✅ 유효한 값 - 정상 생성
username = Username("john_doe")
password = RawPassword("secret123")

# ❌ 잘못된 값 - 즉시 예외 발생
Username("ab")           # DomainTypeError: 5자 미만
Username("__invalid")    # DomainTypeError: 특수문자로 시작
Username("user..name")   # DomainTypeError: 연속 특수문자
RawPassword("12345")     # DomainTypeError: 6자 미만

# 민감 데이터 보호
print(password)  # RawPassword(<hidden>) - 값이 노출되지 않음
```

---

## 11. 우리 프로젝트 적용 방안

### 11.1 현재 vs 목표 구조

**현재** (`domains/auth/`):
```
domains/auth/
├── api/v1/endpoints/      # Presentation (혼합)
├── application/services/  # Application (혼합)
├── core/                  # 설정 + 보안 (혼합)
└── infrastructure/        # Infrastructure
```

**목표**:
```
domains/auth/
├── domain/
│   ├── entities/
│   ├── value_objects/
│   ├── ports/                    # Domain Ports
│   └── services/
│
├── application/
│   ├── use_cases/
│   │   ├── commands/             # Command Use Cases
│   │   └── queries/              # Query Use Cases
│   ├── ports/                    # Application Ports
│   └── services/
│
├── infrastructure/
│   ├── adapters/                 # Port 구현체
│   ├── persistence_postgres/
│   ├── persistence_redis/
│   └── security/
│
├── presentation/
│   └── http/
│       ├── controllers/
│       ├── dependencies/
│       └── errors/
│
├── workers/                      # Worker Entry Points
│   ├── consumers/
│   └── jobs/
│
└── setup/
    ├── config.py
    └── di.py
```

### 11.2 Port-Adapter 매핑 예시

| 현재 | 목표 Port | 목표 Adapter |
|------|----------|-------------|
| `UserRepository` | `IUserCommandGateway` | `PostgresUserDataMapper` |
| `UserRepository` | `IUserQueryGateway` | `PostgresUserReader` |
| `TokenService` | `ITokenService` | `JwtTokenService` |
| `OAuthStateStore` | `IStateStore` | `RedisStateStore` |
| `TokenBlacklist` | `ITokenBlacklist` | `RedisTokenBlacklist` |

---

## 12. 전체 파일 카탈로그

예제 프로젝트의 모든 파일을 계층, 역할, 의존성으로 분류한 상세 목록입니다.

### 12.1 Domain Layer (`src/app/domain/`)

도메인 레이어는 **외부 의존성 ZERO** - 순수 Python만 사용합니다.

#### Entities (`domain/entities/`)

| 파일 | 역할 | 의존성 |
|-----|------|--------|
| `base.py` | Entity 베이스 클래스 (ID 기반 동등성) | 없음 |
| `user.py` | User 엔티티 (Aggregate Root) | `base.py`, `value_objects/*` |

#### Value Objects (`domain/value_objects/`)

| 파일 | 역할 | 의존성 |
|-----|------|--------|
| `base.py` | Value Object 베이스 클래스 (값 기반 동등성) | 없음 |
| `user_id.py` | UserId VO (UUID 래퍼) | `base.py` |
| `username.py` | Username VO (검증 로직 포함) | `base.py` |
| `raw_password.py` | RawPassword VO (평문 비밀번호) | `base.py` |
| `user_password_hash.py` | UserPasswordHash VO (해시된 비밀번호) | `base.py` |

#### Enums (`domain/enums/`)

| 파일 | 역할 | 의존성 |
|-----|------|--------|
| `user_role.py` | UserRole 열거형 (USER, ADMIN, SUPER_ADMIN) | 없음 |

#### Ports (`domain/ports/`)

| 파일 | 역할 | 구현체 위치 |
|-----|------|------------|
| `password_hasher.py` | PasswordHasher Protocol | `infrastructure/adapters/password_hasher_bcrypt.py` |
| `user_id_generator.py` | UserIdGenerator Protocol | `infrastructure/adapters/user_id_generator_uuid.py` |

#### Services (`domain/services/`)

| 파일 | 역할 | 의존성 |
|-----|------|--------|
| `user.py` | UserService (사용자 생성, 비밀번호 설정 등 도메인 로직) | `domain/ports/*`, `domain/entities/*` |

#### Exceptions (`domain/exceptions/`)

| 파일 | 역할 | 의존성 |
|-----|------|--------|
| `base.py` | DomainError 베이스 클래스 | 없음 |
| `user.py` | User 관련 도메인 예외들 | `base.py` |

---

### 12.2 Application Layer (`src/app/application/`)

애플리케이션 레이어는 **Domain에만 의존**합니다.

#### Commands (`application/commands/`)

| 파일 | Use Case | Input | Output | 핵심 의존성 |
|-----|----------|-------|--------|------------|
| `create_user.py` | CreateUserInteractor | CreateUserRequest | CreateUserResponse | UserCommandGateway, UserService, Flusher |
| `activate_user.py` | ActivateUserInteractor | ActivateUserRequest | None | UserCommandGateway, Flusher |
| `deactivate_user.py` | DeactivateUserInteractor | DeactivateUserRequest | None | UserCommandGateway, AccessRevoker |
| `set_user_password.py` | SetUserPasswordInteractor | SetUserPasswordRequest | None | UserCommandGateway, UserService |
| `grant_admin.py` | GrantAdminInteractor | GrantAdminRequest | None | UserCommandGateway |
| `revoke_admin.py` | RevokeAdminInteractor | RevokeAdminRequest | None | UserCommandGateway |

#### Queries (`application/queries/`)

| 파일 | Use Case | Input | Output | 핵심 의존성 |
|-----|----------|-------|--------|------------|
| `list_users.py` | ListUsersQueryService | ListUsersRequest | ListUsersQM | UserQueryGateway |

#### Ports (`application/common/ports/`)

| 파일 | Protocol | 책임 | 구현체 |
|-----|----------|------|--------|
| `user_command_gateway.py` | UserCommandGateway | 사용자 쓰기 작업 | SqlaUserDataMapper |
| `user_query_gateway.py` | UserQueryGateway | 사용자 읽기 작업 | SqlaUserReader |
| `flusher.py` | Flusher | DB 변경사항 플러시 | SqlaMainFlusher |
| `transaction_manager.py` | TransactionManager | 트랜잭션 커밋/롤백 | SqlaMainTransactionManager |
| `identity_provider.py` | IdentityProvider | 현재 사용자 ID 제공 | AuthSessionIdentityProvider |
| `access_revoker.py` | AccessRevoker | 사용자 접근 취소 | AuthSessionAccessRevoker |

#### Services (`application/common/services/`)

| 파일 | 역할 | 의존성 |
|-----|------|--------|
| `current_user.py` | CurrentUserService (현재 로그인 사용자 조회) | IdentityProvider, UserCommandGateway |
| `constants.py` | 애플리케이션 상수 | 없음 |

#### Authorization (`application/common/services/authorization/`)

| 파일 | 역할 | 의존성 |
|-----|------|--------|
| `base.py` | Permission Protocol 정의 | 없음 |
| `authorize.py` | authorize() 헬퍼 함수 | AuthorizationError |
| `permissions.py` | 구체적 Permission 구현들 (CanManageRole 등) | `base.py` |
| `composite.py` | AllOf, AnyOf 복합 Permission | `base.py` |
| `role_hierarchy.py` | 역할 계층 정의 | UserRole |

#### Query Params (`application/common/query_params/`)

| 파일 | 역할 | 의존성 |
|-----|------|--------|
| `offset_pagination.py` | OffsetPaginationParams 데이터클래스 | 없음 |
| `sorting.py` | SortingParams, SortingOrder | 없음 |

#### Exceptions (`application/common/exceptions/`)

| 파일 | 역할 | 의존성 |
|-----|------|--------|
| `base.py` | ApplicationError 베이스 | 없음 |
| `authorization.py` | AuthorizationError | `base.py` |
| `query.py` | SortingError 등 | `base.py` |

---

### 12.3 Infrastructure Layer (`src/app/infrastructure/`)

인프라스트럭처 레이어는 **모든 외부 시스템과의 연결**을 담당합니다.

#### Core Adapters (`infrastructure/adapters/`)

| 파일 | 구현 대상 | 기술 | 의존성 |
|-----|----------|------|--------|
| `user_data_mapper_sqla.py` | UserCommandGateway | SQLAlchemy | `application/common/ports/*` |
| `user_reader_sqla.py` | UserQueryGateway | SQLAlchemy | `application/common/ports/*` |
| `main_flusher_sqla.py` | Flusher | SQLAlchemy | `application/common/ports/*` |
| `main_transaction_manager_sqla.py` | TransactionManager | SQLAlchemy | `application/common/ports/*` |
| `password_hasher_bcrypt.py` | PasswordHasher | bcrypt | `domain/ports/*` |
| `user_id_generator_uuid.py` | UserIdGenerator | uuid | `domain/ports/*` |
| `types.py` | 타입 앨리어스 (MainAsyncSession, HasherThreadPoolExecutor, HasherSemaphore) | NewType | SQLAlchemy, asyncio |
| `constants.py` | 에러 메시지 상수 | - | 없음 |

#### Persistence (`infrastructure/persistence_sqla/`)

| 경로 | 역할 |
|-----|------|
| `registry.py` | SQLAlchemy mapper_registry 설정 |
| `mappings/all.py` | 모든 매핑 import 및 start_mappers() |
| `mappings/user.py` | User Entity ↔ users 테이블 매핑 |
| `mappings/auth_session.py` | AuthSession ↔ auth_sessions 테이블 매핑 |
| `alembic/env.py` | Alembic 마이그레이션 환경 |
| `alembic/versions/*.py` | 데이터베이스 마이그레이션 스크립트 |

#### Auth Module (`infrastructure/auth/`)

**handlers/** - 인증 비즈니스 로직 (Infrastructure 레벨):

| 파일 | 역할 | 의존성 |
|-----|------|--------|
| `log_in.py` | LogInHandler (로그인 처리) | AuthSessionService, UserCommandGateway |
| `log_out.py` | LogOutHandler (로그아웃 처리) | AuthSessionService |
| `sign_up.py` | SignUpHandler (회원가입 처리) | UserService, UserCommandGateway |
| `change_password.py` | ChangePasswordHandler | UserService, UserCommandGateway |
| `constants.py` | 에러 메시지 상수 | 없음 |

**adapters/** - Auth 전용 어댑터:

| 파일 | 구현 대상 | 역할 |
|-----|----------|------|
| `identity_provider.py` | IdentityProvider | 세션에서 현재 사용자 ID 추출 |
| `access_revoker.py` | AccessRevoker | 사용자의 모든 세션 삭제 |
| `data_mapper_sqla.py` | AuthSessionGateway | AuthSession CRUD |
| `transaction_manager_sqla.py` | AuthTransactionManager | Auth DB 트랜잭션 |
| `types.py` | 타입 앨리어스 | AuthAsyncSession 등 |

**session/** - 세션 관리:

| 파일 | 역할 |
|-----|------|
| `model.py` | AuthSession 모델 (Infrastructure 레벨 엔티티) |
| `service.py` | AuthSessionService (세션 생성, 검증, 갱신) |
| `id_generator_str.py` | 문자열 세션 ID 생성기 |
| `timer_utc.py` | UTC 시간 제공자 |

**session/ports/** - Infrastructure 내부 Port:

| 파일 | Protocol | 구현체 |
|-----|----------|--------|
| `gateway.py` | AuthSessionGateway | SqlaAuthSessionDataMapper |
| `transaction_manager.py` | AuthSessionTransactionManager | SqlaAuthSessionTransactionManager |
| `transport.py` | AuthSessionTransport | JwtCookieAuthSessionTransport |

**exceptions.py** - Auth 모듈 예외:

| 예외 | 용도 |
|-----|------|
| `AuthenticationError` | 인증 실패 |
| `AlreadyAuthenticatedError` | 이미 인증됨 |
| `ReAuthenticationError` | 재인증 필요 |
| `AuthenticationChangeError` | 인증 변경 실패 |

#### Infrastructure Exceptions (`infrastructure/exceptions/`)

| 파일 | 역할 |
|-----|------|
| `base.py` | InfrastructureError 베이스 |
| `gateway.py` | DataMapperError, ReaderError |
| `password_hasher.py` | PasswordHasherError |

---

### 12.4 Presentation Layer (`src/app/presentation/`)

프레젠테이션 레이어는 **HTTP 요청/응답 변환**을 담당합니다.

#### Controllers (`presentation/http/controllers/`)

**account/** - 계정 관련 엔드포인트:

| 파일 | 엔드포인트 | Use Case/Handler |
|-----|-----------|------------------|
| `sign_up.py` | POST /account/sign-up | SignUpHandler |
| `log_in.py` | POST /account/log-in | LogInHandler |
| `log_out.py` | POST /account/log-out | LogOutHandler |
| `change_password.py` | POST /account/change-password | ChangePasswordHandler |
| `router.py` | account_router 정의 | - |

**users/** - 사용자 관리 엔드포인트:

| 파일 | 엔드포인트 | Use Case |
|-----|-----------|----------|
| `create_user.py` | POST /users | CreateUserInteractor |
| `list_users.py` | GET /users | ListUsersQueryService |
| `activate_user.py` | POST /users/{id}/activate | ActivateUserInteractor |
| `deactivate_user.py` | POST /users/{id}/deactivate | DeactivateUserInteractor |
| `grant_admin.py` | POST /users/{id}/grant-admin | GrantAdminInteractor |
| `revoke_admin.py` | POST /users/{id}/revoke-admin | RevokeAdminInteractor |
| `set_user_password.py` | POST /users/{id}/set-password | SetUserPasswordInteractor |
| `router.py` | users_router 정의 | - |

**general/** - 일반 엔드포인트:

| 파일 | 엔드포인트 | 역할 |
|-----|-----------|------|
| `health.py` | GET /health | Health check |
| `router.py` | general_router 정의 | - |

**라우터 구조:**

| 파일 | 역할 |
|-----|------|
| `root_router.py` | 최상위 라우터 (general 포함) |
| `api_v1_router.py` | /api/v1 프리픽스 라우터 (account, users 포함) |

#### Auth HTTP Components (`presentation/http/auth/`)

| 파일 | 역할 |
|-----|------|
| `access_token_processor_jwt.py` | JWT 토큰 생성/검증 |
| `asgi_middleware.py` | AuthMiddleware (요청마다 세션 검증) |
| `cookie_params.py` | 쿠키 설정 (httponly, secure 등) |
| `openapi_marker.py` | OpenAPI 보안 스키마 마커 |
| `constants.py` | JWT 관련 상수 |

**adapters/** - Presentation 전용 어댑터:

| 파일 | 구현 대상 | 역할 |
|-----|----------|------|
| `session_transport_jwt_cookie.py` | SessionTransport | JWT를 HTTP 쿠키로 전송 |

#### Error Handling (`presentation/http/errors/`)

| 파일 | 역할 |
|-----|------|
| `translators.py` | 도메인/애플리케이션 예외 → HTTP 응답 변환 |
| `callbacks.py` | FastAPI exception_handler 콜백 |

---

### 12.5 Setup Layer (`src/app/setup/`)

애플리케이션 부트스트랩 및 설정을 담당합니다.

#### Config (`setup/config/`)

| 파일 | 역할 |
|-----|------|
| `loader.py` | TOML 설정 파일 로딩 |
| `settings.py` | Settings 통합 dataclass |
| `database.py` | DatabaseConfig (connection string 등) |
| `security.py` | SecurityConfig (JWT 키, 세션 TTL 등) |
| `logs.py` | LogsConfig (로그 레벨, 포맷) |

#### IoC Container (`setup/ioc/`)

Dishka DI 컨테이너 Provider 정의:

| 파일 | 역할 | 등록 대상 |
|-----|------|----------|
| `settings.py` | 설정 Provider | Settings, DatabaseConfig 등 |
| `domain.py` | Domain Provider | UserService, PasswordHasher, UserIdGenerator |
| `application.py` | Application Provider | Command/Query Use Cases, CurrentUserService |
| `infrastructure.py` | Infrastructure Provider | Gateway, Flusher, Session 등 |
| `presentation.py` | Presentation Provider | AccessTokenProcessor, SessionTransport |
| `provider_registry.py` | 모든 Provider 통합 | Container 생성 |

**Dishka Scope 전략:** *(예제 프로젝트 참고용 - 우리 프로젝트에는 미적용)*

| Scope | 생명주기 | 사용 대상 |
|-------|---------|----------|
| `Scope.APP` | 애플리케이션 전체 | AsyncEngine, SessionMaker, ThreadPoolExecutor, Settings |
| `Scope.REQUEST` | HTTP 요청 단위 | AsyncSession, Use Cases, Handlers |

> ⚠️ **Note**: 우리 프로젝트에서는 FastAPI의 기본 `Depends()` 패턴을 사용하며, Dishka DI 컨테이너는 적용하지 않습니다.

#### App Factory (`setup/app_factory.py`)

```python
def create_app() -> FastAPI:
    # 1. Settings 로드
    # 2. Logging 설정
    # 3. SQLAlchemy Mapper 시작
    # 4. Dishka Container 생성
    # 5. FastAPI 앱 생성
    # 6. Middleware 추가
    # 7. Router 등록
    # 8. Exception Handler 등록
    return app
```

---

### 12.6 Entry Point

| 파일 | 역할 |
|-----|------|
| `src/app/run.py` | uvicorn 실행 진입점 |

---

### 12.7 Tests (`tests/`)

| 경로 | 역할 |
|-----|------|
| `tests/app/unit/domain/` | Domain 레이어 단위 테스트 |
| `tests/app/unit/application/` | Application 레이어 단위 테스트 |
| `tests/app/unit/infrastructure/` | Infrastructure 레이어 단위 테스트 |
| `tests/app/unit/setup/` | Setup 단위 테스트 |
| `tests/app/unit/factories/` | 테스트 팩토리 (엔티티, VO 생성) |
| `tests/app/integration/` | 통합 테스트 |
| `tests/app/performance/` | 성능 프로파일링 테스트 |

---

### 12.8 의존성 흐름 요약

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              DEPENDENCIES FLOW                               │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  presentation/http/controllers/users/create_user.py                          │
│       │                                                                      │
│       ├── Depends(Dishka) ──────────────────────────────────────┐           │
│       │                                                          │           │
│       ▼                                                          │           │
│  application/commands/create_user.py (CreateUserInteractor)      │           │
│       │                                                          │           │
│       ├── UserService           ◄── domain/services/user.py     │           │
│       ├── UserCommandGateway    ◄── application/common/ports/   │ Dishka    │
│       ├── Flusher               ◄── application/common/ports/   │ IoC       │
│       └── TransactionManager    ◄── application/common/ports/   │ Container │
│                                                                  │           │
│       구현체 주입:                                                │           │
│       ├── UserService           ◄── setup/ioc/domain.py         │           │
│       ├── SqlaUserDataMapper    ◄── setup/ioc/infrastructure.py │           │
│       ├── SqlaMainFlusher       ◄── setup/ioc/infrastructure.py │           │
│       └── SqlaMainTxManager     ◄── setup/ioc/infrastructure.py │           │
│                                                                  │           │
│                                                                  ▼           │
│  domain/services/user.py (UserService)                                       │
│       │                                                                      │
│       ├── PasswordHasher        ◄── domain/ports/                           │
│       └── UserIdGenerator       ◄── domain/ports/                           │
│                                                                              │
│       구현체:                                                                 │
│       ├── BcryptPasswordHasher  ◄── infrastructure/adapters/                │
│       └── UuidUserIdGenerator   ◄── infrastructure/adapters/                │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 13. 참고 자료

### 원본 자료 (Primary Sources)

**아키텍처:**
- [The Clean Architecture](https://blog.cleancoder.com/uncle-bob/2012/08/13/the-clean-architecture.html) - Robert C. Martin (2012)
- [Hexagonal Architecture](https://alistair.cockburn.us/hexagonal-architecture/) - Alistair Cockburn (2005)
- [The Onion Architecture](https://jeffreypalermo.com/2008/07/the-onion-architecture-part-1/) - Jeffrey Palermo (2008)
- [CQRS](https://martinfowler.com/bliki/CQRS.html) - Martin Fowler

**패턴 카탈로그:**
- [PoEAA Catalog](https://martinfowler.com/eaaCatalog/) - Martin Fowler
- [Repository Pattern](https://martinfowler.com/eaaCatalog/repository.html)
- [Data Mapper Pattern](https://martinfowler.com/eaaCatalog/dataMapper.html)
- [Unit of Work Pattern](https://martinfowler.com/eaaCatalog/unitOfWork.html)
- [Gateway Pattern](https://martinfowler.com/eaaCatalog/gateway.html)

### 핵심 서적

| 책 | 저자 | 연도 | 별칭 |
|----|-----|------|------|
| *Domain-Driven Design: Tackling Complexity in the Heart of Software* | Eric Evans | 2003 | Blue Book |
| *Implementing Domain-Driven Design* | Vaughn Vernon | 2013 | Red Book |
| *Patterns of Enterprise Application Architecture* | Martin Fowler | 2002 | PoEAA |
| *Clean Architecture: A Craftsman's Guide to Software Structure and Design* | Robert C. Martin | 2017 | - |
| *Clean Code: A Handbook of Agile Software Craftsmanship* | Robert C. Martin | 2008 | - |

### 예제 프로젝트

- [fastapi-clean-example](https://github.com/ivan-borovets/fastapi-clean-example) - 이 문서의 분석 대상
- [python-clean-architecture](https://github.com/pcah/python-clean-architecture) - 또 다른 Python 구현
- [cosmic-python](https://github.com/cosmicpython/book) - Architecture Patterns with Python 책 예제

### 추가 학습 자료

- [Architecture Patterns with Python](https://www.cosmicpython.com/) - Harry Percival, Bob Gregory (무료 온라인)
- [The Clean Code Blog](https://blog.cleancoder.com/) - Robert C. Martin
- [Martin Fowler's Blog](https://martinfowler.com/) - 패턴 및 아키텍처

