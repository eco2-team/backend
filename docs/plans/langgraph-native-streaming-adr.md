# LangGraph Native Streaming Architecture ADR

> LangGraph 1.0+ 네이티브 스트리밍으로 토큰 스트리밍 개선

**작성일**: 2026-01-16
**상태**: Draft
**선행 문서**: [Token Streaming Improvement ADR](./token-streaming-improvement-adr.md)

---

## 1. 개요

### 1.1 현재 구현 방식

```
┌─────────────────────────────────────────────────────────────────┐
│                   현재: Manual Token Streaming                   │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ProcessChatCommand                                              │
│       │                                                          │
│       │ await pipeline.ainvoke(state)  ← 전체 완료까지 대기     │
│       │                                                          │
│       ▼                                                          │
│  LangGraph Pipeline                                              │
│       │                                                          │
│       ├─→ intent_node (이벤트 수동 발행)                         │
│       │       └─→ notify_stage("intent", "started")             │
│       │       └─→ notify_stage("intent", "completed")           │
│       │                                                          │
│       ├─→ [subagent nodes...] (각자 수동 발행)                  │
│       │                                                          │
│       └─→ answer_node (토큰 수동 발행)                          │
│               └─→ async for token in command.execute():         │
│                       notify_token(content=token)  ← 수동!      │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### 1.2 문제점

| 문제 | 영향 |
|------|------|
| `ainvoke` 사용 | 파이프라인 완료까지 단일 응답, 중간 이벤트 없음 |
| 수동 토큰 발행 | 각 노드에서 `notify_token` 직접 호출 필요 |
| 노드별 이벤트 분산 | 이벤트 발행 로직이 모든 노드에 중복 |
| 메타데이터 부재 | 어떤 노드에서 발생한 토큰인지 알 수 없음 |

---

## 2. LangGraph 1.0+ 네이티브 스트리밍

### 2.1 지원 모드

```python
# LangGraph 1.0+ 스트리밍 옵션

# Option 1: stream_mode로 단일 모드 선택
async for event in graph.astream(state, stream_mode="messages"):
    print(event)

# Option 2: astream_events로 세밀한 이벤트 스트리밍
async for event in graph.astream_events(state, version="v2"):
    print(event)

# Option 3: 다중 stream_mode 조합
async for event in graph.astream(state, stream_mode=["values", "messages"]):
    print(event)
```

### 2.2 Stream Modes 비교

| Mode | 설명 | 출력 |
|------|------|------|
| `values` | 각 노드 완료 시 전체 state | `{"intent": "waste", "answer": "..."}` |
| `updates` | 각 노드의 state 변경분만 | `{"intent": "waste"}` |
| `messages` | LLM 토큰 스트리밍 (AIMessage) | `AIMessageChunk(content="플")` |
| `custom` | 사용자 정의 이벤트 | `{"type": "my_event", "data": ...}` |
| `debug` | 디버그 정보 포함 | 내부 상태 |

### 2.3 astream_events 이벤트 타입

```python
# LangGraph astream_events (v2) 이벤트 종류

# 1. 체인/노드 이벤트
"on_chain_start"      # 노드 시작
"on_chain_end"        # 노드 완료
"on_chain_stream"     # 노드 스트림 데이터

# 2. LLM 이벤트 (토큰 스트리밍 핵심)
"on_llm_start"        # LLM 호출 시작
"on_llm_stream"       # 토큰 스트림 ← 토큰 스트리밍!
"on_llm_end"          # LLM 호출 완료

# 3. 도구/검색 이벤트
"on_tool_start"       # 도구 호출 시작
"on_tool_end"         # 도구 호출 완료
"on_retriever_start"  # 검색 시작
"on_retriever_end"    # 검색 완료

# 4. 커스텀 이벤트 (LangGraph 1.0+)
"on_custom_event"     # 사용자 정의 이벤트
```

### 2.4 메타데이터 구조

```python
# astream_events 이벤트 메타데이터

