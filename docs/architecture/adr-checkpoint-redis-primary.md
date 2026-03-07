# ADR: Checkpointer를 Redis Primary + PostgreSQL Async Sync로 전환

> **Status**: Accepted
>
> **Date**: 2026-01-24
>
> **Deciders**: mango
>
> **Scope**: `apps/chat_worker` checkpointing 아키텍처

---

## 1. 문제 발생

### 증상

프로덕션에서 `psycopg_pool.PoolTimeout` 에러가 간헐적으로 발생.
동시 요청량이 높은 시간대(peak)에 집중됨.

```
psycopg_pool.PoolTimeout: couldn't get a connection after 30.0 sec
```

### 영향

- LangGraph `ainvoke()` 실패 → 사용자 응답 불가
- Retry 시에도 pool 포화 상태 지속 → 연쇄 실패
- Worker pod restart까지 복구 불가

---

## 2. 원인 분석

### 2.1 직접 원인: Pool 포화

```
chat_worker (Taskiq)
  └─ --workers 4 --max-async-tasks 10
       └─ 각 task마다 LangGraph ainvoke()
            └─ 노드 5~7개 실행
                 └─ 각 노드 후 AsyncPostgresSaver.aput() → pool.getconn()
```

- 1개 task = 5~7회 pool connection acquire
- max_async_tasks=10 → 동시 50~70회 connection 요청
- **pool_max_size ≤ max_async_tasks** → 포화 불가피

### 2.2 설계 결함 5가지

| # | 결함 | 설명 |
|---|------|------|
| 1 | **Cache-Aside가 no-op** | `CachedPostgresSaver`가 Redis에 `{"cached": True}` 메타데이터만 저장. 실제 checkpoint blob은 항상 PostgreSQL에서 읽기/쓰기 |
| 2 | **Legacy state 필드** | `ChatState`에 미사용 필드 8개 → checkpoint blob 비대화 → 직렬화/역직렬화 시간 증가 |
| 3 | **setup() 미호출** | `AsyncPostgresSaver.setup()` 대신 수동 SQL로 테이블 생성 → v2 내부 초기화 누락 |
| 4 | **Graph 매 요청 compile** | `create_chat_graph()`가 매 요청마다 호출 → 불필요한 컴파일 오버헤드 |
| 5 | **Pool 설정 부적절** | `min_size=10, max_size=100, max_lifetime` 고정 → thundering herd + 과다 연결 |

### 2.3 근본 원인: 아키텍처

**Worker가 PostgreSQL에 직접 접근하는 구조 자체가 문제.**

```
Worker Process (×4/pod, ×4 pods = 16 processes)
  └─ 각 process가 독립 connection pool 보유
       └─ max_size=12 → 총 192 connections
            └─ + persistence_consumer + chat-api + admin
                 └─ max_connections=300에 근접
```

Pool 튜닝으로 완화는 가능하지만, pod 스케일링(KEDA) 시 connection 폭발 재발 가능.

---

## 3. 해결 방안 도출

### 3.1 검토한 선택지

| 선택지 | 장점 | 단점 |
|--------|------|------|
| A. Pool 튜닝만 | 코드 변경 최소 | 스케일링 시 재발, 근본 해결 아님 |
| B. PgBouncer 도입 | Worker 코드 무변경 | 추가 인프라, 운영 복잡도 |
| **C. Redis Primary + PG Sync** | Worker에서 PG 제거, 스케일링 안전 | 구현 필요, sync lag 존재 |
| D. Redis Only | 가장 단순 | 장기 세션 불가 (TTL), 재시작 시 유실 |

### 3.2 결정: C. Redis Primary + PostgreSQL Async Sync

