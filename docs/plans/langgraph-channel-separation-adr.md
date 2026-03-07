# LangGraph Channel Separation ADR

> **Status**: Brainstorming
> **Created**: 2026-01-18
> **Related**: [langgraph-native-streaming-adr.md](./langgraph-native-streaming-adr.md), [chat-worker-production-architecture-adr.md](./chat-worker-production-architecture-adr.md)

## Context

### 문제 상황

`StateGraph(dict)` + Send API 병렬 실행 시 `InvalidUpdateError` 발생:

```
langgraph.errors.InvalidUpdateError: At key '__root__': Can receive only one value per step.
Use an Annotated key with a reducer.
```

**Root Cause**:
- 현재: `graph = StateGraph(dict)` (untyped)
- 각 노드가 `{**state, "my_field": value}` 반환
- Send API로 병렬 실행 시 여러 노드가 동시에 `__root__` 업데이트 → 충돌

### 현재 아키텍처

```
intent_node
    ↓
dynamic_router (Send API)
    ├── Send("waste_rag", state)      ─┐
    ├── Send("weather", state)         │ 병렬 실행
    └── Send("collection_point", state)┘
            ↓
      InvalidUpdateError!  (모두 {**state, ...} 반환)
```

---

## Decision

### 해결 방안: Channel Separation + Annotated Reducer

LangGraph 공식 권장 패턴 적용:
1. `StateGraph(ChatState)` - Typed State 사용
2. 각 서브에이전트별 전용 채널(필드) 정의
3. `Annotated[T, reducer]`로 병합 규칙 명시
4. 노드는 자기 채널만 반환 (spread 금지)

```
intent_node
    ↓
dynamic_router (Send API)
    ├── waste_rag     → {"disposal_rules": {...}}
    ├── weather       → {"weather_context": {...}}      병렬 OK!
    └── collection    → {"collection_point_context": {...}}
            ↓
    aggregator (fan-in)
            ↓
      answer_node
```

---

## Design

### 1. ChatState Schema

```python
# apps/chat_worker/infrastructure/orchestration/langgraph/state.py

from typing import Annotated, Any, TypedDict
from langchain_core.messages import AnyMessage


# ============================================================
# Reducer Functions
# ============================================================

def add_messages(existing: list | None, new: list | AnyMessage) -> list:
    """메시지 누적 reducer."""
    if existing is None:
        existing = []
    if isinstance(new, list):
        return existing + new
    return existing + [new]


def last_value(existing: Any, new: Any) -> Any:
    """Last Write Wins - 단순 덮어쓰기."""
    return new


def merge_context(existing: dict | None, new: dict | None) -> dict | None:
    """컨텍스트 dict 병합.

    병합 규칙:
    - new가 None이면 existing 유지
    - existing이 None이면 new 사용
    - 둘 다 있으면 new가 success=True일 때만 교체
    """
    if new is None:
        return existing
    if existing is None:
        return new
    if new.get("success", True):
        return new
    return existing


# ============================================================
# ChatState Schema
# ============================================================

class ChatState(TypedDict, total=False):
    """Chat 파이프라인 상태.

    Channel Separation + Annotated Reducer로 Send API 병렬 실행 안전.

    계층 구조:
    ┌─────────────────────────────────────────────────────────┐
    │ Core Layer                                               │
    │ - Metadata: job_id, user_id, thread_id                  │
    │ - Input: message, image_url, conversation_history       │
    │ - Intent: intent, confidence, additional_intents        │
    └─────────────────────────────────────────────────────────┘
                            ↓
    ┌─────────────────────────────────────────────────────────┐
    │ Critical Context Layer (Required)                        │
    │ - disposal_rules: waste intent 필수                      │
    │ - bulk_waste_context: bulk_waste intent 필수            │
    │ - location_context: location intent 필수                │
    │ - collection_point_context: collection_point 필수       │
    └─────────────────────────────────────────────────────────┘
                            ↓
    ┌─────────────────────────────────────────────────────────┐
    │ Enrichment Context Layer (Optional)                      │
    │ - character_context: 캐릭터 페르소나                     │
    │ - weather_context: 날씨 기반 팁                          │
    │ - web_search_results: 웹 검색 보충                       │
    │ - recyclable_price_context: 재활용 시세                 │
    │ - image_generation_context: 생성된 이미지               │
    │ - general_context: 일반 대화                            │
    └─────────────────────────────────────────────────────────┘
                            ↓
    ┌─────────────────────────────────────────────────────────┐
    │ Output Layer                                             │
    │ - answer: 최종 응답                                      │
    │ - messages: 대화 히스토리 (누적)                         │
    └─────────────────────────────────────────────────────────┘
    """

    # ==================== Core Layer ====================

    # Metadata (Immutable)
    job_id: str
    user_id: str
    thread_id: str

    # Input (Immutable)
    message: str
    image_url: str | None
    conversation_history: list[dict[str, Any]]

    # Intent Classification Result
    intent: str
    intent_confidence: float
    is_complex: bool
    has_multi_intent: bool
    additional_intents: list[str]
    intent_history: list[str]  # Chain-of-Intent

    # Decomposed Queries (Multi-Intent)
    decomposed_queries: list[str]
    current_query: str

    # Vision Result
    classification_result: str | None

    # ==================== Critical Context Layer ====================
    # Required fields: 누락 시 fallback 트리거
    # contracts.py INTENT_REQUIRED_FIELDS와 일치

    disposal_rules: Annotated[dict[str, Any] | None, merge_context]
    """waste intent 필수. RAG 검색 결과."""

    bulk_waste_context: Annotated[dict[str, Any] | None, merge_context]
    """bulk_waste intent 필수. 대형폐기물 정보."""

    location_context: Annotated[dict[str, Any] | None, merge_context]
    """location intent 필수. gRPC 위치 정보."""

    collection_point_context: Annotated[dict[str, Any] | None, merge_context]
    """collection_point intent 필수. KECO 수거함 위치."""

    # ==================== Enrichment Context Layer ====================
    # Optional fields: 없어도 답변 가능, 있으면 품질 향상
    # contracts.py INTENT_OPTIONAL_FIELDS와 일치

    character_context: Annotated[dict[str, Any] | None, merge_context]
    """캐릭터 페르소나 (gRPC). 응답 톤 조절용."""

    weather_context: Annotated[dict[str, Any] | None, merge_context]
    """날씨 정보. 분리배출 팁 제공용."""

    recyclable_price_context: Annotated[dict[str, Any] | None, merge_context]
    """재활용 시세 정보."""

    web_search_results: Annotated[dict[str, Any] | None, merge_context]
    """웹 검색 결과. Fallback/보충용."""

    image_generation_context: Annotated[dict[str, Any] | None, merge_context]
    """이미지 생성 결과. URL + description."""

    general_context: Annotated[dict[str, Any] | None, merge_context]
    """일반 대화 컨텍스트."""

    # ==================== Aggregator Flags ====================

    needs_fallback: bool
    """필수 컨텍스트 누락 시 True."""

    missing_required_contexts: list[str]
    """누락된 필수 필드 목록."""

    # ==================== Output Layer ====================

    answer: str
    """최종 생성된 응답."""

    messages: Annotated[list[AnyMessage], add_messages]
    """대화 히스토리 (Reducer로 누적)."""
```

