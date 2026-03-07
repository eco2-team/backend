# SSE Pub/Sub Shard 기반 연결 최적화

> 이전 글: [SSE Pub/Sub 연결 최적화: Master Service 분리](53-sse-pubsub-connection-optimization.md)

## 개요

이 글에서는 Redis Pub/Sub 채널을 **Shard 기반**으로 변경하여 연결 수를 O(N)에서 O(4)로 줄이는 최적화를 다룹니다. 기존 이벤트 버스 아키텍처에서 이미 Redis Streams에는 샤딩이 적용되어 있었지만, Pub/Sub 채널은 job_id별로 생성되어 동시 접속 수에 비례하여 연결이 증가함을 관측했습니다.

---

## 1. 기존 이벤트 버스의 샤딩 현황

### 1.1 이미 샤딩된 부분: Redis Streams

이벤트 버스 아키텍처에서 **Redis Streams는 이미 샤딩이 적용**되어 있습니다.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    기존 Streams 샤딩 구조                                    │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  Chat Worker                                                                │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │  job_abc → hash(job_abc) % 4 = 2 → chat:events:2                    │   │
│  │  job_xyz → hash(job_xyz) % 4 = 0 → chat:events:0                    │   │
│  │  job_123 → hash(job_123) % 4 = 1 → chat:events:1                    │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│  Redis Streams (4개 샤드)                                                   │
│  ┌────────────────┐ ┌────────────────┐ ┌────────────────┐ ┌────────────────┐│
│  │ chat:events:0  │ │ chat:events:1  │ │ chat:events:2  │ │ chat:events:3  ││
│  └────────────────┘ └────────────────┘ └────────────────┘ └────────────────┘│
│                                                                             │
│  Event Router (Consumer Group)                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │  XREADGROUP STREAMS chat:events:0 chat:events:1 chat:events:2 ...   │   │
│  │  → 모든 샤드에서 이벤트 소비                                         │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│  ✅ 장점:                                                                   │
│  • 부하 분산: 이벤트가 4개 샤드에 분산 저장                                 │
│  • 병렬 처리: Consumer Group으로 여러 Event Router가 분담                   │
│  • 확장성: 샤드 수 증가로 처리량 확장 가능                                  │
└─────────────────────────────────────────────────────────────────────────────┘
```

**관련 코드 (`redis_progress_notifier.py`):**

```python
STREAM_PREFIX = "chat:events"
DEFAULT_SHARD_COUNT = int(os.environ.get("CHAT_SHARD_COUNT", "4"))

def _get_shard_for_job(job_id: str, shard_count: int | None = None) -> int:
    """job_id에 대한 shard 계산."""
    hash_bytes = hashlib.md5(job_id.encode()).digest()[:8]
    hash_int = int.from_bytes(hash_bytes, byteorder="big")
    return hash_int % shard_count

def _get_stream_key(job_id: str, shard_count: int | None = None) -> str:
    shard = _get_shard_for_job(job_id, shard_count)
    return f"{STREAM_PREFIX}:{shard}"  # chat:events:{shard}
```

### 1.2 샤딩되지 않았던 부분: Redis Pub/Sub

반면 **Pub/Sub 채널은 job_id별로 생성**되어 있었습니다.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    기존 Pub/Sub 구조 (샤딩 미적용)                           │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  Event Router                                    SSE Gateway               │
│  ┌──────────────┐                               ┌──────────────┐           │
│  │              │   sse:events:job_abc   ─────▶ │ subscribe()  │ Client A  │
│  │              │   sse:events:job_xyz   ─────▶ │ subscribe()  │ Client B  │
│  │   PUBLISH    │   sse:events:job_123   ─────▶ │ subscribe()  │ Client C  │
│  │              │   sse:events:job_456   ─────▶ │ subscribe()  │ Client D  │
│  │              │        ...                    │     ...      │           │
│  │              │   sse:events:job_N     ─────▶ │ subscribe()  │ Client N  │
│  └──────────────┘                               └──────────────┘           │
│                                                                             │
│  연결 수: 1개                                    연결 수: N개 (job 수)       │
│                                                                             │
│  ⚠️ 문제점:                                                                 │
│  • 동시 접속 1000명 → 1000개 Redis Pub/Sub 연결                             │
│  • Redis 연결 한계 (기본 10,000) 도달 가능                                  │
│  • 메모리 사용량 증가 (연결당 ~10KB)                                        │
└─────────────────────────────────────────────────────────────────────────────┘
```

