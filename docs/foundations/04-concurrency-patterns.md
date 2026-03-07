# Concurrency Patterns

> [← 03. AMQP Protocol](./03-amqp-protocol.md) | [인덱스](./00-index.md)

> **Celery**: [Concurrency](https://docs.celeryq.dev/en/stable/userguide/concurrency/index.html)
> **Uvicorn**: [Settings](https://www.uvicorn.org/settings/)
> **FastAPI**: [Concurrency and async/await](https://fastapi.tiangolo.com/async/)

---

## 개요

이코에코 스택에서의 동시성 패턴을 정리한다.

```
이코에코 Concurrency 스택:
• Uvicorn (ASGI 서버) - 비동기 HTTP 처리
• FastAPI (웹 프레임워크) - async endpoints
• Celery (태스크 큐) - CPU-bound 작업 분리
```

---

## Uvicorn Concurrency

> 출처: [Uvicorn Settings](https://www.uvicorn.org/settings/)

### Workers vs Event Loop

```
┌─────────────────────────────────────────────────────────────┐
│                Uvicorn 동시성 모델                           │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  단일 Worker (개발 환경)                                    │
│  ─────────────────────────                                  │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  Uvicorn Process                                    │   │
│  │  └── asyncio Event Loop                             │   │
│  │       └── FastAPI Application                       │   │
│  │            ├── Request 1 (async)                    │   │
│  │            ├── Request 2 (async)                    │   │
│  │            └── Request 3 (async)                    │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
│  $ uvicorn main:app                                         │
│                                                             │
│  ───────────────────────────────────────────────────────    │
│                                                             │
│  다중 Worker (프로덕션)                                     │
│  ──────────────────────                                     │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  Master Process                                     │   │
│  │  ├── Worker 1 (Process)                             │   │
│  │  │    └── asyncio Event Loop                        │   │
│  │  │         └── FastAPI                              │   │
│  │  ├── Worker 2 (Process)                             │   │
│  │  │    └── asyncio Event Loop                        │   │
│  │  │         └── FastAPI                              │   │
│  │  └── Worker 3 (Process)                             │   │
│  │       └── asyncio Event Loop                        │   │
│  │            └── FastAPI                              │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
│  $ uvicorn main:app --workers 3                             │
│                                                             │
│  각 Worker가 독립적인 Event Loop 보유                       │
│  멀티코어 활용 + 비동기 I/O 조합                            │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### 이코에코 Uvicorn 설정

```python
# 현재 이코에코 설정 (Kubernetes Deployment)

# workloads/domains/scan/base/deployment.yaml
# command:
#   - uvicorn
#   - main:app
#   - --host=0.0.0.0
#   - --port=8000

# 단일 Worker + asyncio Event Loop
# Kubernetes에서는 Pod 수로 수평 확장
```

### Worker 수 결정 공식

```
┌─────────────────────────────────────────────────────────────┐
│                Worker 수 결정                                │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  공식: workers = (2 × CPU_CORES) + 1                        │
│                                                             │
│  예시 (4코어):                                              │
│  • workers = (2 × 4) + 1 = 9                                │
│  • 9개의 독립적인 Event Loop                                │
│                                                             │
│  그러나 Kubernetes에서는:                                   │
│  ─────────────────────────                                  │
│  • 각 Pod에 1 Worker                                        │
│  • Pod 수로 수평 확장 (HPA)                                 │
│  • 장점: 격리, 장애 복구, 독립 배포                        │
│                                                             │
│  이코에코 전략:                                             │
│  • Uvicorn: 1 Worker per Pod                                │
│  • Kubernetes: replicas로 확장                              │
│  • HPA: CPU/Memory 기반 자동 확장                           │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## FastAPI Concurrency

> 출처: [FastAPI Concurrency and async/await](https://fastapi.tiangolo.com/async/)

### async def vs def

```
┌─────────────────────────────────────────────────────────────┐
│               async def vs def 차이                          │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  async def (비동기 엔드포인트)                              │
│  ──────────────────────────                                 │
│                                                             │
│  @app.get("/async")                                         │
│  async def read_async():                                    │
│      data = await async_db_query()  # I/O 대기 중 다른 요청 │
│      return data                                            │
│                                                             │
│  실행 위치: Main Event Loop (직접)                          │
│  적합한 경우: I/O-bound (DB, HTTP, Redis)                   │
│                                                             │
│  ───────────────────────────────────────────────────────    │
│                                                             │
│  def (동기 엔드포인트)                                      │
│  ────────────────────                                       │
│                                                             │
│  @app.get("/sync")                                          │
│  def read_sync():                                           │
│      data = sync_db_query()  # 블로킹 호출                  │
│      return data                                            │
│                                                             │
│  실행 위치: Thread Pool (별도 스레드)                       │
│  적합한 경우: CPU-bound, 레거시 동기 라이브러리             │
│                                                             │
│  ⚠️ 주의:                                                   │
│  • def 내에서 async 함수 호출 불가                          │
│  • async def 내에서 동기 블로킹 호출은 Event Loop 블로킹!   │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### 흔한 실수

```python
# ❌ 잘못된 예: async def 내에서 동기 블로킹
@app.get("/bad")
async def bad_endpoint():
    time.sleep(5)  # Event Loop 5초간 블로킹!
    data = requests.get(url)  # 또 블로킹!
    return data

# ✅ 올바른 예: 비동기 라이브러리 사용
@app.get("/good")
async def good_endpoint():
    await asyncio.sleep(5)  # 비동기 대기
    async with httpx.AsyncClient() as client:
        data = await client.get(url)  # 비동기 HTTP
    return data.json()

# ✅ 대안: 동기 코드를 run_in_executor로 실행
@app.get("/executor")
async def executor_endpoint():
    loop = asyncio.get_event_loop()
    data = await loop.run_in_executor(None, sync_blocking_call)
    return data
```

### 이코에코 엔드포인트 패턴

```python
# domains/scan/api/v1/endpoints/classification.py

@router.post("/classify")
async def classify_waste(
    payload: ClassificationRequest,
    user: CurrentUser,
    service: ScanServiceDep,  # 비동기 서비스
) -> ClassificationResponse:
    # 모든 I/O가 비동기
    result = await service.classify(payload)
    return result

# ✅ asyncpg (비동기 DB)
# ✅ aioredis (비동기 Redis)
# ✅ httpx (비동기 HTTP)
```

---

## Celery Concurrency

> 출처: [Celery Concurrency](https://docs.celeryq.dev/en/stable/userguide/concurrency/index.html)

### Worker Pool 종류

```
┌─────────────────────────────────────────────────────────────┐
│                 Celery Worker Pool                           │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  1. prefork (기본값, 이코에코 사용)                         │
│  ──────────────────────────────────                         │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  Celery Worker                                      │   │
│  │  ├── Child Process 1 (독립 GIL)                     │   │
│  │  │    └── Task 실행                                 │   │
│  │  ├── Child Process 2 (독립 GIL)                     │   │
│  │  │    └── Task 실행                                 │   │
│  │  └── Child Process 3 (독립 GIL)                     │   │
│  │       └── Task 실행                                 │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
│  장점:                                                      │
│  • GIL 완전 우회 (각 프로세스 독립)                        │
│  • CPU-bound 작업에 최적                                   │
│  • 안정성 (프로세스 격리)                                  │
│                                                             │
│  단점:                                                      │
│  • 메모리 오버헤드 (프로세스당 메모리)                     │
│  • IPC 오버헤드                                            │
│                                                             │
│  $ celery -A app worker --pool=prefork --concurrency=4     │
│                                                             │
│  ───────────────────────────────────────────────────────    │
│                                                             │
│  2. eventlet / gevent (협력적 멀티태스킹)                  │
│  ────────────────────────────────────────                   │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  Celery Worker (단일 프로세스)                      │   │
│  │  └── Green Threads                                  │   │
│  │       ├── Greenlet 1 (Task)                         │   │
│  │       ├── Greenlet 2 (Task)                         │   │
│  │       └── Greenlet 3 (Task)                         │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
│  장점:                                                      │
│  • 수천 개 동시 작업 가능                                  │
│  • 메모리 효율적                                           │
│  • I/O-bound에 적합                                        │
│                                                             │
│  단점:                                                      │
│  • 라이브러리 호환성 문제 (monkey patching)                │
│  • CPU-bound에 부적합 (GIL 공유)                           │
│                                                             │
│  $ celery -A app worker --pool=eventlet --concurrency=1000 │
│                                                             │
│  ───────────────────────────────────────────────────────    │
│                                                             │
│  3. solo (디버깅용)                                        │
│  ─────────────────                                          │
│                                                             │
│  단일 프로세스, 단일 스레드                                │
│  디버깅 및 테스트용                                        │
│                                                             │
│  $ celery -A app worker --pool=solo                        │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### 이코에코 Celery 설정

```python
# domains/_shared/celery/config.py

class CelerySettings(BaseSettings):
    # Worker settings
    worker_prefetch_multiplier: int = Field(
        1,  # Fair dispatch (긴 AI 작업에 적합)
        description="Number of tasks to prefetch per worker",
    )
    worker_concurrency: int = Field(
        2,  # 프로세스 수 (prefork)
        description="Number of concurrent worker processes",
    )
```

### Pool 선택 가이드

```
┌─────────────────────────────────────────────────────────────┐
│                 Pool 선택 가이드                             │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  이코에코 워크로드 분석 (⚠️ 실측 기반 수정):                │
│  ──────────────────────────────────────────                 │
│                                                             │
│  scan.vision  → OpenAI Vision API → I/O-bound (30%)        │
│  scan.rule    → RAG 규칙 매칭     → I/O-bound (21%)        │
│  scan.answer  → OpenAI Chat API   → I/O-bound (35%)        │
│  scan.reward  → DB + gRPC 호출    → I/O-bound (14%)        │
│                                                             │
│  ⚠️ 총 65%가 OpenAI API 호출 (I/O 대기)                    │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### ⚠️ prefork 한계점 (실측 데이터)

> 📊 **측정일**: 2025-12-24
> 🔗 [Grafana Snapshot](https://snapshots.raintank.io/dashboard/snapshot/zz5pBgaMfZXuPDf7TwSLYgcMw103UZUE)

```
┌─────────────────────────────────────────────────────────────┐
│              prefork + I/O-bound = 비효율                    │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  측정 환경:                                                 │
│  • scan-worker replicas: 3                                  │
│  • concurrency: 8 (설정값)                                  │
│  • 실제 workers: 6-9 (메모리 제한)                         │
│  • LLM Provider: OpenAI GPT                                 │
│                                                             │
│  실측 결과:                                                 │
│  ┌────────────────────────────────────────────────────┐    │
│  │  Chain 평균: 41.65초                               │    │
│  │  실측 RPS: 0.0323 req/s                            │    │
│  │  실측 RPM: 1.94 RPM                                │    │
│  │  이론 최대: 9 / 41.65초 = 0.22 RPS                 │    │
│  │  효율: 실측/이론 = 15%                             │    │
│  └────────────────────────────────────────────────────┘    │
│                                                             │
│  문제점:                                                    │
│  • 1 request → 1 worker → 41.65초 블로킹                   │
│  • I/O 대기 중에도 worker가 점유됨                         │
│  • GIL 우회 효과 없음 (이미 I/O 대기 중 해제됨)            │
│                                                             │
│  해결책:                                                    │
│  • prefork → asyncio Pool 전환                             │
│  • 동시 I/O: 6-9 → 100+                                    │
│  • 메모리: 3.6GB → ~100MB                                  │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### Pool 전환 계획

| 항목 | 현재 (prefork) | 개선 (asyncio) |
|------|---------------|----------------|
| 동시 I/O | 6-9 | **100+** |
| 메모리 | 3.6GB+ | **~100MB** |
| 블로킹 | 100% (41초/req) | **논블로킹** |
| 예상 RPS | 0.22 | **OpenAI 한계까지 (~4 RPS)** |

```yaml
# 변경 전
args: [-P, prefork, -c, '8']

# 변경 후 (celery-pool-asyncio)
args: [-P, asyncio, -c, '100']
```

---

## Celery + asyncio 통합

### 현재 이코에코 패턴

```python
# domains/_shared/celery/async_support.py

from __future__ import annotations
import asyncio
from typing import Coroutine, TypeVar

T = TypeVar("T")

# Worker별 공유 event loop
_event_loop: asyncio.AbstractEventLoop | None = None


def init_event_loop() -> None:
    """Worker 시작 시 event loop 초기화."""
    global _event_loop
    if _event_loop is not None:
        return
    
    _event_loop = asyncio.new_event_loop()
    asyncio.set_event_loop(_event_loop)


def run_async(coro: Coroutine[None, None, T]) -> T:
    """공유 event loop에서 코루틴 실행.
    
    Celery task 내에서 비동기 함수를 호출할 때 사용.
    """
    global _event_loop
    
    if _event_loop is None:
        # Fallback
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(coro)
        finally:
            loop.close()
    
    return _event_loop.run_until_complete(coro)
```

### 사용 예

```python
# domains/scan/tasks/vision.py

from domains._shared.celery.async_support import run_async

@celery_app.task
def vision_task(image_url: str) -> dict:
    # 동기 Celery Task 내에서 비동기 함수 호출
    result = run_async(analyze_images_async(image_url))
    return result
```

---

## 전체 아키텍처

```
┌─────────────────────────────────────────────────────────────┐
│              이코에코 Concurrency 아키텍처                   │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  Client                                                     │
│    │                                                        │
│    ▼                                                        │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  Kubernetes Ingress (nginx)                         │   │
│  │  └── Load Balancing                                 │   │
│  └─────────────────────────────────────────────────────┘   │
│    │                                                        │
│    ▼                                                        │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  Uvicorn Pod (replicas: 3)                          │   │
│  │  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐   │   │
│  │  │ Pod 1       │ │ Pod 2       │ │ Pod 3       │   │   │
│  │  │ Event Loop  │ │ Event Loop  │ │ Event Loop  │   │   │
│  │  │ FastAPI     │ │ FastAPI     │ │ FastAPI     │   │   │
│  │  └─────────────┘ └─────────────┘ └─────────────┘   │   │
│  └─────────────────────────────────────────────────────┘   │
│    │                     │                     │            │
│    │ async (asyncpg)     │ async (aioredis)   │ publish    │
│    ▼                     ▼                     ▼            │
│  ┌──────────┐     ┌──────────┐     ┌──────────────────┐   │
│  │PostgreSQL│     │  Redis   │     │    RabbitMQ      │   │
│  └──────────┘     └──────────┘     └────────┬─────────┘   │
│                                              │              │
│                                              ▼              │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  Celery Worker Pod (replicas: 2)                    │   │
│  │  ┌─────────────────────┐ ┌─────────────────────┐   │   │
│  │  │ Pod 1 (prefork)     │ │ Pod 2 (prefork)     │   │   │
│  │  │ ├── Process 1       │ │ ├── Process 1       │   │   │
│  │  │ └── Process 2       │ │ └── Process 2       │   │   │
│  │  └─────────────────────┘ └─────────────────────┘   │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
│  동시성 모델:                                               │
│  • Uvicorn: asyncio Event Loop (I/O-bound)                 │
│  • Celery: prefork 멀티프로세스 (CPU-bound)                │
│  • Kubernetes: Pod 수평 확장 (HPA)                         │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## 성능 최적화 체크리스트

### FastAPI

```
┌─────────────────────────────────────────────────────────────┐
│              FastAPI 최적화 체크리스트                       │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ✅ async def 사용                                          │
│     모든 I/O 엔드포인트에 async def                         │
│                                                             │
│  ✅ 비동기 라이브러리 사용                                  │
│     • asyncpg (PostgreSQL)                                  │
│     • aioredis (Redis)                                      │
│     • httpx (HTTP)                                          │
│     • aio-pika (RabbitMQ)                                   │
│                                                             │
│  ✅ 동기 코드 격리                                          │
│     • run_in_executor 사용                                  │
│     • 또는 Celery로 분리                                    │
│                                                             │
│  ✅ Connection Pool                                         │
│     • asyncpg pool_size 설정                                │
│     • Redis connection pool                                 │
│                                                             │
│  ⚠️ 주의                                                    │
│     • time.sleep() 사용 금지 → asyncio.sleep()             │
│     • requests 사용 금지 → httpx.AsyncClient()             │
│     • psycopg2 사용 금지 → asyncpg                         │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### Celery

```
┌─────────────────────────────────────────────────────────────┐
│              Celery 최적화 체크리스트                        │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ✅ prefetch_multiplier=1                                   │
│     긴 작업에 Fair Dispatch                                 │
│                                                             │
│  ✅ acks_late=True                                          │
│     처리 완료 후 ACK                                        │
│                                                             │
│  ✅ task_reject_on_worker_lost=True                         │
│     Worker 종료 시 재큐잉                                   │
│                                                             │
│  ✅ 적절한 concurrency 설정                                 │
│     CPU 코어 수 고려                                        │
│                                                             │
│  ✅ Task 시간 제한                                          │
│     task_time_limit, task_soft_time_limit                  │
│                                                             │
│  ✅ DLQ 설정                                                │
│     x-dead-letter-exchange                                  │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## 요약

| 컴포넌트 | 동시성 모델 | 적합한 워크로드 |
|----------|-------------|-----------------|
| **Uvicorn** | asyncio Event Loop | I/O-bound HTTP 처리 |
| **FastAPI** | async def + await | 비동기 엔드포인트 |
| **Celery prefork** | 멀티프로세스 | CPU-bound 작업 |
| **Celery eventlet** | Green Threads | 대량 I/O 작업 |

### 이코에코 선택

- **FastAPI**: async def + asyncpg/aioredis/httpx
- **Celery**: prefork pool (CPU-bound AI 작업)
- **확장**: Kubernetes Pod 수평 확장

---

## 참고 자료

### 공식 문서
- [Uvicorn Settings](https://www.uvicorn.org/settings/)
- [FastAPI Concurrency](https://fastapi.tiangolo.com/async/)
- [Celery Concurrency](https://docs.celeryq.dev/en/stable/userguide/concurrency/index.html)
- [Celery Workers Guide](https://docs.celeryq.dev/en/stable/userguide/workers.html)

### 관련 Foundation
- [01-python-asyncio.md](./01-python-asyncio.md) - asyncio 기초
- [02-python-gil.md](./02-python-gil.md) - GIL과 멀티프로세스
- [03-amqp-protocol.md](./03-amqp-protocol.md) - RabbitMQ/Celery 연동
- [12-celery-distributed-task-queue.md](../blogs/async/foundations/12-celery-distributed-task-queue.md) - Celery 실전

