# FastAPI Lifespan: 애플리케이션 생명주기 관리

## 1. Context Manager 기초

FastAPI Lifespan을 이해하기 위해서는 먼저 Python의 **Context Manager** 패턴을 이해해야 합니다.

### 1.1 `with` 문과 Context Manager

```python
# 파일 처리 - 가장 흔한 Context Manager 사용 예
with open("file.txt", "r") as f:
    content = f.read()
# 여기서 파일이 자동으로 닫힘
```

**`with` 문이 하는 일:**

```
1. 진입: __enter__() 호출 → 리소스 획득
2. 본문: 블록 내 코드 실행
3. 퇴장: __exit__() 호출 → 리소스 해제 (예외 발생해도 실행)
```

### 1.2 Context Manager 프로토콜

Context Manager는 두 개의 메서드로 정의됩니다:

```python
class FileManager:
    """수동으로 구현한 Context Manager."""
    
    def __init__(self, filename: str, mode: str):
        self.filename = filename
        self.mode = mode
        self.file = None
    
    def __enter__(self):
        """with 블록 진입 시 호출.
        
        Returns:
            as 절에 바인딩될 값
        """
        print(f"Opening {self.filename}")
        self.file = open(self.filename, self.mode)
        return self.file  # as f 에 할당됨
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """with 블록 종료 시 호출 (예외 발생해도 실행).
        
        Args:
            exc_type: 예외 타입 (없으면 None)
            exc_val: 예외 값 (없으면 None)
            exc_tb: Traceback (없으면 None)
        
        Returns:
            True: 예외 억제
            False/None: 예외 전파
        """
        print(f"Closing {self.filename}")
        if self.file:
            self.file.close()
        return False  # 예외가 있으면 전파


# 사용
with FileManager("test.txt", "w") as f:
    f.write("Hello")
# 출력:
# Opening test.txt
# Closing test.txt
```

### 1.3 `@contextmanager` 데코레이터

클래스 대신 **제너레이터 함수**로 간단하게 Context Manager를 만들 수 있습니다:

```python
from contextlib import contextmanager


@contextmanager
def file_manager(filename: str, mode: str):
    """제너레이터 기반 Context Manager."""
    
    # __enter__ 부분
    print(f"Opening {filename}")
    f = open(filename, mode)
    
    try:
        yield f  # ← as 절에 바인딩, 여기서 with 블록 실행
    finally:
        # __exit__ 부분 (예외 발생해도 실행)
        print(f"Closing {filename}")
        f.close()


# 사용 (동일)
with file_manager("test.txt", "w") as f:
    f.write("Hello")
```

**`yield`의 역할:**

```
┌─────────────────────────────────────────────────────────────┐
│                    @contextmanager 흐름                      │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│   with file_manager("test.txt", "w") as f:                 │
│        │                                                    │
│        ▼                                                    │
│   ┌─────────────────────────────────────────────┐          │
│   │ 1. yield 이전 코드 실행 (= __enter__)        │          │
│   │    f = open(filename, mode)                 │          │
│   └─────────────────────────────────────────────┘          │
│        │                                                    │
│        ▼                                                    │
│   ┌─────────────────────────────────────────────┐          │
│   │ 2. yield f → f가 as 절에 바인딩              │          │
│   │    → 함수 실행 "일시 정지"                   │          │
│   └─────────────────────────────────────────────┘          │
│        │                                                    │
│        ▼                                                    │
│   ┌─────────────────────────────────────────────┐          │
│   │ 3. with 블록 내 코드 실행                    │          │
│   │    f.write("Hello")                         │          │
│   └─────────────────────────────────────────────┘          │
│        │                                                    │
│        ▼                                                    │
│   ┌─────────────────────────────────────────────┐          │
│   │ 4. yield 이후 코드 실행 (= __exit__)         │          │
│   │    f.close()                                │          │
│   │    (finally 블록이므로 예외 발생해도 실행)    │          │
│   └─────────────────────────────────────────────┘          │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### 1.4 비동기 Context Manager (`async with`)

비동기 코드에서는 `__aenter__`/`__aexit__` 프로토콜을 사용합니다:

```python
class AsyncDatabaseConnection:
    """비동기 Context Manager."""
    
    async def __aenter__(self):
        """async with 진입."""
        print("Connecting to database...")
        await asyncio.sleep(0.1)  # 비동기 연결
        self.conn = "database_connection"
        return self.conn
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """async with 종료."""
        print("Disconnecting from database...")
        await asyncio.sleep(0.1)  # 비동기 연결 해제
        self.conn = None
        return False


