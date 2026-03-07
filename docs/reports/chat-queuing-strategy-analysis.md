# Chat Queuing & Event Bus Strategy Analysis Report

> **Date:** 2026-01-18
> **Scope:** chat-api (Producer) + chat-worker (Consumer) + RabbitMQ Topology + Event Router + SSE Gateway
> **Status:** Analysis Complete

---

## Executive Summary

Eco² Chat 서비스의 큐잉 전략과 이벤트 버스를 분석한 결과:

1. **실행 경로 (RabbitMQ)**: 코드베이스 설계는 일관성 있으나, **Topology CR과 실제 클러스터 설정 불일치**
2. **이벤트 경로 (Redis)**: **"A안" 패턴 구현 완료** - 실행과 이벤트 경로가 명확히 분리됨
3. **Event Router**: Redis Streams → Pub/Sub 변환, Lua 기반 idempotent 처리
4. **SSE Gateway**: Redis Pub/Sub → SSE 스트리밍, Token v2 복구 지원

**핵심 설계 원칙**: 실행은 RabbitMQ (DIRECT), 이벤트는 Redis (Streams + Pub/Sub)

---

## 1. Architecture Overview

### 1.1 전체 시스템 구조

```
┌───────────────────────────────────────────────────────┐
│             Eco² Chat Full Architecture               │
├───────────────────────────────────────────────────────┤
│                                                       │
│  [실행 경로 - RabbitMQ]                               │
│  ┌─────────┐  chat_tasks  ┌───────────┐  ┌────────┐  │
│  │chat-api │──(exchange)─▶│chat.process│─▶│ worker │  │
│  └─────────┘              │   queue    │  └────────┘  │
│       │                   └───────────┘       │       │
│       └────── job_id (UUID) ──────────────────┘       │
│                                               │       │
│  [이벤트 경로 - Redis]                         ▼       │
│                                        ┌──────────┐   │
│  ┌───────────┐   Pub/Sub   ┌────────┐  │ Progress │   │
│  │sse-gateway│◀───────────│ Router │◀─│ Notifier │   │
│  └───────────┘             └────────┘  └──────────┘   │
│        │                        │                     │
│        ▼                        ▼                     │
│    Browser              ┌────────────┐                │
│    (SSE)                │chat:state: │                │
│                         │ {job_id}   │                │
│                         └────────────┘                │
└───────────────────────────────────────────────────────┘
```

### 1.2 실행 vs 이벤트 경로 분리

| 경로 | 브로커 | 용도 | 특성 |
|------|--------|------|------|
| **실행** | RabbitMQ | Job dispatch (1:1) | At-least-once, 재시도, DLQ |
| **이벤트** | Redis Streams | 상태 저장 + 순서 보장 | Durable, Consumer Group |
| **실시간** | Redis Pub/Sub | SSE 브로드캐스트 | Fire-and-forget, 실시간 |

### 1.3 데이터 플로우 다이어그램

```
Client ──HTTP──▶ chat-api ──AMQP──▶ RabbitMQ
   ▲                │                   │
   │             job_id            chat.process
   │                │                   ▼
   │                │              chat-worker
   │                │              (LangGraph)
   │                │                   │
   │                │                XADD
   │                │                   ▼
   │                │             Redis Streams
   │                │             chat:events:*
   │                │                   │
   │                │              XREADGROUP
   │                │                   ▼
   │                │             Event Router
   │                │                   │
   │                │        ┌──────────┼──────────┐
   │                │        ▼          ▼          ▼
   │                │    Pub/Sub    State KV   Published
   │                │    PUBLISH    UPDATE      Marker
   │                │        │
   │                │    SUBSCRIBE
   │                │        ▼
   │◀───────────────┼── sse-gateway
  SSE               │
                 job_id 추적
```

---

## 2. Producer Side (chat-api)

### 2.1 Job Submission

**File:** `apps/chat/infrastructure/messaging/job_submitter.py`

```python
class TaskiqJobSubmitter(JobSubmitterPort):
    async def submit(
        self,
        job_id: str,
        session_id: str,
        user_id: str,
        message: str,
        image_url: str | None = None,
        user_location: dict[str, float] | None = None,
        model: str | None = None,
    ) -> bool
```

**Broker Configuration:**

| Parameter | Value |
|-----------|-------|
| URL | `CHAT_RABBITMQ_URL` (환경변수) |
| Exchange | `chat_tasks` |
| declare_exchange | `True` |

### 2.2 Message Format

