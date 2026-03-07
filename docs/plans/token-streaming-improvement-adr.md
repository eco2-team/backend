# Token Streaming 개선 ADR

> Resumable LLM Streams 패턴 적용

**작성일**: 2026-01-16
**상태**: Draft

---

## 1. 문제 정의

### 현재 아키텍처

```
┌─────────────────────────────────────────────────────────────────┐
│                  현재 Token 스트리밍 흐름                        │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  Answer Node                                                     │
│       │                                                          │
│       │ notify_token(content)                                   │
│       ▼                                                          │
│  RedisProgressNotifier                                           │
│       │                                                          │
│       │ TOKEN_XADD_SCRIPT (Redis Streams)                       │
│       │ - chat:events:{shard}에 저장                            │
│       │ - 멱등성 없음                                            │
│       ▼                                                          │
│  Redis Streams (chat:events:{shard})                            │
│       │                                                          │
│       │ XREADGROUP                                               │
│       ▼                                                          │
│  Event Router (processor.py)                                     │
│       │                                                          │
│       │ is_token_event → State 저장 SKIP!                       │
│       │ PUBLISH only (fire-and-forget)                          │
│       ▼                                                          │
│  Redis Pub/Sub (sse:events:{job_id})                            │
│       │                                                          │
│       │ 구독자 없으면 유실!                                      │
│       ▼                                                          │
│  SSE Gateway                                                     │
│       │                                                          │
│       │ 복구 메커니즘 없음                                       │
│       ▼                                                          │
│  Frontend                                                        │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### 문제점

| 문제 | 영향 | 심각도 |
|------|------|--------|
| Token State 미저장 | 재연결 시 복구 불가 | Critical |
| Pub/Sub fire-and-forget | 구독자 없으면 유실 | Critical |
| 재시도 로직 없음 | 네트워크 오류 시 유실 | Major |
| 멱등성 없음 | 중복 처리 가능 | Minor |

---

## 2. OpenCode 토큰 스트리밍 분석

### 2.1 OpenCode 아키텍처

```
┌─────────────────────────────────────────────────────────────────┐
│                 OpenCode Token Streaming                         │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  LLM Provider (Claude/OpenAI)                                    │
│       │                                                          │
│       │ text-delta, reasoning-delta                              │
│       ▼                                                          │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │ Session.updatePart()                                     │    │
│  │                                                          │    │
│  │  Input Schema (Zod):                                     │    │
│  │  z.union([                                               │    │
│  │    MessageV2.Part,                    // 전체 교체       │    │
│  │    { part: TextPart, delta: string }, // 텍스트 증분    │    │
│  │    { part: ReasoningPart, delta: string }               │    │
│  │  ])                                                      │    │
│  │                                                          │    │
│  │  1. Storage에 Part 저장 (파일 시스템)                   │    │
│  │  2. Bus.publish(MessageV2.Event.PartUpdated, {part, delta})│   │
│  └─────────────────────────────────────────────────────────┘    │
│       │                                                          │
│       │ EventEmitter (단일 프로세스, 동기)                      │
│       ▼                                                          │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │ GlobalBus                                                │    │
│  │ - subscribeAll() 구독자에게 브로드캐스트                 │    │
│  │ - 유실 없음 (메모리 내 직접 전달)                        │    │
│  └─────────────────────────────────────────────────────────┘    │
│       │                                                          │
│       │ SSE Stream                                               │
│       ▼                                                          │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │ /global/event 엔드포인트                                 │    │
│  │ - 30초 heartbeat                                         │    │
│  │ - data: {"type":"message.part.updated",                  │    │
│  │         "properties":{"part":{...},"delta":"토"}}        │    │
│  └─────────────────────────────────────────────────────────┘    │
│       │                                                          │
│       ▼                                                          │
│  TUI / Desktop / VS Code Extension                               │
│  - Part Storage에서 복구 가능                                   │
│  - ~/.local/share/opencode/part/ (283MB, 12,248 dirs)           │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### 2.2 OpenCode 핵심 특징

#### Event 정의 (Zod + TypeScript)

```typescript
// packages/opencode/src/session/index.ts
MessageV2.Event.PartUpdated = BusEvent.define(
  "message.part.updated",
  z.object({
    part: MessageV2.Part,
    delta: z.string().optional(),  // 증분 텍스트
  })
)
```

#### 스트리밍 데이터 구조