```
[AS-IS]
Worker → AsyncPostgresSaver → psycopg_pool → PostgreSQL
         (매 노드 후 직접 write, pool 압박)

[TO-BE]
Worker → RedisCheckpointer → Redis (1ms 이하, pool 불필요)
                                 │
                                 └─ checkpoint_syncer (별도 프로세스)
                                      └─ AsyncPostgresSaver → PostgreSQL
                                           (단일 프로세스, 단일 pool)
```

### 3.3 기존 L1+L2(Cache-Aside)와의 차이

| | 기존 (CachedPostgresSaver) | 신규 (Redis Primary + PG Sync) |
|---|---|---|
| Write path | Worker → **PostgreSQL** (+ Redis 메타) | Worker → **Redis only** |
| Read path | Redis miss → **PostgreSQL** | **Redis only** (hot data) |
| Worker의 PG pool | 필요 (포화 원인) | **불필요** (완전 제거) |
| 동기화 | 동기 write-through | **비동기** (consumer가 처리) |
| PG 장애 영향 | Worker 블로킹 | Sync 지연만, Worker 정상 |
| 구현 상태 | no-op (메타데이터만 캐시) | 실제 checkpoint blob 저장 |
| aput_writes 호환 | 시그니처 불일치 | langgraph 네이티브 API 사용 |

**핵심 차이:** 기존은 "PostgreSQL이 primary, Redis가 cache(미구현)" → 신규는 "Redis가 primary, PostgreSQL이 archive"

---

## 4. 아키텍처

### 4.1 전체 흐름

```
┌──────────────────────────────────────────────────────────┐
│  chat_worker (Taskiq: 4 workers × 10 async tasks)        │
│                                                          │
│  graph.ainvoke(state, config={"thread_id": session_id})  │
│    ├─ intent_node → checkpoint                           │
│    ├─ rag_node → checkpoint                              │
│    ├─ answer_node → checkpoint                           │
│    └─ 각 checkpoint = Redis HSET                         │
│                                                          │
│  RedisCheckpointer (langgraph-checkpoint-redis)          │
│    └─ Redis: chat:checkpoint:{thread_id}                 │
└──────────────────────────────┬───────────────────────────┘
                               │ (데이터는 Redis에 존재)
                               │
┌──────────────────────────────v───────────────────────────┐
│  chat-checkpoint-syncer (별도 Deployment, 1 replica)      │
│                                                          │
│  주기적 or 이벤트 기반:                                    │
│    1. Redis에서 최신 checkpoint 읽기                       │
│    2. PostgreSQL에 upsert (langraph_checkpoints 테이블)   │
│    3. 성공 시 Redis에 sync 완료 마킹                       │
│                                                          │
│  AsyncPostgresSaver (psycopg_pool)                       │
│    └─ 단일 프로세스, pool_max_size=5 (충분)               │
└──────────────────────────────────────────────────────────┘
```

### 4.2 장애 시나리오

| 장애 | 영향 | 복구 |
|------|------|------|
| Redis 일시 장애 | Worker checkpoint 실패 → task retry | Redis 복구 후 자동 정상화 |
| Redis 데이터 유실 | 미sync 분 checkpoint 유실 | PostgreSQL에서 마지막 sync 시점 복원 |
| PostgreSQL 장애 | Sync 지연, Worker는 정상 | PG 복구 후 syncer가 밀린 분 처리 |
| Syncer 장애 | Sync 지연, Worker/사용자 영향 없음 | Syncer 재시작 후 밀린 분 처리 |

### 4.3 Read-Through with LRU Promotion (Cold Start 해결)

#### 문제: PG saver가 write-only backup이 되는 구조

Redis Primary 아키텍처에서 syncer가 Redis→PG로 동기화하지만,
Worker가 PG를 읽지 않으면 PG는 write-only backup에 불과함.

```
Write path: Worker → Redis → (syncer) → PG  ✓ 구현됨
Read path:  Worker → Redis (miss) → ???     ✗ 읽기 경로 부재
```

