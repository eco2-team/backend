# Python DI 라이브러리 비교: Dishka vs Dependency-Injector

## 1. 개요

Python 생태계에서 의존성 주입(Dependency Injection)을 지원하는 대표적인 두 라이브러리를 비교합니다.

| 항목 | Dishka | Dependency-Injector |
|------|--------|---------------------|
| GitHub Stars | ~1,200+ ⭐ | ~4,000+ ⭐ |
| 첫 릴리즈 | 2023년 | 2016년 |
| 성숙도 | 신생 (빠르게 성장) | 성숙 (8년+) |
| 최근 커밋 활동 | 활발 | 보통 |
| Python 버전 | 3.10+ | 3.6+ |
| 주요 개발자 | reagento | ETS Labs |

---

## 2. 핵심 철학 비교

### Dishka: "Type-First, Auto-Wiring"
- 타입 힌트 기반 자동 의존성 해결
- 스코프 중심 라이프사이클 관리
- 최소한의 보일러플레이트

### Dependency-Injector: "Explicit Configuration"
- 명시적 Provider 선언
- 컨테이너 기반 조직화
- 다양한 Provider 타입 제공

---

## 3. 코드베이스 비교: 현재 프로젝트 패턴 분석

### 현재 프로젝트의 DI 패턴 (FastAPI Depends)

현재 `auth` 도메인은 FastAPI의 기본 `Depends()` 패턴을 사용합니다:

```python
# domains/auth/application/services/auth.py (현재 방식)
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
        # ...
```

**문제점:**
1. 테스트 시 의존성 교체가 번거로움 (`app.dependency_overrides` 사용 필요)
2. 라이프사이클 관리가 불명확함
3. 중첩 의존성에서 같은 인스턴스 재사용이 보장되지 않음
4. 순환 의존성 감지 불가

---

## 4. Dishka로 리팩토링했을 때

### 4.1 Provider 정의

```python
# domains/auth/di/providers.py
from dishka import Provider, Scope, provide
from sqlalchemy.ext.asyncio import AsyncSession

class AuthProvider(Provider):
    """Auth 도메인 의존성 제공자"""
    
    @provide(scope=Scope.REQUEST)
    async def get_session(self, engine: AsyncEngine) -> AsyncSession:
        """요청 스코프의 DB 세션 - 요청 종료 시 자동 정리"""
        async with AsyncSession(engine) as session:
            yield session
    
    @provide(scope=Scope.REQUEST)
    def get_user_repository(self, session: AsyncSession) -> UserRepository:
        """타입 힌트만으로 session 자동 주입"""
        return UserRepository(session)
    
    @provide(scope=Scope.REQUEST)
    def get_token_service(self, settings: Settings) -> TokenService:
        return TokenService(settings)
    
    @provide(scope=Scope.APP)
    def get_settings(self) -> Settings:
        """앱 스코프 - 싱글톤처럼 동작"""
        return Settings()
    
    @provide(scope=Scope.REQUEST)
    def get_auth_service(
        self,
        session: AsyncSession,
        token_service: TokenService,
        state_store: OAuthStateStore,
        blacklist: TokenBlacklist,
        user_token_store: UserTokenStore,
        settings: Settings,
    ) -> AuthService:
        """모든 의존성 자동 해결"""
        return AuthService(
            session=session,
            token_service=token_service,
            state_store=state_store,
            blacklist=blacklist,
            token_store=user_token_store,
            settings=settings,
        )
```

### 4.2 FastAPI 통합

```python
# domains/auth/main.py
from dishka import make_async_container
from dishka.integrations.fastapi import setup_dishka

from domains.auth.di.providers import AuthProvider, InfraProvider

container = make_async_container(AuthProvider(), InfraProvider())

app = FastAPI()
setup_dishka(container, app)
```

### 4.3 라우터에서 사용

```python
# domains/auth/api/v1/endpoints/auth.py
from dishka.integrations.fastapi import FromDishka, inject

@router.post("/callback")
@inject
async def oauth_callback(
    request: OAuthLoginRequest,
    auth_service: FromDishka[AuthService],  # 자동 주입
):
    return await auth_service.callback(request)
```

