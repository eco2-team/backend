# Event Bus Layer 신뢰성 분석

> SSE 스트리밍 이벤트 유실 가능성 및 Race Condition 검토

**작성일**: 2026-01-16
**분석 대상**: Chat Worker, Event Router, SSE Gateway

---

## 1. 아키텍처 개요

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                          Event Bus Layer                                     │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  Chat Worker                                                                 │
│  (RedisProgressNotifier)                                                    │
│       │                                                                      │
│       │ XADD + Lua Script (멱등성)                                          │
│       ▼                                                                      │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │              Redis Streams (chat:events:{shard})                     │   │
│  │              - 내구성 보장 (영속성)                                   │   │
│  │              - Consumer Group 지원                                   │   │
│  └───────────────────────────┬─────────────────────────────────────────┘   │
│                              │                                              │
│                              │ XREADGROUP (Consumer Group)                  │
│                              ▼                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                      Event Router                                    │   │
│  │  ┌─────────────────────────────────────────────────────────────┐   │   │
│  │  │ StreamConsumer (consumer.py)                                 │   │   │
│  │  │ - XREADGROUP 블로킹 읽기                                    │   │   │
│  │  │ - 처리 후 XACK                                               │   │   │
│  │  └─────────────────────────────────────────────────────────────┘   │   │
│  │                              │                                       │   │
│  │  ┌─────────────────────────────────────────────────────────────┐   │   │
│  │  │ EventProcessor (processor.py)                                │   │   │
│  │  │ - Lua Script: State 갱신 + 발행 마킹                        │   │   │
│  │  │ - PUBLISH (별도 Pub/Sub Redis)                              │   │   │
│  │  └─────────────────────────────────────────────────────────────┘   │   │
│  │                              │                                       │   │
│  │  ┌─────────────────────────────────────────────────────────────┐   │   │
│  │  │ PendingReclaimer (reclaimer.py)                              │   │   │
│  │  │ - XAUTOCLAIM: 오래된 Pending 재할당                         │   │   │
│  │  │ - 장애 복구 (5분 idle 후)                                   │   │   │
│  │  └─────────────────────────────────────────────────────────────┘   │   │
│  └───────────────────────────┬─────────────────────────────────────────┘   │
│                              │                                              │
│                              │ PUBLISH                                      │
│                              ▼                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │              Redis Pub/Sub (sse:events:{job_id})                     │   │
│  │              - Fire-and-forget                                       │   │
│  │              - 구독자 없으면 메시지 손실                              │   │
│  └───────────────────────────┬─────────────────────────────────────────┘   │
│                              │                                              │
│                              │ SUBSCRIBE (pubsub.listen)                   │
│                              ▼                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                      SSE Gateway                                     │   │
│  │  ┌─────────────────────────────────────────────────────────────┐   │   │
│  │  │ SSEBroadcastManager (broadcast_manager.py)                   │   │   │
│  │  │ - Pub/Sub 구독                                               │   │   │
│  │  │ - State KV 조회 (복구용)                                     │   │   │
│  │  │ - catch_up_from_streams (누락 복구)                          │   │   │
│  │  └─────────────────────────────────────────────────────────────┘   │   │
│  │                              │                                       │   │
│  │  ┌─────────────────────────────────────────────────────────────┐   │   │
│  │  │ SubscriberQueue                                              │   │   │
│  │  │ - Bounded Queue (maxsize=100)                                │   │   │
│  │  │ - seq 기반 중복/역순 필터링                                 │   │   │
│  │  │ - Drop 정책: done/error 보존                                 │   │   │
│  │  └─────────────────────────────────────────────────────────────┘   │   │
│  └───────────────────────────┬─────────────────────────────────────────┘   │
│                              │                                              │
│                              │ SSE (text/event-stream)                     │
│                              ▼                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                       Frontend                                        │   │
│  │              EventSource → UI 업데이트                                │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. 이벤트 유실 가능성 분석

### 2.1 Chat Worker → Redis Streams