### 2. Channel Mapping (Single Source of Truth)

| Intent | Required Channel | Optional Channels |
|--------|-----------------|-------------------|
| `waste` | `disposal_rules` | `character_context`, `weather_context` |
| `bulk_waste` | `bulk_waste_context` | `weather_context` |
| `location` | `location_context` | `weather_context` |
| `collection_point` | `collection_point_context` | `weather_context` |
| `general` | - | `general_context`, `web_search_results` |
| `character` | - | `character_context` |
| `weather` | - | `weather_context` |
| `web_search` | - | `web_search_results` |
| `recyclable_price` | - | `recyclable_price_context` |
| `image_generation` | - | `image_generation_context` |

### 3. Node Return Value Pattern

**Before (문제)**:
```python
async def weather_node(state: dict[str, Any]) -> dict[str, Any]:
    output = await command.execute(input_dto)
    return {
        **state,  # ❌ 전체 state spread → 충돌 원인
        "weather_context": output.weather_context,
    }
```

**After (해결)**:
```python
async def weather_node(state: dict[str, Any]) -> dict[str, Any]:
    output = await command.execute(input_dto)
    return {
        "weather_context": output.weather_context,  # ✅ 자기 채널만
    }
```

**표준 컨텍스트 포맷**:
```python
{
    "success": True,           # 성공 여부 (merge_context에서 사용)
    "error": None,             # 에러 메시지 (실패 시)
    "data": {...},             # 실제 데이터
    # 또는 도메인별 필드 직접 포함
    "temperature": 15,
    "condition": "맑음",
}
```

### 4. Aggregator Priority

```python
# apps/chat_worker/infrastructure/orchestration/langgraph/aggregator_priority.py

from dataclasses import dataclass
from enum import Enum


class ContextPriority(Enum):
    """컨텍스트 우선순위."""
    CRITICAL = 1    # 필수: 없으면 fallback
    HIGH = 2        # 중요: 답변 품질에 큰 영향
    MEDIUM = 3      # 보통: 있으면 좋음
    LOW = 4         # 선택: 부가 정보


@dataclass(frozen=True)
class ContextSpec:
    """컨텍스트 필드 스펙."""
    field: str
    priority: ContextPriority
    timeout_ms: int = 2000
    fallback_on_timeout: bool = False
    description: str = ""


# Intent별 컨텍스트 우선순위 맵
CONTEXT_PRIORITY_MAP: dict[str, list[ContextSpec]] = {
    "waste": [
        ContextSpec(
            "disposal_rules",
            ContextPriority.CRITICAL,
            timeout_ms=3000,
            fallback_on_timeout=True,
            description="RAG 분리배출 규정",
        ),
        ContextSpec(
            "character_context",
            ContextPriority.MEDIUM,
            timeout_ms=1000,
            description="캐릭터 페르소나",
        ),
        ContextSpec(
            "weather_context",
            ContextPriority.LOW,
            timeout_ms=1000,
            description="날씨 기반 팁",
        ),
    ],
    "bulk_waste": [
        ContextSpec(
            "bulk_waste_context",
            ContextPriority.CRITICAL,
            timeout_ms=3000,
            fallback_on_timeout=True,
            description="대형폐기물 정보",
        ),
        ContextSpec(
            "weather_context",
            ContextPriority.LOW,
            timeout_ms=1000,
            description="수거일 날씨",
        ),
    ],
    "location": [
        ContextSpec(
            "location_context",
            ContextPriority.CRITICAL,
            timeout_ms=2000,
            fallback_on_timeout=True,
            description="gRPC 위치 정보",
        ),
        ContextSpec(
            "weather_context",
            ContextPriority.LOW,
            timeout_ms=1000,
            description="해당 지역 날씨",
        ),
    ],
    "collection_point": [
        ContextSpec(
            "collection_point_context",
            ContextPriority.CRITICAL,
            timeout_ms=3000,
            fallback_on_timeout=True,
            description="KECO 수거함 위치",
        ),
        ContextSpec(
            "weather_context",
            ContextPriority.LOW,
            timeout_ms=1000,
            description="방문 날씨",
        ),
    ],
    "general": [
        ContextSpec(
            "general_context",
            ContextPriority.HIGH,
            timeout_ms=2000,
            description="일반 대화 컨텍스트",
        ),
        ContextSpec(
            "web_search_results",
            ContextPriority.MEDIUM,
            timeout_ms=3000,
            description="웹 검색 보충",
        ),
    ],
    "character": [
        ContextSpec(
            "character_context",
            ContextPriority.HIGH,
            timeout_ms=1500,
            description="캐릭터 정보",
        ),
    ],
    "weather": [
        ContextSpec(
            "weather_context",
            ContextPriority.HIGH,
            timeout_ms=1500,
            description="날씨 정보",
        ),
    ],
    "web_search": [
        ContextSpec(
            "web_search_results",
            ContextPriority.HIGH,
            timeout_ms=5000,
            description="웹 검색 결과",
        ),
    ],
    "recyclable_price": [
        ContextSpec(
            "recyclable_price_context",
            ContextPriority.HIGH,
            timeout_ms=2000,
            description="재활용 시세",
        ),
    ],
    "image_generation": [
        ContextSpec(
            "image_generation_context",
            ContextPriority.HIGH,
            timeout_ms=10000,
            description="이미지 생성",
        ),
    ],
}


def get_contexts_by_priority(intent: str) -> list[ContextSpec]:
    """Intent의 컨텍스트를 우선순위 순으로 반환."""
    specs = CONTEXT_PRIORITY_MAP.get(intent, [])
    return sorted(specs, key=lambda s: s.priority.value)


def get_critical_contexts(intent: str) -> list[str]:
    """Intent의 필수(CRITICAL) 컨텍스트 필드 목록."""
    specs = CONTEXT_PRIORITY_MAP.get(intent, [])
    return [s.field for s in specs if s.priority == ContextPriority.CRITICAL]
```