```python
BrokerMessage(
    task_id=job_id,
    task_name="chat.process",
    message=json.dumps({
        "args": [],
        "kwargs": {
            "job_id": job_id,
            "session_id": session_id,
            "message": message,
            "user_id": user_id,
            "image_url": image_url,
            "user_location": user_location,
            "model": model,
        },
    }).encode(),
    labels={},
)
```

**Serialization:**
- Format: JSON (UTF-8)
- Protocol: AMQP 0-9-1
- Wrapper: TaskIQ `BrokerMessage`

---

## 3. Consumer Side (chat-worker)

### 3.1 Broker Configuration

**File:** `apps/chat_worker/setup/broker.py`

```python
broker = AioPikaBroker(
    url=settings.rabbitmq_url,
    declare_exchange=not _is_production,  # Prod: False
    exchange_name="chat_tasks",
    queue_name=settings.rabbitmq_queue,   # chat.process
)
```

**Environment-Aware:**
- **Local/Dev:** `declare_exchange=True` (자동 생성)
- **Production:** `declare_exchange=False` (Topology CR 사용)

### 3.2 Task Definition

**File:** `apps/chat_worker/presentation/amqp/process_task.py`

```python
@broker.task(
    task_name="chat.process",
    timeout=120,
    retry_on_error=True,
    max_retries=2,
)
async def process_chat(
    job_id: str,
    session_id: str,
    message: str,
    user_id: str | None = None,
    image_url: str | None = None,
    user_location: dict[str, float] | None = None,
    model: str | None = None,
) -> dict[str, Any]
```

**Configuration:**

| Parameter | Value |
|-----------|-------|
| Task Name | `chat.process` |
| Timeout | 120 seconds |
| Retry on Error | Yes |
| Max Retries | 2 (total 3 attempts) |

---

## 4. RabbitMQ Topology (CR)

### 4.1 Exchange

**File:** `workloads/rabbitmq/base/topology/exchanges.yaml`

```yaml
apiVersion: rabbitmq.com/v1beta1
kind: Exchange
metadata:
  name: chat-tasks
spec:
  name: chat_tasks
  type: direct
  durable: true
  autoDelete: false
  vhost: eco2
```

### 4.2 Queue

**File:** `workloads/rabbitmq/base/topology/queues.yaml`

```yaml
apiVersion: rabbitmq.com/v1beta1
kind: Queue
metadata:
  name: chat-process-queue
spec:
  name: chat.process
  type: classic
  durable: true
  autoDelete: false
  vhost: eco2
  arguments:
    x-dead-letter-exchange: dlx
    x-dead-letter-routing-key: dlq.chat.process
    x-message-ttl: 3600000  # 1시간
```

### 4.3 Binding

**File:** `workloads/rabbitmq/base/topology/bindings.yaml`

```yaml
apiVersion: rabbitmq.com/v1beta1
kind: Binding
metadata:
  name: chat-process-binding
spec:
  source: chat_tasks
  destination: chat.process
  destinationType: queue
  routingKey: chat.process
  vhost: eco2
```

### 4.4 Dead Letter Queue

```yaml
apiVersion: rabbitmq.com/v1beta1
kind: Queue
metadata:
  name: dlq-chat-process
spec:
  name: dlq.chat.process
  type: classic
  durable: true
  arguments:
    x-message-ttl: 604800000  # 7일 보관
```

---

## 5. Configuration Consistency Matrix

### 5.1 코드베이스 내 일관성 (정상)

| Parameter | Producer | Consumer | Topology CR | Status |
|-----------|----------|----------|-------------|--------|
| Exchange Name | `chat_tasks` | `chat_tasks` | `chat_tasks` | ✅ 일치 |
| Queue Name | (implicit) | `chat.process` | `chat.process` | ✅ 일치 |
| Task Name | `chat.process` | `chat.process` | - | ✅ 일치 |
| Routing Key | `chat.process` | (task_name) | `chat.process` | ✅ 일치 |
| Message Format | JSON | JSON | - | ✅ 일치 |

### 5.2 CR vs 실제 클러스터 (불일치 발견)

| Resource | CR 설정 | 실제 클러스터 | Status |
|----------|---------|---------------|--------|
| `chat_tasks` exchange type | `direct` | `topic` | ⚠️ 불일치 |
| `chat.process` queue durable | `true` | `false` | ⚠️ 불일치 |
| `chat.process` DLX | `dlx` | `""` (empty) | ⚠️ 불일치 |
| `chat.process` DLQ routing | `dlq.chat.process` | `chat.process.dead_letter` | ⚠️ 불일치 |
| Binding routing key | `chat.process` | `#` | ⚠️ 불일치 |