### 4.4 Dishka의 장점

```python
# ✅ 스코프 기반 캐싱 - 같은 요청 내 동일 인스턴스 보장
@provide(scope=Scope.REQUEST)
async def get_session(self) -> AsyncSession:
    # 한 요청 내에서 여러 서비스가 같은 세션 공유
    ...

# ✅ 자동 리소스 정리 (yield 사용)
@provide(scope=Scope.REQUEST)
async def get_session(self, engine: AsyncEngine) -> AsyncSession:
    async with AsyncSession(engine) as session:
        yield session  # 요청 종료 시 자동 close
    # cleanup 코드 여기에

# ✅ 컴포넌트로 동일 타입 구분
from dishka import Component

class DbComponent(Component): pass
class CacheComponent(Component): pass

@provide(scope=Scope.APP, component=DbComponent)
async def get_db_redis(self) -> Redis: ...

@provide(scope=Scope.APP, component=CacheComponent)
async def get_cache_redis(self) -> Redis: ...
```

---

## 5. Dependency-Injector로 리팩토링했을 때

### 5.1 Container 정의

```python
# domains/auth/containers.py
from dependency_injector import containers, providers
from dependency_injector.wiring import Provide, inject

class AuthContainer(containers.DeclarativeContainer):
    """Auth 도메인 DI 컨테이너"""
    
    config = providers.Configuration()
    
    # 싱글톤 - 앱 전체에서 공유
    settings = providers.Singleton(Settings)
    
    # DB 엔진 (싱글톤)
    engine = providers.Singleton(
        create_async_engine,
        url=config.database_url,
        echo=False,
    )
    
    # DB 세션 팩토리 (매번 새 인스턴스)
    session_factory = providers.Factory(
        AsyncSession,
        bind=engine,
    )
    
    # 리포지토리 (Factory - 요청마다 새로 생성)
    user_repository = providers.Factory(
        UserRepository,
        session=session_factory,  # 명시적 바인딩 필요
    )
    
    # 토큰 서비스
    token_service = providers.Factory(
        TokenService,
        settings=settings,
    )
    
    # Auth 서비스 (모든 의존성 명시)
    auth_service = providers.Factory(
        AuthService,
        session=session_factory,
        token_service=token_service,
        state_store=providers.Factory(OAuthStateStore, settings=settings),
        blacklist=providers.Factory(TokenBlacklist, settings=settings),
        token_store=providers.Factory(UserTokenStore, settings=settings),
        settings=settings,
    )
```

### 5.2 FastAPI 통합

```python
# domains/auth/main.py
from dependency_injector.wiring import Provide, inject

container = AuthContainer()
container.config.from_dict({
    "database_url": os.getenv("DATABASE_URL"),
})
container.wire(modules=[
    "domains.auth.api.v1.endpoints.auth",
    "domains.auth.api.v1.endpoints.users",
])

app = FastAPI()
```

### 5.3 라우터에서 사용

```python
# domains/auth/api/v1/endpoints/auth.py
from dependency_injector.wiring import Provide, inject

@router.post("/callback")
@inject
async def oauth_callback(
    request: OAuthLoginRequest,
    auth_service: AuthService = Depends(Provide[AuthContainer.auth_service]),
):
    return await auth_service.callback(request)
```

### 5.4 Dependency-Injector의 장점

```python
# ✅ 다양한 Provider 타입
providers.Singleton(...)     # 싱글톤
providers.Factory(...)       # 매번 새 인스턴스
providers.ThreadSafeSingleton(...)  # 스레드 안전 싱글톤
providers.Resource(...)      # 리소스 관리 (init/shutdown)
providers.Callable(...)      # 함수 호출
providers.Object(...)        # 기존 객체 래핑

# ✅ Configuration Provider - 설정 관리 특화
class Container(containers.DeclarativeContainer):
    config = providers.Configuration()
    
    db = providers.Singleton(
        Database,
        host=config.db.host,
        port=config.db.port.as_int(),  # 타입 변환
    )

# 사용
container.config.from_yaml("config.yml")
container.config.from_env("APP_")

# ✅ Override for Testing
def test_auth_service():
    container = AuthContainer()
    
    # Mock으로 교체
    with container.user_repository.override(MockUserRepository()):
        service = container.auth_service()
        result = service.login(...)
```