event = {
    "event": "on_llm_stream",
    "name": "ChatOpenAI",
    "run_id": "uuid...",
    "metadata": {
        "langgraph_node": "answer",      # 현재 노드명
        "langgraph_step": 5,             # 그래프 스텝
        "langgraph_triggers": ["aggregator"],
        "langgraph_path": ["__pregel_pull", "answer"],
        "thread_id": "session-123",      # config에서 전달됨
    },
    "data": {
        "chunk": AIMessageChunk(content="플")
    }
}
```

---

## 3. 전체 라우팅 구조

### 3.1 Pipeline Flow Diagram

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        Eco² Chat Pipeline (LangGraph)                        │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌─────────┐                                                                 │
│  │  START  │                                                                 │
│  └────┬────┘                                                                 │
│       │                                                                      │
│       ▼                                                                      │
│  ┌─────────┐   on_chain_start: intent                                       │
│  │ intent  │   on_llm_stream: intent 분류 토큰 (optional)                   │
│  │  node   │   on_chain_end: {intent, additional_intents, ...}              │
│  └────┬────┘                                                                 │
│       │                                                                      │
│       ├── image_url 있음? ──┐                                               │
│       │                     ▼                                                │
│       │               ┌─────────┐   on_chain_start: vision                  │
│       │               │ vision  │   on_llm_stream: 분류 결과 토큰           │
│       │               │  node   │   on_chain_end: {classification_result}   │
│       │               └────┬────┘                                            │
│       │                    │                                                 │
│       ▼◀───────────────────┘                                                 │
│  ┌─────────┐                                                                 │
│  │ router  │   (passthrough - routing 결정)                                  │
│  │  node   │                                                                 │
│  └────┬────┘                                                                 │
│       │                                                                      │
│       │ dynamic_router() → list[Send]                                        │
│       │                                                                      │
│       ├────────────────────────────────────────────────────────────────────┐ │
│       │              Send API (병렬 실행)                                   │ │
│       ├────────────────────────────────────────────────────────────────────┤ │
│       │                                                                    │ │
│       ▼                    ▼                    ▼                    ▼     │ │
│  ┌──────────┐        ┌──────────┐        ┌──────────┐        ┌──────────┐ │ │
│  │waste_rag │        │character │        │ location │        │ weather  │ │ │
│  │(Milvus)  │        │ (gRPC)   │        │ (Kakao)  │        │ (KMA)    │ │ │
│  └────┬─────┘        └────┬─────┘        └────┬─────┘        └────┬─────┘ │ │
│       │                   │                   │                   │       │ │
│       │                   │                   │                   │       │ │
│       ▼                   │                   │                   │       │ │
│  ┌──────────┐             │                   │                   │       │ │
│  │ feedback │             │                   │                   │       │ │
│  │ (LLM)    │             │                   │                   │       │ │
│  └────┬─────┘             │                   │                   │       │ │
│       │                   │                   │                   │       │ │
│       ├───────────────────┴───────────────────┴───────────────────┘       │ │
│       │                                                                    │ │
│       ▼                    ▼                    ▼                    ▼     │ │
│  ┌──────────┐        ┌──────────┐        ┌──────────┐        ┌──────────┐ │ │
│  │bulk_waste│        │web_search│        │collection│        │  image   │ │ │
│  │ (MOIS)   │        │ (DDG)    │        │  _point  │        │  _gen    │ │ │
│  └────┬─────┘        └────┬─────┘        └────┬─────┘        └────┬─────┘ │ │
│       │                   │                   │                   │       │ │
│       └───────────────────┴───────────────────┴───────────────────┘       │ │
│                                    │                                       │ │
│       ◀────────────────────────────┴───────────────────────────────────────┘ │
│       │                                                                      │
│       ▼                                                                      │
│  ┌──────────┐   on_chain_start: aggregator                                  │
│  │aggregator│   on_chain_end: {merged contexts}                             │
│  │  node    │   (서브에이전트 결과 병합)                                     │
│  └────┬─────┘                                                                │
│       │                                                                      │
│       ├── enable_summarization? ──┐                                         │
│       │                           ▼                                          │
│       │                    ┌──────────┐   on_llm_stream: 요약 토큰          │
│       │                    │summarize │                                      │
│       │                    │  node    │                                      │
│       │                    └────┬─────┘                                      │
│       │                         │                                            │
│       ▼◀────────────────────────┘                                            │
│  ┌──────────┐   on_chain_start: answer                                      │
│  │  answer  │   on_llm_stream: 답변 토큰 ★ (메인 토큰 스트리밍)             │
│  │   node   │   on_llm_end: 전체 응답 완료                                   │
│  └────┬─────┘   on_chain_end: {answer}                                      │
│       │                                                                      │
│       ▼                                                                      │
│  ┌─────────┐                                                                 │
│  │   END   │                                                                 │
│  └─────────┘                                                                 │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 3.2 Subagent 노드 상세

| Node | Intent | 데이터 소스 | 출력 Context |
|------|--------|------------|--------------|
| `waste_rag` | waste | Milvus Vector DB | `disposal_rules` |
| `character` | greeting, etc | Character gRPC | `character_context` |
| `location` | place_search | Kakao Local API | `location_context` |
| `bulk_waste` | bulk_waste | MOIS API (행정안전부) | `bulk_waste_context` |
| `weather` | weather, waste* | KMA API (기상청) | `weather_context` |
| `web_search` | web_search, fallback | DuckDuckGo/Tavily | `web_search_results` |
| `collection_point` | collection_point | KECO API | `collection_point_context` |
| `recyclable_price` | price | KECO API | `recyclable_price_context` |
| `image_generation` | image | OpenAI Responses | `image_generation_context` |
| `general` | general | passthrough | - |

### 3.3 Dynamic Routing 규칙

```python
# routing.py - create_dynamic_router()