```typescript
// 발행 시
Bus.publish(MessageV2.Event.PartUpdated, {
  part: {
    id: "part-123",
    type: "text",
    content: "플라스틱은 재활용...",  // 전체 누적 텍스트
  },
  delta: "은 재활용",  // 이번 증분만
})
```

#### Storage 구조

```
~/.local/share/opencode/
├── message/     # 81 MB, 531 directories
└── part/        # 283 MB, 12,248 directories
    └── {partId}.json  # 각 Part 상태 저장
```

### 2.3 OpenCode vs Eco² 비교

| 항목 | OpenCode | Eco² (현재) | Eco² (개선안) |
|------|----------|-------------|---------------|
| **런타임** | Node.js 단일 프로세스 | Python 분산 (K8s) | Python 분산 (K8s) |
| **Event Bus** | EventEmitter (동기) | Redis Pub/Sub (비동기) | Redis Pub/Sub (비동기) |
| **Token 저장** | 파일 시스템 (Part Storage) | 없음 | Redis Stream + State |
| **Delta 구조** | `{part, delta}` 함께 전송 | `content` 만 전송 | `{delta, accumulated_len}` |
| **복구 방식** | Storage에서 Part 읽기 | 불가 | Stream catch-up + State |
| **유실 가능성** | 없음 (동기 전달) | 있음 (fire-and-forget) | 없음 (재시도 + 저장) |
| **확장성** | 단일 프로세스 한계 | 수평 확장 가능 | 수평 확장 가능 |
| **레이턴시** | ~1ms (메모리 직접) | ~5ms (Redis 경유) | ~6ms (추가 저장) |

### 2.4 OpenCode에서 배울 점

1. **Part + Delta 함께 전송**
   - OpenCode는 전체 Part와 Delta를 함께 보내 언제든 전체 상태 복구 가능
   - 우리도 `accumulated_len` 또는 주기적 `accumulated` 스냅샷으로 유사 구현

2. **Storage 기반 복구**
   - OpenCode는 모든 Part를 파일에 저장하여 영구 복구 가능
   - 우리는 Redis Stream + State로 TTL 기반 복구 (1시간)

3. **State Machine 기반 스트리밍**
   - OpenCode: `text-start → text-delta+ → text-end` 순서 보장
   - 우리도 seq 기반 순서 보장 필요

### 2.5 OpenCode 방식을 채택하지 않는 이유

| OpenCode 방식 | 우리가 다르게 하는 이유 |
|--------------|----------------------|
| 파일 시스템 저장 | K8s Pod는 ephemeral, Redis가 적합 |
| EventEmitter 동기 전달 | 분산 환경에서 Redis Pub/Sub 필수 |
| 단일 프로세스 | 다중 Worker 수평 확장 필요 |
| 전체 Part 매번 전송 | 네트워크 효율성 (delta만 전송) |

### 2.6 Hybrid 접근: 양쪽 장점 결합

```
OpenCode 장점          +         Eco² 장점
─────────────────────────────────────────────────
Part 저장 (복구)       →   Token Stream + State
Delta 구조             →   {delta, accumulated_len}
State Machine          →   seq 기반 순서
동기 안정성            →   재시도 + catch-up
                       +
                       분산 확장성 (Redis)
                       비동기 처리 (K8s)
                       수평 확장 (shard)
```

---

## 3. 목표

1. **Token 유실 방지**: 네트워크 오류, 재연결 시에도 복구 가능
2. **Resumable Stream**: 클라이언트가 마지막 위치부터 재개
3. **누적 텍스트 복구**: 전체 응답 텍스트 언제든 조회 가능
4. **비동기 유지**: 분산 아키텍처 그대로 유지

---

## 3. 설계 옵션

### Option A: Token State 저장 (Simple)

```
변경점:
- Event Router에서 Token도 State에 저장
- 누적 텍스트를 State에 append

장점: 최소 변경
단점: State 크기 증가, 성능 영향
```

### Option B: Dedicated Token Stream (Recommended)

```
변경점:
- Token 전용 Stream (chat:tokens:{job_id})
- Consumer Group으로 클라이언트별 offset 관리
- 누적 텍스트 별도 저장

장점: 확장성, 복구 용이
단점: 복잡도 증가
```

### Option C: Hybrid (OpenCode 스타일)