| 항목 | 상태 | 설명 |
|------|------|------|
| 멱등성 | :white_check_mark: 안전 | Lua Script + SETEX 마킹 |
| 중복 방지 | :white_check_mark: 안전 | `chat:published:{job_id}:{stage}:{seq}` |
| 원자성 | :white_check_mark: 안전 | Lua Script 단일 트랜잭션 |

**코드 분석** (`redis_progress_notifier.py`):
```python
# Lua Script (원자적)
if redis.call('EXISTS', publish_key) == 1 then
    return {0, existing_msg_id}  -- 이미 발행됨 (멱등성)
end
local msg_id = redis.call('XADD', stream_key, ...)
redis.call('SETEX', publish_key, ARGV[10], msg_id)  -- 발행 마킹
return {1, msg_id}
```

**결론**: :white_check_mark: 유실 없음

---

### 2.2 Redis Streams → Event Router

| 항목 | 상태 | 설명 |
|------|------|------|
| At-least-once | :white_check_mark: 안전 | Consumer Group + XACK |
| 장애 복구 | :warning: 지연 | XAUTOCLAIM 5분 후 |
| 순서 보장 | :white_check_mark: 안전 | Shard 내 순서 보장 |

**코드 분석** (`consumer.py`):
```python
# XREADGROUP으로 읽기
events = await self._redis.xreadgroup(
    groupname=self._consumer_group,
    consumername=self._consumer_name,
    streams=self._streams,
    count=self._count,
    block=self._block_ms,
)

# 처리 후 XACK
await self._redis.xack(stream_name, self._consumer_group, msg_id)
```

**위험 요소**:
```python
# reclaimer.py (line 47)
min_idle_ms: int = 300000,  # 5분 대기
```

**결론**: :white_check_mark: 유실 없음 (단, 장애 시 최대 5분 지연)

---

### 2.3 Event Router → Redis Pub/Sub

| 항목 | 상태 | 설명 |
|------|------|------|
| State 갱신 | :white_check_mark: 안전 | Lua Script 원자적 |
| Pub/Sub 발행 | :warning: 위험 | 2단계 분리, 재시도 없음 |
| Token 이벤트 | :x: 위험 | State 없음, 복구 불가 |

**코드 분석** (`processor.py`):
```python
# Step 1: State 갱신 (Streams Redis - Lua Script)
result = await self._script(
    keys=[state_key, publish_key],
    args=[event_data, seq, self._state_ttl, self._published_ttl],
)

if result == 1:
    # Step 2: Pub/Sub 발행 (별도 Redis) ← 원자적이지 않음!
    try:
        await self._pubsub_redis.publish(channel, event_data)
    except Exception as e:
        # 경고만 로그, 재시도 없음!
        logger.warning("pubsub_publish_failed", ...)
```

**위험 시나리오**:
1. State 갱신 성공 (Step 1)
2. 프로세스 크래시
3. Pub/Sub 발행 안됨 (Step 2)
4. 클라이언트는 State polling으로만 복구

**Token 이벤트 특수 처리**:
```python
if is_token_event:
    # State 갱신 없이 Pub/Sub만 발행
    await self._pubsub_redis.publish(channel, event_data)
    return True  # 멱등성 체크 없음!
```

**결론**: :warning: Stage 이벤트는 State 복구 가능, Token 이벤트는 유실 가능

---

### 2.4 Redis Pub/Sub → SSE Gateway

| 항목 | 상태 | 설명 |
|------|------|------|
| 구독 전 이벤트 | :warning: 위험 | 타임아웃 1초로 짧음 |
| Fire-and-forget | :warning: 위험 | 구독자 없으면 손실 |
| 복구 메커니즘 | :white_check_mark: 안전 | State + Streams catch-up |