Redis TTL(24h) 만료 후 재접속한 사용자의 checkpoint는
PG에 존재하지만 Worker가 읽을 수 없음 → multi-turn 컨텍스트 유실.

#### 해결: Read-Through Checkpointer + Temporal Locality

#### Temporal Locality (시간적 지역성) 개념

컴퓨터 과학에서 **참조 지역성(Locality of Reference)** 은 프로그램이 메모리를 접근하는 패턴에서
관찰되는 통계적 규칙성이다. 그 중 **Temporal Locality**는:

> 한번 참조된 데이터는 가까운 미래에 다시 참조될 가능성이 높다.

CPU 캐시(L1/L2/L3)가 이 원리에 기반하여 설계됨:
- 메인 메모리에서 읽은 데이터를 빠른 캐시에 적재 (promote)
- 이후 동일 데이터 접근 시 느린 메모리 대신 빠른 캐시에서 서빙
- 캐시 공간이 부족하면 오래된 데이터부터 제거 (LRU eviction)

**Multi-turn 대화에서의 Temporal Locality:**

챗봇 사용자의 행동 패턴은 temporal locality가 매우 강함:
1. 사용자가 세션을 시작하면 수분~수시간 동안 같은 `thread_id`로 연속 요청
2. 한번 참조된 checkpoint는 세션 종료까지 반복 참조됨
3. 세션 종료 후 24시간 이내 재접속 확률 높음 (TTL 내 유지)

따라서 Redis miss(cold start) 시 PG에서 읽은 checkpoint를
Redis에 즉시 적재(promote)하면, 이후 연속 요청은 Redis에서 서빙 가능.

#### Inline Promote vs Batch Promote

Promote를 배치로 모아서 처리하는 방안도 검토했으나, 적합하지 않음:

```
[Batch Promote — 부적합]
Request 1: Redis miss → PG read → promote 큐에 적재 → 반환
Request 2 (500ms 후): Redis miss → PG read 재발생 ← promote 미완료
Request 3 (1s 후):    Redis miss → PG read 재발생
  ...
Batch job (5초 후): 큐 소비 → Redis write
Request N: Redis hit

[Inline Promote — 채택]
Request 1: Redis miss → PG read → Redis write (+1-2ms) → 반환
Request 2 (500ms 후): Redis hit → 즉시 반환
```

| | Batch Promote | Inline Promote |
|---|---|---|
| 2번째 요청 | PG hit 재발생 (promote 미완료) | **Redis hit** (이미 promote됨) |
| Cold start PG 접근 | N회 (batch 전까지 매 요청) | **1회** (첫 miss만) |
| 추가 latency | 0 (비동기) | ~1-2ms (Redis SET, 무시 가능) |
| Temporal locality 활용 | ✗ (지연으로 locality 이점 상실) | **✓** (즉시 hot path 복원) |

**결론:** Multi-turn 대화의 요청 간격(수백ms~수초)이 batch interval(수초)보다 짧으므로,
batch promote는 temporal locality의 이점을 활용하지 못함.
Inline promote의 1-2ms 추가 비용은 PG read(10-50ms) 절약 대비 무시 가능.

참고: **Write path(Redis→PG)는 batch 적합** — 결과를 기다리는 소비자가 없으므로.
**Read path(PG→Redis promote)는 inline 필수** — 바로 다음 요청이 이 데이터를 참조하므로.

#### 적용

Redis TTL 만료 후 재접속한 사용자는:
1. 첫 요청에서 PG 읽기 발생 (cold start, ~10-50ms 추가 지연)
2. Redis에 inline promote (write-back, +1-2ms)
3. 이후 동일 세션의 연속 요청은 Redis에서 직접 서빙 (~1ms)

한번 참조된 세션은 TTL(24h) 동안 Redis에 유지되므로,
연속 대화 패턴에서는 PG 접근이 첫 1회로 제한됨.

#### 아키텍처