def create_dynamic_router(
    enable_multi_intent: bool = True,
    enable_enrichment: bool = True,
    enable_conditional: bool = True,
):
    """
    Send API 기반 동적 라우팅.

    규칙:
    1. Multi-Intent Fanout
       - additional_intents → 각각 병렬 Send
       - 예: ["waste", "collection_point"] → Send("waste_rag"), Send("collection_point")

    2. Intent 기반 Enrichment
       - waste → weather (분리배출 + 날씨 팁)
       - bulk_waste → weather (대형폐기물 + 날씨)
       - location → weather (장소 + 날씨)

    3. Conditional Enrichment
       - user_location 있으면 weather 자동 추가
    """
```

---

## 4. 노드별 이벤트 명세

### 4.1 이벤트 타입 정의

```python
# 표준 이벤트 타입 (Stage Events)
class StageEvent:
    stage: str          # 노드명 (intent, rag, answer, ...)
    status: str         # started | completed | failed
    progress: int       # 0-100
    message: str        # UI 표시 메시지
    result: dict | None # 완료 시 결과

# 토큰 이벤트 (Token Events) - LangGraph 네이티브
class TokenEvent:
    stage: str = "token"
    node: str           # 발생 노드 (answer, summarize, ...)
    seq: int            # 시퀀스 번호
    content: str        # 토큰 내용

# 커스텀 이벤트 (Custom Events)
class CustomEvent:
    type: str           # 이벤트 타입
    node: str           # 발생 노드
    data: dict          # 이벤트 데이터
```

### 4.2 노드별 이벤트 시퀀스

```yaml
# 전체 이벤트 시퀀스 (정상 흐름)

1. queued:
   - stage: queued, status: started, progress: 0

2. intent:
   - on_chain_start → stage: intent, status: started, progress: 5
   - on_llm_stream  → (optional, intent 분류 토큰)
   - on_chain_end   → stage: intent, status: completed, progress: 10
   - result: {intent, additional_intents, rationale}

3. vision (optional):
   - on_chain_start → stage: vision, status: started, progress: 15
   - on_llm_stream  → 이미지 분류 토큰
   - on_chain_end   → stage: vision, status: completed, progress: 20
   - result: {classification_result}

4. router:
   - (passthrough, 이벤트 없음)

5. subagents (병렬):
   # waste_rag
   - on_chain_start     → stage: rag, status: started, progress: 25
   - on_retriever_start → stage: rag, status: searching
   - on_retriever_end   → stage: rag, status: retrieved
   - on_chain_end       → stage: rag, status: completed, progress: 35
   - result: {disposal_rules, evidence_count}

   # character
   - on_chain_start → stage: character, status: started
   - on_chain_end   → stage: character, status: completed

   # location
   - on_chain_start → stage: location, status: started
   - on_chain_end   → stage: location, status: completed

   # weather
   - on_chain_start → stage: weather, status: started
   - on_chain_end   → stage: weather, status: completed

   # ... (기타 서브에이전트)

6. feedback (waste_rag 후):
   - on_chain_start → stage: feedback, status: started, progress: 40
   - on_llm_stream  → (품질 평가 토큰)
   - on_chain_end   → stage: feedback, status: completed, progress: 50
   - result: {score, needs_fallback}

7. aggregator:
   - on_chain_start → stage: aggregate, status: started, progress: 55
   - on_chain_end   → stage: aggregate, status: completed, progress: 60
   - result: {merged_contexts}

8. summarize (optional):
   - on_chain_start → stage: summarize, status: started, progress: 65
   - on_llm_stream  → 요약 토큰
   - on_chain_end   → stage: summarize, status: completed, progress: 70

9. answer:
   - on_chain_start → stage: answer, status: started, progress: 70
   - on_llm_stream  → ★ 답변 토큰 (메인 스트리밍)
   - on_llm_stream  → 토큰...
   - on_llm_stream  → 토큰...
   - on_llm_end     → stage: answer, status: streaming_end
   - on_chain_end   → stage: answer, status: completed, progress: 100
   - result: {answer}

10. done:
    - stage: done, status: completed, progress: 100
    - result: {intent, answer, persistence}