---

## 6. TaskIQ Settings Conflict Analysis

### 6.1 TaskIQ AioPikaBroker Defaults

**파일:** `taskiq_aio_pika/broker.py` (라이브러리)

```python
class AioPikaBroker:
    def __init__(
        self,
        url: str,
        exchange_name: str = "taskiq",
        exchange_type: ExchangeType = ExchangeType.TOPIC,  # ⚠️ Default: TOPIC
        queue_name: str = "taskiq",
        routing_key: str = "#",  # ⚠️ Default: Wildcard
        declare_exchange: bool = True,
        ...
    )
```

### 6.2 현재 코드베이스 설정

**Producer (`job_submitter.py`):**

```python
self._broker = AioPikaBroker(
    url=self._settings.rabbitmq_url,
    declare_exchange=True,
    exchange_name="chat_tasks",
    # exchange_type 미설정 → TOPIC (default)
    # routing_key 미설정 → "#" (default)
)
```

**Consumer (`broker.py`):**

```python
broker = AioPikaBroker(
    url=settings.rabbitmq_url,
    declare_exchange=not _is_production,
    exchange_name="chat_tasks",
    queue_name=settings.rabbitmq_queue,
    # exchange_type 미설정 → TOPIC (default)
    # routing_key 미설정 → "#" (default)
)
```

### 6.3 충돌 매트릭스

| Setting | Producer (job_submitter) | Consumer (broker.py) | Topology CR | 실제 클러스터 |
|---------|--------------------------|----------------------|-------------|---------------|
| exchange_type | TOPIC (default) | TOPIC (default) | `direct` | `topic` |
| routing_key | `#` (default) | `#` (default) | `chat.process` | `#` |
| exchange_name | `chat_tasks` | `chat_tasks` | `chat_tasks` | `chat_tasks` |

### 6.4 라우팅 동작 분석

**TOPIC Exchange + `#` Routing Key:**
- `#` = 모든 routing key 패턴 매칭 (wildcard)
- Producer가 `task_name="chat.process"`로 전송
- Binding이 `#`이므로 모든 메시지가 `chat.process` 큐로 도달
- **현재 동작: 정상** (wildcard가 모든 것을 캐치)

**DIRECT Exchange + `chat.process` Routing Key (CR 의도):**
- exact match만 허용
- Producer가 `chat.process`로 전송해야 큐에 도달
- 더 명시적이고 안전한 라우팅

### 6.5 불일치 원인

```
┌──────────────────────────────────────────────┐
│         Timeline of Inconsistency            │
├──────────────────────────────────────────────┤
│                                              │
│  1. Topology CR: exchange type: direct       │
│                                              │
│  2. TaskIQ 브로커 실행 (declare=True)        │
│     └─ type 미설정 → TOPIC으로 생성          │
│                                              │
│  3. Topology Operator reconcile              │
│     └─ 기존 exchange → 타입 변경 불가        │
│                                              │
│  4. 결과: CR=DIRECT, 실제=TOPIC              │
│                                              │
└──────────────────────────────────────────────┘
```

### 6.6 해결 방안

**Option A: 코드를 CR에 맞춤 (권장)**

```python
# job_submitter.py
from aio_pika import ExchangeType

self._broker = AioPikaBroker(
    url=self._settings.rabbitmq_url,
    declare_exchange=True,
    exchange_name="chat_tasks",
    exchange_type=ExchangeType.DIRECT,  # 명시적 설정
    routing_key="chat.process",         # 명시적 설정
)
```

```python
# broker.py
from aio_pika import ExchangeType

broker = AioPikaBroker(
    url=settings.rabbitmq_url,
    declare_exchange=not _is_production,
    exchange_name="chat_tasks",
    queue_name=settings.rabbitmq_queue,
    exchange_type=ExchangeType.DIRECT,  # 명시적 설정
    routing_key="chat.process",         # 명시적 설정
)
```

**Option B: CR을 코드에 맞춤**

```yaml
# exchanges.yaml
spec:
  name: chat_tasks
  type: topic  # TOPIC으로 변경
  durable: true

# bindings.yaml
spec:
  source: chat_tasks
  destination: chat.process
  routingKey: "#"  # Wildcard로 변경
```

**권장: Option A**
- DIRECT exchange가 더 명시적이고 예측 가능
- 의도하지 않은 메시지 라우팅 방지
- 기존 exchange/queue 삭제 후 재생성 필요