### 5. JIT Loading Strategy (선택적)

대용량 컨텍스트를 즉시 로딩하지 않고 핸들만 저장하는 패턴:

```python
# apps/chat_worker/infrastructure/orchestration/langgraph/jit_context.py

from typing import TypedDict, Any, Protocol


class ContextHandle(TypedDict):
    """컨텍스트 핸들 (JIT 로딩용).

    대용량 데이터를 state에 직접 저장하지 않고
    로딩에 필요한 정보만 저장.
    """
    loaded: bool                    # 이미 로드됨?
    handle_type: str                # "redis", "grpc", "http"
    handle_key: str                 # Redis key, gRPC method, HTTP endpoint
    preview: dict[str, Any] | None  # 미리보기 (선택)
    ttl_seconds: int                # 핸들 유효 시간


class ContextLoader(Protocol):
    """컨텍스트 로더 프로토콜."""

    async def load(self, handle: ContextHandle) -> dict[str, Any]:
        """핸들로부터 실제 데이터 로드."""
        ...


# JIT 로딩 대상 컨텍스트
JIT_CONTEXTS = {
    "disposal_rules",       # RAG 결과 (문서 청크 다수)
    "web_search_results",   # 웹 검색 결과 (다수 URL)
}


# 사용 예시
async def answer_node_with_jit(state: dict, loader: ContextLoader) -> dict:
    """JIT 로딩을 적용한 answer_node."""

    # 필요한 컨텍스트 JIT 로드
    for field in JIT_CONTEXTS:
        handle = state.get(f"{field}_handle")
        if handle and not handle.get("loaded"):
            state[field] = await loader.load(handle)

    # 응답 생성
    answer = await generate_answer(state)
    return {"answer": answer}
```

**JIT 로딩 적용 시나리오**:

```
waste_rag 노드:
1. RAG 검색 수행 (10개 문서)
2. 결과를 Redis에 저장: SET rag:{job_id} {json}
3. Handle 반환: {"loaded": False, "handle_type": "redis", "handle_key": "rag:{job_id}"}

aggregator 노드:
- Handle 존재 확인만 (실제 로드 X)
- needs_fallback 판단

answer 노드:
1. Handle 감지
2. Redis에서 실제 데이터 로드
3. 응답 생성
```

---

## Implementation Plan

### Phase 1: ChatState 타입 적용

**파일 수정**:
- `apps/chat_worker/infrastructure/orchestration/langgraph/state.py`
- `apps/chat_worker/infrastructure/orchestration/langgraph/factory.py`

```python
# factory.py 수정
from .state import ChatState

# Before
graph = StateGraph(dict)

# After
graph = StateGraph(ChatState)
```

**검증**:
```bash
pytest apps/chat_worker/tests/unit/infrastructure/orchestration -v
```

### Phase 2: 노드 반환값 수정

**수정 대상 노드** (10개):
1. `rag_node.py` → `{"disposal_rules": ...}`
2. `bulk_waste_node.py` → `{"bulk_waste_context": ...}`
3. `location_node.py` → `{"location_context": ...}`
4. `collection_point_node.py` → `{"collection_point_context": ...}`
5. `character_node.py` → `{"character_context": ...}`
6. `weather_node.py` → `{"weather_context": ...}`
7. `web_search_node.py` → `{"web_search_results": ...}`
8. `recyclable_price_node.py` → `{"recyclable_price_context": ...}`
9. `image_generation_node.py` → `{"image_generation_context": ...}`
10. `general_node.py` → `{"general_context": ...}`

**수정 패턴**:
```python
# Before
return {**state, "my_context": output}

# After
return {"my_context": output}
```

### Phase 3: Dynamic Routing 활성화

**파일 수정**:
- `apps/chat_worker/setup/dependencies.py`

```python
# Before
enable_dynamic_routing=False,  # 임시 비활성화

# After
enable_dynamic_routing=True,   # 재활성화
```

**E2E 테스트**:
```bash
# API 호출
curl -X POST "https://api.dev.growbin.app/api/v1/chat" \
  -H "Cookie: s_access=$TOKEN" \
  -d '{"message": "플라스틱 어떻게 버려? 수거함도 알려줘"}'

# SSE 스트림 확인: waste_rag + collection_point 병렬 실행
```