```

### 4.3 Progress 설계 (Phase 기반)

동적 라우팅(Send API)에서는 서브에이전트가 **병렬 실행**되므로, 기존 순차적 Progress 맵은 부적합합니다.

#### 문제: 순차 Progress의 한계

```python
# 기존 설계 (문제점)
PROGRESS_MAP = {
    "rag_started": 25,      # waste_rag만 있다고 가정
    "rag_completed": 35,
}
# → 실제로는 waste_rag, character, location, weather가 병렬 실행!
# → character만 먼저 끝나면? 진행률이 어떻게 되어야 하나?
```

#### 해결: Phase 기반 Progress

```python
# Phase 기반 Progress (동적 라우팅 대응)

@dataclass
class PhaseProgress:
    """Phase별 Progress 범위."""
    start: int
    end: int

PHASE_PROGRESS = {
    # ─────────────────────────────────────────────────────
    # Phase 1: Understanding (0-20%)
    # ─────────────────────────────────────────────────────
    "queued": PhaseProgress(0, 0),
    "intent": PhaseProgress(5, 15),
    "vision": PhaseProgress(15, 20),      # optional

    # ─────────────────────────────────────────────────────
    # Phase 2: Information Gathering (20-55%)
    # → 동적 라우팅으로 1~10개 노드 병렬 실행
    # → 완료된 노드 수 기반으로 진행률 보간
    # ─────────────────────────────────────────────────────
    "subagents": PhaseProgress(20, 55),   # 병렬 실행 전체 구간

    # ─────────────────────────────────────────────────────
    # Phase 3: Synthesis (55-100%)
    # ─────────────────────────────────────────────────────
    "aggregator": PhaseProgress(55, 65),
    "summarize": PhaseProgress(65, 75),   # optional
    "answer": PhaseProgress(75, 95),
    "done": PhaseProgress(100, 100),
}

# 서브에이전트 노드 목록 (Send API 대상)
SUBAGENT_NODES = {
    "waste_rag",
    "character",
    "location",
    "bulk_waste",
    "weather",
    "web_search",
    "collection_point",
    "recyclable_price",
    "image_generation",
    "general",
    "feedback",  # waste_rag 후속
}
```

#### 동적 Progress 계산 로직

```python
class DynamicProgressTracker:
    """동적 라우팅 환경의 Progress 추적기."""

    def __init__(self):
        self._activated_subagents: set[str] = set()
        self._completed_subagents: set[str] = set()

    def on_subagent_start(self, node: str) -> None:
        """서브에이전트 시작 추적."""
        if node in SUBAGENT_NODES:
            self._activated_subagents.add(node)

    def on_subagent_end(self, node: str) -> None:
        """서브에이전트 완료 추적."""
        if node in SUBAGENT_NODES:
            self._completed_subagents.add(node)

    def calculate_progress(self, phase: str, status: str) -> int:
        """Phase와 상태에 따른 Progress 계산.

        Args:
            phase: 현재 Phase (intent, subagents, answer, ...)
            status: 상태 (started, completed)

        Returns:
            Progress 값 (0-100)
        """
        if phase not in PHASE_PROGRESS:
            return 0

        phase_range = PHASE_PROGRESS[phase]

        # 서브에이전트 Phase: 동적 계산
        if phase == "subagents":
            return self._calculate_subagent_progress()

        # 기타 Phase: 시작/완료에 따른 고정값
        return phase_range.start if status == "started" else phase_range.end

    def _calculate_subagent_progress(self) -> int:
        """서브에이전트 병렬 실행 진행률 계산.

        공식: base + (completed / total) * range
        예시:
          - 3개 활성화, 1개 완료: 20 + (1/3) * 35 = 32%
          - 5개 활성화, 3개 완료: 20 + (3/5) * 35 = 41%
        """
        total = len(self._activated_subagents)
        completed = len(self._completed_subagents)

        if total == 0:
            return PHASE_PROGRESS["subagents"].end  # 55%

        phase = PHASE_PROGRESS["subagents"]
        range_size = phase.end - phase.start  # 35

        return phase.start + int((completed / total) * range_size)