---

## 7. Event Router

### 7.1 Overview

**File:** `apps/event_router/`

Event Router는 Redis Streams에서 이벤트를 소비하여 Redis Pub/Sub로 변환하는 서비스입니다.

```
┌─────────────────────────────────────────────────┐
│           Event Router Architecture             │
├─────────────────────────────────────────────────┤
│                                                 │
│  Redis Streams        Event Router      Redis   │
│  ┌───────────┐       ┌──────────┐    ┌───────┐ │
│  │chat:events│─┐     │          │    │Pub/Sub│ │
│  │  :0,:1,   │─┼────▶│ Consumer │───▶│PUBLISH│ │
│  │  :2,:3    │─┘     │          │    └───────┘ │
│  └───────────┘       │          │              │
│                      │Processor │    ┌───────┐ │
│  Consumer Group:     │          │───▶│State  │ │
│  "eventrouter"       │          │    │  KV   │ │
│                      │          │    └───────┘ │
│                      │Reclaimer │              │
│                      │(5min)    │    ┌───────┐ │
│                      └──────────┘───▶│Marker │ │
│                                      └───────┘ │
└─────────────────────────────────────────────────┘
```

### 7.2 핵심 컴포넌트

| Component | File | 역할 |
|-----------|------|------|
| **Consumer** | `core/consumer.py` | XREADGROUP로 Streams 소비 |
| **Processor** | `core/processor.py` | Lua Script로 atomic 처리 |
| **Reclaimer** | `core/reclaimer.py` | XAUTOCLAIM으로 실패 복구 |
| **Config** | `config.py` | 환경별 설정 |

### 7.3 Dual Redis 구조

```python
# 역할 분리
redis_streams_client  # XREADGROUP, State KV, Published Marker
redis_pubsub_client   # PUBLISH only (real-time)
```

| Redis | URL | 용도 |
|-------|-----|------|
| **Streams** | `rfr-streams-redis:6379/0` | 이벤트 소비 + 상태 저장 |
| **Pub/Sub** | `rfr-pubsub-redis:6379/0` | 실시간 브로드캐스트 |

### 7.4 Idempotent Processing (Lua Script)

```lua
-- UPDATE_STATE_SCRIPT (core/processor.py)
-- 1. Idempotency Check
if redis.call("EXISTS", published_key) == 1 then
    return 0  -- Skip duplicate
end

-- 2. Conditional State Update (out-of-order 대응)
local current_seq = redis.call("HGET", state_key, "seq")
if new_seq > current_seq then
    redis.call("HSET", state_key, "seq", new_seq, ...)
    redis.call("EXPIRE", state_key, state_ttl)
end

-- 3. Mark as Published
redis.call("SET", published_key, "1", "EX", published_ttl)
return 1  -- Proceed to Pub/Sub
```

**핵심 특성:**
- **Atomic**: Lua Script는 Redis에서 원자적 실행
- **Idempotent**: `router:published:{job_id}:{seq}` 마커로 중복 방지
- **Out-of-Order Safe**: `new_seq > current_seq` 조건으로 최신 상태만 유지

### 7.5 Token Event 특별 처리

```python
# processor.py line 283-324
if event.get("stage") == "token":
    # State 업데이트 건너뜀 (스트리밍 데이터)
    # Pub/Sub만 발행 (실시간 전달)
    await self._publish_to_pubsub(event)
    return
```

**이유**: Token은 스트리밍 데이터라 State에 저장하면 최종 상태가 깨짐

### 7.6 Failure Recovery (Reclaimer)

```python
# 60초마다 실행
for shard in range(shard_count):
    result = await redis.xautoclaim(
        stream_key=f"chat:events:{shard}",
        consumer_group="eventrouter",
        consumer_name="{current_pod}",
        min_idle_time=300000,  # 5분 이상 미처리
        start_id="0-0"
    )
    for msg_id, data in result[1]:
        await processor.process_event(data)  # Idempotent
        await redis.xack(stream_key, consumer_group, msg_id)
```

### 7.7 Redis Keys Schema

| Key Pattern | Redis | TTL | 용도 |
|-------------|-------|-----|------|
| `chat:events:{shard}` | Streams | - | 이벤트 스트림 (0-3 샤드) |
| `chat:state:{job_id}` | Streams | 1시간 | 최신 Job 상태 |
| `router:published:{job_id}:{seq}` | Streams | 2시간 | Idempotency 마커 |
| `sse:events:{job_id}` | Pub/Sub | - | 실시간 채널 |