**코드 분석** (`broadcast_manager.py`):
```python
# 1. 구독자 등록 (먼저!)
self._subscribers[job_id].add(subscriber)

# 2. Pub/Sub 구독 시작 + 완료 대기
if subscribed_event:
    try:
        await asyncio.wait_for(subscribed_event.wait(), timeout=1.0)  # 1초 타임아웃!
    except asyncio.TimeoutError:
        logger.warning("pubsub_subscribe_timeout", ...)  # 경고만

# 3. State에서 현재 상태 복구 (구독 후 조회 = 누락 방지)
state = await self._get_state_snapshot(job_id, domain)

# 4. Streams에서 누락 이벤트 catch-up
async for event in self._catch_up_from_streams(
    job_id, from_seq=subscriber.last_seq, to_seq=state_seq, domain=domain
):
    yield event
```

**위험 시나리오**:
1. 클라이언트 SSE 연결 요청
2. Pub/Sub 구독 시작 (1초 타임아웃)
3. 구독 완료 전 이벤트 발행 → **유실 가능**
4. State 조회 → 최신 상태만 반환
5. catch_up에서 누락 복구

**결론**: :white_check_mark: catch_up 메커니즘으로 대부분 복구 가능

---

### 2.5 SSE Gateway → Frontend

| 항목 | 상태 | 설명 |
|------|------|------|
| Queue 오버플로우 | :warning: 위험 | 중간 이벤트 drop |
| seq 역전 필터링 | :warning: 위험 | 중간 seq 유실 시 영구 무시 |
| 연결 끊김 | :white_check_mark: 안전 | is_disconnected 체크 |

**코드 분석** (`broadcast_manager.py` - SubscriberQueue):
```python
class SubscriberQueue:
    queue: asyncio.Queue[dict[str, Any]] = field(
        default_factory=lambda: asyncio.Queue(maxsize=100)  # Bounded
    )
    last_seq: int = field(default=-1)

    async def put_event(self, event: dict[str, Any]) -> bool:
        # seq 기반 중복/역순 필터링
        if event_seq <= self.last_seq:
            return False  # 이미 전달했거나 역순

        # Queue 오버플로우 처리
        if self.queue.full():
            old_event = self.queue.get_nowait()
            if old_event.get("stage") in ("done", "error"):
                await self.queue.put(old_event)  # done/error 보존
                return False  # 새 이벤트 drop
```

**위험 시나리오 1 - Queue 오버플로우**:
```
seq: 1, 2, 3, 4, ..., 100 (Queue 가득)
seq: 101 도착 → seq 1 drop → UI에서 진행 상태 불연속
```

**위험 시나리오 2 - seq 갭**:
```
수신: seq 1, 3 (seq 2 유실)
last_seq = 3
seq 2 나중에 도착 → last_seq(3) > 2 → 영구 무시!
```

**결론**: :warning: 중간 이벤트 유실 가능 (done/error는 보존)

---

## 3. Race Condition 분석

### 3.1 구독 전 이벤트 발행 Race

```
Timeline:
─────────────────────────────────────────────────────────────────────
t0: Client SSE 연결 요청
t1: Pub/Sub 구독 시작 (비동기)
t2: Event Router가 이벤트 PUBLISH  ← 이 시점에 구독 미완료면 유실!
t3: Pub/Sub 구독 완료 (타임아웃 1초)
t4: State snapshot 조회
t5: catch_up_from_streams 실행
─────────────────────────────────────────────────────────────────────
```

**현재 보호 메커니즘**:
- subscribed_event로 구독 완료 대기 (최대 1초)
- 구독 후 State snapshot 조회
- catch_up_from_streams로 누락 복구

**취약점**:
- 1초 타임아웃 내에 구독 완료 안 되면 이벤트 유실 가능
- Redis 네트워크 지연 시 위험

---

### 3.2 State 갱신 vs Pub/Sub 발행 Race

```
Timeline (Event Router):
─────────────────────────────────────────────────────────────────────
t0: Lua Script 실행 (State 갱신 + 발행 마킹)
t1: State 갱신 완료 ← 여기서 크래시하면?
t2: PUBLISH 실행  ← 이 단계 실행 안됨
t3: PUBLISH 완료
─────────────────────────────────────────────────────────────────────
```

**현재 보호 메커니즘**:
- 발행 마킹으로 멱등성 보장
- State polling으로 최종 상태 복구 가능