**기존 코드 (`processor.py`):**

```python
# job_id별 채널 (샤딩 없음)
channel = f"{self._pubsub_channel_prefix}:{job_id}"  # sse:events:{job_id}
await self._pubsub_redis.publish(channel, event_data)
```

---

## 2. 문제점 분석

### 2.1 연결 수 증가 문제

| 동시 접속 수 | Streams 연결 | Pub/Sub 연결 (기존) |
|-------------|-------------|---------------------|
| 10명 | 4개 (고정) | 10개 |
| 100명 | 4개 (고정) | 100개 |
| 1,000명 | 4개 (고정) | 1,000개 |
| 10,000명 | 4개 (고정) | 10,000개 ⚠️ |

### 2.2 SSE Gateway의 구독 패턴

기존 SSE Gateway는 클라이언트가 연결될 때마다 해당 job_id의 채널을 새로 구독했습니다.

```python
# 기존 방식: job_id마다 새 Pub/Sub 연결 생성
async def _pubsub_listener(self, job_id: str):
    channel = f"sse:events:{job_id}"
    pubsub = self._pubsub_client.pubsub()
    await pubsub.subscribe(channel)  # 새 연결

    async for msg in pubsub.listen():
        # 이벤트 처리
        ...
```

---

## 3. 해결: Shard 기반 Pub/Sub

### 3.1 아키텍처 변경

Streams와 동일하게 Pub/Sub에도 샤딩을 적용합니다.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    Shard 기반 Pub/Sub 구조 (최적화)                          │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  Event Router                                    SSE Gateway               │
│  ┌──────────────┐                               ┌──────────────┐           │
│  │              │                               │              │           │
│  │ job_abc ─┐   │   sse:events:0   ──────────▶ │ subscribe(0) │           │
│  │ job_xyz ─┤   │   sse:events:1   ──────────▶ │ subscribe(1) │           │
│  │ job_123 ─┼──▶│   sse:events:2   ──────────▶ │ subscribe(2) │           │
│  │ job_456 ─┤   │   sse:events:3   ──────────▶ │ subscribe(3) │           │
│  │   ...   ─┘   │                               │              │           │
│  │              │                               │   내부에서   │           │
│  │  PUBLISH     │                               │   job_id로   │           │
│  │  (shard 계산)│                               │   라우팅     │           │
│  └──────────────┘                               └──────────────┘           │
│                                                                             │
│  연결 수: 1개                                    연결 수: 4개 (shard 수)    │
│                                                                             │
│  ✅ 동시 접속 1000명 → 여전히 4개 Pub/Sub 연결                              │
│  ✅ Redis 연결 부하 대폭 감소                                               │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 3.2 전체 이벤트 버스 샤딩 현황 (변경 후)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    전체 이벤트 버스 샤딩 구조                                 │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  Chat Worker                        Event Router                            │
│  ┌────────────────┐                ┌────────────────┐                      │
│  │   job_abc      │                │                │                      │
│  │   ↓            │                │  XREADGROUP    │                      │
│  │   hash % 4 = 2 │                │  (4 streams)   │                      │
│  └────────────────┘                └────────────────┘                      │
│          │                                 │                                │
│          ▼                                 ▼                                │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                     Redis Streams (샤딩 ✅)                          │   │
│  │  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐ ┌─────────────┐    │   │
│  │  │chat:events:0│ │chat:events:1│ │chat:events:2│ │chat:events:3│    │   │
│  │  └─────────────┘ └─────────────┘ └─────────────┘ └─────────────┘    │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                         │                                   │
│                                         ▼                                   │
│                            Event Router (process)                           │
│                            ┌────────────────────┐                          │
│                            │ shard = hash % 4   │                          │
│                            │ channel = sse:{shard}│                        │
│                            └────────────────────┘                          │
│                                         │                                   │
│                                         ▼                                   │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                     Redis Pub/Sub (샤딩 ✅ NEW!)                     │   │
│  │  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐ ┌─────────────┐    │   │
│  │  │sse:events:0 │ │sse:events:1 │ │sse:events:2 │ │sse:events:3 │    │   │
│  │  └─────────────┘ └─────────────┘ └─────────────┘ └─────────────┘    │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                         │                                   │
│                                         ▼                                   │
│                              SSE Gateway (시작 시)                          │
│                            ┌────────────────────┐                          │
│                            │ 4개 shard 전체 구독 │                          │
│                            │ job_id로 내부 라우팅│                          │
│                            └────────────────────┘                          │
│                                         │                                   │
│                                         ▼                                   │
│                            ┌─────────────────────┐                         │
│                            │  Client A (job_abc) │                         │
│                            │  Client B (job_xyz) │                         │
│                            │  Client C (job_123) │                         │
│                            └─────────────────────┘                         │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 4. 구현 상세