```
변경점:
- Token + 누적 텍스트 함께 발행 {delta, accumulated}
- 최신 누적 텍스트만 State 저장

장점: 복구 + 성능 균형
단점: 중간 복잡도
```

---

## 4. 선택: Option B + C Hybrid

### 설계 원칙

1. **Generation과 Delivery 분리** (Upstash 패턴)
2. **Token Stream 전용 저장소** (Redis Streams)
3. **누적 텍스트 State 저장** (복구용)
4. **Consumer Group 기반 재개** (클라이언트별 offset)

---

## 5. 상세 설계

### 5.1 새로운 아키텍처

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                      개선된 Token 스트리밍 아키텍처                          │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  Answer Node                                                                 │
│       │                                                                      │
│       │ notify_token_v2(content)                                            │
│       ▼                                                                      │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │ RedisProgressNotifier (개선)                                         │   │
│  │                                                                      │   │
│  │  1. 누적 텍스트 계산                                                │   │
│  │     accumulated = self._accumulated[job_id] + content               │   │
│  │                                                                      │   │
│  │  2. Token Stream에 저장 (전용)                                      │   │
│  │     XADD chat:tokens:{job_id} *                                     │   │
│  │       seq {seq}                                                      │   │
│  │       delta {content}                                                │   │
│  │       accumulated_len {len}                                          │   │
│  │                                                                      │   │
│  │  3. Stage Stream에도 저장 (기존 호환)                               │   │
│  │     XADD chat:events:{shard} * (기존 로직)                          │   │
│  │                                                                      │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│       │                                                                      │
│       ├──────────────────────┬───────────────────────────────────────────── │
│       │                      │                                              │
│       ▼                      ▼                                              │
│  Redis Streams          Redis Streams                                       │
│  (chat:tokens:{job_id}) (chat:events:{shard})                              │
│  - job별 전용            - 기존 Stage 이벤트                               │
│  - TTL: 1시간            - Token도 포함 (호환)                              │
│       │                      │                                              │
│       │                      │ XREADGROUP                                   │
│       │                      ▼                                              │
│       │              Event Router                                           │
│       │                      │                                              │
│       │                      │ Token 이벤트 처리 (개선)                     │
│       │                      │ - 누적 텍스트 State 저장                     │
│       │                      │ - 주기적 (10 토큰마다)                       │
│       │                      │ - 재시도 로직 추가                           │
│       │                      ▼                                              │
│       │              Redis Pub/Sub                                          │
│       │              (sse:events:{job_id})                                  │
│       │                      │                                              │
│       └──────────────────────┼──────────────────────────────────────────── │
│                              │                                              │
│                              ▼                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │ SSE Gateway (개선)                                                   │   │
│  │                                                                      │   │
│  │  subscribe_v2(job_id, last_token_seq)                               │   │
│  │                                                                      │   │
│  │  1. Pub/Sub 구독 시작                                               │   │
│  │                                                                      │   │
│  │  2. Token catch-up (새로운 기능)                                    │   │
│  │     - chat:tokens:{job_id}에서 last_seq 이후 읽기                   │   │
│  │     - 누락된 토큰 전달                                              │   │
│  │                                                                      │   │
│  │  3. 누적 텍스트 복구 (State에서)                                    │   │
│  │     - chat:token_state:{job_id} 조회                                │   │
│  │     - 전체 텍스트 즉시 전달 가능                                    │   │
│  │                                                                      │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│       │                                                                      │
│       ▼                                                                      │
│  Frontend                                                                    │
│  - last_token_seq 저장 (localStorage)                                       │
│  - 재연결 시 seq 전달                                                       │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 5.2 데이터 구조

#### Token Stream (chat:tokens:{job_id})

```redis
# 구조
XADD chat:tokens:{job_id} * \
  seq 1001 \
  delta "플라" \
  ts 1705401234.567

XADD chat:tokens:{job_id} * \
  seq 1002 \
  delta "스틱" \
  ts 1705401234.589

# TTL 설정
EXPIRE chat:tokens:{job_id} 3600  # 1시간
```

#### Token State (chat:token_state:{job_id})

```redis
# 구조 (주기적 업데이트)
SETEX chat:token_state:{job_id} 3600 '{
  "last_seq": 1050,
  "accumulated": "플라스틱은 재활용 가능한 플라스틱과...",
  "accumulated_len": 150,
  "updated_at": 1705401234.999
}'
```