### Phase 4: Aggregator Priority 적용 (선택)

**신규 파일**:
- `apps/chat_worker/infrastructure/orchestration/langgraph/aggregator_priority.py`

**aggregator_node.py 수정**:
```python
from .aggregator_priority import get_critical_contexts

# 기존 context_fields dict 대신 priority map 사용
critical = get_critical_contexts(intent)
```

### Phase 5: JIT Loading (선택)

대용량 컨텍스트가 성능 이슈를 일으킬 때 적용.

---

## Alternatives Considered

### 1. Subgraph Isolation

각 서브에이전트를 별도 Subgraph로 분리:

```python
waste_subgraph = StateGraph(WasteState)
weather_subgraph = StateGraph(WeatherState)

# 메인 그래프에서 subgraph 호출
main_graph.add_node("waste", waste_subgraph.compile())
```

**장점**: 완전한 격리, 독립적 테스트
**단점**: 복잡성 증가, 단순 도구 호출에 과도함

**결론**: 현재 서브에이전트는 단순 API 호출 수준이라 Channel Separation으로 충분.

### 2. Reducer Enforcement (모든 필드)

모든 필드에 reducer 적용:

```python
class ChatState(TypedDict):
    job_id: Annotated[str, last_value]
    message: Annotated[str, last_value]
    # ...
```

**장점**: 일관성
**단점**: 불필요한 오버헤드, Core 필드는 불변이라 reducer 불필요

**결론**: Context 필드만 선택적 reducer 적용.

---

## References