# 사용
async def main():
    async with AsyncDatabaseConnection() as conn:
        print(f"Using {conn}")
```

### 1.5 `@asynccontextmanager` 데코레이터

**비동기 제너레이터**로 간단하게 비동기 Context Manager를 만듭니다:

```python
from contextlib import asynccontextmanager


@asynccontextmanager
async def async_database():
    """비동기 제너레이터 기반 Context Manager."""
    
    # __aenter__ 부분
    print("Connecting to database...")
    await asyncio.sleep(0.1)
    conn = "database_connection"
    
    try:
        yield conn  # ← as 절에 바인딩, 여기서 async with 블록 실행
    finally:
        # __aexit__ 부분
        print("Disconnecting from database...")
        await asyncio.sleep(0.1)


# 사용
async def main():
    async with async_database() as conn:
        print(f"Using {conn}")
```

### 1.6 Generator의 이해

`yield`를 사용하는 함수는 **Generator 함수**가 됩니다.

```python
def countdown(n):
    """일반 Generator 함수."""
    print("Starting countdown")
    while n > 0:
        yield n  # 값을 반환하고 일시 정지
        n -= 1
    print("Done!")


# Generator 객체 생성 (아직 실행 안 됨)
gen = countdown(3)
print(type(gen))  # <class 'generator'>

# next()로 값을 하나씩 가져옴
print(next(gen))  # Starting countdown → 3
print(next(gen))  # 2
print(next(gen))  # 1
print(next(gen))  # Done! → StopIteration 예외
```

**Generator의 특징:**

| 특징 | 설명 |
|------|------|
| **지연 실행 (Lazy)** | 호출 시 코드가 바로 실행되지 않음 |
| **상태 유지** | 지역 변수가 `yield` 사이에서 유지됨 |
| **일회성** | 한 번 소진되면 재사용 불가 |
| **메모리 효율** | 모든 값을 한번에 생성하지 않음 |

### 1.7 Async Generator (PEP 525)

Python 3.6+에서 **비동기 제너레이터**를 사용할 수 있습니다:

```python
async def async_countdown(n):
    """Async Generator 함수."""
    print("Starting async countdown")
    while n > 0:
        await asyncio.sleep(0.1)  # 비동기 대기
        yield n  # async yield
        n -= 1
    print("Done!")


# 사용
async def main():
    async for num in async_countdown(3):
        print(num)
```

**`@asynccontextmanager`의 내부 동작:**

```python
# @asynccontextmanager가 하는 일 (간소화)
def asynccontextmanager(func):
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        return _AsyncGeneratorContextManager(func, args, kwargs)
    return wrapper


class _AsyncGeneratorContextManager:
    def __init__(self, func, args, kwargs):
        self._gen = func(*args, **kwargs)  # async generator 생성
    
    async def __aenter__(self):
        # generator에서 첫 번째 yield까지 실행
        return await self._gen.__anext__()
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        # generator의 나머지 부분 실행 (finally)
        try:
            await self._gen.__anext__()
        except StopAsyncIteration:
            pass
```

### 1.8 핵심 요약: `yield`의 세 가지 역할

| 역할 | 설명 | 예시 |
|------|------|------|
| **값 반환** | `as` 절에 바인딩될 값 | `yield conn` → `as conn` |
| **실행 중단** | 함수 실행을 일시 정지 | with/async with 블록 실행 |
| **제어 반환** | 블록 종료 후 yield 이후 실행 | finally 블록의 cleanup 코드 |

```python
@asynccontextmanager
async def example():
    resource = await acquire_resource()  # 1. 리소스 획득
    try:
        yield resource  # 2. 반환 + 중단 + 제어 반환
    finally:
        await release_resource(resource)  # 3. 정리
```

### 1.9 yield vs return vs yield from

```python
# return: 함수 종료, 값 반환
def get_value():
    return 42


# yield: 값 생성, 함수 일시 정지 (Generator)
def generate_values():
    yield 1
    yield 2
    yield 3