```
graph.ainvoke() → ReadThroughCheckpointer
                    │
                    ├─ aget_tuple()
                    │    ├─ Redis hit → 즉시 반환 (hot path, ~1ms)
                    │    └─ Redis miss
                    │         ├─ PG read (cold start, ~10-50ms)
                    │         ├─ Redis write-back (promote, LRU)
                    │         └─ 반환
                    │
                    ├─ aput() → SyncableRedisSaver
                    │    ├─ Redis write
                    │    └─ LPUSH sync queue (syncer가 PG 동기화)
                    │
                    └─ alist() → Redis first, PG fallback
```

#### Worker의 PG Pool 설정 (Read-Only)

| 설정 | 값 | 근거 |
|------|-----|------|
| `pool_max_size` | **2** | Cold start만 사용. 대부분 Redis hit |
| `pool_min_size` | 1 | 최소 1개 warm connection 유지 |
| `timeout` | 30s | Cold start는 드문 이벤트, 여유 있게 |
| `max_lifetime` | 300s + jitter | 연결 갱신, thundering herd 방지 |

**총 PG 연결 수 (After):**
```
Worker (read-through): 4 pods × 2 pool = 8 connections
Syncer (write):        1 pod × 5 pool = 5 connections
persistence_consumer:  ~5
chat-api:              ~5
admin:                 ~10
= ~33 / 300 max_connections (기존 212에서 84% 감소)
```

#### LRU와의 유사점/차이점

| | CPU L1/L2 Cache (LRU) | ReadThroughCheckpointer |
|---|---|---|
| Eviction | LRU 순서 (가장 오래된 것 제거) | TTL 기반 (24h 후 만료) |
| Miss penalty | L2 접근 (~10ns) | PG 접근 (~10-50ms) |
| Write-back | Dirty bit → lower level | Promote → Redis SET + TTL |
| Locality 가정 | Temporal + Spatial | **Temporal** (최근 참조 세션 재참조) |
| 적합 패턴 | Loop, sequential access | **Multi-turn 대화** (연속 요청) |

Multi-turn 대화는 temporal locality가 매우 강함:
- 사용자가 세션 재개 → 이후 수분~수시간 동안 같은 thread_id로 연속 요청
- 첫 1회 PG 접근 후 TTL(24h) 동안 Redis에서 서빙 → hit rate ≈ 99%+

### 4.4 데이터 정합성 보장

- **Redis TTL**: checkpoint에 TTL 설정 (기본 24h). 장기 미접속 세션은 자연 만료.
- **Sync lag**: syncer가 5초 이내에 PostgreSQL 반영 목표
- **Cold start**: Redis miss → PostgreSQL read → Redis promote (ReadThroughCheckpointer)
- **Consistency**: 같은 thread_id의 checkpoint는 monotonic version → 순서 보장
- **Promote 실패**: PG 결과는 그대로 반환 (graceful degradation, Redis 적재만 실패)

---

## 5. 구현부 위치 선정

### 5.1 근거

checkpoint_syncer는 `langgraph-checkpoint-postgres`와 `psycopg_pool`에 의존.
이 패키지들은 **chat_worker 이미지에만 존재**.

| Consumer | 쓰는 테이블 | 도메인 모델 소속 | Docker 이미지 |
|---|---|---|---|
| persistence_consumer | `chat_message` | `apps/chat/` | chat-api |
| **checkpoint_syncer** | `checkpoint_writes` | `apps/chat_worker/` | **chat-worker** |

### 5.2 파일 구조

```
apps/chat_worker/
├── main.py                          # Taskiq worker (기존)
├── checkpoint_syncer.py             # ← 새 entrypoint (Redis→PG sync)
├── setup/
│   ├── config.py                    # Read-Through + Syncer 설정
│   └── dependencies.py             # ReadThroughCheckpointer 조립
└── infrastructure/
    └── orchestration/
        └── langgraph/
            ├── checkpointer.py      # 팩토리: Redis, ReadThrough, PG, Memory
            └── sync/
                ├── __init__.py
                ├── syncable_redis_saver.py      # Redis + sync queue (Worker write)
                ├── read_through_checkpointer.py # Redis→PG fallback→Redis promote
                └── checkpoint_sync_service.py   # BRPOP→PG write (Syncer)
```