### 5.3 RedisProgressNotifier 개선

```python
# 새로운 상수
TOKEN_STREAM_PREFIX = "chat:tokens"
TOKEN_STATE_PREFIX = "chat:token_state"
TOKEN_STREAM_TTL = 3600  # 1시간
TOKEN_STATE_SAVE_INTERVAL = 10  # 10 토큰마다 State 저장

# 새로운 Lua Script
TOKEN_XADD_V2_SCRIPT = """
local token_stream = KEYS[1]   -- chat:tokens:{job_id}
local token_state = KEYS[2]    -- chat:token_state:{job_id}

local job_id = ARGV[1]
local seq = ARGV[2]
local delta = ARGV[3]
local ts = ARGV[4]
local accumulated = ARGV[5]
local save_state = tonumber(ARGV[6])  -- 1이면 State 저장
local ttl = tonumber(ARGV[7])

-- 1. Token Stream에 추가
local msg_id = redis.call('XADD', token_stream, 'MAXLEN', '~', 10000, '*',
    'seq', seq,
    'delta', delta,
    'ts', ts
)

-- 2. Stream TTL 설정 (첫 메시지일 때만)
local stream_len = redis.call('XLEN', token_stream)
if stream_len == 1 then
    redis.call('EXPIRE', token_stream, ttl)
end

-- 3. 주기적으로 State 저장 (accumulated 복구용)
if save_state == 1 then
    local state = cjson.encode({
        last_seq = tonumber(seq),
        accumulated = accumulated,
        accumulated_len = string.len(accumulated),
        updated_at = tonumber(ts)
    })
    redis.call('SETEX', token_state, ttl, state)
end

return msg_id
"""

class RedisProgressNotifier(ProgressNotifierPort):
    def __init__(self, ...):
        ...
        self._accumulated: dict[str, str] = {}  # job_id → 누적 텍스트
        self._token_count: dict[str, int] = {}  # job_id → 토큰 카운트

    async def notify_token_v2(
        self,
        task_id: str,
        content: str,
    ) -> str:
        """개선된 토큰 스트리밍 (복구 가능)."""
        await self._ensure_scripts()

        # 누적 텍스트 계산
        if task_id not in self._accumulated:
            self._accumulated[task_id] = ""
            self._token_count[task_id] = 0

        self._accumulated[task_id] += content
        self._token_count[task_id] += 1
        accumulated = self._accumulated[task_id]

        # seq 계산
        if task_id not in self._token_seq:
            self._token_seq[task_id] = TOKEN_SEQ_START
        self._token_seq[task_id] += 1
        seq = self._token_seq[task_id]

        # State 저장 여부 (10 토큰마다)
        save_state = 1 if self._token_count[task_id] % TOKEN_STATE_SAVE_INTERVAL == 0 else 0

        ts = str(time.time())

        # Token Stream + State 저장
        token_stream_key = f"{TOKEN_STREAM_PREFIX}:{task_id}"
        token_state_key = f"{TOKEN_STATE_PREFIX}:{task_id}"

        msg_id = await self._token_v2_script(
            keys=[token_stream_key, token_state_key],
            args=[
                task_id,
                str(seq),
                content,
                ts,
                accumulated,
                str(save_state),
                str(TOKEN_STREAM_TTL),
            ],
        )

        # 기존 Stage Stream에도 발행 (호환성)
        await self._publish_to_stage_stream(task_id, seq, content, ts)

        return msg_id

    async def finalize_token_stream(self, task_id: str) -> None:
        """토큰 스트리밍 완료 시 최종 State 저장."""
        if task_id in self._accumulated:
            accumulated = self._accumulated[task_id]
            seq = self._token_seq.get(task_id, TOKEN_SEQ_START)

            token_state_key = f"{TOKEN_STATE_PREFIX}:{task_id}"
            state = {
                "last_seq": seq,
                "accumulated": accumulated,
                "accumulated_len": len(accumulated),
                "completed": True,
                "updated_at": time.time(),
            }
            await self._redis.setex(
                token_state_key,
                TOKEN_STREAM_TTL,
                json.dumps(state, ensure_ascii=False),
            )

            # 메모리 정리
            del self._accumulated[task_id]
            del self._token_count[task_id]
            self.clear_token_counter(task_id)
```

### 5.4 Event Router 개선