```

#### Progress 시나리오 예시

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    Progress 시나리오별 예시                                  │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  Scenario 1: intent=waste (2개 노드)                                        │
│  ───────────────────────────────────────                                    │
│  활성화: [waste_rag, weather]                                               │
│                                                                              │
│  이벤트 시퀀스:                                                             │
│  queued_started     → 0%                                                    │
│  intent_started     → 5%                                                    │
│  intent_completed   → 15%                                                   │
│  router             → 20% (subagents 시작)                                  │
│  waste_rag_started  → 20% (2개 중 0개 완료)                                │
│  weather_started    → 20%                                                   │
│  weather_completed  → 37% (2개 중 1개 완료: 20 + 0.5*35)                   │
│  waste_rag_completed→ 55% (2개 중 2개 완료)                                │
│  aggregator_started → 55%                                                   │
│  aggregator_completed→ 65%                                                  │
│  answer_started     → 75%                                                   │
│  answer_completed   → 95%                                                   │
│  done               → 100%                                                  │
│                                                                              │
│  ───────────────────────────────────────────────────────────────────────── │
│                                                                              │
│  Scenario 2: intent=waste + additional=[collection_point] (4개 노드)        │
│  ───────────────────────────────────────                                    │
│  활성화: [waste_rag, collection_point, weather, feedback]                   │
│                                                                              │
│  이벤트 시퀀스:                                                             │
│  ...intent → 15%                                                            │
│  router             → 20%                                                   │
│  weather_completed  → 29% (4개 중 1개: 20 + 0.25*35)                       │
│  collection_completed→ 37% (4개 중 2개: 20 + 0.5*35)                       │
│  waste_rag_completed→ 46% (4개 중 3개: 20 + 0.75*35)                       │
│  feedback_completed → 55% (4개 중 4개)                                     │
│  aggregator...                                                              │
│                                                                              │
│  ───────────────────────────────────────────────────────────────────────── │
│                                                                              │
│  Scenario 3: intent=general (1개 노드)                                      │
│  ───────────────────────────────────────                                    │
│  활성화: [general]                                                          │
│                                                                              │
│  router             → 20%                                                   │
│  general_completed  → 55% (1개 중 1개: 단일 노드 즉시 완료)                │
│  aggregator...                                                              │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

#### UI 구현 고려사항

```typescript
// Frontend: Progress 표시 전략

interface ProgressState {
  phase: string;           // 현재 Phase
  progress: number;        // 0-100
  subagentStatus?: {       // 서브에이전트 상세 (optional)
    total: number;
    completed: number;
    active: string[];
  };
}

// Progress Bar 렌더링
function renderProgress(state: ProgressState) {
  // 1. 메인 Progress Bar: 0-100%
  renderMainProgress(state.progress);

  // 2. Phase 라벨: "정보 수집 중..." 등
  renderPhaseLabel(state.phase);

  // 3. 서브에이전트 상세 (선택적)
  if (state.phase === "subagents" && state.subagentStatus) {
    renderSubagentDetail(
      `${state.subagentStatus.completed}/${state.subagentStatus.total} 완료`
    );
  }
}
```

---

## 5. 클라이언트 전달 메커니즘

### 5.1 전체 흐름

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                     Event Delivery Architecture                              │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │ Chat Worker (LangGraph Pipeline)                                      │   │
│  │                                                                       │   │
│  │  async for event in graph.astream_events(state, version="v2"):       │   │
│  │      │                                                                │   │
│  │      ├─ on_chain_start/end → notify_stage()                          │   │
│  │      │                                                                │   │
│  │      └─ on_llm_stream     → notify_token()                           │   │
│  │                               ↓                                       │   │
│  └───────────────────────────────┼──────────────────────────────────────┘   │
│                                  │                                          │
│                                  ▼                                          │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │ Redis Progress Notifier                                               │   │
│  │                                                                       │   │
│  │  1. Stage Events → chat:events:{shard} (Sharded Stream)              │   │
│  │  2. Token Events → chat:tokens:{job_id} (Job-specific Stream)        │   │
│  │  3. Token State  → chat:token_state:{job_id} (주기적 스냅샷)         │   │
│  │                                                                       │   │
│  └───────────────────────────────┼──────────────────────────────────────┘   │
│                                  │                                          │
│         ┌────────────────────────┴────────────────────────┐                 │
│         │                                                  │                 │
│         ▼                                                  ▼                 │
│  ┌─────────────────────┐                    ┌─────────────────────────┐     │
│  │ Redis Streams       │                    │ Redis Streams           │     │
│  │ chat:events:{shard} │                    │ chat:tokens:{job_id}    │     │
│  │ (4 shards)          │                    │ (job별 전용)            │     │
│  └──────────┬──────────┘                    └────────────┬────────────┘     │
│             │                                            │                  │
│             │ XREADGROUP                                 │ (복구용)         │
│             ▼                                            │                  │
│  ┌──────────────────────────────────────────────────────┼─────────────┐    │
│  │ Event Router                                          │             │    │
│  │                                                       │             │    │
│  │  1. Consumer Group으로 이벤트 소비                    │             │    │
│  │  2. Stage Event → State 저장 + Pub/Sub 발행          │             │    │
│  │  3. Token Event → Pub/Sub 발행 (State 선택적)        │             │    │
│  │                                                       │             │    │
│  └───────────────────────────────┼───────────────────────┼─────────────┘    │
│                                  │                       │                  │
│                                  ▼                       │                  │
│  ┌──────────────────────────────────────────────────────┼─────────────┐    │
│  │ Redis Pub/Sub                                         │             │    │
│  │ sse:events:{job_id}                                   │             │    │
│  │                                                       │             │    │
│  └───────────────────────────────┼───────────────────────┼─────────────┘    │
│                                  │                       │                  │
│                                  ▼                       │                  │
│  ┌──────────────────────────────────────────────────────┼─────────────┐    │
│  │ SSE Gateway                                           │             │    │
│  │                                                       │             │    │
│  │  1. Pub/Sub 구독 → 실시간 스트리밍                    │             │    │
│  │  2. Token catch-up ←──────────────────────────────────┘             │    │
│  │     (chat:tokens:{job_id}에서 누락 토큰 복구)                       │    │
│  │  3. Token State 복구                                                │    │
│  │     (chat:token_state:{job_id}에서 누적 텍스트)                     │    │
│  │                                                                     │    │
│  └───────────────────────────────┼─────────────────────────────────────┘    │
│                                  │                                          │
│                                  │ SSE (Server-Sent Events)                 │
│                                  ▼                                          │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │ Frontend (React)                                                      │   │
│  │                                                                       │   │
│  │  EventSource("/api/v1/chat/{job_id}/events?last_token_seq=N")        │   │
│  │                                                                       │   │
│  │  1. stage events → Progress UI 업데이트                               │   │
│  │  2. token events → Answer 실시간 타이핑                               │   │
│  │  3. token_recovery → 재연결 시 누적 텍스트 복구                       │   │
│  │  4. done event → 완료 처리                                            │   │
│  │                                                                       │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 5.2 SSE 이벤트 포맷

```typescript
// Frontend가 수신하는 SSE 이벤트 형식