### 5.3 Kubernetes 배포

```
workloads/domains/chat-worker/base/
├── deployment.yaml                          # 기존 worker
├── deployment-checkpoint-syncer.yaml        # ← 새 Deployment
├── configmap.yaml                           # SYNCER_* 환경변수 추가
└── kustomization.yaml                       # resource 추가
```

---

## 6. 상세 구현 스펙

### 6.1 Worker 측: ReadThroughCheckpointer (Redis + PG Cold Start)

**변경 파일:** `setup/dependencies.py`

```python
async def get_checkpointer():
    """ReadThroughCheckpointer (Redis Primary + PG Cold Start Fallback)."""
    if settings.checkpoint_read_postgres_url:
        # Read-Through: Redis + PG cold start fallback
        _checkpointer = await create_read_through_checkpointer(
            redis_url=settings.redis_url,
            postgres_url=settings.checkpoint_read_postgres_url,
            ttl_minutes=settings.checkpoint_ttl_minutes,
            pg_pool_min_size=settings.checkpoint_read_pg_pool_min,
            pg_pool_max_size=settings.checkpoint_read_pg_pool_max,
        )
    else:
        # Redis-only (PG fallback 비활성화)
        _checkpointer = await create_redis_checkpointer(...)
```

**새 파일:** `sync/read_through_checkpointer.py`

```python
class ReadThroughCheckpointer:
    """Redis Primary + PostgreSQL Read-Through (LRU Promotion)."""

    async def aget_tuple(self, config):
        result = await self._redis_saver.aget_tuple(config)
        if result is not None:
            return result  # Redis hit (hot path)

        # Redis miss → PG fallback → promote to Redis
        pg_result = await self._pg_saver.aget_tuple(config)
        if pg_result:
            await self._redis_saver.aput(...)  # LRU write-back
        return pg_result
```

**ConfigMap 변경:**
```yaml
# Worker Read-Through (cold start PG fallback)
CHAT_WORKER_CHECKPOINT_READ_POSTGRES_URL: postgresql+asyncpg://...
CHAT_WORKER_CHECKPOINT_READ_PG_POOL_MIN: '1'
CHAT_WORKER_CHECKPOINT_READ_PG_POOL_MAX: '2'

# Redis URL은 기존 유지 (primary checkpointer)
CHAT_WORKER_REDIS_URL: redis://...
```

### 6.2 Syncer: checkpoint_syncer.py

```python
"""Chat Checkpoint Syncer.

Redis의 LangGraph checkpoint를 PostgreSQL로 비동기 동기화.
chat_worker 이미지의 별도 entrypoint로 실행.

실행: python -m chat_worker.checkpoint_syncer
"""

import asyncio
import signal
import logging

from chat_worker.setup.config import get_settings
from chat_worker.infrastructure.orchestration.langgraph.sync import (
    CheckpointSyncService,
)

logger = logging.getLogger(__name__)


async def main():
    settings = get_settings()
    service = await CheckpointSyncService.create(
        redis_url=settings.redis_url,
        postgres_url=settings.syncer_postgres_url,
        pg_pool_min_size=settings.syncer_pg_pool_min_size,
        pg_pool_max_size=settings.syncer_pg_pool_max_size,
        sync_interval=settings.syncer_interval,
        batch_size=settings.syncer_batch_size,
    )

    loop = asyncio.get_event_loop()
    stop_event = asyncio.Event()

    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, stop_event.set)

    logger.info("Checkpoint syncer started")
    try:
        await service.run(stop_event)
    finally:
        await service.close()
        logger.info("Checkpoint syncer stopped")


if __name__ == "__main__":
    asyncio.run(main())
```