### 4.1 Event Router 변경

**변경 전:**
```python
channel = f"{self._pubsub_channel_prefix}:{job_id}"  # sse:events:{job_id}
```

**변경 후:**
```python
def _get_shard_for_job(self, job_id: str) -> int:
    """job_id에서 shard 계산."""
    hash_bytes = hashlib.md5(job_id.encode()).digest()[:8]
    hash_int = int.from_bytes(hash_bytes, byteorder="big")
    return hash_int % self._shard_count

# 사용
shard = self._get_shard_for_job(job_id)
channel = f"{self._pubsub_channel_prefix}:{shard}"  # sse:events:{shard}
```

### 4.2 SSE Gateway 변경

**변경 전 (job_id별 구독):**
```python
async def subscribe(self, job_id: str):
    # 클라이언트 연결마다 새 Pub/Sub 채널 구독
    if job_id not in self._pubsub_tasks:
        self._pubsub_tasks[job_id] = asyncio.create_task(
            self._pubsub_listener(job_id)  # job_id별 리스너
        )
```

**변경 후 (shard별 구독):**
```python
async def _initialize(self):
    # 초기화 시 4개 shard 전체 구독 (고정)
    await self._start_shard_listeners()

async def _start_shard_listeners(self):
    for shard in range(self._pubsub_shard_count):
        self._shard_listener_tasks[shard] = asyncio.create_task(
            self._shard_pubsub_listener(shard)  # shard별 리스너
        )

async def _shard_pubsub_listener(self, shard: int):
    channel = f"sse:events:{shard}"
    pubsub = self._pubsub_client.pubsub()
    await pubsub.subscribe(channel)

    async for msg in pubsub.listen():
        event = json.loads(msg["data"])
        job_id = event["job_id"]  # 메시지에서 job_id 추출

        # 해당 job_id의 구독자에게만 전달
        if job_id in self._subscribers:
            for subscriber in self._subscribers[job_id]:
                await subscriber.put_event(event)
```

---

## 5. 메시지 격리 보장

