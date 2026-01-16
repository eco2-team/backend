# Chat Worker Production Architecture - Implementation Report

> **ADR**: [chat-worker-production-architecture-adr.md](../plans/chat-worker-production-architecture-adr.md)
> **일자**: 2026-01-16
> **브랜치**: `refactor/reward-fanout-exchange`

---

## 1. Executive Summary

ADR에서 정의한 Chat Worker Production Architecture를 구현 완료했습니다. P0(Critical), P1(Production Critical) 항목을 모두 구현하여 Production 환경에서 안정적으로 운영 가능한 기반을 마련했습니다.

### Commit History

| Commit | 설명 | 우선순위 |
|--------|------|----------|
| [`be1a6060`](https://github.com/eco2-team/backend/commit/be1a6060) | Event-First Architecture for message persistence | Infra |
| [`8c3d3e5c`](https://github.com/eco2-team/backend/commit/8c3d3e5c) | Add timeout to gRPC clients and image generator | **P0** |
| [`c361ef1f`](https://github.com/eco2-team/backend/commit/c361ef1f) | Add production resilience infrastructure | **P1** |

---

## 2. P0 Implementation: Timeout Fixes

### 2.1 문제점

ADR 검증 과정에서 발견된 Critical Gap:
- gRPC 클라이언트가 timeout 없이 호출되어 무제한 대기 가능
- Image Generator가 SDK 기본값(10분) 사용

### 2.2 수정 내용

**Character gRPC Client** (`grpc_client.py:96`)
```python
DEFAULT_GRPC_TIMEOUT = 3.0

response = await stub.GetCharacterByMatch(
    request,
    timeout=DEFAULT_GRPC_TIMEOUT  # 3초 타임아웃
)
```

**Location gRPC Client** (`grpc_client.py:110`)
```python
DEFAULT_GRPC_TIMEOUT = 3.0

response = await stub.SearchNearby(
    request,
    timeout=DEFAULT_GRPC_TIMEOUT
)
```

**Image Generator** (`openai_responses.py:78`)
```python
DEFAULT_IMAGE_TIMEOUT = httpx.Timeout(
    connect=5.0,   # 연결 5초
    read=60.0,     # DALL-E 생성 대기 60초
    write=5.0,
    pool=5.0,
)

self._client = AsyncOpenAI(
    api_key=api_key,
    timeout=DEFAULT_IMAGE_TIMEOUT,
)
```

---

## 3. P1 Implementation: Production Resilience

### 3.1 신규 컴포넌트

```
apps/chat_worker/
├── domain/enums/
│   └── fail_mode.py              # FailMode Enum
├── application/
│   ├── dto/
│   │   ├── intent_signals.py     # IntentSignals DTO
│   │   ├── intent_result.py      # Extended IntentResult
│   │   └── node_result.py        # NodeResult 표준 스키마
│   └── ports/
│       └── circuit_breaker.py    # CircuitBreakerPort
└── infrastructure/
    ├── resilience/
    │   └── circuit_breaker.py    # InMemoryCircuitBreaker
    └── orchestration/langgraph/
        ├── policies/
        │   └── node_policy.py    # NodePolicy + 테이블
        └── nodes/
            ├── node_executor.py  # Policy-aware 실행기
            └── aggregator_node.py # 검증 로직 추가
```

### 3.2 FailMode Enum

```python
class FailMode(str, Enum):
    """노드 실패 시 동작 모드."""

    FAIL_OPEN = "fail_open"
    # 실패해도 다음 단계 진행 (보조 정보 노드)
    # 사용: weather, character, image_generation

    FAIL_CLOSE = "fail_close"
    # 실패 시 전체 파이프라인 중단
    # 사용: general (최후의 보루)

    FAIL_FALLBACK = "fail_fallback"
    # fallback_node로 대체 실행
    # 사용: waste_rag, bulk_waste, location
```

### 3.3 IntentSignals

ADR 2.1절 구현:

```python
@dataclass(frozen=True)
class IntentSignals:
    """의도 분류 신뢰도 구성 신호."""

    previous_intents: list[str] = field(default_factory=list)
    has_image: bool = False
    user_location: dict[str, float] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "previous_intents": self.previous_intents,
            "has_image": self.has_image,
            "has_location": self.user_location is not None,
        }
```

### 3.4 IntentResult 확장

```python
@dataclass(frozen=True)
class IntentResult:
    intent: Intent
    complexity: QueryComplexity
    confidence: float
    additional_intents: list[Intent]
    raw_response: str | None
    rationale: str | None = None      # 신규: 판단 근거
    signals: IntentSignals | None = None  # 신규: 신호
```

### 3.5 NodeResult 표준 스키마

ADR 5.1절 구현:

```python
class NodeStatus(str, Enum):
    SUCCESS = "success"
    FAILED = "failed"
    TIMEOUT = "timeout"
    SKIPPED = "skipped"
    FALLBACK = "fallback"

@dataclass
class NodeResult:
    node_name: str
    status: NodeStatus
    data: dict[str, Any] | None = None
    error: str | None = None
    latency_ms: float = 0.0
    retry_count: int = 0
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    fallback_used: bool = False
    fallback_node: str | None = None
```

### 3.6 NodePolicy 테이블

ADR 3.2절 검증 완료된 테이블:

```python
NODE_POLICIES: dict[str, NodePolicy] = {
    "waste_rag": NodePolicy(
        node_name="waste_rag",
        timeout_ms=1000,      # 로컬 파일 캐싱
        retry_count=1,
        circuit_breaker_threshold=5,
        fail_mode=FailMode.FAIL_FALLBACK,
        fallback_node="web_search",
        is_required=True,
    ),
    "bulk_waste": NodePolicy(
        node_name="bulk_waste",
        timeout_ms=10000,     # MOIS API: 15s
        retry_count=2,
        circuit_breaker_threshold=5,
        fail_mode=FailMode.FAIL_FALLBACK,
        fallback_node="web_search",
        is_required=True,
    ),
    "character": NodePolicy(
        node_name="character",
        timeout_ms=3000,      # gRPC
        retry_count=1,
        circuit_breaker_threshold=3,
        fail_mode=FailMode.FAIL_OPEN,  # 보조 정보
        is_required=False,
    ),
    # ... (전체 테이블은 node_policy.py 참조)
}
```

### 3.7 Circuit Breaker

ADR 3.4절 상태 다이어그램 구현:

```python
class CircuitBreakerState(str, Enum):
    CLOSED = "closed"      # 정상 동작
    OPEN = "open"          # 차단 상태
    HALF_OPEN = "half_open"  # 테스트 상태

class InMemoryCircuitBreaker:
    """Thread-safe Circuit Breaker."""

    async def call(
        self,
        func: Callable[[], Awaitable[T]],
        fallback: Callable[[], Awaitable[T]] | None = None,
    ) -> T:
        state = await self._get_state()

        if state == CircuitBreakerState.OPEN:
            if fallback:
                return await fallback()
            raise CircuitOpenError(...)

        try:
            result = await func()
            await self._record_success()
            return result
        except Exception as e:
            await self._record_failure()
            if fallback:
                return await fallback()
            raise
```

### 3.8 Aggregator 검증 로직

ADR 5.2-5.3절 구현:

```python
REQUIRED_CONTEXTS: dict[str, set[str]] = {
    "waste": {"disposal_rules"},
    "bulk_waste": {"bulk_waste_context"},
    "location": {"location_context"},
    "collection_point": {"collection_point_context"},
}

OPTIONAL_CONTEXTS: set[str] = {
    "weather_context",
    "character_context",
    "image_url",
    "recyclable_price_context",
}

async def aggregator_node(state: dict[str, Any]) -> dict[str, Any]:
    intent = state.get("intent", "general")
    required_fields = REQUIRED_CONTEXTS.get(intent, set())

    # Required 검증
    missing_required = [
        field for field in required_fields
        if not state.get(field)
    ]

    if missing_required:
        state["trigger_fallback"] = True
        state["fallback_reason"] = "missing_required_context"
        return state

    # Metadata 기록
    state["aggregation_metadata"] = {
        "required_satisfied": True,
        "collected_optional": [...],
        "missing_optional": [...],
    }

    return state
```

---

## 4. Event-First Architecture (Infra)

### 4.1 배경

기존 Dual-Write 문제:
- Worker → RabbitMQ + Redis Streams (두 곳에 동시 쓰기)
- 일관성 보장 어려움

### 4.2 구현

**Single Write Path**:
```
Worker → Redis Streams (done event + persistence data)
         │
         ├── Consumer Group: event-router → SSE Gateway
         │
         └── Consumer Group: chat-persistence → PostgreSQL
```

**done 이벤트에 persistence 데이터 포함**:
```python
await self._progress_notifier.notify_stage(
    task_id=request.job_id,
    stage="done",
    result={
        "intent": intent,
        "answer": answer,
        "persistence": {
            "conversation_id": request.session_id,
            "user_id": request.user_id,
            "user_message": request.message,
            "assistant_message": answer,
            "intent": intent,
            "metadata": result.get("metadata"),
        },
    },
)
```

**Redis Streams Consumer**:
```python
class ChatPersistenceConsumer:
    CONSUMER_GROUP = "chat-persistence"

    async def consume(self, callback):
        # XREADGROUP으로 이벤트 소비
        # done 이벤트의 persistence 데이터 추출
        # 콜백 성공 시 XACK
```

---

## 5. Implementation Status

### ADR Checklist 대비 완료 상태

| 항목 | ADR 섹션 | 상태 | 커밋 |
|------|----------|------|------|
| gRPC timeout 추가 | 11. P0 | ✅ | `8c3d3e5c` |
| Image Generator timeout | 11. P0 | ✅ | `8c3d3e5c` |
| IntentResult 확장 (rationale, signals) | 2.1 | ✅ | `c361ef1f` |
| IntentSignals DTO | 2.1 | ✅ | `c361ef1f` |
| NodePolicy 데이터클래스 | 3.1 | ✅ | `c361ef1f` |
| NodePolicy 테이블 | 3.2 | ✅ | `c361ef1f` |
| FailMode Enum | 3.3 | ✅ | `c361ef1f` |
| NodeResult 표준 스키마 | 5.1 | ✅ | `c361ef1f` |
| Circuit Breaker 구현 | 3.4 | ✅ | `c361ef1f` |
| Aggregator required/optional 검증 | 5.2-5.3 | ✅ | `c361ef1f` |
| NodeExecutor (policy 적용) | - | ✅ | `c361ef1f` |

### P2 (권장) 상태

| 항목 | 상태 | 비고 |
|------|------|------|
| Soft dependency timeout | ✅ | NodeExecutor에서 처리 |
| Chain-of-Intent 부스트 상한 | ⏳ | IntentSignals로 구조 준비 |
| IntentSignals confidence 계산 | ⏳ | 구조 준비, 로직 미구현 |
| OpenTelemetry span | ⏳ | 별도 작업 |

---

## 6. Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                    Chat Worker Pipeline (Updated)                │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  [START]                                                         │
│     │                                                            │
│     ▼                                                            │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │  Intent Node                                             │    │
│  │  └─ Output: IntentResult (+ rationale, signals)         │    │
│  └─────────────────────────────────────────────────────────┘    │
│     │                                                            │
│     ▼                                                            │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │  Dynamic Router (Send API)                               │    │
│  │  ├─ Intent → Node 매핑                                  │    │
│  │  └─ Multi-Intent Fanout                                 │    │
│  └─────────────────────────────────────────────────────────┘    │
│     │                                                            │
│     ▼                                                            │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │  Parallel Execution (with NodeExecutor)                  │    │
│  │                                                          │    │
│  │  ┌─────────────────────────────────────────────────┐    │    │
│  │  │  NodeExecutor.execute(node_func)                │    │    │
│  │  │  ├─ NodePolicy 조회                             │    │    │
│  │  │  ├─ Circuit Breaker 체크                        │    │    │
│  │  │  ├─ Timeout 적용                                │    │    │
│  │  │  ├─ Retry 로직                                  │    │    │
│  │  │  └─ FailMode에 따른 처리                        │    │    │
│  │  └─────────────────────────────────────────────────┘    │    │
│  │                                                          │    │
│  │  ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐       │    │
│  │  │waste_rag│ │character│ │location │ │ weather │       │    │
│  │  │(1000ms) │ │(3000ms) │ │(3000ms) │ │(5000ms) │       │    │
│  │  │FALLBACK │ │FAIL_OPEN│ │FALLBACK │ │FAIL_OPEN│       │    │
│  │  └─────────┘ └─────────┘ └─────────┘ └─────────┘       │    │
│  │                                                          │    │
│  └──────────────────────────────────────────────────────────┘    │
│     │                                                            │
│     ▼                                                            │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │  Aggregator (with Validation)                            │    │
│  │  ├─ REQUIRED_CONTEXTS 검증                              │    │
│  │  ├─ Missing → trigger_fallback = True                   │    │
│  │  └─ OPTIONAL_CONTEXTS 수집                              │    │
│  └─────────────────────────────────────────────────────────┘    │
│     │                                                            │
│     ▼                                                            │
│  [Answer Node] → [END]                                          │
│                                                                  │
│  done event → Redis Streams                                     │
│               ├── event-router → SSE Gateway                    │
│               └── chat-persistence → PostgreSQL                 │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## 7. Testing Strategy

### Unit Tests

```bash
# Circuit Breaker
pytest apps/chat_worker/tests/unit/infrastructure/resilience/ -v

# NodePolicy
pytest apps/chat_worker/tests/unit/infrastructure/orchestration/langgraph/policies/ -v

# NodeResult
pytest apps/chat_worker/tests/unit/application/dto/ -v
```

### Integration Tests

```bash
# gRPC timeout 검증
pytest apps/chat_worker/tests/integration/test_grpc_timeout.py -v

# Aggregator 검증
pytest apps/chat_worker/tests/integration/test_aggregator_validation.py -v
```

---

## 8. Next Steps (P2/P3)

1. **Chain-of-Intent Boost 로직**: IntentSignals 기반 confidence 계산
2. **OpenTelemetry 통합**: 각 노드 span 속성 추가
3. **Dynamic Policy Adjustment**: A/B 테스트 기반 정책 튜닝
4. **Partial Response**: 일부 컨텍스트만 준비되면 먼저 응답

---

## 9. References

- [ADR: Chat Worker Production Architecture](../plans/chat-worker-production-architecture-adr.md)
- [LangGraph Send API](https://langchain-ai.github.io/langgraph/concepts/low_level/#send)
- [Circuit Breaker Pattern](https://martinfowler.com/bliki/CircuitBreaker.html)