### 6.3 Sync Service

```python
"""CheckpointSyncService.

Redis → PostgreSQL 동기화 루프.

전략:
1. Redis SCAN으로 checkpoint 키 탐색
2. 각 키의 version을 PostgreSQL 최신 version과 비교
3. 신규/업데이트분만 PostgreSQL에 upsert
4. 성공 시 Redis에 sync marker 기록
"""

class CheckpointSyncService:
    def __init__(self, redis, pg_saver, sync_interval, batch_size):
        self._redis = redis
        self._pg_saver = pg_saver
        self._sync_interval = sync_interval  # 초 (기본 5)
        self._batch_size = batch_size  # 기본 50

    @classmethod
    async def create(cls, redis_url, postgres_url, ...):
        redis = Redis.from_url(redis_url)
        pg_saver = await create_pg_saver(postgres_url, pool_min_size, pool_max_size)
        return cls(redis, pg_saver, sync_interval, batch_size)

    async def run(self, stop_event: asyncio.Event):
        while not stop_event.is_set():
            try:
                synced = await self._sync_batch()
                if synced > 0:
                    logger.info("Synced %d checkpoints", synced)
            except Exception:
                logger.exception("Sync error, retrying")
            await asyncio.sleep(self._sync_interval)

    async def _sync_batch(self) -> int:
        """한 배치 동기화."""
        # 1. Redis에서 미sync checkpoint 키 조회
        keys = await self._get_unsynced_keys(limit=self._batch_size)
        if not keys:
            return 0

        synced = 0
        for key in keys:
            # 2. Redis에서 checkpoint 데이터 읽기
            checkpoint_data = await self._read_checkpoint(key)
            if not checkpoint_data:
                continue

            # 3. PostgreSQL에 upsert
            await self._pg_saver.aput(
                config=checkpoint_data["config"],
                checkpoint=checkpoint_data["checkpoint"],
                metadata=checkpoint_data["metadata"],
                new_versions=checkpoint_data.get("new_versions"),
            )

            # 4. Sync 완료 마킹
            await self._mark_synced(key)
            synced += 1

        return synced

    async def close(self):
        await self._redis.close()
        # pg_saver pool close
```

### 6.4 Config 추가

**파일:** `setup/config.py`

```python
# Checkpoint Redis TTL
checkpoint_ttl_minutes: int = 1440  # 24시간

# Read-Through (Worker용, Cold Start Fallback)
# None이면 Redis-only (PG fallback 비활성화)
checkpoint_read_postgres_url: str | None = None
checkpoint_read_pg_pool_min: int = 1   # cold start만 사용
checkpoint_read_pg_pool_max: int = 2   # cold start만 사용

# Checkpoint Syncer (별도 프로세스용)
syncer_postgres_url: str | None = None
syncer_pg_pool_min_size: int = 1
syncer_pg_pool_max_size: int = 5
syncer_interval: float = 5.0       # sync 주기 (초)
syncer_batch_size: int = 50         # 배치당 최대 checkpoint 수
```

### 6.5 Deployment

```yaml
# workloads/domains/chat-worker/base/deployment-checkpoint-syncer.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: chat-checkpoint-syncer
  labels:
    app: chat-worker
    tier: syncer
spec:
  replicas: 1
  selector:
    matchLabels:
      app: chat-checkpoint-syncer
  template:
    metadata:
      labels:
        app: chat-checkpoint-syncer
        tier: syncer
    spec:
      containers:
      - name: checkpoint-syncer
        image: docker.io/mng990/eco2:chat-worker-dev-latest
        command: [python, -m, chat_worker.checkpoint_syncer]
        envFrom:
        - configMapRef:
            name: chat-worker-config
        - secretRef:
            name: chat-worker-secret
        resources:
          requests: { memory: 256Mi, cpu: 100m }
          limits:   { memory: 512Mi, cpu: 250m }
        livenessProbe:
          exec:
            command: [/bin/sh, -c, "cat /proc/1/cmdline | grep -q checkpoint_syncer || exit 1"]
          periodSeconds: 30
      nodeSelector:
        domain: worker-ai
      tolerations:
      - key: domain
        value: worker-ai
        effect: NoSchedule
```

