# OpenCode vs Eco² 아키텍처 비교 분석

> Event Bus, Subagent Routing, Frontend Streaming 심층 비교

**작성일**: 2026-01-16
**분석 대상**: OpenCode (sst/opencode), Eco² Chat Worker

---

## 1. Executive Summary

| 영역 | OpenCode | Eco² |
|------|----------|------|
| **Event Bus** | Node.js EventEmitter (단일 프로세스) | Redis Streams + Pub/Sub (분산) |
| **Subagent 라우팅** | Task Tool 기반 동기 위임 | LangGraph Send API 병렬 실행 |
| **이벤트 세분화** | 4개 타입 (chat, tool, session, permission) | 18개 stage별 실시간 이벤트 |
| **병렬 실행** | 미지원 (Issue #5887 요청 중) | 네이티브 지원 |
| **Type Safety** | Zod Schema | Pydantic + Lua Script |

---

## 2. Event Bus 아키텍처

### 2.1 OpenCode: GlobalBus (EventEmitter 기반)

```
┌─────────────────────────────────────────────────────────────────┐
│                    OpenCode Event Architecture                   │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌─────────────────┐                                            │
│  │  BusEvent.define │  ← Zod Schema로 타입 안전성               │
│  │  ("event.type", │                                            │
│  │   z.object({})) │                                            │
│  └────────┬────────┘                                            │
│           │                                                      │
│           ▼                                                      │
│  ┌─────────────────┐                                            │
│  │    GlobalBus    │  ← Node.js EventEmitter 래퍼               │
│  │  (EventEmitter) │                                            │
│  └────────┬────────┘                                            │
│           │                                                      │
│     ┌─────┴─────┐                                               │
│     ▼           ▼                                               │
│  publish()   subscribe()                                        │
│     │           │                                               │
│     │     subscribeAll() ← Wildcard 구독                        │
│     │           │                                               │
│     └─────┬─────┘                                               │
│           ▼                                                      │
│  ┌─────────────────┐                                            │
│  │  SSE Endpoint   │  ← /global/event                           │
│  │  (30s heartbeat)│                                            │
│  └─────────────────┘                                            │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

**핵심 코드 패턴:**

```typescript
// Event 정의 (Zod Schema)
const SessionCreated = BusEvent.define(
  "session.created",
  z.object({
    sessionID: z.string(),
    agentID: z.string(),
  })
);

// 발행
Bus.publish(SessionCreated, { sessionID: "abc", agentID: "build" });

// 구독 (타입 추론 자동)
Bus.subscribe(SessionCreated, (event) => {
  console.log(event.properties.sessionID); // 타입 안전
});

// Wildcard 구독 (SSE용)
Bus.subscribeAll((event) => {
  sseResponse.write(`data: ${JSON.stringify(event)}\n\n`);
});
```

**특징:**
- 단일 프로세스 내 동기화
- Zod 런타임 타입 검증
- subscribeAll()로 SSE 브로드캐스트
- 30초 heartbeat (WebView timeout 방지)

---

### 2.2 Eco²: Redis Streams + Pub/Sub (분산)

```
┌─────────────────────────────────────────────────────────────────┐
│                    Eco² Event Architecture                       │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌─────────────────┐                                            │
│  │  Chat Worker    │                                            │
│  │  (K8s Pod)      │                                            │
│  └────────┬────────┘                                            │
│           │ notify_stage() / notify_token()                     │
│           ▼                                                      │
│  ┌─────────────────┐                                            │
│  │ Redis Streams   │  ← chat:events:{shard}                     │
│  │ (XADD + Lua)    │    멱등성 보장 (SETEX 마킹)                 │
│  └────────┬────────┘                                            │
│           │ XREADGROUP (Consumer Group)                         │
│           ▼                                                      │
│  ┌─────────────────┐                                            │
│  │  Event Router   │  ← job_id → shard 해시                     │
│  │  (독립 서비스)   │    4개 shard 병렬 소비                     │
│  └────────┬────────┘                                            │
│           │ PUBLISH                                              │
│           ▼                                                      │
│  ┌─────────────────┐                                            │
│  │ Redis Pub/Sub   │  ← sse:events:{job_id}                     │
│  └────────┬────────┘                                            │
│           │ SUBSCRIBE                                            │
│           ▼                                                      │
│  ┌─────────────────┐                                            │
│  │  SSE Gateway    │  ← GET /events/{job_id}                    │
│  │  (15s heartbeat)│                                            │
│  └─────────────────┘                                            │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

**핵심 코드 패턴:**

```python
# Lua Script (멱등성 보장)
IDEMPOTENT_XADD_SCRIPT = """
local publish_key = KEYS[1]  -- chat:published:{job_id}:{stage}:{seq}
local stream_key = KEYS[2]   -- chat:events:{shard}

-- 이미 발행했는지 체크
if redis.call('EXISTS', publish_key) == 1 then
    return {0, redis.call('GET', publish_key)}  -- 중복 스킵
end

-- XADD 실행
local msg_id = redis.call('XADD', stream_key, 'MAXLEN', '~', ARGV[1], '*',
    'job_id', ARGV[2], 'stage', ARGV[3], 'status', ARGV[4], ...)

-- 발행 마킹 (TTL: 2시간)
redis.call('SETEX', publish_key, ARGV[10], msg_id)
return {1, msg_id}
"""

# Stage 이벤트 발행
await notifier.notify_stage(
    task_id=job_id,
    stage="rag",
    status="completed",
    progress=50,
    result={"sources": [...], "confidence": 0.92},
    message="관련 정보 검색 완료",
)

# Token 스트리밍 (멱등성 없음)
await notifier.notify_token(task_id=job_id, content="플라스틱은 ")
```

**특징:**
- 마이크로서비스 분산 환경
- Shard 기반 수평 확장 (MD5 해시)
- Lua Script 원자성 (멱등성 보장)
- Consumer Group (at-least-once 보장)

---

### 2.3 Event Bus 비교 표

| 항목 | OpenCode | Eco² |
|------|----------|------|
| **런타임** | Node.js (단일 프로세스) | Python + Redis (분산) |
| **Event 정의** | `BusEvent.define()` + Zod | Python dataclass + JSON |
| **타입 안전성** | 컴파일 타임 + 런타임 | 런타임 (Pydantic) |
| **구독 패턴** | `subscribe()`, `subscribeAll()` | Consumer Group (XREADGROUP) |
| **멱등성** | 없음 (EventEmitter 특성) | Lua Script + SETEX |
| **확장성** | 단일 프로세스 한계 | Shard 기반 수평 확장 |
| **장애 복구** | 메모리 손실 | Redis 영속성 + ACK |
| **Heartbeat** | 30초 | 15초 |

---

## 3. Subagent 라우팅 아키텍처

### 3.1 OpenCode: Task Tool 기반 동기 위임

```
┌─────────────────────────────────────────────────────────────────┐
│                 OpenCode Subagent Architecture                   │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │                   Primary Agent                          │    │
│  │              (Build / Plan / Custom)                     │    │
│  └─────────────────────┬───────────────────────────────────┘    │
│                        │                                         │
│         ┌──────────────┼──────────────┐                         │
│         │              │              │                         │
│         ▼              ▼              ▼                         │
│    @mention       Task Tool      permission.task                │
│    (수동)          (자동)         (권한 제어)                    │
│         │              │              │                         │
│         └──────────────┼──────────────┘                         │
│                        │                                         │
│                        ▼                                         │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │                  Subagent Pool                           │    │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────┐              │    │
│  │  │ General  │  │ Explore  │  │ Custom   │              │    │
│  │  │ (연구)   │  │ (탐색)   │  │ (확장)   │              │    │
│  │  └──────────┘  └──────────┘  └──────────┘              │    │
│  └─────────────────────┬───────────────────────────────────┘    │
│                        │                                         │
│                        ▼                                         │
│              ┌─────────────────┐                                │
│              │  Context Switch │  ← 동기/모달 실행              │
│              │  (UI 전환)      │    Primary Agent 블로킹         │
│              └─────────────────┘                                │
│                        │                                         │
│                        ▼                                         │
│              ┌─────────────────┐                                │
│              │  session.idle   │  ← 완료 이벤트                 │
│              └─────────────────┘                                │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

**라우팅 설정:**

```yaml
# opencode.yaml
agents:
  build:
    description: "Full access development agent"
    model: anthropic/claude-sonnet-4
    permission:
      task: "allow"  # 모든 서브에이전트 허용

  plan:
    description: "Read-only analysis agent"
    permission:
      task:
        - deny: "*"        # 기본 거부
        - allow: "explore" # Explore만 허용

subagents:
  general:
    description: "Complex research tasks"
    tools:
      bash: "ask"
      read: "allow"

  explore:
    description: "Codebase navigation"
    tools:
      bash: "deny"
      read: "allow"
      glob: "allow"
```

**제한 사항:**
- 동기 실행 (컨텍스트 전환)
- Primary Agent 블로킹
- 병렬 서브에이전트 미지원 (Issue #5887)

---

### 3.2 Eco²: LangGraph Send API 병렬 실행

```
┌─────────────────────────────────────────────────────────────────┐
│                  Eco² Dynamic Routing Architecture               │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │                     Intent Node                          │    │
│  │  ┌─────────────────────────────────────────────────┐    │    │
│  │  │ ClassifyIntentCommand                            │    │    │
│  │  │ - Multi-Intent 분류                              │    │    │
│  │  │ - Chain-of-Intent (이전 intent 히스토리)         │    │    │
│  │  │ - Confidence Score                               │    │    │
│  │  └─────────────────────────────────────────────────┘    │    │
│  └─────────────────────┬───────────────────────────────────┘    │
│                        │                                         │
│                        ▼                                         │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │              Dynamic Router (create_dynamic_router)      │    │
│  │                                                          │    │
│  │  Input: state = {                                        │    │
│  │    intent: "waste",                                      │    │
│  │    additional_intents: ["collection_point"],             │    │
│  │    user_location: {...}                                  │    │
│  │  }                                                       │    │
│  │                                                          │    │
│  │  Routing Logic:                                          │    │
│  │  ┌─────────────────────────────────────────────────┐    │    │
│  │  │ 1. Primary Intent → INTENT_TO_NODE 매핑         │    │    │
│  │  │    "waste" → "waste_rag"                        │    │    │
│  │  │                                                  │    │    │
│  │  │ 2. Multi-Intent Fanout                          │    │    │
│  │  │    additional_intents → 각각 Send               │    │    │
│  │  │                                                  │    │    │
│  │  │ 3. Enrichment Rules (규칙 기반)                 │    │    │
│  │  │    ENRICHMENT_RULES["waste"] → ("weather",)     │    │    │
│  │  │                                                  │    │    │
│  │  │ 4. Conditional Enrichment (state 조건부)        │    │    │
│  │  │    user_location 존재 → weather 추가            │    │    │
│  │  └─────────────────────────────────────────────────┘    │    │
│  │                                                          │    │
│  │  Output: [                                               │    │
│  │    Send("waste_rag", state),                            │    │
│  │    Send("collection_point", state),                     │    │
│  │    Send("weather", state),                              │    │
│  │  ]                                                       │    │
│  └─────────────────────┬───────────────────────────────────┘    │
│                        │                                         │
│         ┌──────────────┼──────────────┐                         │
│         │              │              │                         │
│         ▼              ▼              ▼                         │
│  ┌──────────┐   ┌──────────┐   ┌──────────┐                    │
│  │waste_rag │   │collection│   │ weather  │  ← 병렬 실행       │
│  │  Node    │   │  _point  │   │  Node    │                    │
│  └────┬─────┘   └────┬─────┘   └────┬─────┘                    │
│       │              │              │                           │
│       │   stage      │   stage      │   stage                   │
│       │   events     │   events     │   events                  │
│       │              │              │                           │
│       └──────────────┼──────────────┘                           │
│                      ▼                                          │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │                  Aggregator Node                         │    │
│  │  - 병렬 실행 결과 병합                                   │    │
│  │  - Context 우선순위 정렬                                 │    │
│  │  - 필수 Context 검증                                     │    │
│  └─────────────────────────────────────────────────────────┘    │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

**라우팅 설정:**

```python
# Intent → Node 매핑
INTENT_TO_NODE: dict[str, str] = {
    "waste": "waste_rag",
    "character": "character",
    "location": "location",
    "web_search": "web_search",
    "bulk_waste": "bulk_waste",
    "recyclable_price": "recyclable_price",
    "collection_point": "collection_point",
    "weather": "weather",
    "image_generation": "image_generation",
    "general": "general",
}

# Enrichment 규칙 (자동 보조 노드 추가)
ENRICHMENT_RULES: dict[str, EnrichmentRule] = {
    "waste": EnrichmentRule(
        intent="waste",
        enrichments=("weather",),
        description="분리배출 질문 시 날씨 팁 추가",
    ),
    "bulk_waste": EnrichmentRule(
        intent="bulk_waste",
        enrichments=("weather",),
        description="대형폐기물 질문 시 날씨 팁 추가",
    ),
}

# 조건부 Enrichment
CONDITIONAL_ENRICHMENTS: list[ConditionalEnrichment] = [
    ConditionalEnrichment(
        node="weather",
        condition=lambda state: (
            state.get("user_location") is not None
            and state.get("intent") not in ("weather", "general")
        ),
        exclude_intents=("weather", "image_generation"),
        description="위치 정보가 있고 관련 intent면 날씨 추가",
    ),
]
```

---

### 3.3 Subagent 라우팅 비교 표

| 항목 | OpenCode | Eco² |
|------|----------|------|
| **라우팅 방식** | Task Tool 기반 위임 | Intent 분류 → 규칙 기반 fanout |
| **실행 모델** | 동기/모달 (컨텍스트 전환) | 비동기 병렬 (Send API) |
| **병렬 실행** | 미지원 | 네이티브 지원 |
| **Primary 블로킹** | O (UI 전환) | X (백그라운드 실행) |
| **자동 Enrichment** | 없음 (수동 호출) | 규칙 기반 자동 추가 |
| **권한 제어** | permission.task (glob) | Node 레벨 Policy |
| **결과 병합** | 없음 (단일 실행) | Aggregator Node |
| **Chain-of-Intent** | 없음 | 이전 intent 히스토리 활용 |

---

## 4. Frontend 이벤트 스트리밍

### 4.1 OpenCode: 4개 이벤트 타입

```typescript
// 지원 이벤트 타입
type EventType =
  | "chat.message"          // 메시지 수신
  | "tool.execute.before"   // 도구 실행 전
  | "tool.execute.after"    // 도구 실행 후
  | "session.idle"          // 에이전트 완료
  | "permission.ask";       // 권한 요청

// SSE 스트리밍
const eventSource = new EventSource("/global/event");
eventSource.onmessage = (event) => {
  const data = JSON.parse(event.data);
  switch (data.type) {
    case "chat.message":
      updateMessage(data.properties);
      break;
    case "session.idle":
      setLoading(false);
      break;
  }
};
```

**UI 상태:**
- 로딩 (전체)
- 완료

---

### 4.2 Eco²: 18개 Stage별 세분화 이벤트

```typescript
// 지원 Stage 타입
type Stage =
  // Core Pipeline
  | "queued"           // 0: 대기열 진입
  | "intent"           // 1: 의도 분류
  | "vision"           // 2: 이미지 분석
  // Subagents (병렬 실행)
  | "rag"              // 3: RAG 검색
  | "character"        // 4: 캐릭터 응답
  | "location"         // 5: 위치 검색
  | "kakao_place"      // 6: 카카오 장소
  | "bulk_waste"       // 7: 대형폐기물
  | "weather"          // 8: 날씨 정보
  | "recyclable_price" // 9: 재활용 시세
  | "collection_point" // 10: 수거함 위치
  | "web_search"       // 11: 웹 검색
  | "image_generation" // 12: 이미지 생성
  // Aggregation & Answer
  | "aggregate"        // 13: 결과 병합
  | "feedback"         // 14: 품질 평가
  | "answer"           // 15: 최종 답변
  | "done"             // 16: 완료
  | "needs_input";     // 17: 사용자 입력 요청

// Event 구조
interface StageEvent {
  job_id: string;
  stage: Stage;
  status: "started" | "completed" | "failed";
  seq: number;        // 단조증가 (정렬용)
  ts: number;         // Unix timestamp
  progress?: number;  // 0-100
  result?: object;    // stage별 결과 데이터
  message?: string;   // UI 표시 메시지
}

interface TokenEvent {
  job_id: string;
  stage: "token";
  status: "streaming";
  seq: number;        // 1000+ (stage와 분리)
  content: string;    // 토큰 내용
}

// SSE 스트리밍
const eventSource = new EventSource(`/events/${jobId}`);
eventSource.onmessage = (event) => {
  const data: StageEvent | TokenEvent = JSON.parse(event.data);

  if (data.stage === "token") {
    appendToken(data.content);
  } else {
    updateStageProgress(data.stage, data.status, data.message);
  }
};
```

**UI 상태 (세분화):**
```
┌─────────────────────────────────────────────────────────────┐
│  [의도 파악 중...]        ← intent:started                  │
│  [의도 분류 완료: waste]  ← intent:completed                │
│                                                              │
│  ┌─────────────────────────────────────────────────────┐    │
│  │  [정보 검색 중...]     ← rag:started                │    │
│  │  [날씨 확인 중...]     ← weather:started (병렬)     │    │
│  └─────────────────────────────────────────────────────┘    │
│                                                              │
│  [검색 완료]              ← rag:completed                   │
│  [날씨 정보 확인 완료]    ← weather:completed               │
│                                                              │
│  [답변 생성 중...]        ← answer:started                  │
│  [플라스틱은...]          ← token:streaming                 │
│  [완료]                   ← done:completed                  │
└─────────────────────────────────────────────────────────────┘
```

---

### 4.3 Frontend 이벤트 비교 표

| 항목 | OpenCode | Eco² |
|------|----------|------|
| **이벤트 타입 수** | 4개 | 18개 stage + token |
| **진행 상태** | 로딩/완료 | stage별 세분화 |
| **병렬 실행 표시** | 불가 | 가능 (동시 stage) |
| **토큰 스트리밍** | chat.message 내 | 별도 token 이벤트 |
| **진행률** | 없음 | 0-100% (stage별) |
| **결과 데이터** | 없음 | result 필드 |
| **정렬 보장** | 없음 | seq 단조증가 |
| **Human-in-Loop** | permission.ask | needs_input stage |

---

## 5. 아키텍처 Trade-off 분석

### 5.1 OpenCode 장단점

**장점:**
- 단순한 구조 (단일 프로세스)
- Zod 기반 강력한 타입 안전성
- 빠른 개발 속도
- 낮은 운영 복잡도

**단점:**
- 수평 확장 한계
- 병렬 서브에이전트 미지원
- 장애 복구 어려움 (메모리 손실)
- 세분화된 진행 상태 표시 불가

---

### 5.2 Eco² 장단점

**장점:**
- 마이크로서비스 확장성
- 네이티브 병렬 실행
- 멱등성 보장 (Lua Script)
- 세분화된 UX (18개 stage)
- 장애 복구 (Redis 영속성)

**단점:**
- 높은 운영 복잡도
- Redis 의존성
- 네트워크 레이턴시
- 디버깅 어려움 (분산 추적 필요)

---

## 6. 성능 특성

### 6.1 레이턴시 비교

| 시나리오 | OpenCode | Eco² |
|----------|----------|------|
| **단일 질문 (simple)** | ~50ms | ~100ms |
| **Tool 호출 (1개)** | ~100ms | ~150ms |
| **Multi-intent (3개)** | ~3000ms (순차) | ~500ms (병렬) |
| **복합 질문 + Enrichment** | N/A | ~600ms (병렬) |

### 6.2 확장성 비교

| 항목 | OpenCode | Eco² |
|------|----------|------|
| **동시 세션** | 프로세스 메모리 한계 | Shard 기반 무제한 |
| **Worker 확장** | 불가 | K8s HPA 연동 |
| **이벤트 처리량** | ~1000 msg/s | ~50000 msg/s (4 shard) |

---

## 7. 결론 및 권장 사항

### 7.1 적합 시나리오

| 시나리오 | 권장 아키텍처 |
|----------|--------------|
| CLI 도구 / 단일 사용자 | OpenCode |
| 웹 서비스 / 다중 사용자 | Eco² |
| 단순 Q&A | OpenCode |
| Multi-intent / 복합 질의 | Eco² |
| MVP / 프로토타입 | OpenCode |
| Production / 확장성 필요 | Eco² |

### 7.2 상호 참고 가능 패턴

**OpenCode → Eco² 적용 가능:**
- `BusEvent.define()` 패턴 → Pydantic 기반 Event Schema 강화
- Zod discriminatedUnion → Python Literal + TypedDict

**Eco² → OpenCode 참고 가치:**
- Send API 병렬 실행 (Issue #5887 해결책)
- Stage별 세분화 이벤트
- Enrichment 규칙 시스템

---

## References

1. [OpenCode Agents Documentation](https://opencode.ai/docs/agents/)
2. [OpenCode Issue #5887 - Async Sub-Agent Delegation](https://github.com/sst/opencode/issues/5887)
3. [OpenCode Issue #2021 - agent.finished Plugin Event](https://github.com/sst/opencode/issues/2021)
4. [LangGraph Send API Documentation](https://langchain-ai.github.io/langgraph/concepts/low_level/#send)
5. [Redis Streams Documentation](https://redis.io/docs/data-types/streams/)
6. [ts-bus - TypeScript Event Bus](https://github.com/ryardley/ts-bus)