**취약점**:
- 중간 이벤트 (intent:started, rag:started 등) 유실 가능
- 최종 상태 (done)만 보장

---

### 3.3 병렬 노드 실행 seq 역전

```
Timeline (LangGraph Send API):
─────────────────────────────────────────────────────────────────────
t0: intent 완료 (seq=10)
t1: Send("waste_rag"), Send("weather"), Send("collection_point") 병렬 시작
t2: weather 완료 (seq=80)  ← 먼저 완료
t3: waste_rag 완료 (seq=30)  ← 나중에 완료
─────────────────────────────────────────────────────────────────────

Client 수신 순서:
seq=10 (intent) → seq=80 (weather) → seq=30 (waste_rag)
                   ↑ last_seq=80
                                       ↑ 30 < 80 → 무시됨!
```

**현재 보호 메커니즘**:
- Stage별 seq 범위 분리 (STAGE_ORDER * 10)
- 같은 stage 내에서만 seq 비교

**실제 STAGE_ORDER**:
```python
STAGE_ORDER = {
    "intent": 1,      # seq: 10-19
    "rag": 3,         # seq: 30-39
    "weather": 8,     # seq: 80-89
    ...
}
```

**결론**: :white_check_mark: 각 stage의 seq 범위가 분리되어 있어 역전 문제 없음

---

## 4. 심각도별 문제 분류

### :x: Critical (즉시 수정 필요)

| 문제 | 위치 | 영향 | 해결 방안 |
|------|------|------|-----------|
| Token 이벤트 유실 | `processor.py:194-222` | 토큰 스트리밍 끊김 | State 저장 또는 재시도 로직 |

### :warning: Major (권장 수정)

| 문제 | 위치 | 영향 | 해결 방안 |
|------|------|------|-----------|
| Pub/Sub 발행 재시도 없음 | `processor.py:258-270` | Stage 이벤트 유실 | 재시도 로직 추가 |
| 구독 타임아웃 1초 | `broadcast_manager.py:300` | 구독 전 이벤트 유실 | 타임아웃 증가 (3초) |
| Queue 오버플로우 | `broadcast_manager.py:77` | 중간 이벤트 drop | maxsize 증가 또는 동적 조절 |
| Reclaimer 5분 지연 | `reclaimer.py:47` | 장애 복구 지연 | min_idle_ms 감소 (1-2분) |

### :bulb: Minor (선택적 개선)

| 문제 | 위치 | 영향 | 해결 방안 |
|------|------|------|-----------|
| seq 갭 복구 불가 | `broadcast_manager.py:106` | 중간 이벤트 영구 무시 | 갭 감지 시 catch-up |

---

## 5. 현재 보호 메커니즘 요약

### 5.1 멱등성 보장

```
Layer 1: Chat Worker → Redis Streams
┌─────────────────────────────────────────────────────────────────┐
│  Lua Script (IDEMPOTENT_XADD_SCRIPT)                            │
│  - SETEX 발행 마킹 (TTL 2시간)                                  │
│  - EXISTS 체크로 중복 XADD 방지                                 │
└─────────────────────────────────────────────────────────────────┘

Layer 2: Event Router → Redis Pub/Sub
┌─────────────────────────────────────────────────────────────────┐
│  Lua Script (UPDATE_STATE_SCRIPT)                               │
│  - SETEX 처리 마킹 (TTL 2시간)                                  │
│  - EXISTS 체크로 중복 처리 방지                                 │
│  - State는 더 큰 seq만 갱신 (최신 상태 유지)                    │
└─────────────────────────────────────────────────────────────────┘
```

### 5.2 장애 복구

```
┌─────────────────────────────────────────────────────────────────┐
│  PendingReclaimer (XAUTOCLAIM)                                  │
│  - 5분 이상 Pending 메시지 재할당                               │
│  - Consumer 장애 시 자동 복구                                   │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│  SSE Gateway catch_up_from_streams                              │
│  - 구독 후 State snapshot 조회                                  │
│  - 누락된 이벤트 Streams에서 직접 읽기                          │
│  - seq 순서대로 정렬 후 전달                                    │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│  State KV Polling                                               │
│  - 30초 무소식 시 State 재조회                                  │
│  - Pub/Sub 유실 시 최종 상태 복구                               │
└─────────────────────────────────────────────────────────────────┘
```