// 1. Stage Event
event: stage
data: {
  "job_id": "job-123",
  "stage": "intent",
  "status": "completed",
  "progress": 10,
  "message": "의도 분류 완료",
  "result": {
    "intent": "waste",
    "additional_intents": ["weather"]
  }
}

// 2. Token Event
event: token
data: {
  "job_id": "job-123",
  "stage": "token",
  "seq": 1001,
  "content": "플라",
  "node": "answer"
}

// 3. Token Recovery Event (재연결 시)
event: token_recovery
data: {
  "job_id": "job-123",
  "stage": "token_recovery",
  "status": "snapshot",
  "accumulated": "플라스틱은 재활용...",
  "last_seq": 1050
}

// 4. Done Event
event: done
data: {
  "job_id": "job-123",
  "stage": "done",
  "status": "completed",
  "progress": 100,
  "result": {
    "intent": "waste",
    "answer": "플라스틱은 재활용..."
  }
}
```

### 5.3 Frontend 구현

```typescript
// React Hook: useSSEStream

function useChatSSE(jobId: string) {
  const [progress, setProgress] = useState(0);
  const [stage, setStage] = useState('queued');
  const [answer, setAnswer] = useState('');
  const [lastTokenSeq, setLastTokenSeq] = useState(0);

  useEffect(() => {
    // localStorage에서 마지막 seq 복구
    const savedSeq = localStorage.getItem(`token_seq_${jobId}`);
    const initialSeq = savedSeq ? parseInt(savedSeq, 10) : 0;

    const url = `/api/v1/chat/${jobId}/events?last_token_seq=${initialSeq}`;
    const eventSource = new EventSource(url);

    // Stage 이벤트
    eventSource.addEventListener('stage', (e) => {
      const data = JSON.parse(e.data);
      setStage(data.stage);
      setProgress(data.progress);
    });

    // Token 이벤트
    eventSource.addEventListener('token', (e) => {
      const data = JSON.parse(e.data);
      setAnswer(prev => prev + data.content);
      setLastTokenSeq(data.seq);

      // 10 토큰마다 저장
      if (data.seq % 10 === 0) {
        localStorage.setItem(`token_seq_${jobId}`, data.seq.toString());
      }
    });

    // Token Recovery (재연결 시)
    eventSource.addEventListener('token_recovery', (e) => {
      const data = JSON.parse(e.data);
      setAnswer(data.accumulated);
      setLastTokenSeq(data.last_seq);
    });

    // Done 이벤트
    eventSource.addEventListener('done', (e) => {
      const data = JSON.parse(e.data);
      setProgress(100);
      localStorage.removeItem(`token_seq_${jobId}`);
      eventSource.close();
    });

    return () => eventSource.close();
  }, [jobId]);

  return { progress, stage, answer };
}
```

---

## 6. 구현 설계

### 6.1 ProcessChatCommand 개선

```python
# process_chat.py - astream_events 적용