### 7.8 Configuration

```yaml
# 환경변수
REDIS_STREAMS_URL: redis://rfr-streams-redis:6379/0
REDIS_PUBSUB_URL: redis://rfr-pubsub-redis:6379/0
CONSUMER_GROUP: eventrouter
SHARD_COUNT: 4           # scan domain
CHAT_SHARD_COUNT: 4      # chat domain
XREAD_BLOCK_MS: 5000     # 5초 blocking read
XREAD_COUNT: 100         # 배치 크기
RECLAIM_MIN_IDLE_MS: 300000  # 5분
STATE_TTL: 3600          # 1시간
```

---

## 8. SSE Gateway

### 8.1 Overview

**File:** `apps/sse_gateway/`

SSE Gateway는 Redis Pub/Sub를 구독하여 클라이언트에 Server-Sent Events로 스트리밍합니다.

```
┌───────────────────────────────────────────────┐
│          SSE Gateway Architecture             │
├───────────────────────────────────────────────┤
│                                               │
│  Redis Pub/Sub       SSE Gateway     Clients  │
│  ┌───────────┐      ┌──────────┐    ┌──────┐ │
│  │sse:events:│      │          │ SSE│Client│ │
│  │ {job_id}  │─────▶│Broadcast │───▶│  1   │ │
│  └───────────┘      │ Manager  │    └──────┘ │
│                     │          │ SSE┌──────┐ │
│  Redis State        │(Fan-out) │───▶│Client│ │
│  ┌───────────┐      │          │    │  2   │ │
│  │chat:state:│─GET─▶│ State    │    └──────┘ │
│  │ {job_id}  │      │ Recovery │ SSE┌──────┐ │
│  └───────────┘      │          │───▶│Client│ │
│                     └──────────┘    │  3   │ │
│  Redis Streams           │          └──────┘ │
│  ┌───────────┐           │                   │
│  │chat:events│──XRANGE──▶│ (Catch-up)        │
│  └───────────┘                               │
└───────────────────────────────────────────────┘
```

### 8.2 핵심 컴포넌트

| Component | File | 역할 |
|-----------|------|------|
| **BroadcastManager** | `core/broadcast_manager.py` | Pub/Sub 구독 + Fan-out |
| **Stream Endpoint** | `api/v1/stream.py` | SSE 엔드포인트 |
| **Config** | `config.py` | 환경별 설정 |

### 8.3 SSE Endpoints

```python
# Legacy (scan domain)
GET /api/v1/stream?job_id={job_id}

# RESTful (multi-domain)
GET /api/v1/{service}/{job_id}/events
GET /api/v1/chat/{job_id}/events?last_token_seq=1050
```

### 8.4 In-Memory Fan-out 패턴

```python
class SSEBroadcastManager:
    _subscribers: dict[str, set[SubscriberQueue]]  # job_id → clients
    _pubsub_tasks: dict[str, asyncio.Task]         # job_id → listener

    async def subscribe(self, job_id: str) -> SubscriberQueue:
        queue = SubscriberQueue(job_id, maxsize=100)
        self._subscribers[job_id].add(queue)

        # 첫 구독자면 Pub/Sub listener 시작
        if len(self._subscribers[job_id]) == 1:
            self._pubsub_tasks[job_id] = asyncio.create_task(
                self._pubsub_listener(job_id)
            )
        return queue
```

**특징:**
- **Single Worker**: `workers=1`로 단일 프로세스 보장
- **Pod당 Fan-out**: 각 Pod가 독립적으로 구독 관리
- **Lazy Subscription**: 클라이언트 연결 시에만 Pub/Sub 구독

### 8.5 State Recovery & Catch-up

```
┌──────────────────────────────────────────────┐
│             SSE Recovery Flow                │
├──────────────────────────────────────────────┤
│                                              │
│  1. 클라이언트 연결                          │
│     └─▶ State KV 조회 (chat:state:{job_id}) │
│                                              │
│  2. 상태 스냅샷 전송                         │
│     └─▶ progress, stage 정보                │
│                                              │
│  3. Pub/Sub 구독 시작                        │
│     └─▶ 실시간 이벤트 수신                   │
│                                              │
│  4. Streams Catch-up (선택)                  │
│     └─▶ 스냅샷~Pub/Sub 갭 메우기            │
│                                              │
│  5. Token v2 Recovery (chat)                 │
│     └─▶ last_token_seq 이후 복구            │
│                                              │
└──────────────────────────────────────────────┘
```

### 8.6 Event Sequencing & Deduplication