# yield from: 다른 iterable/generator 위임 (PEP 380)
def nested_generator():
    yield from [1, 2, 3]  # 리스트의 각 요소를 순차 yield
    yield from generate_values()  # 다른 generator 위임


# 비교
print(get_value())  # 42
print(list(generate_values()))  # [1, 2, 3]
print(list(nested_generator()))  # [1, 2, 3, 1, 2, 3]
```

---

## 2. FastAPI Lifespan 개요

### 2.1 Lifespan이란?

**Lifespan**은 `@asynccontextmanager`를 활용하여 FastAPI 애플리케이션의 **시작(startup)**과 **종료(shutdown)** 시점에 실행되는 코드를 정의하는 메커니즘입니다.

```
┌─────────────────────────────────────────────────────────────────┐
│                    Application Lifecycle                         │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│   ┌──────────┐     ┌──────────────────┐     ┌──────────┐        │
│   │ STARTUP  │ ──▶ │ RUNNING (yield)  │ ──▶ │ SHUTDOWN │        │
│   │          │     │                  │     │          │        │
│   │ • DB 연결 │     │ • HTTP 요청 처리  │     │ • DB 종료 │        │
│   │ • 캐시   │     │ • WebSocket     │     │ • 캐시    │        │
│   │   워밍업  │     │ • Background    │     │   플러시  │        │
│   │ • 리소스 │     │   Tasks         │     │ • 리소스  │        │
│   │   초기화 │     │                  │     │   정리   │        │
│   └──────────┘     └──────────────────┘     └──────────┘        │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### 2.2 왜 필요한가?

| 문제 | Lifespan 해결책 |
|------|----------------|
| 콜드 스타트 지연 | 서버 시작 시 캐시 워밍업 |
| 리소스 누수 | 종료 시 연결 정리 |
| 초기화 순서 보장 | 의존성 순서대로 초기화 |
| Graceful Shutdown | 진행 중인 작업 완료 후 종료 |

## 3. 기본 구조

### 3.1 AsyncContextManager 패턴

FastAPI 0.95+에서 권장하는 방식입니다:

```python
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """애플리케이션 생명주기 관리."""
    
    # ═══════════════════════════════════════════
    # 🟢 STARTUP: yield 이전 (서버 시작 전)
    # ═══════════════════════════════════════════
    print("Starting up...")
    
    # 리소스 초기화
    await initialize_database()
    await warmup_cache()
    start_background_tasks()
    
    yield  # ← 여기서 "대기" → 서버가 요청 처리
    
    # ═══════════════════════════════════════════
    # 🔴 SHUTDOWN: yield 이후 (서버 종료 시)
    # ═══════════════════════════════════════════
    print("Shutting down...")
    
    # 리소스 정리
    stop_background_tasks()
    await flush_cache()
    await close_database()


# FastAPI 앱에 lifespan 등록
app = FastAPI(lifespan=lifespan)
```

### 3.2 yield의 의미

```python
yield  # "여기서 멈추고, 서버 실행, 종료 신호 오면 다시 진행"
```

**실행 흐름:**

```
1. uvicorn main:app 실행
   │
2. lifespan() 호출 시작
   │
3. yield 이전 코드 실행 (STARTUP)
   │  ├─ DB 연결
   │  ├─ 캐시 워밍업
   │  └─ Consumer 시작
   │
4. yield 도달 → 일시 정지
   │
5. ✅ 서버 Ready → HTTP 요청 수신 시작
   │  (서버 실행 중...)
   │
6. 종료 신호 (SIGTERM, Ctrl+C)
   │
7. yield 이후 코드 실행 (SHUTDOWN)
   │  ├─ Consumer 중지
   │  ├─ 캐시 플러시
   │  └─ DB 연결 종료
   │
8. 서버 완전 종료
```

## 4. 상태 공유 (State)

### 4.1 yield를 통한 상태 전달

