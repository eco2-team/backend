# Python asyncio 기초

> [← 인덱스](./00-index.md) | [02. Python GIL →](./02-python-gil.md)

> **공식 문서**: [asyncio — Asynchronous I/O](https://docs.python.org/3.11/library/asyncio.html)
> **핵심 PEP**: PEP 3156, PEP 492, PEP 525, PEP 530

---

## 개요

`asyncio`는 Python의 비동기 I/O 프레임워크로, **단일 스레드**에서 **동시성**을 구현한다.

```python
# 이코에코 현재 버전
Python 3.11
asyncio (표준 라이브러리)
```

### 핵심 특징

| 특징 | 설명 |
|------|------|
| **단일 스레드** | 하나의 스레드에서 여러 작업을 동시에 처리 |
| **협력적 멀티태스킹** | 작업이 자발적으로 제어권을 양보 (await) |
| **I/O 최적화** | I/O 대기 시간에 다른 작업 실행 |
| **GIL 우회** | GIL의 영향을 받지 않는 동시성 모델 |

---

## PEP 3156: asyncio 설계 원문

> 원문: [PEP 3156 - Asynchronous I/O Support Rebooted](https://peps.python.org/pep-3156/)
> 저자: Guido van Rossum
> 상태: Final (Python 3.4+)

### 설계 목표

PEP 3156에서 Guido가 제시한 asyncio의 핵심 목표:

```
┌─────────────────────────────────────────────────────────────┐
│                  PEP 3156 설계 목표                          │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  1. 표준화된 이벤트 루프 인터페이스                          │
│     → Twisted, Tornado 등 기존 프레임워크와의 상호운용성     │
│                                                             │
│  2. 콜백 기반 + 코루틴 기반 API 제공                        │
│     → 점진적 마이그레이션 지원                               │
│                                                             │
│  3. 트랜스포트/프로토콜 분리                                 │
│     → 네트워크 코드의 재사용성                               │
│                                                             │
│  4. 확장 가능한 이벤트 루프                                  │
│     → 플랫폼별 최적화 구현 가능                              │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### Event Loop 구조

```
┌─────────────────────────────────────────────────────────────┐
│                    Event Loop 동작                           │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│                    ┌─────────────┐                          │
│                    │ Event Loop  │                          │
│                    │  (단일 스레드)│                          │
│                    └──────┬──────┘                          │
│                           │                                 │
│           ┌───────────────┼───────────────┐                 │
│           │               │               │                 │
│           ▼               ▼               ▼                 │
│    ┌──────────┐    ┌──────────┐    ┌──────────┐            │
│    │  Task 1  │    │  Task 2  │    │  Task 3  │            │
│    │ (running)│    │(waiting) │    │(waiting) │            │
│    └──────────┘    └──────────┘    └──────────┘            │
│           │               │               │                 │
│           │         I/O 완료         I/O 완료               │
│           │               │               │                 │
│           ▼               ▼               ▼                 │
│    ┌──────────────────────────────────────────┐            │
│    │              Ready Queue                  │            │
│    │  실행 가능한 Task들이 대기                 │            │
│    └──────────────────────────────────────────┘            │
│                                                             │
│  Event Loop 동작:                                           │
│  1. Ready Queue에서 Task 선택                               │
│  2. await까지 실행                                          │
│  3. await 만나면 제어권 반환                                │
│  4. I/O 완료된 Task를 Ready Queue에 추가                    │
│  5. 반복                                                    │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### 코드 예제 (PEP 3156 스타일)

```python
import asyncio

# PEP 3156 이후: async/await 없이 yield from 사용
@asyncio.coroutine
def fetch_data():
    yield from asyncio.sleep(1)
    return "data"

# Python 3.4 스타일 (역사적 참고용)
loop = asyncio.get_event_loop()
result = loop.run_until_complete(fetch_data())
loop.close()
```

---

## PEP 492: async/await 문법

> 원문: [PEP 492 - Coroutines with async and await syntax](https://peps.python.org/pep-0492/)
> 저자: Yury Selivanov
> 상태: Final (Python 3.5+)

### 문법 도입 배경

PEP 3156의 `@asyncio.coroutine` + `yield from`은 직관적이지 않았다:

```python
# Before PEP 492 (Python 3.4)
@asyncio.coroutine
def fetch():
    response = yield from http_client.get(url)
    return response

# After PEP 492 (Python 3.5+)
async def fetch():
    response = await http_client.get(url)
    return response
```

### async/await의 의미

```
┌─────────────────────────────────────────────────────────────┐
│                  async/await 키워드                          │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  async def:                                                 │
│  ──────────                                                 │
│  • 코루틴 함수를 정의                                        │
│  • 호출 시 코루틴 객체 반환 (즉시 실행 X)                    │
│  • 반드시 await, asyncio.run() 등으로 실행                  │
│                                                             │
│  await:                                                     │
│  ──────                                                     │
│  • 코루틴/Future/Task의 완료를 기다림                       │
│  • 대기 중 제어권을 Event Loop에 반환                       │
│  • async def 내부에서만 사용 가능                           │
│                                                             │
│  예시:                                                      │
│  ┌────────────────────────────────────────────────────┐    │
│  │ async def main():                                  │    │
│  │     print("시작")                                  │    │
│  │     await asyncio.sleep(1)  # 1초 대기, 제어권 반환│    │
│  │     print("끝")              # 1초 후 재개         │    │
│  └────────────────────────────────────────────────────┘    │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### Awaitable 프로토콜

PEP 492는 `__await__` 메서드를 정의하여 커스텀 awaitable 객체를 만들 수 있게 했다:

```python
class CustomAwaitable:
    def __await__(self):
        yield  # 제어권 반환
        return "result"

async def use_custom():
    result = await CustomAwaitable()
    print(result)  # "result"
```

---

## PEP 525: Asynchronous Generators

> 원문: [PEP 525 - Asynchronous Generators](https://peps.python.org/pep-0525/)
> 저자: Yury Selivanov
> 상태: Final (Python 3.6+)

### 비동기 제너레이터란?

`async def` 함수에서 `yield`를 사용하면 비동기 제너레이터가 된다:

```python
# 일반 제너레이터
def sync_gen():
    for i in range(3):
        yield i

# 비동기 제너레이터 (PEP 525)
async def async_gen():
    for i in range(3):
        await asyncio.sleep(0.1)
        yield i

# 사용
async def main():
    async for item in async_gen():
        print(item)
```

### 이코에코 적용: SSE 스트리밍

```python
# domains/scan/api/v1/endpoints/completion.py
async def _completion_generator(
    payload: ClassificationRequest,
    user: CurrentUser,
    service: ScanServiceDep,
) -> AsyncGenerator[str, None]:
    """SSE 스트림 생성기."""
    
    # 비동기 제너레이터로 SSE 이벤트 스트리밍
    while not task_completed:
        event = await event_queue.get()
        yield f"data: {json.dumps(event)}\n\n"
```

---

## PEP 530: Asynchronous Comprehensions

> 원문: [PEP 530 - Asynchronous Comprehensions](https://peps.python.org/pep-0530/)
> 저자: Yury Selivanov
> 상태: Final (Python 3.6+)

### 비동기 컴프리헨션

```python
# 동기 리스트 컴프리헨션
results = [process(x) for x in items]

# 비동기 리스트 컴프리헨션 (PEP 530)
results = [await process(x) async for x in async_items]

# 비동기 조건부 컴프리헨션
results = [x async for x in async_gen() if await is_valid(x)]
```

### await in Comprehensions

```python
# async for + await 조합
async def fetch_all(urls):
    return [await fetch(url) for url in urls]  # 순차 실행

# 병렬 실행 (권장)
async def fetch_all_parallel(urls):
    return await asyncio.gather(*[fetch(url) for url in urls])
```

---

## Coroutine, Task, Future 관계

```
┌─────────────────────────────────────────────────────────────┐
│              Coroutine / Task / Future 관계                  │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  Coroutine (코루틴)                                         │
│  ─────────────────                                          │
│  • async def로 정의된 함수의 호출 결과                      │
│  • 아직 실행되지 않은 상태                                   │
│  • await 또는 Task로 래핑해야 실행                          │
│                                                             │
│  async def my_coro():                                       │
│      return "result"                                        │
│                                                             │
│  coro = my_coro()  # 코루틴 객체 (실행 X)                   │
│  result = await coro  # 실행 및 결과 반환                   │
│                                                             │
│  ───────────────────────────────────────────────────────    │
│                                                             │
│  Task (태스크)                                              │
│  ─────────────                                              │
│  • 코루틴을 Event Loop에 등록한 것                          │
│  • 생성 즉시 스케줄링됨 (백그라운드 실행)                    │
│  • asyncio.create_task()로 생성                             │
│                                                             │
│  task = asyncio.create_task(my_coro())  # 즉시 스케줄링     │
│  # 다른 작업 가능...                                        │
│  result = await task  # 결과 대기                           │
│                                                             │
│  ───────────────────────────────────────────────────────    │
│                                                             │
│  Future (퓨처)                                              │
│  ─────────────                                              │
│  • 미래에 완료될 결과를 나타내는 저수준 객체                │
│  • Task의 부모 클래스                                       │
│  • 직접 사용은 드묾 (주로 라이브러리 내부용)                │
│                                                             │
│  future = asyncio.Future()                                  │
│  future.set_result("result")  # 결과 설정                   │
│  result = await future                                      │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### 실행 방식 비교

```python
import asyncio

async def work(n):
    await asyncio.sleep(1)
    return n * 2

# 1. 순차 실행 (총 3초)
async def sequential():
    r1 = await work(1)
    r2 = await work(2)
    r3 = await work(3)
    return [r1, r2, r3]

# 2. 병렬 실행 with create_task (총 1초)
async def parallel_tasks():
    t1 = asyncio.create_task(work(1))
    t2 = asyncio.create_task(work(2))
    t3 = asyncio.create_task(work(3))
    return [await t1, await t2, await t3]

# 3. 병렬 실행 with gather (총 1초, 권장)
async def parallel_gather():
    return await asyncio.gather(work(1), work(2), work(3))
```

---

## 이코에코 적용 포인트

### 1. FastAPI Endpoints

```python
# domains/scan/api/v1/endpoints/classification.py

# ✅ 비동기 엔드포인트 (I/O-bound)
@router.post("/classify")
async def classify_waste(
    payload: ClassificationRequest,
    user: CurrentUser,
    service: ScanServiceDep,
) -> ClassificationResponse:
    # asyncpg로 비동기 DB 조회
    result = await service.classify(payload)
    return result
```

### 2. 비동기 데이터베이스 (asyncpg)

```python
# domains/scan/database/connection.py

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession

# asyncpg 드라이버 사용
engine = create_async_engine(
    "postgresql+asyncpg://user:pass@host/db",
    pool_size=20,
    max_overflow=10,
)

async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSession(engine) as session:
        yield session
```

### 3. 비동기 Redis (aioredis)

```python
# domains/_shared/cache/redis_cache.py

import aioredis

redis = aioredis.from_url("redis://localhost:6379")

async def get_cached(key: str) -> Optional[str]:
    return await redis.get(key)

async def set_cached(key: str, value: str, ttl: int = 3600):
    await redis.setex(key, ttl, value)
```

### 4. 비동기 HTTP (httpx)

```python
# domains/_shared/llm/gemini_provider.py

import httpx

async def call_gemini_api(prompt: str) -> dict:
    async with httpx.AsyncClient() as client:
        response = await client.post(
            "https://api.gemini.com/v1/generate",
            json={"prompt": prompt},
            timeout=30.0,
        )
        return response.json()
```

---

## 주의사항

### 1. 블로킹 코드 회피

```python
# ❌ 잘못된 예: 동기 코드가 Event Loop 블로킹
async def bad_example():
    time.sleep(5)  # 전체 Event Loop가 5초간 멈춤!
    return "done"

# ✅ 올바른 예: 비동기 sleep 사용
async def good_example():
    await asyncio.sleep(5)  # 다른 Task 실행 가능
    return "done"

# ✅ 블로킹 코드를 별도 스레드에서 실행
async def with_executor():
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(None, blocking_function)
    return result
```

### 2. Task 누수 방지

```python
# ❌ Task 누수: create_task 후 await 안 함
async def task_leak():
    asyncio.create_task(some_work())  # Task가 완료 전 함수 종료
    return "done"

# ✅ Task 완료 보장
async def no_leak():
    task = asyncio.create_task(some_work())
    try:
        return "done"
    finally:
        await task  # Task 완료 대기
```

### 3. 예외 처리

```python
async def handle_exceptions():
    results = await asyncio.gather(
        work(1),
        work(2),
        work(3),
        return_exceptions=True,  # 예외도 결과로 반환
    )
    
    for result in results:
        if isinstance(result, Exception):
            logger.error(f"Task failed: {result}")
        else:
            process(result)
```

---

## 참고 자료

### 공식 문서
- [asyncio — Asynchronous I/O](https://docs.python.org/3.11/library/asyncio.html)
- [Coroutines and Tasks](https://docs.python.org/3.11/library/asyncio-task.html)
- [Event Loop](https://docs.python.org/3.11/library/asyncio-eventloop.html)

### PEP 문서
- [PEP 3156 - Asynchronous I/O Support Rebooted](https://peps.python.org/pep-3156/)
- [PEP 492 - Coroutines with async and await syntax](https://peps.python.org/pep-0492/)
- [PEP 525 - Asynchronous Generators](https://peps.python.org/pep-0525/)
- [PEP 530 - Asynchronous Comprehensions](https://peps.python.org/pep-0530/)

### 관련 Foundation
- [02-python-gil.md](./02-python-gil.md) - GIL과 asyncio의 관계
- [04-concurrency-patterns.md](./04-concurrency-patterns.md) - FastAPI에서의 활용