```python
class SubscriberQueue:
    last_seq: int = 0

    async def put(self, event: dict) -> bool:
        seq = event.get("seq", 0)
        if seq <= self.last_seq:
            return False  # Duplicate or out-of-order
        self.last_seq = seq
        # ... queue logic
```

### 8.7 SSE Event Schema

```typescript
// Stage Event
event: vision
data: {"stage":"vision","status":"success","seq":5,"progress":25}

// Token Event (chat)
event: token
data: {"stage":"token","content":"Hello ","seq":1050,"node":"answer"}

// Token Recovery (chat)
event: token_recovery
data: {"accumulated":"Hello world...","last_seq":1050,"completed":false}

// Keepalive (15초 간격)
event: keepalive
data: {"type":"keepalive","timestamp":"2026-01-18T10:30:00Z"}

// Completion
event: done
data: {"stage":"done","status":"success","seq":100,"result":{...}}

// Error
event: error
data: {"type":"error","error":"timeout","message":"Max wait exceeded"}
```

### 8.8 Queue Management

```python
# 큐가 가득 찼을 때
if queue.full():
    # 오래된 이벤트 제거 (단, done/error는 보존)
    while not queue.empty():
        old = queue.get_nowait()
        if old.get("stage") in ("done", "error"):
            queue.put_nowait(old)  # 다시 넣기
            break
    # 새 이벤트 추가
    queue.put_nowait(event)
```

### 8.9 Configuration

```yaml
# 환경변수
REDIS_STREAMS_URL: redis://rfr-streams-redis:6379/0   # State, Catch-up
REDIS_PUBSUB_URL: redis://rfr-pubsub-redis:6379/1     # Subscribe

# SSE 설정
SSE_KEEPALIVE_INTERVAL: 15.0    # 15초
SSE_MAX_WAIT_SECONDS: 300       # 5분 최대 연결
SSE_QUEUE_MAXSIZE: 100          # 클라이언트당 버퍼

# Pub/Sub
PUBSUB_CHANNEL_PREFIX: sse:events
STATE_KEY_PREFIX: chat:state    # or scan:state
STATE_TIMEOUT_SECONDS: 5        # Silence 감지

# Sharding
SHARD_COUNT: 4
CHAT_SHARD_COUNT: 4
```

### 8.10 Metrics

| Metric | Type | 용도 |
|--------|------|------|
| `sse_gateway_connections_active` | Gauge | 현재 연결 수 |
| `sse_gateway_active_jobs` | Gauge | 활성 Job 수 |
| `sse_gateway_events_distributed_total` | Counter | 전송된 이벤트 |
| `sse_gateway_ttfb_seconds` | Histogram | Time to First Byte |
| `sse_gateway_queue_dropped_total` | Counter | 드롭된 이벤트 |

---

## 9. Error Handling Strategy

### 9.1 Retry Policy

**File:** `apps/chat_worker/infrastructure/error_handling/retry_policy.py`

```python
@dataclass
class RetryPolicy:
    max_retries: int = 3
    base_delay: float = 1.0
    max_delay: float = 30.0
    exponential_base: float = 2.0
    jitter: bool = True
```

**Backoff Schedule:**
- Attempt 0: 1.0s ± 0.25s
- Attempt 1: 2.0s ± 0.5s
- Attempt 2: 4.0s ± 1.0s

### 7.2 Dead Letter Handling

**File:** `apps/chat_worker/infrastructure/error_handling/dlq_handler.py`

```python
DLQ_STREAM_KEY = "chat:dlq"
DLQ_TTL = 7 * 24 * 60 * 60  # 7일
DLQ_MAXLEN = 10000
```

**Storage:** Redis Streams (`chat:dlq`)

---

## 10. Message Flow

```
1. Client → POST /api/v1/chat/{chat_id}/messages
   │
2. ├── SubmitChatCommand.execute()
   │   └── Generate job_id (UUID)
   │
3. ├── TaskiqJobSubmitter.submit()
   │   ├── Build BrokerMessage
   │   └── broker.kick(message)
   │
4. ├── RabbitMQ
   │   ├── Exchange: chat_tasks (direct)
   │   ├── Routing Key: chat.process
   │   └── Queue: chat.process
   │
5. ├── chat-worker
   │   ├── @broker.task("chat.process")
   │   ├── Deserialize JSON → kwargs
   │   └── ProcessChatCommand.execute()
   │
6. ├── LangGraph Pipeline
   │   └── Emit events to Redis Pub/Sub
   │
7. └── SSE Gateway → Client
```