```python
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI, Request
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[dict]:
    """상태를 공유하는 lifespan."""
    
    # 리소스 생성
    engine = create_async_engine("postgresql+asyncpg://...")
    redis = await aioredis.from_url("redis://...")
    
    # app.state에 저장 (전통적 방식)
    app.state.db_engine = engine
    app.state.redis = redis
    
    # 또는 yield로 상태 전달 (권장)
    yield {"db": engine, "redis": redis}
    
    # 정리
    await redis.close()
    await engine.dispose()


app = FastAPI(lifespan=lifespan)


@app.get("/")
async def root(request: Request):
    # app.state에서 접근
    engine = request.app.state.db_engine
    
    # 또는 request.state에서 접근 (lifespan yield 값)
    # (FastAPI 0.106+ 필요)
    return {"status": "ok"}
```

### 4.2 전역 싱글톤 패턴

```python
# database.py
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

_engine: AsyncEngine | None = None
_session_factory: sessionmaker | None = None


async def init_database(url: str) -> None:
    """DB 엔진 초기화."""
    global _engine, _session_factory
    
    _engine = create_async_engine(url, pool_pre_ping=True)
    _session_factory = sessionmaker(
        bind=_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )


async def close_database() -> None:
    """DB 엔진 종료."""
    global _engine
    
    if _engine:
        await _engine.dispose()
        _engine = None


def get_session_factory() -> sessionmaker:
    """세션 팩토리 반환."""
    if _session_factory is None:
        raise RuntimeError("Database not initialized")
    return _session_factory


# main.py
@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    await init_database(settings.database_url)
    yield
    await close_database()
```

## 5. 실전 패턴

### 5.1 캐시 워밍업 (Cold Start 해결)

```python
from apps.character.infrastructure.cache import get_character_cache
from apps.character.infrastructure.persistence_postgres import SqlaCharacterReader


async def warmup_local_cache() -> None:
    """로컬 캐시 워밍업.
    
    서버 시작 시 DB에서 데이터를 로드하여
    첫 요청부터 캐시 hit이 되도록 합니다.
    """
    try:
        cache = get_character_cache()
        
        # 이미 초기화되어 있으면 스킵
        if cache.is_initialized:
            logger.info("Cache already initialized")
            return
        
        # DB에서 로드
        async with async_session_factory() as session:
            reader = SqlaCharacterReader(session)
            characters = await reader.list_all()
            
            if characters:
                cache.set_all(list(characters))
                logger.info(f"Cache warmup: {len(characters)} items loaded")
            else:
                logger.warning("Cache warmup: no data found")
                
    except Exception as e:
        # Graceful degradation: 실패해도 서버는 시작
        logger.warning(f"Cache warmup failed: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    # 워밍업 (실패해도 서버 시작)
    await warmup_local_cache()
    
    yield
    
    # 정리는 필요 없음 (인메모리 캐시는 프로세스 종료 시 자동 해제)
```

### 5.2 백그라운드 Consumer 관리

```python
from apps.character.infrastructure.cache import (
    start_cache_consumer,
    stop_cache_consumer,
)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    logger.info("Starting Character API service")
    
    # 캐시 워밍업
    await warmup_local_cache()
    
    # MQ Consumer 시작 (데몬 스레드)
    if settings.celery_broker_url:
        start_cache_consumer(settings.celery_broker_url)
        logger.info("Cache consumer started")
    
    yield
    
    # MQ Consumer 중지 (graceful)
    stop_cache_consumer()
    logger.info("Cache consumer stopped")
```

### 5.3 OpenTelemetry 초기화

```python
from domains._shared.observability.tracing import setup_tracing, shutdown_tracing


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    # OpenTelemetry 설정
    if settings.otel_enabled:
        setup_tracing(
            service_name=settings.service_name,
            environment=settings.environment,
            endpoint=settings.otel_exporter_otlp_endpoint,
        )
        logger.info("OpenTelemetry tracing enabled")
    
    yield
    
    # 트레이싱 종료 (버퍼 플러시)
    if settings.otel_enabled:
        shutdown_tracing()
```

### 5.4 다중 리소스 관리