class ChatPipelinePort(Protocol):
    """Chat 파이프라인 Port (개선)."""

    async def astream_events(
        self,
        state: dict[str, Any],
        config: dict[str, Any] | None = None,
        version: str = "v2",
    ) -> AsyncIterator[dict[str, Any]]:
        """이벤트 스트리밍 파이프라인 실행."""
        ...


class ProcessChatCommand:
    async def execute(self, request: ProcessChatRequest) -> ProcessChatResponse:
        """네이티브 스트리밍으로 파이프라인 실행."""

        # 작업 시작 이벤트
        await self._progress_notifier.notify_stage(
            task_id=request.job_id,
            stage="queued",
            status="started",
            progress=0,
        )

        config = {
            "configurable": {"thread_id": request.session_id},
        }

        final_state = {}

        # 네이티브 스트리밍
        async for event in self._pipeline.astream_events(
            initial_state,
            config=config,
            version="v2",
        ):
            event_type = event.get("event")
            metadata = event.get("metadata", {})
            node_name = metadata.get("langgraph_node", "")

            # 노드 시작/완료 이벤트
            if event_type == "on_chain_start":
                await self._handle_chain_start(event, request.job_id)

            elif event_type == "on_chain_end":
                await self._handle_chain_end(event, request.job_id)
                # 최종 state 캡처
                if node_name == "answer":
                    final_state = event.get("data", {}).get("output", {})

            # LLM 토큰 스트리밍
            elif event_type == "on_llm_stream":
                await self._handle_llm_stream(event, request.job_id, node_name)

        # 완료 이벤트
        await self._progress_notifier.notify_stage(
            task_id=request.job_id,
            stage="done",
            status="completed",
            progress=100,
            result={
                "intent": final_state.get("intent"),
                "answer": final_state.get("answer"),
            },
        )

        return ProcessChatResponse(...)

    async def _handle_llm_stream(
        self,
        event: dict,
        job_id: str,
        node_name: str,
    ) -> None:
        """LLM 토큰 스트리밍 처리."""
        chunk = event.get("data", {}).get("chunk")
        if chunk and hasattr(chunk, "content") and chunk.content:
            await self._progress_notifier.notify_token_v2(
                task_id=job_id,
                content=chunk.content,
                node=node_name,  # 메타데이터로 노드명 전달
            )
```

### 6.2 Answer Node 간소화

```python
# answer_node.py - 토큰 발행 로직 제거

def create_answer_node(
    llm: "LLMClientPort",
    event_publisher: "ProgressNotifierPort",
    cache: "CachePort | None" = None,
):
    """답변 생성 노드 (간소화).

    LangGraph 네이티브 스트리밍 사용 시:
    - notify_token 제거 (상위 레벨에서 처리)
    - notify_stage는 유지 (Progress UI)
    """
    command = GenerateAnswerCommand(llm=llm, prompt_builder=prompt_builder, cache=cache)

    async def answer_node(state: dict[str, Any]) -> dict[str, Any]:
        job_id = state["job_id"]

        # Progress: 시작
        await event_publisher.notify_stage(
            task_id=job_id,
            stage="answer",
            status="started",
            progress=70,
        )

        try:
            # LangGraph가 토큰 스트리밍을 처리하므로
            # 여기서는 전체 응답만 수집
            answer_parts = []
            async for token in command.execute(input_dto):
                # notify_token 제거 - LangGraph 네이티브 스트리밍이 처리
                answer_parts.append(token)

            answer = "".join(answer_parts)

            # Progress: 완료
            await event_publisher.notify_stage(
                task_id=job_id,
                stage="answer",
                status="completed",
                progress=100,
            )

            return {**state, "answer": answer}

        except Exception as e:
            # 에러 처리
            ...

    return answer_node
```

### 6.3 ProgressNotifierPort 확장

```python
# progress_notifier.py - notify_token_v2 추가