Shard 채널을 공유해도 메시지가 엉키지 않습니다. 핵심은 **메시지에 job_id가 포함**되어 있고, SSE Gateway가 **내부에서 필터링**하기 때문입니다.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    메시지 격리 동작 방식                                     │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  1. Event Router: 이벤트에 job_id 포함하여 shard 채널에 발행                 │
│     ┌─────────────────────────────────────────────────────────────────┐    │
│     │  payload = {                                                     │    │
│     │      "job_id": "abc123",  ← 라우팅 키                            │    │
│     │      "stage": "answer",                                          │    │
│     │      "seq": 30,                                                  │    │
│     │      "data": {...}                                               │    │
│     │  }                                                               │    │
│     │  shard = hash("abc123") % 4 = 2                                  │    │
│     │  redis.publish("sse:events:2", payload)                          │    │
│     └─────────────────────────────────────────────────────────────────┘    │
│                                                                             │
│  2. SSE Gateway: shard 채널에서 수신 후 job_id로 필터링                      │
│     ┌─────────────────────────────────────────────────────────────────┐    │
│     │  # sse:events:2 채널에서 메시지 수신                              │    │
│     │  event = json.loads(msg["data"])                                 │    │
│     │  job_id = event["job_id"]  # "abc123"                            │    │
│     │                                                                   │    │
│     │  # 내부 라우팅 테이블 조회                                        │    │
│     │  if job_id in self._subscribers:                                 │    │
│     │      # abc123의 구독자에게만 전달                                 │    │
│     │      for sub in self._subscribers[job_id]:                       │    │
│     │          await sub.put_event(event)                              │    │
│     └─────────────────────────────────────────────────────────────────┘    │
│                                                                             │
│  3. 결과: 각 클라이언트는 자신의 job_id 이벤트만 수신                        │
│     ┌─────────────────────────────────────────────────────────────────┐    │
│     │  Client A (job=abc123) ← sse:events:2 ← {"job_id":"abc123",...} │    │
│     │  Client B (job=xyz789) ← sse:events:0 ← {"job_id":"xyz789",...} │    │
│     │                                                                   │    │
│     │  같은 shard 채널을 구독해도:                                      │    │
│     │  • Client A: job=abc123 이벤트만 수신 (다른 job 필터링)           │    │
│     │  • Client B: job=xyz789 이벤트만 수신 (다른 job 필터링)           │    │
│     └─────────────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 6. 연결 수 비교 (최종)

| 구성 요소 | 기존 | 최적화 후 |
|-----------|------|-----------|
| **Redis Streams** | 4개 (샤드) | 4개 (샤드) |
| **Pub/Sub (Event Router → Redis)** | 1개 | 1개 |
| **Pub/Sub (SSE Gateway ← Redis)** | N개 (job 수) | **4개 (샤드)** |

| 동시 접속 수 | Pub/Sub 연결 (기존) | Pub/Sub 연결 (최적화) | 절감률 |
|-------------|---------------------|----------------------|--------|
| 10명 | 10개 | 4개 | 60% |
| 100명 | 100개 | 4개 | 96% |
| 1,000명 | 1,000개 | 4개 | 99.6% |
| 10,000명 | 10,000개 | 4개 | 99.96% |

---

## 7. 정리

### 이전 샤딩 현황

| 컴포넌트 | 샤딩 여부 | 패턴 |
|----------|----------|------|
| Redis Streams | ✅ 적용됨 | `chat:events:{shard}` |
| Redis Pub/Sub | ❌ 미적용 | `sse:events:{job_id}` |

### 변경 후 샤딩 현황

| 컴포넌트 | 샤딩 여부 | 패턴 |
|----------|----------|------|
| Redis Streams | ✅ 적용됨 | `chat:events:{shard}` |
| Redis Pub/Sub | ✅ **적용됨** | `sse:events:{shard}` |

### 수정된 파일

**Event Router:**
- `apps/event_router/core/processor.py`
  - `_get_shard_for_job()` 메서드 추가
  - 채널 계산 로직 변경

**SSE Gateway:**
- `apps/sse_gateway/core/broadcast_manager.py`
  - `_start_shard_listeners()` 메서드 추가
  - `_shard_pubsub_listener()` 메서드 추가
  - job_id 기반 내부 라우팅 로직 추가

---

## 참고

- [Redis Pub/Sub Documentation](https://redis.io/docs/manual/pubsub/)
- [53-sse-pubsub-connection-optimization.md](53-sse-pubsub-connection-optimization.md)
- [34-sse-HA-architecture.md](34-sse-HA-architecture.md)