```python
@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """복잡한 리소스 초기화/정리."""
    
    resources = []
    
    try:
        # ═══ STARTUP ═══
        
        # 1. 로깅 설정
        setup_logging(settings.log_level)
        
        # 2. OpenTelemetry
        if settings.otel_enabled:
            setup_tracing(settings.service_name)
            resources.append(("tracing", shutdown_tracing))
        
        # 3. 데이터베이스
        await init_database(settings.database_url)
        resources.append(("database", close_database))
        
        # 4. 캐시 워밍업
        await warmup_local_cache()
        
        # 5. MQ Consumer
        if settings.celery_broker_url:
            start_cache_consumer(settings.celery_broker_url)
            resources.append(("cache_consumer", stop_cache_consumer))
        
        # 6. Health check ready
        app.state.ready = True
        
        logger.info("All resources initialized")
        
        yield
        
    finally:
        # ═══ SHUTDOWN ═══
        
        app.state.ready = False
        
        # 역순으로 정리 (LIFO)
        for name, cleanup in reversed(resources):
            try:
                if asyncio.iscoroutinefunction(cleanup):
                    await cleanup()
                else:
                    cleanup()
                logger.info(f"Resource cleaned up: {name}")
            except Exception as e:
                logger.error(f"Failed to cleanup {name}: {e}")
```

## 6. 레거시: on_event 데코레이터 (Deprecated)

FastAPI 0.95 이전에 사용하던 방식입니다. **새 프로젝트에서는 사용하지 마세요.**

```python
# ❌ 레거시 방식 (deprecated)
app = FastAPI()


@app.on_event("startup")
async def startup():
    await init_database()


@app.on_event("shutdown")
async def shutdown():
    await close_database()


# ✅ 권장 방식 (lifespan)
@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    await init_database()
    yield
    await close_database()


app = FastAPI(lifespan=lifespan)
```

**레거시 방식의 문제점:**

| 문제 | 설명 |
|------|------|
| 상태 공유 어려움 | startup/shutdown 간 상태 전달 불가 |
| 에러 처리 복잡 | try/finally 패턴 적용 어려움 |
| 순서 보장 안됨 | 여러 핸들러 실행 순서 불명확 |
| 테스트 어려움 | 모킹이 복잡함 |

## 7. 테스트

### 7.1 Lifespan 테스트

```python
import pytest
from fastapi.testclient import TestClient
from httpx import AsyncClient

from main import app, lifespan


def test_health_with_lifespan():
    """lifespan이 정상 실행되는지 테스트."""
    with TestClient(app) as client:
        # TestClient는 자동으로 lifespan 실행
        response = client.get("/health")
        assert response.status_code == 200


@pytest.mark.asyncio
async def test_async_with_lifespan():
    """비동기 테스트."""
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.get("/health")
        assert response.status_code == 200
```

### 7.2 Lifespan 모킹

```python
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, patch


@asynccontextmanager
async def mock_lifespan(app):
    """테스트용 lifespan (리소스 초기화 스킵)."""
    yield


def test_without_real_resources():
    """실제 리소스 없이 테스트."""
    app.router.lifespan_context = mock_lifespan
    
    with TestClient(app) as client:
        response = client.get("/")
        assert response.status_code == 200
```

## 8. 우리 프로젝트 적용 예시

### 8.1 Character API (`apps/character/main.py`)

```python
"""Character Service Main Entry Point."""

import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI

from apps.character.presentation.http.controllers import catalog, health, reward
from apps.character.setup.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


async def warmup_local_cache() -> None:
    """로컬 캐시 워밍업."""
    try:
        from apps.character.infrastructure.cache import get_character_cache
        from apps.character.infrastructure.persistence_postgres import SqlaCharacterReader
        from apps.character.setup.database import async_session_factory

        cache = get_character_cache()
        if cache.is_initialized:
            return

        async with async_session_factory() as session:
            reader = SqlaCharacterReader(session)
            characters = await reader.list_all()
            if characters:
                cache.set_all(list(characters))
                logger.info(f"Cache warmup: {len(characters)} characters")

    except Exception as e:
        logger.warning(f"Cache warmup failed: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """애플리케이션 라이프사이클 관리."""
    logger.info("Starting Character API service")

    # OpenTelemetry
    if settings.otel_enabled:
        from domains._shared.observability.tracing import setup_tracing
        setup_tracing(settings.service_name)

    # 캐시 워밍업
    await warmup_local_cache()

    # MQ Consumer
    if settings.celery_broker_url:
        from apps.character.infrastructure.cache import start_cache_consumer
        start_cache_consumer(settings.celery_broker_url)

    yield

    # Cleanup
    logger.info("Shutting down Character API service")
    
    from apps.character.infrastructure.cache import stop_cache_consumer
    stop_cache_consumer()


app = FastAPI(
    title="Character API",
    lifespan=lifespan,
)

app.include_router(health.router)
app.include_router(catalog.router, prefix="/api/v1")
app.include_router(reward.router, prefix="/api/v1")
```