```python
# processor.py 개선

TOKEN_STATE_SAVE_INTERVAL = 10  # 10 토큰마다 State 저장

async def process_event(self, event: dict[str, Any], stream_name: str | None = None) -> bool:
    ...

    if is_token_event:
        seq = event.get("seq", 0)

        # 1. 재시도 로직 추가
        for attempt in range(3):
            try:
                await self._pubsub_redis.publish(channel, event_data)
                break
            except Exception as e:
                if attempt == 2:
                    logger.error("token_pubsub_publish_failed", ...)
                    return False
                await asyncio.sleep(0.1 * (attempt + 1))

        # 2. 주기적 State 저장 (복구용)
        # NOTE: 이 로직은 Worker에서 이미 처리하므로 여기서는 skip 가능
        # 또는 Worker가 못한 경우를 대비해 여기서도 처리

        return True
```

### 5.5 SSE Gateway 개선

```python
# broadcast_manager.py 개선

TOKEN_STREAM_PREFIX = "chat:tokens"
TOKEN_STATE_PREFIX = "chat:token_state"

async def subscribe_v2(
    self,
    job_id: str,
    domain: str = "chat",
    last_token_seq: int = 0,  # 클라이언트가 마지막으로 받은 seq
    ...
) -> AsyncGenerator[dict[str, Any], None]:
    """개선된 구독 (Token 복구 지원)."""

    # 1. 구독자 등록 + Pub/Sub 구독 (기존 로직)
    ...

    # 2. Token catch-up (새로운 기능)
    if last_token_seq > 0:
        async for event in self._catch_up_tokens(job_id, last_token_seq):
            yield event
    else:
        # 새 연결: Token State에서 누적 텍스트 복구
        token_state = await self._get_token_state(job_id)
        if token_state and token_state.get("accumulated"):
            yield {
                "stage": "token_recovery",
                "status": "snapshot",
                "accumulated": token_state["accumulated"],
                "last_seq": token_state["last_seq"],
            }

    # 3. 실시간 스트리밍 (기존 로직)
    ...

async def _catch_up_tokens(
    self,
    job_id: str,
    from_seq: int,
) -> AsyncGenerator[dict[str, Any], None]:
    """Token Stream에서 누락된 토큰 복구."""
    token_stream_key = f"{TOKEN_STREAM_PREFIX}:{job_id}"

    try:
        # Token Stream에서 읽기
        messages = await self._streams_client.xrange(
            token_stream_key,
            min="-",
            max="+",
            count=1000,
        )

        for msg_id, data in messages:
            seq = int(data.get("seq", "0"))
            if seq > from_seq:
                yield {
                    "stage": "token",
                    "status": "streaming",
                    "seq": seq,
                    "content": data.get("delta", ""),
                }

    except Exception as e:
        logger.warning("token_catch_up_error", extra={"job_id": job_id, "error": str(e)})

async def _get_token_state(self, job_id: str) -> dict[str, Any] | None:
    """Token State 조회."""
    token_state_key = f"{TOKEN_STATE_PREFIX}:{job_id}"
    try:
        data = await self._streams_client.get(token_state_key)
        if data:
            return json.loads(data)
    except Exception as e:
        logger.warning("token_state_error", extra={"job_id": job_id, "error": str(e)})
    return None
```

### 5.6 Frontend 변경

```typescript
// SSE 클라이언트 개선

interface TokenRecoveryEvent {
  stage: "token_recovery";
  status: "snapshot";
  accumulated: string;
  last_seq: number;
}

class ChatSSEClient {
  private lastTokenSeq: number = 0;

  connect(jobId: string) {
    // localStorage에서 마지막 seq 복구
    const savedSeq = localStorage.getItem(`token_seq_${jobId}`);
    if (savedSeq) {
      this.lastTokenSeq = parseInt(savedSeq, 10);
    }

    // seq 파라미터와 함께 연결
    const url = `/api/v1/chat/${jobId}/events?last_token_seq=${this.lastTokenSeq}`;
    const eventSource = new EventSource(url);

    eventSource.addEventListener("token_recovery", (e) => {
      const data: TokenRecoveryEvent = JSON.parse(e.data);
      // 전체 텍스트 즉시 표시
      this.setAnswer(data.accumulated);
      this.lastTokenSeq = data.last_seq;
    });

    eventSource.addEventListener("token", (e) => {
      const data = JSON.parse(e.data);
      this.appendToken(data.content);
      this.lastTokenSeq = data.seq;
      // 주기적 저장 (10 토큰마다)
      if (data.seq % 10 === 0) {
        localStorage.setItem(`token_seq_${jobId}`, data.seq.toString());
      }
    });
  }
}
```