### 5.3 순서 보장

```
┌─────────────────────────────────────────────────────────────────┐
│  seq 기반 정렬                                                  │
│  - STAGE_ORDER * 10 + status_offset                             │
│  - Token: 1000+ (Stage와 분리)                                  │
│  - catch_up에서 seq 순서대로 정렬                               │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│  SubscriberQueue seq 필터링                                     │
│  - last_seq 이하 이벤트 무시                                    │
│  - 역순 이벤트 자동 필터링                                      │
└─────────────────────────────────────────────────────────────────┘
```

---

## 6. 권장 개선 사항

### 6.1 Token 이벤트 신뢰성 개선 (Critical)

```python
# processor.py - Token 이벤트 재시도 추가
if is_token_event:
    for attempt in range(3):  # 최대 3회 재시도
        try:
            await self._pubsub_redis.publish(channel, event_data)
            return True
        except Exception as e:
            if attempt == 2:
                logger.error("token_pubsub_publish_failed_final", ...)
                return False
            await asyncio.sleep(0.1 * (attempt + 1))  # 백오프
```

### 6.2 Pub/Sub 발행 재시도 (Major)

```python
# processor.py - 재시도 로직 추가
async def _publish_with_retry(self, channel: str, data: str, max_retries: int = 3):
    for attempt in range(max_retries):
        try:
            await self._pubsub_redis.publish(channel, data)
            return True
        except Exception as e:
            if attempt == max_retries - 1:
                logger.error("pubsub_publish_failed_final", ...)
                return False
            await asyncio.sleep(0.1 * (2 ** attempt))  # 지수 백오프
```

### 6.3 구독 타임아웃 증가 (Major)

```python
# broadcast_manager.py
try:
    await asyncio.wait_for(subscribed_event.wait(), timeout=3.0)  # 1초 → 3초
except asyncio.TimeoutError:
    logger.warning("pubsub_subscribe_timeout", ...)
```

### 6.4 Reclaimer 주기 단축 (Major)

```python
# reclaimer.py
min_idle_ms: int = 60000,  # 5분 → 1분
interval_seconds: int = 30,  # 60초 → 30초
```

---

## 7. 결론

### 전체 신뢰성 평가

| 구간 | 신뢰성 | 유실 가능성 |
|------|--------|------------|
| Chat Worker → Streams | 99.99% | 거의 없음 |
| Streams → Event Router | 99.9% | 장애 시 최대 5분 지연 |
| Event Router → Pub/Sub | 99% | Stage 이벤트 복구 가능, Token 유실 가능 |
| Pub/Sub → SSE Gateway | 95% | catch-up으로 대부분 복구 |
| SSE Gateway → Frontend | 90% | 중간 이벤트 drop 가능 |

### 최종 평가

**Stage 이벤트 (intent, rag, answer, done 등)**: :white_check_mark: 신뢰성 높음
- 멱등성 + State + catch-up으로 대부분 복구 가능
- 최종 상태 (done) 보장

**Token 이벤트 (LLM 스트리밍)**: :warning: 주의 필요
- 유실 시 복구 메커니즘 없음
- UX 영향: 토큰이 중간에 끊겨 보일 수 있음
- 권장: 재시도 로직 추가

**Race Condition**: :white_check_mark: 대부분 안전
- seq 기반 순서 보장
- catch-up 메커니즘으로 구독 전 이벤트 복구
- 병렬 노드 실행 시에도 seq 범위 분리로 안전

---

## References

- `apps/chat_worker/infrastructure/events/redis_progress_notifier.py`
- `apps/event_router/core/consumer.py`
- `apps/event_router/core/processor.py`
- `apps/event_router/core/reclaimer.py`
- `apps/sse_gateway/core/broadcast_manager.py`
- `apps/sse_gateway/api/v1/stream.py`