- [LangGraph Send API Documentation](https://langchain-ai.github.io/langgraph/how-tos/send-api/)
- [LangGraph State Reducers](https://langchain-ai.github.io/langgraph/concepts/low_level/#reducers)
- [contracts.py](../../apps/chat_worker/infrastructure/orchestration/langgraph/contracts.py) - 필드 요구사항 Single Source of Truth
- [dynamic_router.py](../../apps/chat_worker/infrastructure/orchestration/langgraph/routing/dynamic_router.py) - Send API 기반 라우팅
- [aggregator_node.py](../../apps/chat_worker/infrastructure/orchestration/langgraph/nodes/aggregator_node.py) - Fan-in 수집

---

## Race Condition Analysis

### 현재 안전성

Channel Separation 설계는 다음 두 가지 조건으로 Race Condition을 방지:

**1. 노드-채널 1:1 매핑**

```python
# contracts.py - 각 노드는 고유한 출력 채널을 가짐
NODE_OUTPUT_FIELDS = {
    "waste_rag": frozenset({"disposal_rules"}),      # 유일한 producer
    "weather": frozenset({"weather_context"}),        # 유일한 producer
    "collection_point": frozenset({"collection_point_context"}),  # 유일한 producer
    # ...
}
```

**2. 중복 Send 방지** (`dynamic_router.py`):

```python
activated_nodes: set[str] = set()

# Multi-intent에서도 같은 노드는 한 번만 Send
if node in activated_nodes:
    continue

sends.append(Send(node, state))
activated_nodes.add(node)
```

### Race Condition 발생 시나리오

**Scenario 1: 여러 노드가 같은 채널에 쓰는 경우**

```python
# 미래에 A/B 테스트 등으로 이런 구조가 생긴다면:
NODE_OUTPUT_FIELDS = {
    "waste_rag": frozenset({"disposal_rules"}),
    "waste_rag_v2": frozenset({"disposal_rules"}),  # 동일 채널!
}
```

병렬 실행 시:
```
Send("waste_rag", state)     → {"disposal_rules": result_v1}  ─┐
Send("waste_rag_v2", state)  → {"disposal_rules": result_v2}  ─┤ Race!
                                                               ↓
                              merge_context 호출 순서 = 도착 순서 (비결정적)
```

**Scenario 2: Enrichment 중복 트리거 (버그)**

`dynamic_router`에서 중복 체크가 누락되면:
```python
# Bug: activated_nodes 체크 없이 추가
if primary_intent in enrichment_rules:
    for node in enrichment_rules[primary_intent]:
        sends.append(Send(node, state))  # weather 추가

if "weather" in additional_intents:
    sends.append(Send("weather", state))  # weather 또 추가! (중복)
```

**Scenario 3: Retry/Fallback에서 재실행**

```python
# fallback 시 같은 노드 재실행
if needs_fallback:
    sends.append(Send("waste_rag", state))  # 이미 실행된 노드
```

### 현재 `merge_context` Reducer의 한계

```python
def merge_context(existing: dict | None, new: dict | None) -> dict | None:
    if new is None:
        return existing
    if existing is None:
        return new
    if new.get("success", True):
        return new  # Last Write Wins
    return existing
```

**문제점**: 둘 다 `success=True`면 **나중에 도착한 값이 승리** → 비결정적 결과

### 해결 방안

#### Option A: 노드-채널 1:1 강제 검증 (권장)

```python
# contracts.py에 Import-time 검증 추가
def validate_unique_channel_producers():
    """한 채널에 여러 노드가 쓰지 않는지 검증."""
    field_producers: dict[str, list[str]] = {}

    for node, fields in NODE_OUTPUT_FIELDS.items():
        for field in fields:
            if field not in field_producers:
                field_producers[field] = []
            field_producers[field].append(node)

    conflicts = {f: nodes for f, nodes in field_producers.items() if len(nodes) > 1}
    if conflicts:
        raise ValueError(f"Channel conflict: multiple producers for same channel: {conflicts}")

# Import-time 실행
validate_unique_channel_producers()
```

**장점**: 단순, 명확, 컴파일 타임 검증
**단점**: 같은 역할의 노드 여러 개 불가 (A/B 테스트 제한)

#### Option B: Priority Scheduling (OS 스케줄링 알고리즘 적용) ✅ 선택

운영체제 이론에서 검증된 **4가지 핵심 스케줄링 알고리즘**을 적용:

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    적용 스케줄링 알고리즘                                 │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  알고리즘                    │  역할                    │  적용 위치     │
│  ──────────────────────────┼────────────────────────┼──────────────── │
│  1. Priority Scheduling     │  우선순위 기반 선택      │  Reducer       │
│  2. Preemptive Scheduling   │  높은 우선순위가 선점    │  Reducer       │
│  3. Aging                   │  기아 방지, 대기 보상    │  Dynamic Prio  │
│  4. Lamport Clock           │  이벤트 순서 보장        │  Sequence      │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

##### 알고리즘 선택 근거

| 알고리즘 | 범용성 | 선택 이유 |
|----------|--------|----------|
| **Priority Scheduling** | ★★★★★ | 모든 OS의 기본, 가장 직관적 |
| **Preemptive Scheduling** | ★★★★★ | 현대 OS 표준, 응답성 보장 |
| **Aging** | ★★★★☆ | Starvation 방지의 표준 기법 |
| **Lamport Clock** | ★★★★★ | 분산 시스템 순서 보장의 de facto 표준 |

> **제외된 알고리즘**: MLFQ(복잡), PIP(RTOS 특화), CFS(Linux 특화)
> → 핵심 4가지로 동일한 효과 달성 가능

##### B.1 Priority Scheduling (Static Priority)

**정의**: 각 태스크에 우선순위를 부여하고, 높은 우선순위 태스크를 먼저 처리

```python
# apps/chat_worker/infrastructure/orchestration/langgraph/priority.py

from enum import IntEnum


class Priority(IntEnum):
    """우선순위 레벨.

    낮은 값 = 높은 우선순위 (0이 가장 높음)
    UNIX nice 값(-20~19)과 유사한 개념
    """
    CRITICAL = 0      # 필수 컨텍스트 (답변 생성에 반드시 필요)
    HIGH = 25         # 주요 서비스 (gRPC, 검색)
    NORMAL = 50       # 기본값
    LOW = 75          # Enrichment (부가 정보)
    BACKGROUND = 100  # 백그라운드 (로깅, 메트릭)


# 노드 → 정적 우선순위 매핑
NODE_PRIORITY: dict[str, Priority] = {
    # Critical: 이 컨텍스트 없으면 답변 불가
    "waste_rag": Priority.CRITICAL,
    "bulk_waste": Priority.CRITICAL,
    "location": Priority.CRITICAL,
    "collection_point": Priority.CRITICAL,

    # High: 주요 응답 품질에 영향
    "character": Priority.HIGH,
    "general": Priority.HIGH,
    "web_search": Priority.HIGH,

    # Normal: 일반
    "recyclable_price": Priority.NORMAL,
    "image_generation": Priority.NORMAL,

    # Low: 있으면 좋지만 없어도 됨
    "weather": Priority.LOW,
}
```

##### B.2 Preemptive Scheduling

**정의**: 높은 우선순위 태스크가 도착하면 현재 실행 중인 낮은 우선순위 태스크를 중단(선점)

LangGraph에서는 Reducer가 이 역할 수행:

```python
def preemptive_priority_reducer(
    existing: dict | None,
    new: dict | None,
) -> dict | None:
    """선점형 우선순위 Reducer.

    Preemptive Scheduling 원칙:
    - 높은 우선순위(낮은 값)가 낮은 우선순위를 선점
    - 동일 우선순위는 Lamport Clock(sequence)으로 결정

    Args:
        existing: 현재 채널에 있는 값
        new: 새로 도착한 값

    Returns:
        선점된(승리한) 값
    """
    if new is None:
        return existing
    if existing is None:
        return new

    # 실패한 결과는 성공한 결과에 선점됨
    if new.get("success") and not existing.get("success"):
        return new
    if existing.get("success") and not new.get("success"):
        return existing

    # 우선순위 비교 (Preemption)
    existing_priority = existing.get("_priority", Priority.NORMAL)
    new_priority = new.get("_priority", Priority.NORMAL)

    if new_priority < existing_priority:
        return new  # 높은 우선순위가 선점
    if new_priority > existing_priority:
        return existing

    # 동일 우선순위 → Lamport Clock으로 결정
    existing_seq = existing.get("_sequence", 0)
    new_seq = new.get("_sequence", 0)

    return new if new_seq >= existing_seq else existing
```

##### B.3 Aging

**정의**: 오래 대기한 태스크의 우선순위를 점진적으로 높여 기아(Starvation) 방지

```python
def calculate_effective_priority(
    base_priority: int,
    created_at: float,
    deadline_ms: int,
    is_fallback: bool = False,
) -> int:
    """유효 우선순위 계산 (Aging 적용).

    Aging 원칙:
    - 대기 시간이 길어질수록 우선순위 상승
    - deadline에 가까워질수록 더 급격히 상승

    Args:
        base_priority: 정적 우선순위
        created_at: 생성 시각 (timestamp)
        deadline_ms: 마감 시간 (ms)
        is_fallback: fallback 결과 여부

    Returns:
        조정된 우선순위 (낮을수록 높은 우선순위)
    """
    import time

    priority = base_priority

    # Aging: deadline 80% 경과 시 우선순위 부스트
    elapsed_ms = (time.time() - created_at) * 1000
    deadline_ratio = elapsed_ms / deadline_ms

    if deadline_ratio > 0.8:
        # 최대 20 부스트 (예: LOW 75 → HIGH 55)
        aging_boost = min(20, int((deadline_ratio - 0.8) * 100))
        priority -= aging_boost

    # Fallback penalty: 원본보다 낮은 우선순위
    if is_fallback:
        priority += 15

    return max(0, min(100, priority))
```

##### B.4 Lamport Clock (Logical Clock)

**정의**: 분산 시스템에서 이벤트의 인과적 순서를 보장하는 논리적 시계

```python
# apps/chat_worker/infrastructure/orchestration/langgraph/sequence.py

from threading import Lock


class LamportClock:
    """Lamport Logical Clock 구현.

    Lamport Clock 규칙:
    1. 각 이벤트 발생 시 카운터 증가
    2. happens-before 관계 보장: a → b 이면 C(a) < C(b)

    LangGraph 적용:
    - job_id별 독립적인 카운터
    - 노드 실행마다 sequence 증가
    - Reducer에서 최신 결과 판단에 사용
    """

    def __init__(self):
        self._counters: dict[str, int] = {}
        self._lock = Lock()

    def tick(self, job_id: str) -> int:
        """이벤트 발생 시 호출. 카운터 증가 후 반환."""
        with self._lock:
            self._counters[job_id] = self._counters.get(job_id, 0) + 1
            return self._counters[job_id]

    def get(self, job_id: str) -> int:
        """현재 카운터 값 조회."""
        return self._counters.get(job_id, 0)

    def cleanup(self, job_id: str) -> None:
        """작업 완료 후 메모리 정리."""
        with self._lock:
            self._counters.pop(job_id, None)


# 싱글톤 인스턴스
_clock = LamportClock()


def get_sequence(job_id: str) -> int:
    """현재 job의 다음 sequence 번호 반환."""
    return _clock.tick(job_id)
```

##### B.5 통합: 컨텍스트 생성 헬퍼

4가지 알고리즘을 통합한 컨텍스트 생성:

```python
import time
from typing import Any


def create_context(
    data: dict[str, Any],
    producer: str,
    job_id: str,
    is_fallback: bool = False,
    deadline_ms: int = 5000,
) -> dict[str, Any]:
    """스케줄링 메타데이터가 포함된 컨텍스트 생성.

    적용 알고리즘:
    1. Priority Scheduling: 노드별 정적 우선순위
    2. Aging: deadline 기반 동적 우선순위 조정
    3. Lamport Clock: sequence로 순서 보장

    Args:
        data: 실제 컨텍스트 데이터
        producer: 생산 노드 이름
        job_id: 작업 ID
        is_fallback: fallback 결과 여부
        deadline_ms: 마감 시간

    Returns:
        메타데이터가 포함된 컨텍스트
    """
    created_at = time.time()
    base_priority = NODE_PRIORITY.get(producer, Priority.NORMAL)

    # Aging 적용
    effective_priority = calculate_effective_priority(
        base_priority=base_priority,
        created_at=created_at,
        deadline_ms=deadline_ms,
        is_fallback=is_fallback,
    )

    # Lamport Clock
    sequence = get_sequence(job_id)

    return {
        # 스케줄링 메타데이터
        "_priority": effective_priority,
        "_sequence": sequence,
        "_producer": producer,
        "_created_at": created_at,
        "_is_fallback": is_fallback,
        # 실제 데이터
        "success": True,
        **data,
    }
```

##### B.6 노드 반환값 예시

```python
# weather_node.py
async def weather_node(state: dict[str, Any]) -> dict[str, Any]:
    job_id = state.get("job_id", "")
    output = await command.execute(input_dto)

    return {
        "weather_context": create_context(
            data={
                "temperature": output.temperature,
                "condition": output.condition,
                "tip": output.disposal_tip,
            },
            producer="weather",
            job_id=job_id,
        )
    }


# waste_rag_node.py (fallback 시)
async def waste_rag_fallback(state: dict[str, Any]) -> dict[str, Any]:
    job_id = state.get("job_id", "")
    output = await web_search_fallback(state)

    return {
        "disposal_rules": create_context(
            data={"source": "web_search", "results": output.results},
            producer="waste_rag",
            job_id=job_id,
            is_fallback=True,  # fallback 표시 → 우선순위 하락
        )
    }
```

##### B.7 Reducer 동작 예시

```
시나리오: waste_rag와 waste_rag_v2가 동시 실행 (A/B 테스트)

waste_rag (먼저 완료):
  {_priority: 0, _sequence: 1, success: true, ...}

waste_rag_v2 (나중 완료):
  {_priority: 0, _sequence: 2, success: true, ...}

Reducer 판단:
  1. priority 동일 (0 == 0)
  2. sequence 비교 → v2가 최신 (2 > 1)
  → v2 선택
```

```
시나리오: waste_rag 실패 → web_search fallback

1차 (waste_rag 실패):
  {_priority: 0, _sequence: 1, success: false, error: "timeout"}

2차 (fallback 성공):
  {_priority: 15, _sequence: 2, success: true, _is_fallback: true, ...}

Reducer 판단:
  1. success 비교 → 2차가 success
  → 2차 선택 (fallback이지만 성공한 결과)
```

**장점**:
- **단순성**: 4가지 기본 알고리즘만 사용
- **범용성**: OS 이론 교과서 수준의 표준 개념
- **결정성**: 도착 순서와 무관한 결정적 병합
- **확장성**: A/B 테스트, Fallback 자연스럽게 지원

**단점**:
- 메타데이터 오버헤드 (`_priority`, `_sequence` 등)
- 디버깅 시 우선순위 흐름 추적 필요

#### Option C: List Accumulator + Aggregator 선택

```python
def accumulate_contexts(existing: list | None, new: dict | None) -> list:
    """모든 결과를 리스트로 누적."""
    if existing is None:
        existing = []
    if new is not None:
        existing.append(new)
    return existing
```

Aggregator에서 최종 선택:
```python
# aggregator_node.py
disposal_results = state.get("disposal_rules", [])
# 가장 높은 confidence 선택
best_result = max(
    [r for r in disposal_results if r.get("success")],
    key=lambda r: r.get("confidence", 0),
    default=None,
)
state["disposal_rules"] = best_result
```

**장점**: 모든 결과 보존, aggregator에서 유연한 선택
**단점**: 메모리 증가, aggregator 로직 복잡

### 권장 구현: Option B (Priority Scheduling)

OS 스케줄링 개념을 적용한 Priority-based 병합으로 결정.

#### 구현 파일 구조

```
apps/chat_worker/infrastructure/orchestration/langgraph/
├── priority.py          # 신규: Priority 시스템
│   ├── PriorityLevel (IntEnum)
│   ├── ContextMetadata (dataclass)
│   ├── NODE_BASE_PRIORITY (dict)
│   ├── create_context_with_priority()
│   └── priority_preemptive_reducer()
│
├── sequence.py          # 신규: Lamport Clock
│   ├── SequenceGenerator
│   └── get_sequence(job_id)
│
├── state.py             # 수정: Reducer 교체
│   └── Annotated[..., priority_preemptive_reducer]
│
└── nodes/*.py           # 수정: 반환값에 priority 메타데이터
```

#### 단계별 구현

**Phase 1: Priority 시스템 구축**
```python
# priority.py 신규 생성
- PriorityLevel enum
- ContextMetadata dataclass
- NODE_BASE_PRIORITY 매핑
- create_context_with_priority() 헬퍼
- priority_preemptive_reducer() 함수
```

**Phase 2: Sequence Generator (Lamport Clock)**
```python
# sequence.py 신규 생성
from threading import Lock

class SequenceGenerator:
    """Job별 Lamport Clock 구현."""

    def __init__(self):
        self._sequences: dict[str, int] = {}
        self._lock = Lock()

    def next(self, job_id: str) -> int:
        with self._lock:
            seq = self._sequences.get(job_id, 0) + 1
            self._sequences[job_id] = seq
            return seq

    def cleanup(self, job_id: str) -> None:
        with self._lock:
            self._sequences.pop(job_id, None)


_generator = SequenceGenerator()

def get_sequence(job_id: str) -> int:
    return _generator.next(job_id)
```

**Phase 3: State 수정**
```python
# state.py 수정
from .priority import priority_preemptive_reducer

class ChatState(TypedDict, total=False):
    # Context 채널들: merge_context → priority_preemptive_reducer
    disposal_rules: Annotated[dict[str, Any] | None, priority_preemptive_reducer]
    weather_context: Annotated[dict[str, Any] | None, priority_preemptive_reducer]
    # ...
```

**Phase 4: 노드 수정**
```python
# 각 노드에서 create_context_with_priority() 사용
return {
    "weather_context": create_context_with_priority(
        data={...},
        producer="weather",
        channel="weather_context",
        confidence=0.95,
    )
}
```

#### Fallback 재시도 시나리오

```
waste_rag 실패 → web_search fallback

1차 시도 (waste_rag):
  disposal_rules = {
    _meta: { priority: 10 (CRITICAL), sequence: 1, is_fallback: false }
    success: false,
    error: "RAG timeout"
  }

2차 시도 (web_search fallback):
  disposal_rules = {
    _meta: { priority: 25 (CRITICAL+15), sequence: 2, is_fallback: true }
    success: true,
    data: {...}
  }

Reducer 결과:
  - 2차가 success=true이므로 선점
  - is_fallback=true로 aggregator에서 품질 저하 인지 가능
```

#### A/B 테스트 시나리오

```
waste_rag_v1 vs waste_rag_v2 동시 실행

waste_rag_v1:
  disposal_rules = {
    _meta: { priority: 10, sequence: 1, confidence: 0.85 }
    ...
  }

waste_rag_v2:
  disposal_rules = {
    _meta: { priority: 10, sequence: 2, confidence: 0.92 }
    ...
  }

Reducer 결과:
  - priority 동일 → sequence 비교 → v2가 최신
  - v2 선택 (confidence도 높음)
```

### 체크리스트

- [ ] `priority.py` 신규 생성
  - [ ] PriorityLevel enum
  - [ ] ContextMetadata dataclass
  - [ ] NODE_BASE_PRIORITY 매핑
  - [ ] create_context_with_priority()
  - [ ] priority_preemptive_reducer()
- [ ] `sequence.py` 신규 생성
  - [ ] SequenceGenerator 클래스
  - [ ] get_sequence() 함수
- [ ] `state.py` 수정
  - [ ] Context 채널들 reducer 교체
- [ ] 각 노드 수정 (10개)
  - [ ] `{**state, ...}` → `create_context_with_priority()` 변경
- [ ] 단위 테스트
  - [ ] priority_preemptive_reducer 테스트
  - [ ] SequenceGenerator 동시성 테스트
- [ ] 통합 테스트
  - [ ] A/B 테스트 시나리오
  - [ ] Fallback 재시도 시나리오

---

## Open Questions

### 결정됨

1. ~~**Race Condition 대응 수준**: Option A (1:1 강제) vs Option B (Priority)?~~
   - **결정**: Option B (Priority Scheduling) 선택
   - OS 스케줄링 개념 적용으로 결정적(Deterministic) 병합 보장

2. ~~**merge_context reducer 정책**: `success=False`일 때 기존 값 유지 vs 새 값으로 교체?~~
   - **결정**: Priority Preemptive Reducer로 대체
   - success=true가 success=false를 선점, 동일 시 priority/sequence/confidence 순 비교

### 논의 필요

3. **Aging 부스트 임계값**: deadline의 몇 %에서 우선순위 상승?
   - 현재 제안: 80% (3000ms deadline → 2400ms 경과 시 부스트 시작)
   - 고려사항: 너무 빠르면 불필요한 부스트, 너무 늦으면 효과 없음

4. **Fallback Penalty 값**: fallback 결과의 우선순위 페널티?
   - 현재 제안: +15 (CRITICAL 10 → 25로 하락)
   - 고려사항: 너무 크면 fallback이 무시됨, 너무 작으면 원본과 충돌

5. **Priority Inheritance 적용 범위**: 어떤 의존성에 적용?
   - 현재 제안: `waste_rag → character`, `answer → weather`
   - 고려사항: 모든 의존성에 적용 시 복잡성 증가

6. **Sequence Generator 구현**: 메모리 vs Redis?
   - 옵션 A: 로컬 메모리 (단일 워커)
   - 옵션 B: Redis INCR (분산 워커)
   - 현재 제안: 옵션 A (단일 워커 환경)

7. **JIT Loading 범위**: 어떤 컨텍스트에 JIT 적용?
   - 현재 제안: `disposal_rules`, `web_search_results` (대용량 가능성)
   - Phase 5에서 성능 측정 후 결정

8. **Timeout 정책**: 노드별 timeout을 어디서 관리?
   - 옵션 A: `ContextMetadata.deadline_ms`에서 정적 정의
   - 옵션 B: NodeExecutor 설정에서 동적 조회
   - 현재 제안: 옵션 A (단순성)

---

## Appendix: 적용 알고리즘 상세

### A.1 Priority Scheduling

**출처**: 운영체제 이론 기초 (모든 OS 교과서)

```
정의:
- 각 프로세스에 우선순위(priority number) 부여
- 높은 우선순위 프로세스 먼저 실행
- 낮은 숫자 = 높은 우선순위 (관례)

종류:
- Static Priority: 생성 시 고정
- Dynamic Priority: 실행 중 변경 가능

문제점:
- Starvation: 낮은 우선순위가 영원히 실행 안 됨
- 해결: Aging 적용

우리 시스템:
- Priority enum (0=CRITICAL ~ 100=BACKGROUND)
- NODE_PRIORITY로 노드별 정적 우선순위 부여
- Reducer에서 우선순위 비교
```

### A.2 Preemptive Scheduling

**출처**: 현대 운영체제의 표준 방식

```
정의:
- 실행 중인 프로세스를 강제로 중단하고 다른 프로세스 실행
- 높은 우선순위 도착 시 현재 프로세스 선점(preempt)

vs Non-preemptive:
- Non-preemptive: 현재 프로세스가 자발적으로 CPU 양보할 때까지 대기
- Preemptive: 더 중요한 작업 도착 시 즉시 전환

우리 시스템:
- Reducer가 선점 역할
- 높은 우선순위 컨텍스트가 낮은 것을 덮어씀
- 이미 저장된 값도 더 좋은 값이 오면 교체
```

### A.3 Aging

**출처**: Starvation 방지 기법 (범용)

```
정의:
- 대기 시간에 비례하여 우선순위 점진적 상승
- 오래 기다린 프로세스가 결국 실행되도록 보장

공식 (일반적):
  effective_priority = base_priority - (wait_time * aging_factor)

변형:
- Linear Aging: 일정 비율로 상승
- Threshold Aging: 임계값 초과 시 급격히 상승

우리 시스템:
- deadline의 80% 경과 시 부스트 시작
- 최대 20 포인트 부스트 (LOW 75 → HIGH 55)
- Fallback은 +15 페널티 (원본 우선)
```

### A.4 Lamport Clock (Logical Clock)

**출처**: Leslie Lamport, "Time, Clocks, and the Ordering of Events in a Distributed System" (1978)

```
정의:
- 분산 시스템에서 이벤트 순서를 결정하는 논리적 시계
- 물리적 시간이 아닌 인과 관계(causality) 기반

규칙:
1. 각 프로세스는 로컬 카운터 C 유지
2. 이벤트 발생 시: C = C + 1
3. 메시지 전송 시: 메시지에 C 포함
4. 메시지 수신 시: C = max(C, received_C) + 1

성질:
- a → b (a가 b보다 먼저 발생) 이면 C(a) < C(b)
- 역은 성립 안 함 (동시 발생 가능)

우리 시스템:
- job_id별 독립적 카운터
- 노드 실행마다 tick() 호출
- 동일 우선순위일 때 sequence로 최신 결과 판단
```

### A.5 알고리즘 조합 흐름

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         알고리즘 적용 흐름                               │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  노드 실행 시작                                                          │
│       │                                                                  │
│       ▼                                                                  │
│  ┌─────────────────────────────────────────┐                            │
│  │ 1. Priority Scheduling                  │                            │
│  │    base_priority = NODE_PRIORITY[node]  │                            │
│  └─────────────────────────────────────────┘                            │
│       │                                                                  │
│       ▼                                                                  │
│  ┌─────────────────────────────────────────┐                            │
│  │ 2. Aging                                │                            │
│  │    effective = base - aging_boost       │                            │
│  │    if fallback: effective += penalty    │                            │
│  └─────────────────────────────────────────┘                            │
│       │                                                                  │
│       ▼                                                                  │
│  ┌─────────────────────────────────────────┐                            │
│  │ 3. Lamport Clock                        │                            │
│  │    sequence = clock.tick(job_id)        │                            │
│  └─────────────────────────────────────────┘                            │
│       │                                                                  │
│       ▼                                                                  │
│  노드 결과 반환: {_priority, _sequence, data...}                         │
│       │                                                                  │
│       ▼                                                                  │
│  ┌─────────────────────────────────────────┐                            │
│  │ 4. Preemptive Scheduling (Reducer)      │                            │
│  │    if new._priority < existing._priority│                            │
│  │        → new 선점                        │                            │
│  │    elif same priority                   │                            │
│  │        → sequence 큰 것 선택             │                            │
│  └─────────────────────────────────────────┘                            │
│       │                                                                  │
│       ▼                                                                  │
│  최종 상태 저장                                                          │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```