---

## 6. 성능 영향 분석

### 추가 Redis 연산

| 연산 | 빈도 | 예상 레이턴시 |
|------|------|--------------|
| Token Stream XADD | 토큰당 1회 | ~0.5ms |
| Token State SETEX | 10 토큰당 1회 | ~0.5ms |
| Token catch-up XRANGE | 재연결 시 1회 | ~2ms |

### 메모리 사용량

```
Token Stream (chat:tokens:{job_id}):
- 평균 응답: 500 토큰 × 20 bytes = 10KB
- TTL: 1시간 → 자동 정리

Token State (chat:token_state:{job_id}):
- 평균 크기: ~2KB
- TTL: 1시간 → 자동 정리

동시 1000 job 기준:
- Stream: 10KB × 1000 = 10MB
- State: 2KB × 1000 = 2MB
- 총 추가: ~12MB (무시 가능)
```

---

## 7. 구현 계획

### Phase 1: Worker 측 개선

```
1.1 RedisProgressNotifier.notify_token_v2() 구현
    - 누적 텍스트 추적
    - Token Stream 저장
    - 주기적 State 저장

1.2 Answer Node 수정
    - notify_token → notify_token_v2
    - finalize_token_stream 호출

1.3 테스트
    - 단위 테스트: notify_token_v2
    - 통합 테스트: 전체 흐름
```

### Phase 2: Event Router 개선

```
2.1 Token 이벤트 재시도 로직 추가
2.2 Token State 저장 로직 (옵션)
```

### Phase 3: SSE Gateway 개선

```
3.1 subscribe_v2() 구현
    - last_token_seq 파라미터
    - Token catch-up
    - Token State 복구

3.2 API 엔드포인트 업데이트
    - /chat/{job_id}/events?last_token_seq=N
```

### Phase 4: Frontend 업데이트

```
4.1 last_token_seq 관리
4.2 token_recovery 이벤트 처리
4.3 localStorage 저장
```

---

## 8. 마이그레이션

### 하위 호환성

```
- 기존 notify_token() 유지
- 기존 SSE 엔드포인트 유지
- 점진적 전환 가능
```

### 전환 순서

```
1. Worker에서 notify_token_v2() 배포 (기존과 병행)
2. SSE Gateway에서 subscribe_v2() 배포
3. Frontend 업데이트
4. 모니터링 후 기존 로직 제거
```

---

## 9. 모니터링 메트릭

```python
# 추가 메트릭
TOKEN_STREAM_WRITES = Counter("token_stream_writes_total", ...)
TOKEN_STATE_SAVES = Counter("token_state_saves_total", ...)
TOKEN_CATCHUP_COUNT = Histogram("token_catchup_count", ...)
TOKEN_RECOVERY_LATENCY = Histogram("token_recovery_latency_seconds", ...)
```

---

## 10. 결론

### Before vs After

| 항목 | Before | After |
|------|--------|-------|
| Token 유실 | 가능 | 불가능 (복구) |
| 재연결 복구 | 불가 | 즉시 복구 |
| 누적 텍스트 | 없음 | State 저장 |
| 성능 영향 | - | ~1ms/token 추가 |
| 메모리 | - | ~12MB/1000 job |

### 핵심 개선

1. **Token Stream 분리**: `chat:tokens:{job_id}`로 job별 독립 관리
2. **누적 텍스트 State**: 10 토큰마다 저장, 즉시 복구 가능
3. **Consumer 재개**: `last_token_seq`로 마지막 위치부터 재개
4. **재시도 로직**: Pub/Sub 발행 실패 시 자동 재시도

---

## References

- [Upstash: Resumable LLM Streams](https://upstash.com/blog/resumable-llm-streams)
- [Redis: Streaming LLM Output](https://redis.io/tutorials/howtos/solutions/streams/streaming-llm-output/)
- [ElectricSQL: Durable Streams](https://electric-sql.com/blog/2025/12/09/announcing-durable-streams)
- [OpenCode session/index.ts](https://github.com/sst/opencode/blob/dev/packages/opencode/src/session/index.ts)