---

## 6. 기능별 상세 비교

### 6.1 자동 와이어링 (Auto-Wiring)

| 기능 | Dishka | Dependency-Injector |
|------|--------|---------------------|
| 타입 힌트 기반 자동 해결 | ✅ 기본 지원 | ❌ 명시적 바인딩 필요 |
| 의존성 그래프 자동 구축 | ✅ | ❌ |
| 순환 의존성 감지 | ✅ 컴파일 타임 | ❌ |

**Dishka 예시:**
```python
# 타입 힌트만으로 자동 주입
@provide(scope=Scope.REQUEST)
def get_auth_service(
    self,
    repo: UserRepository,      # 자동으로 UserRepository provider 찾음
    token: TokenService,       # 자동으로 TokenService provider 찾음
) -> AuthService:
    return AuthService(repo, token)
```

**Dependency-Injector 예시:**
```python
# 모든 의존성 명시적 연결 필요
auth_service = providers.Factory(
    AuthService,
    repo=user_repository,     # 명시적 바인딩
    token=token_service,      # 명시적 바인딩
)
```

### 6.2 스코프 & 라이프사이클

| 기능 | Dishka | Dependency-Injector |
|------|--------|---------------------|
| 스코프 종류 | APP, REQUEST, ACTION, SESSION | Singleton, Factory만 기본 |
| 요청 스코프 캐싱 | ✅ 자동 | ❌ 수동 구현 필요 |
| 스코프 간 의존성 검증 | ✅ | ❌ |
| 리소스 자동 정리 | ✅ yield 지원 | ⚠️ Resource provider만 |

**Dishka - 스코프 계층:**
```python
class Scope(Enum):
    APP = "app"           # 앱 전체 (싱글톤)
    REQUEST = "request"   # HTTP 요청
    ACTION = "action"     # 단일 작업 단위
    SESSION = "session"   # 사용자 세션

# REQUEST 스코프는 APP 스코프에 의존 가능
# APP 스코프는 REQUEST 스코프에 의존 불가 (검증됨)
```

### 6.3 Async 지원

| 기능 | Dishka | Dependency-Injector |
|------|--------|---------------------|
| async provider | ✅ 네이티브 | ⚠️ 제한적 |
| async 리소스 정리 | ✅ | ⚠️ |
| async context manager | ✅ | ❌ |

**Dishka - 완전한 async 지원:**
```python
@provide(scope=Scope.REQUEST)
async def get_session(self, engine: AsyncEngine) -> AsyncSession:
    async with AsyncSession(engine) as session:
        yield session  # async generator로 리소스 관리

@provide(scope=Scope.REQUEST)
async def get_redis(self) -> Redis:
    client = await Redis.from_url("redis://localhost")
    yield client
    await client.close()  # async cleanup
```

**Dependency-Injector - 제한적 async:**
```python
# Resource provider로 가능하지만 복잡함
class AsyncResource:
    async def init(self) -> Redis:
        return await Redis.from_url("...")
    
    async def shutdown(self, resource: Redis):
        await resource.close()

redis = providers.Resource(AsyncResource)
```

### 6.4 테스트 용이성

| 기능 | Dishka | Dependency-Injector |
|------|--------|---------------------|
| Mock 주입 | ✅ 컨테이너 교체 | ✅ override() |
| 부분 교체 | ✅ | ✅ |
| 병렬 테스트 안전성 | ✅ | ⚠️ 전역 상태 주의 |

**Dishka 테스트:**
```python
@pytest.fixture
def test_container():
    return make_async_container(
        TestProvider(),  # Mock provider
        AuthProvider(),
    )

async def test_auth_service(test_container):
    async with test_container() as request_container:
        service = await request_container.get(AuthService)
        result = await service.login(...)
```

