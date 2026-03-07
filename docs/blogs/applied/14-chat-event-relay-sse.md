# 이코에코(Eco²) Agent #4: Event Relay & SSE 아키텍처

> Chat Worker에서 발행한 이벤트가 클라이언트까지 도달하는 Event Relay 계층 설계

[Agent #3](https://rooftopsnow.tistory.com/167)에서 Taskiq 기반 비동기 큐잉을 다뤘습니다. 이번 포스팅에서는 Chat Worker가 발행한 이벤트가 클라이언트의 SSE 연결까지 전달되는 **Event Relay 계층**을 설계합니다.

---

## 문제: Chat Worker와 클라이언트 사이의 간극

```
Chat Worker                              Client
     │                                      │
     │ Redis Streams (XADD)                 │
     │ chat:events:{job_id}                 │
     ▼                                      │
   [???]  ─────────────────────────────▶  SSE
                 어떻게 연결?
```

Chat Worker는 Redis Streams에 이벤트를 발행합니다. 하지만 클라이언트는 HTTP SSE로 연결됩니다.
이 간극을 메우는 것이 **Event Relay 계층**입니다.

---

## Scan의 Event Relay 패턴

Scan 서비스는 이미 이 문제를 해결했습니다:

```
┌─────────────────────────────────────────────────────────────┐
│              Scan Event Relay 아키텍처                       │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  [Scan Worker]                                              │
│       │                                                     │
│       │ XADD                                                │
│       ▼                                                     │
│  ┌─────────────────┐                                        │
│  │ Redis Streams   │  scan:events:{shard}                   │
│  │ (내구성 저장소)  │  - 샤딩으로 병렬 처리                   │
│  │                 │  - Consumer Group으로 분산 소비         │
│  └────────┬────────┘                                        │
│           │                                                 │
│           │ XREADGROUP (Consumer Group)                     │
│           ▼                                                 │
│  ┌─────────────────┐                                        │
│  │ Event Router    │  - State KV 갱신                       │
│  │ (릴레이 서비스)  │  - 멱등성 보장 (Lua Script)            │
│  │                 │  - Pub/Sub 발행                        │
│  └────────┬────────┘                                        │
│           │                                                 │
│           │ PUBLISH                                         │
│           ▼                                                 │
│  ┌─────────────────┐                                        │
│  │ Redis Pub/Sub   │  sse:events:{job_id}                   │
│  │ (실시간 전달)    │  - 구독자에게 즉시 전달                 │
│  │                 │  - 저장 안함 (휘발성)                   │
│  └────────┬────────┘                                        │
│           │                                                 │
│           │ SUBSCRIBE                                       │
│           ▼                                                 │
│  ┌─────────────────┐                                        │
│  │ Scan API        │  SSE Gateway                           │
│  │ SSE Gateway     │  - Pub/Sub 구독                        │
│  │                 │  - StreamingResponse                   │
│  └────────┬────────┘                                        │
│           │                                                 │
│           │ HTTP SSE                                        │
│           ▼                                                 │
│  [Client]                                                   │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### 핵심 컴포넌트

| 컴포넌트 | 역할 | Redis 타입 |
|---------|------|-----------|
| **Redis Streams** | 이벤트 영속 저장, 순서 보장 | XADD/XREAD |
| **Event Router** | Streams → Pub/Sub 릴레이 | Consumer |
| **Redis Pub/Sub** | 실시간 브로드캐스트 | PUBLISH/SUBSCRIBE |
| **SSE Gateway** | Pub/Sub → HTTP SSE | Subscriber |

### 왜 이렇게 복잡한가?

**Streams만 쓰면 안 되나요?**

```
문제: Streams는 Pull 모델
─────────────────────────────

XREAD BLOCK 5000 ...  (5초 대기)
  → 메시지 없음
XREAD BLOCK 5000 ...  (5초 대기)
  → 메시지 도착!

지연 발생 + 폴링 오버헤드
```

**Pub/Sub만 쓰면 안 되나요?**

```
문제: Pub/Sub는 휘발성
─────────────────────────────

Client A 구독 중
  ← 이벤트 1 수신 ✓
  ← 이벤트 2 수신 ✓

Client A 재연결...
  ← 이벤트 3 손실! ✗

네트워크 끊기면 이벤트 유실
```

**해결: 둘의 장점 결합**

```
Streams (내구성) + Pub/Sub (실시간) = Event Relay

- Streams: 이벤트 영속 저장 → 재시도, 복구 가능
- Pub/Sub: 실시간 푸시 → 지연 없음
- State KV: 현재 상태 저장 → 재연결 시 복구
```

---

## Chat에 적용: event_router 확장

### 현재 문제

```python
# apps/event_router/config.py (현재)
class Settings(BaseSettings):
    stream_prefix: str = "scan:events"  # ❌ scan만 처리
```

event_router는 `scan:events`만 구독합니다. Chat Worker의 `chat:events`는 무시됩니다.

### 해결: 멀티 스트림 지원

```python
# apps/event_router/config.py (변경)
class Settings(BaseSettings):
    # 단일 → 멀티 스트림
    stream_prefixes: list[str] = ["scan:events", "chat:events"]
    
    # Shard 설정 (도메인별 독립)
    shard_counts: dict[str, int] = {
        "scan:events": 4,
        "chat:events": 2,  # Chat은 상대적으로 적은 트래픽
    }
```

### Consumer 수정

```python
# apps/event_router/core/consumer.py (변경)

class MultiStreamConsumer:
    """멀티 스트림 Consumer."""
    
    def __init__(self, settings: Settings):
        self._settings = settings
        self._streams = self._build_stream_keys()
    
    def _build_stream_keys(self) -> list[str]:
        """도메인별 샤드 키 생성."""
        keys = []
        for prefix in self._settings.stream_prefixes:
            shard_count = self._settings.shard_counts.get(prefix, 4)
            for i in range(shard_count):
                keys.append(f"{prefix}:{i}")
        return keys
        # ["scan:events:0", ..., "scan:events:3",
        #  "chat:events:0", "chat:events:1"]
    
    async def consume(self):
        """모든 스트림에서 이벤트 소비."""
        while True:
            events = await self._redis.xreadgroup(
                groupname=self._settings.consumer_group,
                consumername=self._settings.consumer_name,
                streams={key: ">" for key in self._streams},
                count=self._settings.xread_count,
                block=self._settings.xread_block_ms,
            )
            for stream_key, messages in events:
                for msg_id, data in messages:
                    await self._processor.process_event(data)
                    await self._redis.xack(
                        stream_key,
                        self._settings.consumer_group,
                        msg_id,
                    )
```

---

## Chat API SSE Gateway

### 엔드포인트 구현

```python
# apps/chat/presentation/http/controllers/sse.py

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from redis.asyncio import Redis

router = APIRouter()


@router.get("/chat/{job_id}/events")
async def chat_events(job_id: str):
    """채팅 진행 상황 SSE 스트리밍."""
    return StreamingResponse(
        event_generator(job_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # nginx 버퍼링 비활성화
        },
    )


async def event_generator(job_id: str):
    """SSE 이벤트 생성기."""
    redis = await get_pubsub_redis()
    pubsub = redis.pubsub()
    channel = f"sse:events:{job_id}"
    
    await pubsub.subscribe(channel)
    
    try:
        # 1. 현재 상태 먼저 전송 (재연결 복구)
        state = await get_current_state(job_id)
        if state:
            yield format_sse_event("state", state)
        
        # 2. 실시간 이벤트 스트리밍
        async for message in pubsub.listen():
            if message["type"] == "message":
                data = message["data"]
                event = json.loads(data)
                
                # 이벤트 타입별 처리
                event_type = event.get("event_type", "stage")
                
                if event_type == "token":
                    # 토큰 스트리밍 (LLM 응답)
                    yield format_sse_event("token", event)
                elif event_type == "stage":
                    # 단계 진행 상황
                    yield format_sse_event("stage", event)
                    
                    # 완료 시 종료
                    if event.get("stage") == "done":
                        yield format_sse_event("done", event)
                        break
                        
    finally:
        await pubsub.unsubscribe(channel)
        await pubsub.close()


def format_sse_event(event_type: str, data: dict) -> str:
    """SSE 포맷으로 변환."""
    return f"event: {event_type}\ndata: {json.dumps(data)}\n\n"
```

### State KV로 재연결 복구

```python
async def get_current_state(job_id: str) -> dict | None:
    """현재 상태 조회 (재연결 시 복구용)."""
    redis = await get_streams_redis()
    state_key = f"chat:state:{job_id}"
    
    state = await redis.get(state_key)
    if state:
        return json.loads(state)
    return None
```

클라이언트가 재연결하면 State KV에서 현재 상태를 가져와 즉시 전송합니다.
이후 Pub/Sub로 실시간 이벤트를 수신합니다.

---

## LangGraph Checkpointing

### Scan vs Chat 체크포인팅 비교

[Clean Architecture #14](https://rooftopsnow.tistory.com/144)에서 Scan은 **Stateless Reducer Pattern**으로 체크포인팅을 직접 구현했습니다. Chat은 **Cache-Aside 패턴**을 활용합니다.

| 항목 | Scan (직접 구현) | Chat (Cache-Aside) |
|------|----------------|------------------|
| **패턴** | Stateless Reducer + CheckpointingStepRunner | **Cache-Aside Checkpointer** |
| **L1 캐시** | Redis SETEX 직접 호출 | Redis (TTL 24시간) |
| **L2 저장소** | - | **PostgreSQL (영구)** |
| **복구 단위** | Step 단위 (Vision → Rule → Answer) | 노드 단위 (intent → rag → answer) |
| **세션 유지** | 단일 요청 (TTL 1시간) | **멀티턴 대화 (영구 저장)** |
| **Hot session** | N/A | Redis ~1ms |
| **Cold session** | N/A | PostgreSQL ~5-10ms → 캐싱 |

### Cache-Aside 패턴

```
┌─────────────────────────────────────────────────────────────┐
│              Cache-Aside Checkpointer                        │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  조회 (get)                                                  │
│  ─────────                                                  │
│  Client → Redis (L1, ~1ms)                                  │
│              │                                              │
│              ├── Hit → Return (빠름)                        │
│              │                                              │
│              └── Miss → PostgreSQL (L2, ~5-10ms)            │
│                              │                              │
│                              └── Redis에 캐싱 (warm-up)     │
│                                                             │
│  저장 (put)                                                  │
│  ─────────                                                  │
│  Client → PostgreSQL (영구) + Redis (캐시)                   │
│           Write-Through                                     │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

| 시나리오 | 응답 시간 | 설명 |
|----------|----------|------|
| **Hot session** (최근 대화) | ~1ms | Redis 캐시 히트 |
| **Cold session** (오래된 대화) | ~5-10ms | PostgreSQL 조회 → 캐싱 |
| **장기 보존** | 영구 | PostgreSQL에 저장 |

### 체크포인터 구현

```python
# apps/chat_worker/infrastructure/langgraph/checkpointer.py

class CachedPostgresSaver:
    """Cache-Aside 패턴 Checkpointer.
    
    L1: Redis (빠름, TTL 24시간)
    L2: PostgreSQL (영구)
    """
    
    def __init__(self, postgres_saver, redis, cache_ttl=86400):
        self._postgres = postgres_saver
        self._redis = redis
        self._ttl = cache_ttl
    
    async def aget_tuple(self, config):
        thread_id = config["configurable"]["thread_id"]
        cache_key = f"chat:checkpoint:cache:{thread_id}"
        
        # L1: Redis 캐시 조회
        cached = await self._redis.get(cache_key)
        if cached:
            logger.debug("checkpoint_cache_hit")
        
        # L2: PostgreSQL 조회
        result = await self._postgres.aget_tuple(config)
        
        if result:
            # Warm-up: Redis에 캐싱
            await self._redis.setex(cache_key, self._ttl, ...)
        
        return result
```

### Factory 수정

```python
# apps/chat_worker/infrastructure/langgraph/factory.py

from langgraph.checkpoint.base import BaseCheckpointSaver


def create_chat_graph(
    llm: LLMPort,
    retriever: RetrieverPort,
    event_publisher: EventPublisherPort,
    character_client: CharacterClientPort | None = None,
    location_client: LocationClientPort | None = None,
    checkpointer: BaseCheckpointSaver | None = None,  # 🆕 추가
) -> CompiledGraph:
    """Chat 파이프라인 그래프 생성."""
    
    graph = StateGraph(dict)
    
    # ... 노드 추가 ...
    
    # 체크포인터 연결 🆕
    return graph.compile(checkpointer=checkpointer)
```

### Command 수정: thread_id로 세션 연결

```python
# apps/chat_worker/application/chat/commands/process_chat.py

class ProcessChatCommand:
    async def execute(self, request: ProcessChatRequest):
        # 🆕 세션 ID → thread_id로 체크포인트 연결
        config = {
            "configurable": {
                "thread_id": request.session_id,  # 멀티턴 대화 연결
            }
        }
        
        initial_state = {
            "job_id": request.job_id,
            "session_id": request.session_id,
            "message": request.message,
            # ...
        }
        
        # 🆕 config 전달 → 이전 대화 컨텍스트 자동 로드
        result = await self._pipeline.ainvoke(initial_state, config=config)
        
        # 자동으로 체크포인트 저장됨
        return result
```

### PostgreSQL 스키마 (LangGraph 자동 생성)

```sql
-- LangGraph가 자동 생성하는 테이블
CREATE TABLE checkpoints (
    thread_id TEXT NOT NULL,
    checkpoint_id TEXT NOT NULL,
    parent_id TEXT,
    checkpoint JSONB NOT NULL,
    metadata JSONB,
    created_at TIMESTAMP DEFAULT NOW(),
    PRIMARY KEY (thread_id, checkpoint_id)
);

CREATE INDEX idx_checkpoints_thread ON checkpoints(thread_id);
CREATE INDEX idx_checkpoints_created ON checkpoints(created_at);
```

### Dependencies 수정

```python
# apps/chat_worker/setup/dependencies.py

from chat_worker.infrastructure.langgraph.checkpointer import (
    create_cached_postgres_checkpointer,
)

_checkpointer = None


async def get_checkpointer():
    """Cache-Aside 체크포인터 싱글톤.
    
    L1: Redis (빠름, TTL 24시간) - Hot session
    L2: PostgreSQL (영구) - Cold session, 장기 보존
    """
    global _checkpointer
    if _checkpointer is None:
        settings = get_settings()
        redis = await get_redis()
        
        _checkpointer = await create_cached_postgres_checkpointer(
            conn_string=settings.postgres_url,
            redis=redis,
            cache_ttl=86400,  # 24시간
        )
    return _checkpointer


async def get_chat_graph(...):
    # ...
    checkpointer = await get_checkpointer()  # 🆕
    
    return create_chat_graph(
        llm=llm,
        retriever=retriever,
        event_publisher=event_publisher,
        character_client=character_client,
        location_client=location_client,
        checkpointer=checkpointer,  # 🆕
    )
```

### Config 수정

```python
# apps/chat_worker/setup/config.py

class Settings(BaseSettings):
    # 기존 설정...
    
    # 🆕 PostgreSQL (체크포인팅)
    postgres_url: str = "postgresql://localhost:5432/eco2"
```

---

## 전체 플로우

```
┌─────────────────────────────────────────────────────────────┐
│              Chat Event Relay 전체 플로우                    │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  [Client]                                                   │
│      │                                                      │
│      │ 1. POST /chat                                        │
│      │    {session_id, message}                             │
│      ▼                                                      │
│  ┌─────────────────┐                                        │
│  │ Chat API        │                                        │
│  │                 │──▶ 2. Taskiq 발행 (RabbitMQ)           │
│  │                 │      job_id 생성                       │
│  └────────┬────────┘                                        │
│           │                                                 │
│           │ Response: {job_id, stream_url}                  │
│           │                                                 │
│  [Client] ◀────────────────────────────────────────────────│
│      │                                                      │
│      │ 3. GET /chat/{job_id}/events (SSE)                   │
│      ▼                                                      │
│  ┌─────────────────┐                                        │
│  │ Chat API        │                                        │
│  │ SSE Gateway     │◀─┐                                     │
│  └────────┬────────┘  │                                     │
│           │           │ 8. SUBSCRIBE                        │
│           │           │    sse:events:{job_id}              │
│           │           │                                     │
│  [RabbitMQ]           │                                     │
│      │                │                                     │
│      │ 4. Consume     │                                     │
│      ▼                │                                     │
│  ┌─────────────────┐  │                                     │
│  │ Chat Worker     │  │                                     │
│  │                 │  │                                     │
│  │ ┌─────────────┐ │  │                                     │
│  │ │ LangGraph   │ │  │                                     │
│  │ │ Pipeline    │ │  │                                     │
│  │ └──────┬──────┘ │  │                                     │
│  │        │        │  │                                     │
│  │ 5. XADD│        │  │                                     │
│  │   chat:events   │  │                                     │
│  └────────┬────────┘  │                                     │
│           │           │                                     │
│           ▼           │                                     │
│  ┌─────────────────┐  │                                     │
│  │ Redis Streams   │  │                                     │
│  │ chat:events:*   │  │                                     │
│  └────────┬────────┘  │                                     │
│           │           │                                     │
│           │ 6. XREADGROUP                                   │
│           ▼           │                                     │
│  ┌─────────────────┐  │                                     │
│  │ Event Router    │  │                                     │
│  │ (확장)          │  │                                     │
│  │                 │──┼──▶ 7. PUBLISH                       │
│  └─────────────────┘  │       sse:events:{job_id}           │
│                       │                                     │
│                       │                                     │
│  ┌────────────────────┘                                     │
│  │                                                          │
│  │ 9. SSE 이벤트 스트리밍                                    │
│  ▼                                                          │
│  [Client]                                                   │
│  ├── event: stage                                           │
│  │   data: {"stage": "intent", "message": "의도 분류 중"}   │
│  │                                                          │
│  ├── event: stage                                           │
│  │   data: {"stage": "rag", "message": "규정 검색 중"}      │
│  │                                                          │
│  ├── event: token                                           │
│  │   data: {"content": "페"}                                │
│  │                                                          │
│  ├── event: token                                           │
│  │   data: {"content": "트병은"}                            │
│  │                                                          │
│  └── event: done                                            │
│      data: {"stage": "done", "status": "completed"}         │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## Scan vs Chat 전체 비교

### 체크포인팅 패턴

| 항목 | Scan | Chat |
|------|------|------|
| **패턴** | Stateless Reducer (직접 구현) | **Cache-Aside Checkpointer** |
| **L1 캐시** | Redis (TTL 1시간) | Redis (TTL 24시간) |
| **L2 저장소** | - | **PostgreSQL (영구)** |
| **복구 단위** | Step 단위 | 노드 단위 |
| **세션 유지** | 단일 요청 | **멀티턴 대화** |
| **Hot session** | N/A | Redis ~1ms |
| **Cold session** | N/A | PostgreSQL ~5-10ms → 캐싱 |
| **비용 절감** | LLM 재호출 방지 | LLM 재호출 방지 + 히스토리 검색 |

### Event Relay

| 항목 | Scan | Chat |
|------|------|------|
| **Stream Prefix** | `scan:events` | `chat:events` |
| **Shard 수** | 4 | 2 (상대적 저트래픽) |
| **이벤트 타입** | `stage` only | `stage` + `token` |
| **State KV 용도** | 진행 상황 복구 | 진행 상황 복구 |
| **Checkpointing 용도** | 파이프라인 중단 복구 | **대화 히스토리 영구 저장** |

### 저장소 역할 분리

```
┌─────────────────────────────────────────────────────────────┐
│              Chat 저장소 아키텍처 (Cache-Aside)              │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  [L1 캐시 - Redis]                                          │
│  ├── 체크포인트 캐시 (Cache-Aside)  TTL: 24시간 🆕          │
│  ├── SSE 이벤트 (Streams)          TTL: 2시간               │
│  ├── 진행 상태 (State KV)           TTL: 1시간              │
│  └── 멱등성 마커                     TTL: 2시간             │
│                                                             │
│  [L2 영구 저장 - PostgreSQL]                                │
│  ├── 대화 히스토리 (checkpoints)  영구 저장 🆕               │
│  ├── 사용자 세션 메타데이터        영구 저장                  │
│  └── 토큰 사용량 통계             영구 저장                  │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## 구현 완료 ✅

### Event Relay 계층

| 작업 | 파일 | 상태 |
|------|------|------|
| event_router 확장 | `apps/event_router/config.py` | ✅ `stream_prefixes` 멀티 스트림 |
| Consumer 수정 | `apps/event_router/core/consumer.py` | ✅ 멀티 스트림 구독 |
| Processor 수정 | `apps/event_router/core/processor.py` | ✅ 도메인별 state prefix |
| SSE Gateway | `apps/chat/presentation/http/sse.py` | ✅ Pub/Sub 구독, SSE 스트리밍 |

### LangGraph Checkpointing (Cache-Aside)

| 작업 | 파일 | 상태 |
|------|------|------|
| CachedPostgresSaver | `apps/chat_worker/infrastructure/langgraph/checkpointer.py` | ✅ Cache-Aside 패턴 |
| Factory 수정 | `apps/chat_worker/infrastructure/langgraph/factory.py` | ✅ `checkpointer` 파라미터 |
| Command 수정 | `apps/chat_worker/application/chat/commands/process_chat.py` | ✅ `thread_id` config |
| Dependencies | `apps/chat_worker/setup/dependencies.py` | ✅ `get_checkpointer()` |
| Config | `apps/chat_worker/setup/config.py` | ✅ `postgres_url` |

### 구현 후 코드

```python
# ✅ Cache-Aside 체크포인터
class CachedPostgresSaver:
    async def aget_tuple(self, config):
        # L1: Redis 캐시 조회 (~1ms)
        # L2: PostgreSQL 조회 (~5-10ms) → 캐싱
        ...

# ✅ thread_id로 멀티턴 대화 연결
config = {"configurable": {"thread_id": request.session_id}}
result = await self._pipeline.ainvoke(initial_state, config=config)
```

---

## 결론

Chat 서비스의 Event Relay 계층은 **기존 Scan 인프라를 확장**하여 구현합니다:

### Event Relay

1. **event_router 확장**: `chat:events` 스트림 추가 구독
2. **동일한 릴레이 패턴**: Streams → Event Router → Pub/Sub → SSE Gateway
3. **운영 통합**: 새 서비스 없이 기존 컴포넌트 확장

### Checkpointing: Scan vs Chat

| 서비스 | 패턴 | L1 캐시 | L2 저장소 | 이유 |
|--------|------|---------|----------|------|
| **Scan** | Stateless Reducer | Redis (TTL 1시간) | - | 단일 요청, 파이프라인 복구 |
| **Chat** | **Cache-Aside** | Redis (TTL 24시간) | **PostgreSQL** | 멀티턴 대화, 장기 세션 |

[Clean Architecture #14](https://rooftopsnow.tistory.com/144)에서 Scan은 **Stateless Reducer Pattern**으로 체크포인팅을 직접 구현했습니다. Chat은 **Cache-Aside 패턴**으로 Hot/Cold session을 효율적으로 처리합니다.

### 핵심 차이

```
Scan: 단일 요청 파이프라인 → Redis (휘발성 OK)
Chat: 멀티턴 대화 세션 → Redis L1 + PostgreSQL L2 (Cache-Aside)
      - Hot session: Redis ~1ms
      - Cold session: PostgreSQL ~5-10ms → 캐싱
```

다음 포스팅 [Agent #5: Checkpointer & State](15-chat-checkpointer-state.md)에서 Cache-Aside 구현 상세를 다룹니다.