### 6.6 Pool 사이즈 비교 (Before/After)

**Before (Worker 직접 접근):**
```
4 pods × 4 workers × 12 pool = 192 connections
+ persistence_consumer (~5)
+ chat-api (~5)
+ admin (~10)
= ~212 / 300 max_connections
```

**After (Read-Through + Syncer):**
```
4 pods × 2 pool (read-through, cold start only) = 8 connections
1 syncer × 5 pool (write) = 5 connections
+ persistence_consumer (~5)
+ chat-api (~5)
+ admin (~10)
= ~33 / 300 max_connections
```

**84% 감소. Worker의 PG pool은 cold start(Redis TTL 만료 세션)에만 사용되므로 실질 활성 연결은 0~2개.**
**KEDA 스케일링으로 pods가 10개로 늘어도: 10×2+5+20 = 45 connections (안전).**

---

## 7. 마이그레이션 전략

### 7.1 단계적 전환

1. **Phase 1**: Redis checkpointer 구현 + syncer 구현 (이 ADR)
2. **Phase 2**: Worker에서 PostgreSQL pool 제거, Redis checkpointer 활성화
3. **Phase 3**: 기존 PostgreSQL checkpoint 데이터 → Redis로 warm-up (cold start 방지)
4. **Phase 4**: 모니터링 안정화 확인 후 `CachedPostgresSaver` 코드 완전 삭제

### 7.2 Rollback 계획

- Worker의 checkpointer를 `AsyncPostgresSaver`로 즉시 원복 가능
- Redis와 PostgreSQL 양쪽에 checkpoint가 존재하므로 데이터 유실 없음
- ConfigMap에서 `CHAT_WORKER_POSTGRES_URL` 복원 + image rollback

---

## 8. 모니터링

### 8.1 Syncer 메트릭

| 메트릭 | 설명 | Alert 조건 |
|--------|------|------------|
| `checkpoint_sync_lag_seconds` | Redis 마지막 write ~ PG sync 완료 | > 30s |
| `checkpoint_sync_batch_size` | 배치당 처리 건수 | batch_size 근접 시 부하 경고 |
| `checkpoint_sync_errors_total` | 동기화 실패 카운터 | > 0/5min |
| `checkpoint_redis_keys_unsynced` | 미sync 키 수 | > 100 (축적 경고) |

### 8.2 PostgreSQL 연결 모니터링

```sql
SELECT count(*) FROM pg_stat_activity
WHERE application_name = 'checkpoint-syncer';
-- 예상: 1~5 (pool_max_size)
```

---

## 9. 의존성

### 9.1 추가 패키지

```
langgraph-checkpoint-redis>=0.3.0   # 이미 requirements.txt에 존재
```

### 9.2 Redis 용량

- Checkpoint blob 크기: ~2~10KB/thread (messages 수에 비례)
- 동시 활성 세션: ~1,000개 가정
- Redis 메모리: ~10MB 추가 (무시 가능)
- TTL 24h: 미접속 세션 자동 정리

---

## 10. 참고

- [langgraph-checkpoint-redis 문서](https://langchain-ai.github.io/langgraph/reference/checkpoints/#langgraph.checkpoint.redis)
- [psycopg_pool PoolTimeout 분석](https://www.psycopg.org/psycopg3/docs/api/pool.html)
- [Redis persistence (AOF/RDB)](https://redis.io/docs/latest/operate/oss_and_stack/management/persistence/)