---

## 11. Issues & Recommendations

### 11.1 Critical: CR vs Cluster 불일치

**문제:** Topology CR과 실제 RabbitMQ 큐 설정이 다름

**원인 추정:**
1. CR 적용 전 큐가 수동으로 생성됨
2. Topology Operator가 기존 리소스를 덮어쓰지 않음
3. Taskiq broker가 `declare_exchange=True`로 자동 생성

**해결 방안:**

```bash
# 1. 기존 큐/exchange 삭제 (메시지 없을 때)
kubectl exec -n rabbitmq eco2-rabbitmq-server-0 -- \
  rabbitmqctl delete_queue chat.process -p eco2
kubectl exec -n rabbitmq eco2-rabbitmq-server-0 -- \
  rabbitmqctl delete_exchange chat_tasks -p eco2

# 2. Topology CR reconcile 트리거
kubectl annotate queue.rabbitmq.com -n rabbitmq chat-process-queue \
  reconcile=$(date +%s) --overwrite

# 3. Worker/API 재시작으로 reconnect
kubectl rollout restart deploy/chat-api -n chat
kubectl rollout restart deploy/chat-worker -n chat
```

### 11.2 Minor: Message TTL vs Task Timeout

**현재 설정:**
- Queue TTL: 3,600,000ms (1시간)
- Task Timeout: 120s (2분)

**관계:**
- LLM 처리가 2분 이상 걸리면 task timeout
- 메시지가 1시간 동안 처리되지 않으면 DLQ로 이동

**권장:** 현재 설정 적절함 (LLM 스트리밍 고려)

### 11.3 Improvement: Circuit Breaker

**현재:** Redis Pub/Sub 실패 시 이벤트 손실 가능

**권장:** Event publishing에 circuit breaker 패턴 적용

---

## 12. Key Findings Summary

| Category | Status | Notes |
|----------|--------|-------|
| Producer-Consumer 일관성 | ✅ Good | 모든 설정값 일치 |
| Message Format | ✅ Good | TaskIQ 표준 준수 |
| Error Handling | ✅ Good | Exponential backoff + DLQ |
| Observability | ✅ Good | OpenTelemetry 통합 |
| **CR vs Cluster** | ⚠️ Issue | 수동 동기화 필요 |
| **TaskIQ vs CR** | ⚠️ Issue | TOPIC vs DIRECT exchange 충돌 |
| TTL 설정 | ✅ Good | LLM 워크로드 적합 |
| **Event Router** | ✅ Good | Lua Script idempotent 처리 |
| **SSE Gateway** | ✅ Good | Token v2 복구, Fan-out 패턴 |
| **실행/이벤트 분리** | ✅ Good | RabbitMQ(실행) / Redis(이벤트) |

---

## 13. File Reference

### 13.1 RabbitMQ (실행 경로)

| Purpose | File Path |
|---------|-----------|
| Producer Job Submitter | `apps/chat/infrastructure/messaging/job_submitter.py` |
| Producer Config | `apps/chat/setup/config.py` |
| Consumer Task | `apps/chat_worker/presentation/amqp/process_task.py` |
| Consumer Broker | `apps/chat_worker/setup/broker.py` |
| Consumer Config | `apps/chat_worker/setup/config.py` |
| Exchange CR | `workloads/rabbitmq/base/topology/exchanges.yaml` |
| Queue CR | `workloads/rabbitmq/base/topology/queues.yaml` |
| Binding CR | `workloads/rabbitmq/base/topology/bindings.yaml` |
| Retry Policy | `apps/chat_worker/infrastructure/error_handling/retry_policy.py` |
| DLQ Handler | `apps/chat_worker/infrastructure/error_handling/dlq_handler.py` |

### 13.2 Event Router (이벤트 경로)

| Purpose | File Path |
|---------|-----------|
| Main Entry | `apps/event_router/main.py` |
| Configuration | `apps/event_router/config.py` |
| Stream Consumer | `apps/event_router/core/consumer.py` |
| Event Processor | `apps/event_router/core/processor.py` |
| Failure Reclaimer | `apps/event_router/core/reclaimer.py` |
| Tracing | `apps/event_router/core/tracing.py` |
| Prometheus Metrics | `apps/event_router/metrics.py` |
| K8s Deployment | `workloads/domains/event-router/base/deployment.yaml` |

### 13.3 SSE Gateway (스트리밍)