class ProgressNotifierPort(Protocol):
    """진행 상황 알림 Port (확장)."""

    async def notify_stage(
        self,
        task_id: str,
        stage: str,
        status: str,
        progress: int | None = None,
        result: dict[str, Any] | None = None,
        message: str | None = None,
    ) -> str:
        """단계 이벤트 발행."""
        ...

    async def notify_token(
        self,
        task_id: str,
        content: str,
    ) -> str:
        """토큰 이벤트 발행 (기존)."""
        ...

    async def notify_token_v2(
        self,
        task_id: str,
        content: str,
        node: str | None = None,  # 발생 노드명
    ) -> str:
        """토큰 이벤트 발행 (개선 - 복구 가능)."""
        ...

    async def finalize_token_stream(self, task_id: str) -> None:
        """토큰 스트림 완료 처리."""
        ...

    def clear_token_counter(self, task_id: str) -> None:
        """토큰 카운터 정리."""
        ...
```

---

## 7. 구현 계획

### Phase 1: 기반 작업

```
1.1 ProgressNotifierPort 확장
    - notify_token_v2 시그니처 추가
    - finalize_token_stream 시그니처 추가

1.2 RedisProgressNotifier 개선
    - notify_token_v2 구현 (Token Stream + State)
    - finalize_token_stream 구현
    - 누적 텍스트 추적 로직
```

### Phase 2: Pipeline 네이티브 스트리밍

```
2.1 ChatPipelinePort 확장
    - astream_events 시그니처 추가

2.2 ProcessChatCommand 개선
    - ainvoke → astream_events 전환
    - 이벤트 핸들러 구현
    - Stage/Token 이벤트 발행 로직

2.3 Answer Node 간소화
    - notify_token 직접 호출 제거
    - notify_stage만 유지
```

### Phase 3: Event Router & SSE Gateway

```
3.1 Event Router 개선
    - Token 재시도 로직 추가
    - State 저장 로직 (선택적)

3.2 SSE Gateway 개선
    - subscribe_v2 구현
    - Token catch-up 로직
    - Token State 복구 로직
```

### Phase 4: Frontend

```
4.1 SSE 클라이언트 개선
    - last_token_seq 관리
    - token_recovery 이벤트 처리
    - localStorage 저장

4.2 UI 업데이트
    - Progress 표시
    - 답변 실시간 타이핑
```

---

## 8. 롤백 계획

### 하위 호환성

```
- 기존 ainvoke() 유지 (병행 운영)
- 기존 notify_token() 유지
- 기존 SSE 엔드포인트 유지
- Feature flag로 전환 제어
```

### 롤백 트리거

```
- Token 유실률 > 1%
- 레이턴시 증가 > 50ms
- 메모리 사용량 급증
```

---

## 9. 모니터링

### 메트릭

```python
# 추가 메트릭
STREAM_EVENTS_TOTAL = Counter("langgraph_stream_events_total", labels=["event_type", "node"])
TOKEN_STREAM_LATENCY = Histogram("token_stream_latency_seconds")
TOKEN_RECOVERY_COUNT = Counter("token_recovery_count_total")
NATIVE_STREAMING_ERRORS = Counter("native_streaming_errors_total", labels=["error_type"])
```

### 로그

```python
# 핵심 로그 포인트
logger.info("stream_event_received", extra={"event_type": ..., "node": ...})
logger.info("token_stream_started", extra={"job_id": ...})
logger.info("token_stream_completed", extra={"job_id": ..., "total_tokens": ...})
logger.warning("token_recovery_triggered", extra={"job_id": ..., "from_seq": ...})
```

---

## 10. 결론

### Before vs After

| 항목 | Before (ainvoke) | After (astream_events) |
|------|------------------|------------------------|
| 파이프라인 실행 | 전체 완료 대기 | 실시간 이벤트 스트림 |
| 토큰 발행 위치 | 각 노드에서 수동 | ProcessChatCommand에서 통합 |
| 메타데이터 | 없음 | node, step, triggers 포함 |
| 이벤트 타입 | stage, token | on_chain_*, on_llm_*, on_tool_* |
| 노드 상태 추적 | Progress 수동 계산 | 자동 (on_chain_start/end) |
| 토큰 복구 | 불가 | Token Stream + State |

### 핵심 개선

1. **LangGraph 네이티브 스트리밍**: `astream_events`로 통합 이벤트 처리
2. **메타데이터 활용**: 어떤 노드에서 발생한 토큰인지 추적
3. **토큰 복구**: Token Stream + State로 재연결 시 복구
4. **코드 간소화**: 각 노드의 이벤트 발행 로직 제거

---

## References

- [LangGraph Streaming](https://langchain-ai.github.io/langgraph/how-tos/streaming-tokens/)
- [LangGraph astream_events](https://langchain-ai.github.io/langgraph/how-tos/streaming-events-from-within-tools/)
- [Token Streaming Improvement ADR](./token-streaming-improvement-adr.md)
- [Event Bus Reliability Analysis](../reports/event-bus-reliability-analysis.md)