**Dependency-Injector 테스트:**
```python
def test_auth_service():
    container = AuthContainer()
    
    with container.user_repository.override(MockUserRepository()):
        with container.token_service.override(MockTokenService()):
            service = container.auth_service()
            result = service.login(...)
```

### 6.5 성능

| 측정 항목 | Dishka | Dependency-Injector |
|----------|--------|---------------------|
| 의존성 해결 속도 | 빠름 | 보통 |
| 메모리 사용량 | 낮음 | 보통 |
| 대규모 그래프 초기화 | 빠름 | 느림 |
| 스코프 캐싱 오버헤드 | 최소 | N/A |

---

## 7. 프레임워크 통합 지원

### Dishka 공식 지원
- ✅ FastAPI
- ✅ Litestar
- ✅ aiohttp
- ✅ Flask
- ✅ Starlette
- ✅ FastStream
- ✅ Arq (task queue)
- ✅ gRPC

### Dependency-Injector 공식 지원
- ✅ Flask
- ⚠️ FastAPI (wiring 필요)
- ⚠️ aiohttp (수동 설정)
- ❌ 대부분 수동 통합

---

## 8. 마이그레이션 고려사항

### 현재 프로젝트 → Dishka

**장점:**
1. FastAPI Depends와 유사한 패턴으로 학습 곡선 낮음
2. 타입 힌트 기반으로 기존 코드 변경 최소화
3. 스코프 기반 리소스 관리로 DB 세션 누수 방지
4. async 완벽 지원

**고려할 점:**
1. 비교적 새로운 라이브러리 (안정성 검증 필요)
2. 커뮤니티 규모가 작음
3. 문서/예제가 상대적으로 적음

### 현재 프로젝트 → Dependency-Injector

**장점:**
1. 성숙한 라이브러리로 안정성 검증됨
2. 큰 커뮤니티와 풍부한 문서
3. Configuration provider로 설정 관리 통합
4. 다양한 Provider 타입

**고려할 점:**
1. 명시적 바인딩으로 보일러플레이트 증가
2. async 지원이 제한적
3. 스코프 캐싱 직접 구현 필요

---

## 9. 권장 사항

### 이 프로젝트에 적합한 선택: **Dishka** 🏆

**이유:**

1. **async-first 아키텍처**
   - 현재 프로젝트는 `AsyncSession`, `aioredis`, `aio_pika` 등 완전한 async 스택
   - Dishka의 네이티브 async 지원이 자연스러움

2. **FastAPI 통합**
   - 공식 FastAPI 통합으로 기존 `Depends()` 패턴에서 부드러운 전환
   - `FromDishka[T]` 타입 힌트로 명확한 주입 표현

3. **스코프 기반 리소스 관리**
   - DB 세션, Redis 연결 등의 라이프사이클 자동 관리
   - 연결 누수 방지

4. **타입 힌트 활용**
   - 현재 코드베이스가 이미 타입 힌트를 적극 사용
   - 자동 와이어링으로 보일러플레이트 감소

5. **현대적 Python**
   - Python 3.10+ 타겟으로 최신 기능 활용
   - `typing` 모듈 완벽 지원

### 점진적 마이그레이션 전략

```
Phase 1: 인프라 레이어 (2주)
├── Settings, Redis, DB Engine을 Dishka로 이전
└── 기존 Depends()와 공존

Phase 2: 도메인 서비스 (2주)
├── Repository, Service 클래스 이전
└── Provider 모듈화

Phase 3: API 레이어 (1주)
├── 라우터 @inject 적용
└── Depends() 제거

Phase 4: 테스트 리팩토링 (1주)
├── Test Provider 구성
└── Mock 주입 패턴 확립
```

---

## 10. 참고 자료

- [Dishka GitHub](https://github.com/reagento/dishka)
- [Dishka Documentation](https://dishka.readthedocs.io/)
- [Dishka vs Dependency-Injector 공식 비교](https://dishka.readthedocs.io/en/latest/alternatives/dependency-injector.html)
- [Dependency-Injector GitHub](https://github.com/ets-labs/python-dependency-injector)
- [Dependency-Injector Documentation](https://python-dependency-injector.ets-labs.org/)