| Purpose | File Path |
|---------|-----------|
| Main Entry | `apps/sse_gateway/main.py` |
| Configuration | `apps/sse_gateway/config.py` |
| SSE Endpoint | `apps/sse_gateway/api/v1/stream.py` |
| Broadcast Manager | `apps/sse_gateway/core/broadcast_manager.py` |
| Tracing | `apps/sse_gateway/core/tracing.py` |
| Prometheus Metrics | `apps/sse_gateway/metrics.py` |

---

## Appendix A: Topology CR 전체 구조

```
workloads/rabbitmq/base/topology/
├── exchanges.yaml
│   └── chat_tasks (direct, durable)
├── queues.yaml
│   ├── chat.process (classic, TTL 1h, DLX enabled)
│   └── dlq.chat.process (classic, TTL 7d)
├── bindings.yaml
│   ├── chat_tasks → chat.process (routing: chat.process)
│   └── dlx → dlq.chat.process (routing: dlq.chat.process)
└── kustomization.yaml
```

---

## Appendix B: Redis Keys Schema (Event Bus)

```
┌──────────────────────────────────────────────┐
│           Redis Keys Overview                │
├──────────────────────────────────────────────┤
│                                              │
│  [Streams Redis]                             │
│                                              │
│  이벤트 스트림 (Worker → Router)             │
│  ├── chat:events:0..3  # 4 Shards           │
│                                              │
│  토큰 스트림 (Token v2)                      │
│  └── chat:tokens:{job_id}  # TTL: 1h        │
│                                              │
│  상태 KV                                     │
│  └── chat:state:{job_id}   # TTL: 1h        │
│      ├── stage, status, seq                 │
│      ├── progress, result                   │
│                                              │
│  토큰 상태 (v2 복구용)                       │
│  └── chat:token_state:{job_id}  # TTL: 1h   │
│      ├── accumulated, last_seq              │
│                                              │
│  Idempotency 마커                            │
│  └── router:published:{job_id}:{seq}  #2h   │
│                                              │
│  DLQ (실패 메시지)                           │
│  └── chat:dlq  # MAXLEN: 10000              │
│                                              │
├──────────────────────────────────────────────┤
│                                              │
│  [Pub/Sub Redis]                             │
│                                              │
│  실시간 채널                                 │
│  └── sse:events:{job_id}                    │
│                                              │
└──────────────────────────────────────────────┘
```

### Key Naming Conventions

| Pattern | Example | 용도 |
|---------|---------|------|
| `{domain}:events:{shard}` | `chat:events:2` | Sharded 이벤트 스트림 |
| `{domain}:tokens:{job_id}` | `chat:tokens:abc-123` | Token 스트리밍 (v2) |
| `{domain}:state:{job_id}` | `chat:state:abc-123` | 최신 Job 상태 |
| `{domain}:token_state:{job_id}` | `chat:token_state:abc-123` | 누적 토큰 상태 |
| `router:published:{job_id}:{seq}` | `router:published:abc-123:50` | Idempotency |
| `sse:events:{job_id}` | `sse:events:abc-123` | Pub/Sub 채널 |
| `{domain}:dlq` | `chat:dlq` | Dead Letter Queue |

### TTL Policy

| Key Type | TTL | 근거 |
|----------|-----|------|
| State KV | 1시간 | LLM 처리 시간 + 여유 |
| Token State | 1시간 | 동일 |
| Token Stream | 1시간 | 동일 |
| Published Marker | 2시간 | State보다 길어야 idempotent |
| DLQ | 7일 | 장애 분석 기간 |

---

## Appendix C: Design Decision - "A안" 구현 평가

현재 Eco² 아키텍처는 **"실행은 DIRECT, 이벤트는 Redis"** 패턴을 구현합니다.

### 평가 매트릭스

| 기준 | 제안 모델 | Eco² 현재 | 평가 |
|------|----------|-----------|------|
| 실행 경로 | RabbitMQ DIRECT | RabbitMQ (TOPIC default) | ⚠️ DIRECT로 수정 필요 |
| 이벤트 저장 | Redis Stream | Redis Streams | ✅ 일치 |
| 실시간 전달 | Redis Pub/Sub | Redis Pub/Sub | ✅ 일치 |
| SSE 복구 | State + Catch-up | State + Catch-up | ✅ 일치 |
| Token 스트리밍 | - | Token v2 (Streams + State) | ✅ 확장 구현 |

### 결론

**Eco²는 이미 "A안" 패턴을 Redis 기반으로 완성**했습니다.
남은 작업은 RabbitMQ 실행 경로를 Topology CR(DIRECT)에 맞추는 것입니다.