## 9. 베스트 프랙티스

### 9.1 Do's ✅

```python
# 1. Graceful Degradation
async def warmup_cache():
    try:
        await do_warmup()
    except Exception as e:
        logger.warning(f"Warmup failed: {e}")  # 실패해도 서버 시작

# 2. 역순 정리 (LIFO)
resources = []
resources.append(resource1)
resources.append(resource2)
# ...
for resource in reversed(resources):
    await resource.close()

# 3. 타임아웃 설정
async def cleanup_with_timeout():
    try:
        await asyncio.wait_for(cleanup(), timeout=5.0)
    except asyncio.TimeoutError:
        logger.error("Cleanup timed out")

# 4. Health Check 연동
app.state.ready = False
await init_resources()
app.state.ready = True
yield
app.state.ready = False
await cleanup_resources()
```

### 9.2 Don't ❌

```python
# 1. 블로킹 호출 금지
@asynccontextmanager
async def lifespan(app):
    time.sleep(10)  # ❌ 블로킹!
    await asyncio.sleep(10)  # ✅ 비동기
    yield

# 2. 무한 대기 금지
@asynccontextmanager
async def lifespan(app):
    await some_resource.connect()  # 타임아웃 없음 ❌
    await asyncio.wait_for(some_resource.connect(), timeout=30)  # ✅
    yield

# 3. 예외 무시 금지
@asynccontextmanager
async def lifespan(app):
    yield
    try:
        await cleanup()
    except:
        pass  # ❌ 예외 무시
    except Exception as e:
        logger.error(f"Cleanup failed: {e}")  # ✅ 로깅
```

## 10. 정리

### 10.1 Context Manager 개념

| 개념 | 동기 | 비동기 |
|------|------|--------|
| 프로토콜 | `__enter__` / `__exit__` | `__aenter__` / `__aexit__` |
| 사용 문법 | `with` | `async with` |
| 데코레이터 | `@contextmanager` | `@asynccontextmanager` |
| Generator | `yield` | `async yield` |

### 10.2 FastAPI Lifespan

| 개념 | 설명 |
|------|------|
| `@asynccontextmanager` | 비동기 컨텍스트 매니저 데코레이터 |
| `yield` 이전 | STARTUP 코드 (서버 시작 전) |
| `yield` | 서버 실행 대기 지점, `as`에 값 전달 |
| `yield` 이후 | SHUTDOWN 코드 (서버 종료 시) |
| `finally` 블록 | 예외 발생해도 정리 코드 실행 보장 |
| `app.state` | 애플리케이션 전역 상태 저장소 |

### 10.3 베스트 프랙티스

| 패턴 | 설명 |
|------|------|
| Graceful Degradation | 초기화 실패해도 서버 시작 |
| Graceful Shutdown | 리소스 정리 후 종료 |
| LIFO 정리 | 초기화 역순으로 리소스 해제 |
| 타임아웃 설정 | 무한 대기 방지 |
| Health Check 연동 | ready 상태 관리 |

## 참고 자료

### 공식 문서
- [FastAPI Lifespan Events](https://fastapi.tiangolo.com/advanced/events/)
- [Starlette Lifespan](https://www.starlette.io/lifespan/)
- [Python contextlib](https://docs.python.org/3/library/contextlib.html)
- [Python typing — AsyncContextManager](https://docs.python.org/3/library/typing.html#typing.AsyncContextManager)

### PEP 문서 (Python Enhancement Proposals)
- [PEP 343 - The "with" Statement](https://peps.python.org/pep-0343/) - Context Manager 표준화
- [PEP 492 - Coroutines with async and await syntax](https://peps.python.org/pep-0492/) - async/await 문법
- [PEP 525 - Asynchronous Generators](https://peps.python.org/pep-0525/) - async generator (async yield)
- [PEP 380 - Syntax for Delegating to a Subgenerator](https://peps.python.org/pep-0380/) - yield from

### Generator 이해
- [Python Generators Tutorial](https://realpython.com/introduction-to-python-generators/)
- [How to Use Generators and yield in Python](https://realpython.com/python-generators/)

