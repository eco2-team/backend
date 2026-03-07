# Chat 서비스 Workflow 패턴 결정

> LangGraph Workflow/Agent 패턴 분석을 통한 Chat 서비스 최적 아키텍처 선택
>
> **참고**: [LangGraph Workflows + Agents](https://docs.langchain.com/oss/python/langgraph/workflows-agents)

---

## 1. 개요

### 1.1 Workflow vs Agent

| 구분 | Workflow | Agent |
|------|----------|-------|
| **흐름** | 사전 정의된 코드 경로 | LLM이 동적으로 결정 |
| **예측 가능성** | 높음 | 낮음 |
| **디버깅** | 용이 | 어려움 |
| **적합한 작업** | 구조화된 작업 | 탐색적 작업 |

```
Workflow:
A → B → C (고정된 경로)

Agent:
LLM ⇄ Tool ⇄ LLM (동적 루프)
```

### 1.2 Chat 서비스 요구사항

| 요구사항 | 설명 | 우선순위 |
|---------|------|---------|
| 이미지 분류 | 폐기물 이미지 → 분류 → 규정 → 답변 | 필수 |
| 텍스트 질의 | 의도 분류 → RAG → 답변 | 필수 |
| 실시간 피드백 | SSE로 진행 상황 스트리밍 | 필수 |
| 멀티 모델 | GPT, Gemini 지원 | 필수 |
| 복잡한 질의 | 멀티 카테고리 질문 처리 | 향후 |

---

## 2. LangGraph 패턴 분석

### 2.1 Prompt Chaining (순차 실행)

**특징**: 각 LLM 호출이 이전 결과를 처리, 검증 가능한 단계별 실행

```
A → (검증) → B → (검증) → C
```

**적용 가능성**: ⭐⭐⭐⭐⭐

- 이미지 파이프라인: `vision → rule → answer`
- 각 단계에서 결과 검증 가능
- SSE 이벤트 발행 용이

```python
# Prompt Chaining 예시
def check_classification(state):
    """분류 결과 검증 게이트."""
    if state["classification"]["confidence"] > 0.8:
        return "Pass"
    return "Fail"

workflow.add_conditional_edges(
    "vision",
    check_classification,
    {"Pass": "rule", "Fail": "retry_vision"}
)
```

---

### 2.2 Parallelization (병렬 실행)

**특징**: 독립적인 작업을 동시 실행, 속도 향상

```
    ┌→ A ─┐
START─┼→ B ─┼→ END
    └→ C ─┘
```

**적용 가능성**: ⭐⭐⭐

- 멀티 카테고리 질문에 적용 가능
- 예: 분리배출 규정 + 환경 정보 동시 조회

```python
# Parallelization 예시
graph.add_edge(START, "fetch_disposal_rules")
graph.add_edge(START, "fetch_location_info")
graph.add_edge(START, "fetch_character_info")

# 모든 병렬 작업 완료 후 합류
graph.add_edge("fetch_disposal_rules", "aggregator")
graph.add_edge("fetch_location_info", "aggregator")
graph.add_edge("fetch_character_info", "aggregator")
```

**주의**: SSE 이벤트 순서 관리 필요

---

### 2.3 Routing (조건부 분기)

**특징**: 입력에 따라 다른 경로로 분기

```
         ┌→ waste_rag ─┐
START → 의도분류 ─┼→ character ─┼→ answer
         └→ location ──┘
```

**적용 가능성**: ⭐⭐⭐⭐⭐

- 텍스트 의도 분류 필수
- 이미지/텍스트 입력 분기 필수

```python
# Routing 예시
def route_by_intent(state):
    """의도에 따라 분기."""
    intent = state["intent"]
    if intent == "waste":
        return "waste_rag"
    elif intent == "character":
        return "character_info"
    elif intent == "location":
        return "location_tool"
    return "general_answer"

graph.add_conditional_edges(
    "intent_classifier",
    route_by_intent,
    {
        "waste_rag": "waste_rag",
        "character_info": "character_info",
        "location_tool": "location_tool",
        "general_answer": "general_answer",
    }
)
```

---

### 2.4 Orchestrator-Worker (동적 작업자)

**특징**: LLM이 작업을 분해하고 워커에 할당

```
         ┌─ Worker 1 ─┐
Orchestrator ─┼─ Worker 2 ─┼→ Synthesizer
         └─ Worker 3 ─┘
```

**적용 가능성**: ⭐⭐

- 복잡한 보고서 생성에 적합
- Chat 서비스에는 과도한 복잡성

```python
# Orchestrator-Worker 예시 (향후 확장 시)
def orchestrator(state):
    """LLM이 작업 분해."""
    response = llm.invoke(
        f"Break down: {state['question']}"
    )
    return {"sections": response.sections}

def assign_workers(state):
    """동적 워커 할당."""
    return [
        Send("worker", {"section": s})
        for s in state["sections"]
    ]
```

---

### 2.5 Evaluator-Optimizer (평가-최적화 루프)

**특징**: 결과 평가 → 피드백 → 재생성 루프

```
Generator → Evaluator → (Pass) → END
              ↓ (Fail)
           Feedback → Generator
```

**적용 가능성**: ⭐⭐⭐

- 답변 품질 향상에 유용
- 지연 시간 증가 우려

```python
# Evaluator-Optimizer 예시
class AnswerEvaluation(BaseModel):
    is_complete: bool
    feedback: str | None

def evaluate_answer(state):
    """답변 평가."""
    eval_result = evaluator_llm.invoke(
        f"Evaluate: {state['answer']}"
    )
    return {
        "evaluation": eval_result.is_complete,
        "feedback": eval_result.feedback
    }

def route_by_evaluation(state):
    if state["evaluation"]:
        return "done"
    return "regenerate"

graph.add_conditional_edges(
    "evaluator",
    route_by_evaluation,
    {"done": END, "regenerate": "generator"}
)
```

---

### 2.6 Agent (도구 사용 에이전트)

**특징**: LLM이 도구 사용 여부와 순서를 동적 결정

```
    ┌────────────────┐
    ↓                |
LLM → Tool Call? → Yes → Execute → LLM
    ↓ No
   END
```

**적용 가능성**: ⭐⭐

- 탐색적 질문에 유용
- 예측 불가능한 흐름
- 디버깅 어려움

```python
# Agent 예시 (복잡한 질의 처리 시)
@tool
def search_disposal_rules(query: str) -> str:
    """폐기물 분리배출 규정 검색."""
    return rag.search(query)

@tool
def get_nearby_centers(location: str) -> str:
    """주변 재활용 센터 조회."""
    return location_api.search(location)

llm_with_tools = llm.bind_tools([
    search_disposal_rules,
    get_nearby_centers,
])

def should_continue(state):
    last_message = state["messages"][-1]
    if last_message.tool_calls:
        return "tool_node"
    return END
```

---

## 3. Chat 서비스 패턴 결정

### 3.1 결정 매트릭스

| 패턴 | 이미지 | 텍스트 | SSE 호환 | 복잡도 | 총점 |
|------|--------|--------|---------|--------|------|
| Prompt Chaining | ⭐⭐⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | 18 |
| Routing | ⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ | 17 |
| Parallelization | ⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐ | 11 |
| Evaluator-Optimizer | ⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐ | 11 |
| Orchestrator-Worker | ⭐⭐ | ⭐⭐ | ⭐⭐ | ⭐⭐ | 8 |
| Agent | ⭐⭐ | ⭐⭐ | ⭐⭐ | ⭐ | 7 |

### 3.2 최종 결정: Intent-Routed Workflow with Subagent

**핵심 패턴 조합**:

1. **Routing** - 입력 유형/의도에 따른 분기
2. **Prompt Chaining** - 각 분기 내 순차 실행
3. **Subagent** - 컨텍스트 격리 + 병렬 처리 (복잡한 질문)
4. **Tool Calling** - 외부 서비스 연동
5. **Evaluator-Optimizer** - (선택) 답변 품질 검증

```
Chat Service Workflow (Subagent 포함)
=====================================

START
  │
  v
[Input Router]
  │
  ├─ image? ──▶ [Vision] → [Rule RAG] → [Answer]
  │
  └─ text? ──▶ [Intent Classifier]
                    │
                    ├─ simple ──▶ [Single Node] ────────┐
                    │                                   │
                    └─ complex ──▶ [Decomposer]         │
                                       │                │
                              ┌────────┼────────┐       │
                              v        v        v       │
                         [waste]  [location] [char]     │
                         Expert    Expert    Expert     │
                              │        │        │       │
                              └────────┼────────┘       │
                                       v                │
                                  [Synthesizer] ────────┤
                                                        v
                                                   [Answer]
                                                        │
                                                       END
```

**Subagent 적용 기준:**
- **단순 질문**: 단일 노드로 처리 (기존 방식)
- **복잡한 질문**: Subagent로 분해 → 병렬 처리 → 합성

---

## 4. 상세 설계

### 4.1 ChatState 정의

```python
from typing import TypedDict, Literal
from dataclasses import dataclass


class ChatState(TypedDict):
    """Chat 파이프라인 상태.
    
    LangGraph는 State 기반 오케스트레이션을 제공.
    단순 체이닝이 아닌 상태 전이를 통한 흐름 제어.
    """
    
    # 입력
    job_id: str
    user_id: str
    message: str
    image_url: str | None
    model: str
    
    # 🆕 대화 히스토리 (컨텍스트 관리)
    messages: list[dict]  # [{"role": "user/assistant", "content": "..."}]
    
    # 라우팅
    input_type: Literal["image", "text"] | None
    intent: Literal[
        "waste", "character", "character_preview", 
        "location", "general"
    ] | None
    
    # 중간 결과
    classification: dict | None  # Vision 결과
    disposal_rules: dict | None  # RAG 결과
    tool_results: dict | None    # Tool 호출 결과
    context: str | None          # 검색된 컨텍스트
    
    # 최종 결과
    answer: str | None
    
    # 메타데이터
    latencies: dict
```

### 4.2 컨텍스트 관리 (오케스트레이션 핵심)

**LangChain vs LangGraph 비교:**

```
LangChain (단순 체이닝):
┌────────┐    ┌────────┐    ┌────────┐
│ Step A │ →  │ Step B │ →  │ Step C │
└────────┘    └────────┘    └────────┘
- 선형 흐름, 상태 없음
- 대화 히스토리는 외부에서 관리

LangGraph (상태 기반 오케스트레이션):
           ┌─────────────────────────┐
           │       ChatState         │
           │  - messages (히스토리)   │
           │  - intent (라우팅 키)    │
           │  - context (검색 결과)   │
           └─────────────────────────┘
                      │
        ┌─────────────┼─────────────┐
        │             │             │
        v             v             v
   ┌────────┐   ┌────────┐   ┌────────┐
   │ Node A │   │ Node B │   │ Node C │
   └────────┘   └────────┘   └────────┘
- 상태 전이 기반 흐름 제어
- 조건부 분기, 루프 가능
- 체크포인트로 상태 영속화
```

**Memory & Checkpointing:**

```python
from langgraph.checkpoint.memory import MemorySaver
from langgraph.checkpoint.postgres import PostgresSaver

# langgraph-checkpoint-redis 패키지 필요
# pip install langgraph-checkpoint-redis
from langgraph_checkpoint_redis import RedisSaver


# 1. 메모리 기반 (개발/테스트)
memory_checkpointer = MemorySaver()

# 2. PostgreSQL 기반
postgres_checkpointer = PostgresSaver.from_conn_string(
    "postgresql://user:pass@host/db"
)

# 3. Redis 기반 (scan_worker와 일관성 유지) ✅ 권장
redis_checkpointer = RedisSaver.from_conn_string(
    "redis://rfr-cache-redis.redis.svc.cluster.local:6379/0"
)

# 그래프에 체크포인터 연결
graph = create_chat_graph()
app = graph.compile(checkpointer=redis_checkpointer)
```

**scan_worker와의 인프라 일관성:**

```
scan_worker (Celery + 수동 체크포인팅)
=============================================
┌─────────────────────┐     ┌─────────────────────┐
│  Redis Streams      │     │  Redis Cache        │
│  (이벤트 발행)       │     │  (체크포인팅)        │
│  rfr-streams-redis  │     │  rfr-cache-redis    │
│  XADD → SSE Gateway │     │  SET/GET Context    │
└─────────────────────┘     └─────────────────────┘

chat (LangGraph + RedisSaver)
=============================================
┌─────────────────────┐     ┌─────────────────────┐
│  Redis Streams      │     │  Redis Cache        │
│  (이벤트 발행)       │     │  (LangGraph 체크포인트)│
│  rfr-streams-redis  │     │  rfr-cache-redis    │
│  EventPublisher →   │     │  RedisSaver →       │
│  SSE Gateway        │     │  thread_id별 상태   │
└─────────────────────┘     └─────────────────────┘

✅ 동일한 Redis 인프라 재사용
✅ 운영 복잡도 감소
```

**Checkpointer 선택 가이드:**

| 환경 | Checkpointer | 이유 |
|------|-------------|------|
| 로컬 개발 | `MemorySaver` | 빠른 테스트 |
| 단일 Pod | `MemorySaver` | 간단한 구조 |
| **프로덕션 (K8s)** | `RedisSaver` | scan과 인프라 통일, 확장성 |
| 장기 보관 필요 | `PostgresSaver` | 영구 저장, 분석 용이 |

**대화 히스토리 관리:**

```python
async def chat_with_history(
    user_id: str,
    message: str,
    app: CompiledGraph,
) -> AsyncIterator[dict]:
    """대화 히스토리를 유지하며 채팅."""
    
    # thread_id로 대화 세션 구분
    config = {"configurable": {"thread_id": f"user:{user_id}"}}
    
    # 이전 상태 불러오기 (자동)
    # LangGraph가 checkpointer에서 thread_id로 조회
    
    # 새 메시지 추가하여 실행
    async for event in app.astream(
        {"message": message},
        config=config,
        stream_mode="updates",
    ):
        yield event
    
    # 상태 자동 저장 (체크포인트)
```

**상태 전이 예시:**

```python
# 초기 상태
state_0 = {
    "messages": [],
    "message": "페트병 어떻게 버려?",
    "intent": None,
    ...
}

# intent_classifier 노드 실행 후
state_1 = {
    "messages": [
        {"role": "user", "content": "페트병 어떻게 버려?"}
    ],
    "message": "페트병 어떻게 버려?",
    "intent": "waste",  # 🆕 의도 분류됨
    ...
}

# waste_rag_node 실행 후
state_2 = {
    "messages": [...],
    "intent": "waste",
    "context": "페트병은 내용물을 비우고...",  # 🆕 RAG 결과
    ...
}

# answer_node 실행 후
state_3 = {
    "messages": [
        {"role": "user", "content": "페트병 어떻게 버려?"},
        {"role": "assistant", "content": "페트병은..."}  # 🆕 답변 추가
    ],
    "answer": "페트병은...",
    ...
}

# 다음 질문 시 (같은 thread_id)
state_4 = {
    "messages": [
        {"role": "user", "content": "페트병 어떻게 버려?"},
        {"role": "assistant", "content": "페트병은..."},
        {"role": "user", "content": "그럼 유리병은?"}  # 🆕 이어서
    ],
    "message": "그럼 유리병은?",
    ...
}
```

**왜 LangGraph 오케스트레이션이 필요한가?**

| 요구사항 | LangChain | LangGraph |
|---------|-----------|-----------|
| 조건부 분기 | 수동 구현 | `add_conditional_edges` |
| 대화 히스토리 | 외부 관리 | State + Checkpointer |
| 상태 저장/복원 | 직접 구현 | `MemorySaver/PostgresSaver` |
| 루프/재시도 | 복잡 | 그래프 엣지로 표현 |
| 디버깅/추적 | 어려움 | 상태 스냅샷 제공 |

### 4.3 라우팅 함수

```python
def route_by_input_type(state: ChatState) -> str:
    """입력 유형에 따른 1차 분기."""
    if state.get("image_url"):
        return "vision_node"
    return "intent_classifier"


def route_by_intent(state: ChatState) -> str:
    """의도에 따른 2차 분기."""
    intent = state.get("intent", "general")
    
    routes = {
        "waste": "waste_rag_node",
        "character": "character_node",
        "location": "location_tool_node",
        "general": "general_llm_node",
    }
    return routes.get(intent, "general_llm_node")
```

### 4.4 그래프 구성

```python
from langgraph.graph import StateGraph, START, END

def create_chat_graph(
    vision_model,
    intent_classifier,
    llm,
    retrievers,
    event_publisher,
    subagents,  # Subagent 추가
):
    """Chat 파이프라인 그래프 생성."""
    
    graph = StateGraph(ChatState)
    
    # 메인 노드 등록
    graph.add_node("vision_node", create_vision_node(
        vision_model, event_publisher
    ))
    graph.add_node("intent_classifier", create_intent_node(
        intent_classifier, event_publisher
    ))
    graph.add_node("rule_rag_node", create_rule_node(
        retrievers["rule"], event_publisher
    ))
    graph.add_node("answer_node", create_answer_node(
        llm, event_publisher
    ))
    
    # 단순 질문용 노드
    graph.add_node("waste_rag_node", create_rag_node(
        retrievers["waste"], event_publisher
    ))
    graph.add_node("character_node", create_character_node(
        event_publisher
    ))
    graph.add_node("general_llm_node", create_llm_node(
        llm, event_publisher
    ))
    
    # Subagent 노드 (복잡한 질문용)
    graph.add_node("decomposer", create_decomposer_node(
        llm, event_publisher
    ))
    graph.add_node("waste_expert", subagents["waste_expert"])
    graph.add_node("location_expert", subagents["location_expert"])
    graph.add_node("character_expert", subagents["character_expert"])
    graph.add_node("synthesizer", create_synthesizer_node(
        llm, event_publisher
    ))
    
    # 1차 라우팅 (입력 유형)
    graph.add_conditional_edges(
        START,
        route_by_input_type,
        {
            "vision_node": "vision_node",
            "intent_classifier": "intent_classifier",
        }
    )
    
    # 이미지 파이프라인
    graph.add_edge("vision_node", "rule_rag_node")
    graph.add_edge("rule_rag_node", "answer_node")
    
    # 2차 라우팅 (복잡도 기반)
    graph.add_conditional_edges(
        "intent_classifier",
        route_by_complexity,  # 복잡도 라우팅
        {
            # 단순 질문 → 단일 노드
            "simple_waste": "waste_rag_node",
            "simple_character": "character_node",
            "simple_general": "general_llm_node",
            # 복잡한 질문 → Subagent
            "complex": "decomposer",
        }
    )
    
    # 단순 경로 → Answer
    graph.add_edge("waste_rag_node", "answer_node")
    graph.add_edge("character_node", "answer_node")
    graph.add_edge("general_llm_node", END)
    
    # Subagent 병렬 실행 → Synthesizer → Answer
    graph.add_edge("decomposer", "waste_expert")
    graph.add_edge("decomposer", "location_expert")
    graph.add_edge("decomposer", "character_expert")
    graph.add_edge("waste_expert", "synthesizer")
    graph.add_edge("location_expert", "synthesizer")
    graph.add_edge("character_expert", "synthesizer")
    graph.add_edge("synthesizer", "answer_node")
    
    # 종료
    graph.add_edge("answer_node", END)
    
    return graph.compile()
```

**복잡도 라우팅 함수:**

```python
def route_by_complexity(state: ChatState) -> str:
    """복잡도에 따른 라우팅.
    
    단순 질문: 단일 노드 처리
    복잡한 질문: Subagent 분해 → 병렬 처리
    """
    message = state["message"]
    intent = state.get("intent", "general")
    
    # 복잡한 질문 감지
    if is_complex_query(message):
        return "complex"
    
    # 단순 질문
    return f"simple_{intent}"


def is_complex_query(message: str) -> bool:
    """복잡한 질문 여부 판단."""
    # 멀티 카테고리 감지
    categories = count_waste_categories(message)
    if categories >= 2:
        return True
    
    # 멀티 도구 필요 감지
    needs_location = any(kw in message for kw in ["근처", "주변", "가까운"])
    needs_character = any(kw in message for kw in ["캐릭터", "얻"])
    needs_waste = any(kw in message for kw in ["버려", "분리배출", "재활용"])
    
    tool_count = sum([needs_location, needs_character, needs_waste])
    if tool_count >= 2:
        return True
    
    return False
```

### 4.5 컨텍스트 사용량 추적

컨텍스트 사용량(토큰) 추적은 비용 관리와 UX에 중요합니다.

#### 4.5.1 모델별 컨텍스트 한도

> **기준일**: 2026-01-13 (GPT-5.2, Gemini 3.0 시리즈 반영)

| Provider | Model | Context Window | 비고 |
|----------|-------|----------------|------|
| **OpenAI** | gpt-5.2 | 128K | Pro/Enterprise |
| | gpt-5.2-thinking | 196K | 추론 특화 |
| | gpt-5.2-mini | 32K | Plus/Business |
| | gpt-4o | 128K | Legacy |
| **Anthropic** | claude-opus-4-5 | 200K | 최상위 모델 |
| | claude-sonnet-4-5 | 200K / 1M (beta) | 균형 모델 |
| | claude-haiku-4-5 | 200K | 빠른 응답 |
| **Google** | gemini-3.0-pro | 1M | 최대 컨텍스트 |
| | gemini-3.0-flash | 1M | 빠른 응답 |
| | gemini-2.5-pro | 1M | Legacy |

#### 4.5.2 토큰 카운팅 구현

**OpenAI (tiktoken):**

```python
import tiktoken

class OpenAITokenCounter:
    """OpenAI 토큰 카운터."""
    
    def __init__(self, model: str = "gpt-5.2"):
        self.encoding = tiktoken.encoding_for_model(model)
    
    def count(self, text: str) -> int:
        return len(self.encoding.encode(text))
    
    def count_messages(self, messages: list[dict]) -> int:
        """메시지 목록 토큰 수 (오버헤드 포함)."""
        total = 0
        for msg in messages:
            total += 4  # 메시지 오버헤드
            total += self.count(msg.get("content", ""))
        total += 2  # 프라이밍
        return total
```

**Anthropic (API 응답):**

```python
class AnthropicTokenCounter:
    """Anthropic 토큰 카운터."""
    
    def __init__(self, client: AsyncAnthropic):
        self.client = client
    
    async def count(self, messages: list[dict]) -> int:
        """메시지 토큰 수 (API 호출)."""
        response = await self.client.messages.count_tokens(
            model="claude-sonnet-4-5-20250929",
            messages=messages,
        )
        return response.input_tokens
    
    def extract_usage(self, response) -> dict:
        """응답에서 사용량 추출."""
        return {
            "input_tokens": response.usage.input_tokens,
            "output_tokens": response.usage.output_tokens,
        }
```

**Google Gemini:**

```python
import google.generativeai as genai

class GeminiTokenCounter:
    """Gemini 토큰 카운터."""
    
    def __init__(self, model_name: str = "gemini-3.0-flash"):
        self.model = genai.GenerativeModel(model_name)
    
    def count(self, text: str) -> int:
        response = self.model.count_tokens(text)
        return response.total_tokens
    
    def count_contents(self, contents: list) -> int:
        response = self.model.count_tokens(contents)
        return response.total_tokens
```

#### 4.5.3 Port/Adapter 추상화

```python
from abc import ABC, abstractmethod


class TokenCounterPort(ABC):
    """토큰 카운터 포트."""
    
    @abstractmethod
    def count(self, text: str) -> int:
        """텍스트 토큰 수."""
        ...
    
    @abstractmethod
    def count_messages(self, messages: list[dict]) -> int:
        """메시지 목록 토큰 수."""
        ...
    
    @property
    @abstractmethod
    def max_context(self) -> int:
        """최대 컨텍스트 크기."""
        ...


class OpenAITokenCounterAdapter(TokenCounterPort):
    max_context = 128_000
    ...


class AnthropicTokenCounterAdapter(TokenCounterPort):
    max_context = 200_000
    ...


class GeminiTokenCounterAdapter(TokenCounterPort):
    max_context = 1_000_000
    ...
```

#### 4.5.4 ChatState에 사용량 추적

```python
class ChatState(TypedDict):
    """Chat LangGraph State."""
    messages: Annotated[list, add_messages]
    intent: str | None
    tool_results: dict[str, Any]
    user_location: dict | None
    
    # 컨텍스트 사용량 추적
    token_usage: TokenUsage | None


class TokenUsage(TypedDict):
    """토큰 사용량."""
    input_tokens: int
    output_tokens: int
    total_tokens: int
    max_tokens: int
    percentage: float  # 0.0 ~ 1.0
```

#### 4.5.5 SSE로 사용량 전달

```python
async def answer_node(
    state: ChatState,
    event_publisher: EventPublisher,
    token_counter: TokenCounterPort,
) -> ChatState:
    job_id = state["job_id"]
    
    # 현재 컨텍스트 토큰 수 계산
    messages = state["messages"]
    current_tokens = token_counter.count_messages(messages)
    max_tokens = token_counter.max_context
    
    # SSE로 사용량 이벤트 전송
    await event_publisher.publish(job_id, {
        "type": "context_usage",
        "current": current_tokens,
        "max": max_tokens,
        "percentage": round(current_tokens / max_tokens * 100, 1),
    })
    
    # ... LLM 호출 ...
    
    # 응답 후 업데이트된 사용량
    usage = llm_response.usage
    await event_publisher.publish(job_id, {
        "type": "context_usage",
        "input_tokens": usage.input_tokens,
        "output_tokens": usage.output_tokens,
        "total": usage.input_tokens + usage.output_tokens,
        "max": max_tokens,
        "percentage": round(
            (usage.input_tokens + usage.output_tokens) / max_tokens * 100, 1
        ),
    })
    
    return {**state, "token_usage": usage}
```

#### 4.5.6 클라이언트 컨텍스트 링 UI

> **디자인**: Cursor 스타일 원형 링 (Circle Progress)

```
SSE Event: {
  "type": "context_usage",
  "current": 4521,
  "max": 128000,
  "percentage": 3.5
}

컨텍스트 링 (원형, Cursor 스타일):

     🟢 정상 (3.5%)          🟡 주의 (75%)          🔴 경고 (92%)
         ╭───╮                  ╭───╮                  ╭───╮
        ╱     ╲                ╱█████╲                ╱█████╲
       │       │              │███████│              │███████│
       │  3.5% │              │  75%  │              │  92%  │
       │       │              │███████│              │███████│
        ╲     ╱                ╲█████╱                ╲█████╱
         ╰───╯                  ╰───╯                  ╰───╯
      4.5K / 128K            96K / 128K           118K / 128K
```

**React 컴포넌트 예시:**

```tsx
interface ContextRingProps {
  current: number;
  max: number;
  percentage: number;
}

const ContextRing = ({ current, max, percentage }: ContextRingProps) => {
  const getColor = () => {
    if (percentage < 70) return "#22c55e";  // green
    if (percentage < 90) return "#eab308";  // yellow
    return "#ef4444";  // red
  };

  return (
    <div className="context-ring">
      <svg viewBox="0 0 36 36" className="circular-chart">
        {/* 배경 원 */}
        <path
          className="circle-bg"
          d="M18 2.0845
             a 15.9155 15.9155 0 0 1 0 31.831
             a 15.9155 15.9155 0 0 1 0 -31.831"
          fill="none"
          stroke="#e5e7eb"
          strokeWidth="3"
        />
        {/* 진행 원 */}
        <path
          className="circle"
          strokeDasharray={`${percentage}, 100`}
          d="M18 2.0845
             a 15.9155 15.9155 0 0 1 0 31.831
             a 15.9155 15.9155 0 0 1 0 -31.831"
          fill="none"
          stroke={getColor()}
          strokeWidth="3"
          strokeLinecap="round"
        />
        {/* 중앙 텍스트 */}
        <text x="18" y="20" className="percentage">
          {percentage.toFixed(0)}%
        </text>
      </svg>
      <span className="token-count">
        {(current / 1000).toFixed(1)}K / {(max / 1000).toFixed(0)}K
      </span>
    </div>
  );
};
```

**임계값 및 자동 조치:**

| 비율 | 상태 | 색상 | 조치 |
|------|------|------|------|
| < 70% | 정상 | 🟢 `#22c55e` | - |
| 70~85% | 주의 | 🟡 `#eab308` | UI 색상 변경 (알림 없음) |
| > 85% | 압축 | 🔴 `#ef4444` | **자동 컨텍스트 압축** |

> **Note**: "새 대화를 시작하세요" 경고 대신 **자동 컨텍스트 압축**으로 UX 연속성 유지.

**자동 압축 SSE 이벤트:**

```json
{
  "type": "context_compressed",
  "before_tokens": 118000,
  "after_tokens": 45000,
  "message": "이전 대화를 요약했어요 📝"
}
```

#### 4.5.7 대화 세션 사이드바 (우측)

> **디자인**: Cursor 우측 Agents 패널과 동일한 UX
> 각 세션은 **독립적인 컨텍스트**를 가짐

**레이아웃:**

```
┌───────────────────────────────────────────────────────────┐
│                                     │ ┌─────────────────┐ │
│  💬 채팅 영역                        │ │ Search Agents...│ │
│                                     │ ├─────────────────┤ │
│  ┌──────────────────────────────┐   │ │   New Agent     │ │
│  │ User: 페트병 어떻게 버려?     │   │ ├─────────────────┤ │
│  └──────────────────────────────┘   │ │ Agents          │ │
│                                     │ │─────────────────│ │
│  ┌──────────────────────────────┐   │ │ ● 분리배출 질문  │ │
│  │ 🤖 이코: 페트병은 내용물을... │   │ │   Now           │ │
│  └──────────────────────────────┘   │ │ ○ 근처 재활용센터│ │
│                                     │ │   5m            │ │
│              ╭───╮                  │ │ ○ 캐릭터 미리보기│ │
│  입력창...   │12%│                  │ │   1h            │ │
│              ╰───╯                  │ │ ○ 유리병 분리수거│ │
│                                     │ │   2d            │ │
│                                     │ └─────────────────┘ │
└───────────────────────────────────────────────────────────┘
```

**핵심 개념:**

| 항목 | 설명 |
|------|------|
| **각 세션** | 독립적인 컨텍스트 (thread_id) |
| **New Agent** | 새 대화 세션 생성 |
| **세션 목록** | 이전 대화 기록, 시간순 정렬 |
| **내부 라우팅** | LangGraph가 자동 처리 (사용자 선택 X) |

**세션별 컨텍스트 관리:**

```python
# 각 세션 = 독립적인 thread_id
# LangGraph RedisSaver가 세션별 상태 관리

class ChatSession(BaseModel):
    """대화 세션."""
    session_id: str  # UUID
    title: str       # 자동 생성 또는 첫 메시지 기반
    created_at: datetime
    updated_at: datetime
    message_count: int
    
    # 컨텍스트 사용량
    token_usage: TokenUsage | None


# API: 세션 목록 조회
@router.get("/sessions")
async def list_sessions(
    user: CurrentUser,
) -> list[ChatSession]:
    """사용자의 대화 세션 목록."""
    return await session_repo.list_by_user(user.id)


# API: 새 세션 생성
@router.post("/sessions")
async def create_session(
    user: CurrentUser,
) -> ChatSession:
    """새 대화 세션 생성."""
    session_id = str(uuid.uuid4())
    return await session_repo.create(user.id, session_id)


# API: 채팅 메시지 제출 (Job 패턴)
# 상세: 05-async-job-queue-decision.md
class ChatSubmitResponse(BaseModel):
    """채팅 제출 응답."""
    job_id: str
    stream_url: str
    status: Literal["queued", "processing", "completed", "failed"]


@router.post("/messages")
async def submit_message(
    request: ChatMessageRequest,
    user: CurrentUser,
) -> ChatSubmitResponse:
    """채팅 메시지 제출.
    
    Job 기반 비동기 처리:
    1. 즉시 job_id 반환 (200ms 이내)
    2. Taskiq Worker가 백그라운드 처리
    3. SSE로 실시간 스트리밍
    """
    from chat_worker.tasks.chat_task import process_chat_task
    
    job_id = str(uuid.uuid4())
    
    # Taskiq Job 제출
    await process_chat_task.kiq(
        job_id=job_id,
        session_id=request.session_id,
        message=request.message,
        image_url=str(request.image_url) if request.image_url else None,
        location=request.location.model_dump() if request.location else None,
        model=request.model,
    )
    
    return ChatSubmitResponse(
        job_id=job_id,
        stream_url=f"/api/v1/stream/{job_id}",
        status="queued",
    )
```

**LangGraph 라우팅 (내부 자동):**

```python
def route_by_input_type(state: ChatState) -> str:
    """입력 유형에 따른 자동 라우팅.
    
    Note: 사용자가 서브에이전트를 직접 선택하지 않음.
          LangGraph가 Intent 분류 후 자동으로 라우팅.
    """
    if state.get("image_url"):
        return "vision_node"
    return "intent_classifier"


def route_by_intent(state: ChatState) -> str:
    """의도에 따른 자동 분기 (내부 처리)."""
    intent = state.get("intent", "general")
    
    routes = {
        "waste": "waste_rag_node",
        "character": "character_node",
        "character_preview": "character_preview_node",
        "location": "location_tool_node",
        "general": "general_llm_node",
    }
    return routes.get(intent, "general_llm_node")
```

**장점:**
1. **컨텍스트 격리**: 세션별 독립적인 대화 히스토리
2. **UX 일관성**: Cursor Agents 패널과 동일한 패턴
3. **간편한 관리**: 이전 대화로 쉽게 돌아가기
4. **자동 라우팅**: 사용자는 의도를 신경 쓸 필요 없음

---

## 5. SSE 이벤트 설계

### 5.1 노드별 이벤트

| 노드 | 이벤트 타입 | 메시지 예시 |
|------|------------|------------|
| vision_node | progress | 🔍 이미지 분류 중... |
| intent_classifier | progress | 🤔 질문 분석 중... |
| waste_rag_node | progress | 📚 규정 검색 중... |
| answer_node | delta | (토큰 스트리밍) |
| answer_node | done | 답변 완료 |

### 5.2 노드 구현 패턴

```python
from langgraph.types import StreamWriter


async def create_vision_node(
    vision_model,
    event_publisher,
):
    async def vision_node(
        state: ChatState,
        writer: StreamWriter,
    ) -> ChatState:
        job_id = state["job_id"]
        
        # 시작 이벤트
        await event_publisher.publish(job_id, {
            "type": "progress",
            "stage": "vision",
            "status": "started",
            "message": "🔍 이미지 분류 중...",
        })
        
        # Vision 호출
        result = await vision_model.classify(
            state["image_url"]
        )
        
        # 완료 이벤트
        await event_publisher.publish(job_id, {
            "type": "progress",
            "stage": "vision",
            "status": "completed",
            "result": result,
        })
        
        return {
            **state,
            "input_type": "image",
            "classification": result,
        }
    
    return vision_node
```

### 5.3 Tool Calling SSE 이벤트

**Tool 호출 과정에서의 이벤트 흐름:**

```
┌────────────────────────────────────────────────────────┐
│ User: "강남역 근처 재활용센터랑 페트병 캐릭터 알려줘"    │
└────────────────────────────────────────────────────────┘
        │
        v
┌─────────────────────┐
│  SSE: intent        │  {"type":"progress","stage":"intent",
│  "🤔 질문 분석 중"   │   "message":"🤔 질문 분석 중..."}
└─────────────────────┘
        │
        v
┌─────────────────────┐
│  SSE: tool_start    │  {"type":"tool","action":"start",
│  "🔧 정보 조회 중"   │   "tools":["location","character"]}
└─────────────────────┘
        │
        v (Claude: 코드 실행 / GPT: 순차 호출)
┌─────────────────────┐
│  SSE: tool_progress │  {"type":"tool","action":"progress",
│  "📍 주변 센터 검색" │   "current":"search_nearby_centers"}
└─────────────────────┘
        │
        v
┌─────────────────────┐
│  SSE: tool_progress │  {"type":"tool","action":"progress",
│  "🎭 캐릭터 조회"    │   "current":"preview_character"}
└─────────────────────┘
        │
        v
┌─────────────────────┐
│  SSE: tool_done     │  {"type":"tool","action":"done",
│  "✅ 정보 수집 완료" │   "results_count":2}
└─────────────────────┘
        │
        v
┌─────────────────────┐
│  SSE: delta (반복)  │  {"type":"delta","content":"강남역"}
│  토큰 스트리밍       │  {"type":"delta","content":" 근처"}
└─────────────────────┘
        │
        v
┌─────────────────────┐
│  SSE: done          │  {"type":"done","stage":"complete"}
└─────────────────────┘
```

**이벤트 타입 정의:**

| 이벤트 타입 | 용도 | 클라이언트 UX |
|------------|------|-------------|
| `progress` | 단계 진행 | 로딩 메시지 표시 |
| `tool` | Tool 호출 상태 | Tool 아이콘/상태 표시 |
| `delta` | 토큰 스트리밍 | 글자 단위 출력 |
| `done` | 완료 | 로딩 종료 |

### 5.4 모델별 Tool Calling SSE 구현

**Claude (Programmatic Tool Calling):**

```python
async def claude_tool_node(
    state: ChatState,
    event_publisher: EventPublisher,
) -> ChatState:
    job_id = state["job_id"]
    
    # Tool 시작 이벤트
    await event_publisher.publish(job_id, {
        "type": "tool",
        "action": "start",
        "message": "🔧 정보 조회 중...",
    })
    
    response = await client.beta.messages.create(
        betas=["advanced-tool-use-2025-11-20"],
        model="claude-sonnet-4-5-20250929",
        tools=[
            {"type": "code_execution_20250825", ...},
            {"name": "search_nearby_centers", ...},
            {"name": "preview_character", ...},
        ],
        messages=[...],
        # 스트리밍으로 중간 상태 확인
        stream=True,
    )
    
    async for event in response:
        if event.type == "content_block_start":
            if event.content_block.type == "tool_use":
                await event_publisher.publish(job_id, {
                    "type": "tool",
                    "action": "progress",
                    "current": event.content_block.name,
                })
    
    # Tool 완료 이벤트
    await event_publisher.publish(job_id, {
        "type": "tool",
        "action": "done",
        "message": "✅ 정보 수집 완료",
    })
    
    return {**state, "tool_results": response.content}
```

**GPT/Gemini (Function Calling):**

```python
async def openai_tool_node(
    state: ChatState,
    event_publisher: EventPublisher,
    tool_executors: dict,
) -> ChatState:
    job_id = state["job_id"]
    
    # Tool 시작 이벤트
    await event_publisher.publish(job_id, {
        "type": "tool",
        "action": "start",
        "message": "🔧 정보 조회 중...",
    })
    
    response = await client.chat.completions.create(
        model="gpt-5.2",
        tools=[...],
        parallel_tool_calls=True,
        messages=[...],
    )
    
    tool_calls = response.choices[0].message.tool_calls
    results = []
    
    for tc in tool_calls:
        # 개별 Tool 진행 이벤트
        await event_publisher.publish(job_id, {
            "type": "tool",
            "action": "progress",
            "current": tc.function.name,
        })
        
        # Tool 실행 (개발자 코드에서)
        executor = tool_executors[tc.function.name]
        result = await executor(**json.loads(tc.function.arguments))
        results.append(result)
    
    # Tool 완료 이벤트
    await event_publisher.publish(job_id, {
        "type": "tool",
        "action": "done",
        "message": "✅ 정보 수집 완료",
    })
    
    return {**state, "tool_results": results}
```

### 5.5 답변 토큰 스트리밍

**Claude 토큰 스트리밍:**

```python
async def claude_answer_node(
    state: ChatState,
    event_publisher: EventPublisher,
) -> ChatState:
    job_id = state["job_id"]
    full_response = ""
    
    async with client.messages.stream(
        model="claude-sonnet-4-5-20250929",
        messages=[...],
    ) as stream:
        async for text in stream.text_stream:
            full_response += text
            await event_publisher.publish(job_id, {
                "type": "delta",
                "content": text,
            })
    
    await event_publisher.publish(job_id, {
        "type": "done",
        "stage": "complete",
    })
    
    return {**state, "answer": full_response}
```

**GPT 토큰 스트리밍:**

```python
async def openai_answer_node(
    state: ChatState,
    event_publisher: EventPublisher,
) -> ChatState:
    job_id = state["job_id"]
    full_response = ""
    
    stream = await client.chat.completions.create(
        model="gpt-5.2",
        messages=[...],
        stream=True,
    )
    
    async for chunk in stream:
        if chunk.choices[0].delta.content:
            content = chunk.choices[0].delta.content
            full_response += content
            await event_publisher.publish(job_id, {
                "type": "delta",
                "content": content,
            })
    
    await event_publisher.publish(job_id, {
        "type": "done",
        "stage": "complete",
    })
    
    return {**state, "answer": full_response}
```

### 5.6 클라이언트 SSE 처리 예시

```typescript
// React 클라이언트 예시
const ChatMessage = ({ jobId }: { jobId: string }) => {
  const [status, setStatus] = useState<string>("");
  const [content, setContent] = useState<string>("");
  const [toolStatus, setToolStatus] = useState<string>("");

  useEffect(() => {
    const eventSource = new EventSource(
      `/api/chat/stream/${jobId}`
    );

    eventSource.onmessage = (event) => {
      const data = JSON.parse(event.data);

      switch (data.type) {
        case "progress":
          setStatus(data.message);
          break;
        case "tool":
          if (data.action === "progress") {
            setToolStatus(`🔧 ${data.current} 실행 중...`);
          } else if (data.action === "done") {
            setToolStatus("");
          }
          break;
        case "delta":
          setContent((prev) => prev + data.content);
          setStatus("");  // 스트리밍 시작하면 상태 메시지 제거
          break;
        case "done":
          eventSource.close();
          break;
      }
    };

    return () => eventSource.close();
  }, [jobId]);

  return (
    <div>
      {status && <div className="status">{status}</div>}
      {toolStatus && <div className="tool-status">{toolStatus}</div>}
      <div className="content">{content}</div>
    </div>
  );
};
```

---

## 6. Knowledge Base 설계

### 6.1 scan_worker와 동일한 파일셋 복사

**원칙**: Clean Architecture에서 각 서비스는 **독립적**이어야 합니다.

```
⚠️ 왜 공유하지 않고 복사하는가?

1. 배포 독립성: chat과 scan_worker가 별도로 배포
2. 버전 관리: 서비스별 독립적인 규정 업데이트 가능
3. 테스트 격리: 각 서비스의 테스트가 다른 서비스에 영향 없음
4. Docker 이미지 독립: COPY 시 다른 서비스 의존 없음
```

### 6.2 복사할 파일 구조

> **Note**: 비즈니스 로직은 `chat_worker`에 위치 (scan/scan_worker 패턴)

```
apps/chat_worker/infrastructure/assets/
├── data/
│   ├── item_class_list.yaml      # 품목 분류 목록
│   ├── situation_tags.yaml       # 상황 태그
│   └── source/                   # 분리배출 규정 (18개)
│       ├── 공사장생활폐기물.json
│       ├── 대형폐기물.json
│       ├── 불연성종량제폐기물.json
│       ├── 생활계유해폐기물.json
│       ├── 음식물류폐기물.json
│       ├── 일반종량제폐기물.json
│       ├── 재활용폐기물_금속류.json
│       ├── 재활용폐기물_무색페트병.json
│       ├── 재활용폐기물_발포합성수지.json
│       ├── 재활용폐기물_비닐류.json
│       ├── 재활용폐기물_유리병.json
│       ├── 재활용폐기물_의류및원단.json
│       ├── 재활용폐기물_전기전자제품.json
│       ├── 재활용폐기물_전지.json
│       ├── 재활용폐기물_조명제품.json
│       ├── 재활용폐기물_종이.json
│       ├── 재활용폐기물_종이팩.json
│       └── 재활용폐기물_플라스틱류.json
└── prompts/
    ├── answer_generation_prompt.txt
    ├── text_classification_prompt.txt
    ├── vision_classification_prompt.txt
    └── intent_classification_prompt.txt  # chat 전용 추가
```

### 6.3 RAG Retriever 구현

```python
# apps/chat_worker/infrastructure/persistence/retriever.py
from pathlib import Path
import json
import yaml


class DisposalRulesRetriever:
    """분리배출 규정 검색기.
    
    scan_worker와 동일한 로직이지만 독립적인 인스턴스.
    """
    
    def __init__(self, data_dir: Path | None = None):
        self.data_dir = data_dir or Path(__file__).parent.parent / "assets" / "data"
        self._rules: dict[str, dict] = {}
        self._item_classes: dict = {}
        self._load_data()
    
    def _load_data(self):
        """데이터 로드."""
        # 품목 분류 로드
        with open(self.data_dir / "item_class_list.yaml") as f:
            self._item_classes = yaml.safe_load(f)
        
        # 규정 파일 로드
        source_dir = self.data_dir / "source"
        for json_file in source_dir.glob("*.json"):
            with open(json_file, encoding="utf-8") as f:
                data = json.load(f)
                key = json_file.stem
                self._rules[key] = data
    
    def search(
        self,
        category: str,
        subcategory: str | None = None,
    ) -> dict | None:
        """분류 결과로 규정 검색."""
        # 카테고리 매핑 로직
        for key, rules in self._rules.items():
            if self._matches(rules, category, subcategory):
                return rules
        return None
    
    def _matches(
        self,
        rules: dict,
        category: str,
        subcategory: str | None,
    ) -> bool:
        """매칭 로직."""
        # 구현: scan_worker의 rule_step 로직 참조
        pass
```

### 6.4 Prompt Loader

```python
# apps/chat_worker/infrastructure/assets/prompts/loader.py
from pathlib import Path
from functools import lru_cache


class PromptLoader:
    """프롬프트 템플릿 로더."""
    
    def __init__(self, prompts_dir: Path | None = None):
        self.prompts_dir = prompts_dir or Path(__file__).parent.parent / "assets" / "prompts"
    
    @lru_cache(maxsize=10)
    def load(self, name: str) -> str:
        """프롬프트 로드 (캐싱)."""
        path = self.prompts_dir / f"{name}.txt"
        if not path.exists():
            raise FileNotFoundError(f"Prompt not found: {name}")
        return path.read_text(encoding="utf-8")
    
    def get_vision_prompt(self) -> str:
        return self.load("vision_classification_prompt")
    
    def get_answer_prompt(self) -> str:
        return self.load("answer_generation_prompt")
    
    def get_intent_prompt(self) -> str:
        return self.load("intent_classification_prompt")
```

### 6.5 복사 스크립트

```bash
#!/bin/bash
# scripts/sync-chat-assets.sh
# scan_worker assets를 chat으로 동기화

SOURCE="apps/scan_worker/infrastructure/assets"
TARGET="apps/chat_worker/infrastructure/assets"

# 디렉토리 생성
mkdir -p "$TARGET/data/source"
mkdir -p "$TARGET/prompts"

# 데이터 복사
cp "$SOURCE/data/item_class_list.yaml" "$TARGET/data/"
cp "$SOURCE/data/situation_tags.yaml" "$TARGET/data/"
cp "$SOURCE/data/source/"*.json "$TARGET/data/source/"

# 프롬프트 복사
cp "$SOURCE/prompts/"*.txt "$TARGET/prompts/"

echo "✅ Assets synced from scan_worker to chat"
```

---

## 7. Tool Calling 확장

### 7.1 기존 서비스 Tool 연동

Chat에서 활용 가능한 기존 서비스:

| 서비스 | API | Tool 용도 |
|--------|-----|----------|
| **location** | `GET /locations/centers` | 주변 재활용센터/제로웨이스트샵 검색 |
| **character** | `GET /characters` | 캐릭터 정보 조회 |
| **users** | `GET /users/me/characters` | 사용자 보유 캐릭터 조회 |

### 7.2 위치 정보 전달 설계

Location Tool 호출 시 사용자 위치가 필요합니다. 클라이언트는 Kakao Map API를 사용합니다.

#### 7.2.1 위치 획득 방식

| 방식 | 설명 |
|------|------|
| **브라우저 Geolocation API** | `navigator.geolocation.getCurrentPosition()` |
| **Kakao Map 중심 좌표** | 사용자가 지도에서 선택한 위치 |
| **IP 기반 추정** | Fallback (정확도 낮음) |

#### 7.2.2 요청 스키마 확장

```python
class UserLocation(BaseModel):
    """사용자 위치 (Optional)."""
    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)


class ChatMessageRequest(BaseModel):
    """채팅 메시지 요청."""
    message: str = Field(..., min_length=1, max_length=2000)
    image_url: HttpUrl | None = None
    
    # 위치 정보 (Optional)
    location: UserLocation | None = Field(
        default=None,
        description="위치 검색 시 사용할 좌표 (Optional)"
    )
    
    model: str = Field(default="gpt-5.2")
```

#### 7.2.3 위치 없을 때 SSE 요청 플로우

```
클라이언트                     Chat API (LangGraph)
    │                              │
    │ POST /chat {                 │
    │   message: "근처 재활용센터"   │
    │ }  (위치 없음)                │
    ├─────────────────────────────▶│
    │                              │
    │          의도 분류: location  │
    │          위치 정보 없음 감지   │
    │                              │
    │   SSE: {                     │
    │     type: "request_location",│
    │     message: "위치 정보가     │
    │       필요해요. 공유해주세요" │
    │   }                          │
    │◀─────────────────────────────┤
    │                              │
    │ 사용자 동의 → Geolocation    │
    │                              │
    │ POST /chat {                 │
    │   message: "근처 재활용센터", │
    │   location: {                │
    │     lat: 37.5665,            │
    │     lon: 126.9780            │
    │   }                          │
    │ }                            │
    ├─────────────────────────────▶│
    │                              │
    │   SSE: 검색 결과 스트리밍      │
    │◀─────────────────────────────┤
```

#### 7.2.4 LangGraph State에 위치 저장

```python
class ChatState(TypedDict):
    """Chat LangGraph State."""
    messages: Annotated[list, add_messages]
    intent: str | None
    tool_results: dict[str, Any]
    
    # 위치 정보
    user_location: dict | None  # {"lat": 37.5665, "lon": 126.9780}


def location_node(state: ChatState) -> ChatState:
    """위치 검색 노드."""
    location = state.get("user_location")
    
    if not location:
        # 위치 없음 → SSE 이벤트 발행
        return {
            **state,
            "tool_results": {
                "location_search": {
                    "status": "need_location",
                    "message": "위치 정보가 필요해요. 공유해주세요! 📍"
                }
            }
        }
    
    # 위치 있음 → API 호출
    results = search_nearby_centers(
        latitude=location["lat"],
        longitude=location["lon"],
    )
    return {**state, "tool_results": {"location_search": results}}
```

#### 7.2.5 SSE 이벤트 타입

```python
class SSEEventType(str, Enum):
    """SSE 이벤트 타입."""
    TOKEN = "token"              # 답변 토큰
    PROGRESS = "progress"        # 진행 상황
    TOOL_START = "tool_start"    # Tool 실행 시작
    TOOL_END = "tool_end"        # Tool 실행 완료
    REQUEST_LOCATION = "request_location"  # 위치 요청
    DONE = "done"                # 완료
    ERROR = "error"              # 에러
```

### 7.3 location Tool 정의

```python
from langchain.tools import tool
from pydantic import BaseModel, Field
import httpx


class LocationSearchInput(BaseModel):
    """위치 검색 입력."""
    latitude: float = Field(..., description="위도 (예: 37.5665)")
    longitude: float = Field(..., description="경도 (예: 126.9780)")
    radius: int = Field(
        default=2000,
        description="검색 반경 (미터). 기본값 2km"
    )
    store_category: str = Field(
        default="all",
        description="매장 카테고리 필터. "
                    "refill_zero, cafe_bakery, vegan_dining, "
                    "upcycle_recycle, public_dropbox, all"
    )


@tool(args_schema=LocationSearchInput)
async def search_nearby_centers(
    latitude: float,
    longitude: float,
    radius: int = 2000,
    store_category: str = "all",
) -> str:
    """주변 재활용 센터나 제로웨이스트샵을 검색합니다.
    
    사용자가 "주변 재활용 센터", "근처 제로웨이스트샵",
    "가까운 분리수거함" 등을 물어볼 때 사용합니다.
    """
    async with httpx.AsyncClient() as client:
        response = await client.get(
            "http://location-api:8000/locations/centers",
            params={
                "lat": latitude,
                "lon": longitude,
                "radius": radius,
                "store_category": store_category,
            },
        )
        response.raise_for_status()
        
    centers = response.json()
    
    if not centers:
        return "근처에 재활용 센터를 찾지 못했습니다."
    
    # 포맷팅
    result_lines = [f"📍 주변 {len(centers)}개의 센터를 찾았습니다:\n"]
    for c in centers[:5]:  # 상위 5개
        result_lines.append(
            f"• {c['name']} ({c['distance_text']})\n"
            f"  주소: {c['road_address']}\n"
            f"  운영: {c.get('start_time', '?')}~{c.get('end_time', '?')}"
        )
    
    return "\n".join(result_lines)
```

### 7.3 의도 분류 확장

```python
# 의도 분류에 'location' 추가
INTENTS = Literal[
    "waste",      # 분리배출 질문
    "character",  # 캐릭터 관련
    "location",   # 위치 검색
    "general",    # 일반 대화
]


def route_by_intent(state: ChatState) -> str:
    """의도에 따른 분기."""
    intent = state.get("intent", "general")
    
    routes = {
        "waste": "waste_rag_node",
        "character": "character_node",
        "location": "location_tool_node",
        "general": "general_llm_node",
    }
    return routes.get(intent, "general_llm_node")
```

### 7.4 확장된 Workflow

```
Chat Service Workflow (Tool Calling 포함)
=========================================

START
  │
  ├─ image? ──▶ Vision → Rule RAG → Answer
  │
  └─ text? ──▶ Intent Classifier
                    │
                    ├─ waste ────▶ Waste RAG ───┐
                    ├─ character ▶ Char Info ───┼──▶ Answer
                    ├─ location ─▶ Location Tool┤
                    └─ general ──▶ LLM ─────────┘
                                                  │
                                                  v
                                                 END
```

### 7.5 StoreCategory / PickupCategory

**location 서비스에서 지원하는 카테고리:**

| StoreCategory | 설명 |
|--------------|------|
| `refill_zero` | 리필/제로웨이스트 |
| `cafe_bakery` | 카페/베이커리 |
| `vegan_dining` | 비건 식당 |
| `upcycle_recycle` | 업사이클/재활용 |
| `public_dropbox` | 공공 수거함 |

| PickupCategory | 설명 |
|---------------|------|
| `clear_pet` | 투명 페트병 |
| `can` | 캔 |
| `paper` | 종이 |
| `plastic` | 플라스틱 |
| `glass` | 유리 |
| `textile` | 의류 |
| `electronics` | 전자제품 |

### 7.6 Tool 사용 예시 대화

```
사용자: 근처에 제로웨이스트샵 있어?

[Intent: location]
[Tool: search_nearby_centers]

봇: 🗺️ 주변 센터 검색 중...

📍 주변 3개의 센터를 찾았습니다:

• 알맹상점 (0.8km)
  주소: 서울시 마포구 월드컵로 49
  운영: 11:00~20:00
...
```

---

## 8. 캐릭터 미리보기 워크플로우

### 8.1 요구사항

사용자가 분리배출 **전에** 어떤 캐릭터를 얻을 수 있는지 미리 확인:

| 입력 유형 | 예시 | 필요한 처리 |
|----------|------|------------|
| **이미지 + 질문** | "이거 분리배출하면 어떤 캐릭터?" | Vision → 매칭 조회 |
| **텍스트 질문** | "플라스틱 버리면 무슨 캐릭터?" | 품목 추출 → 매칭 조회 |

### 8.2 캐릭터 데이터 분리 구조

**핵심**: 캐릭터 이미지/상세 정보는 **프론트엔드**에, 매칭 로직은 **백엔드**에

```
┌─────────────────────────────────────────────────────────┐
│ Frontend (React)                                        │
│ src/constants/CharacterInfo.ts                          │
│                                                         │
│ CHARACTER_DATA = {                                      │
│   pet:    { name: "페티", wasteName: "무색페트병",       │
│            characterImage: sub_pet.png, ... },          │
│   metal:  { name: "메탈리", wasteName: "금속류", ... }, │
│   glass:  { name: "글래시", wasteName: "유리병", ... }, │
│   ...                                                   │
│ }                                                       │
│                                                         │
│ ✅ 이미지, 설명, 서브설명 등 UI 관련 정보               │
└─────────────────────────────────────────────────────────┘
                        ↑
                        │ characterKey (예: "pet")
                        │
┌─────────────────────────────────────────────────────────┐
│ Backend (FastAPI)                                       │
│ apps/character/domain/entities/character.py             │
│                                                         │
│ @dataclass                                              │
│ class Character:                                        │
│     code: str         # "pet" (프론트엔드 key와 동일)   │
│     name: str         # "페티"                          │
│     match_label: str  # "무색페트병" (매칭용)           │
│     dialog: str       # "분리배출 잘했어!"              │
│                                                         │
│ ✅ 매칭 로직, 대사, 소유권 관리                         │
└─────────────────────────────────────────────────────────┘
```

**캐릭터 매칭 흐름:**

```
Vision 결과: middle_category = "무색페트병"
                 │
                 v
Backend: match_label == "무색페트병" → code = "pet"
                 │
                 v
Response: { "characterKey": "pet", "name": "페티", "dialog": "..." }
                 │
                 v
Frontend: CHARACTER_DATA["pet"] → 이미지, 상세 정보 렌더링
```

**프론트엔드 캐릭터 목록:**

| Key | Name | WasteName | Type |
|-----|------|-----------|------|
| eco | 이코 | 이코 | main |
| paper | 페이피 | 종이 | sub |
| paperProduct | 팩토리 | 종이팩 | sub |
| pet | 페티 | 무색페트병 | sub |
| vinyl | 비니 | 비닐류 | sub |
| glass | 글래시 | 유리병 | sub |
| clothes | 코튼 | 의류·원단 | sub |
| plastic | 플리 | 플라스틱류 | sub |
| metal | 메탈리 | 금속류 | sub |
| battery | 배리 | 전지 | sub |
| lighting | 라이티 | 조명제품 | sub |
| monitor | 일렉 | 전기전자 | sub |
| styrofoam | 폼이 | 발포합성수지 | sub |

### 8.3 의도 분류 확장

```python
INTENTS = Literal[
    "waste",           # 분리배출 질문
    "character",       # 캐릭터 관련
    "character_preview",  # 캐릭터 미리보기
    "location",        # 위치 검색
    "general",         # 일반 대화
]

# 의도 분류 프롬프트 힌트
"""
character_preview: 
  - "~하면 어떤 캐릭터 얻어?"
  - "~버리면 무슨 캐릭터?"
  - "이거 분리배출하면 캐릭터?"
"""
```

### 8.4 확장된 Workflow

```
Chat Service Workflow (캐릭터 미리보기 포함)
============================================

START
  │
  ├─ image + "캐릭터?" ──▶ [Vision] → [Character Preview] → Answer
  │
  ├─ image ──▶ [Vision] → [Rule RAG] → [Answer]
  │
  └─ text ──▶ [Intent Classifier]
                    │
                    ├─ waste ──────────▶ [Waste RAG] ────┐
                    ├─ character ──────▶ [Char Info] ────┤
                    ├─ character_preview ▶ [Char Preview]┼──▶ Answer
                    ├─ location ───────▶ [Location Tool] ┤
                    └─ general ────────▶ [LLM] ──────────┘
```

### 8.5 Character Preview Tool 정의

```python
from langchain.tools import tool
import httpx


@tool
async def preview_character_by_category(
    middle_category: str,
) -> dict:
    """분리배출 품목으로 얻을 수 있는 캐릭터를 미리 확인합니다.
    
    사용자가 "~하면 어떤 캐릭터?", "~버리면 무슨 캐릭터?"
    등을 물어볼 때 사용합니다.
    
    Args:
        middle_category: 품목 중분류 (예: "무색페트병", "금속류", "유리병")
    
    Returns:
        characterKey: 프론트엔드 CHARACTER_DATA key
        name: 캐릭터 이름
        dialog: 캐릭터 대사
        
    Note:
        이미지는 프론트엔드 CHARACTER_DATA에서 조회
        (frontend/src/constants/CharacterInfo.ts)
    """
    # character 서비스의 카탈로그 API 호출
    async with httpx.AsyncClient() as client:
        response = await client.get(
            "http://character-api:8000/characters",
        )
        response.raise_for_status()
    
    characters = response.json()
    
    # match_label로 매칭 → characterKey(code) 반환
    for char in characters:
        if char.get("match") == middle_category:
            return {
                "characterKey": char["code"],  # 프론트 key
                "name": char["name"],
                "dialog": char["dialog"],
                "matched": True,
            }
    
    # 기본 캐릭터 (eco)
    return {
        "characterKey": "eco",
        "name": "이코",
        "dialog": "분리배출 잘했어!",
        "matched": False,
    }
```

**응답 예시 (SSE):**

```json
{
  "type": "character_preview",
  "data": {
    "characterKey": "pet",
    "name": "페티",
    "dialog": "페트병 분리배출 잘했어!"
  }
}
```

**프론트엔드 처리:**

```typescript
// 프론트엔드에서 characterKey로 이미지 조회
const characterKey = response.data.characterKey;  // "pet"
const characterInfo = CHARACTER_DATA[characterKey];

// 렌더링
<img src={characterInfo.characterImage} />
<p>{characterInfo.characterName}: {response.data.dialog}</p>
```

### 8.6 Character Preview 노드 구현

```python
async def character_preview_node(
    state: ChatState,
    event_publisher: EventPublisher,
) -> ChatState:
    """캐릭터 미리보기 노드.
    
    이미지 입력: Vision 결과의 middle_category 사용
    텍스트 입력: LLM으로 품목 추출 후 사용
    
    Note:
        이미지는 프론트엔드 CHARACTER_DATA에서 조회
        백엔드는 characterKey만 반환
    """
    job_id = state["job_id"]
    
    # 진행 이벤트
    await event_publisher.publish(job_id, {
        "type": "progress",
        "stage": "character_preview",
        "status": "started",
        "message": "🔮 캐릭터 확인 중...",
    })
    
    # middle_category 결정
    if state.get("classification"):
        # 이미지 → Vision 결과에서 추출
        middle_category = state["classification"].get(
            "middle_category"
        )
    else:
        # 텍스트 → LLM으로 품목 추출
        middle_category = await extract_category_from_text(
            state["message"]
        )
    
    if not middle_category:
        return {
            **state,
            "context": "어떤 품목인지 알려주시면 캐릭터 정보를 알려드릴게요!",
        }
    
    # 캐릭터 매칭 조회 (characterKey 반환)
    result = await preview_character_by_category(middle_category)
    
    # 프론트엔드용 character_preview 이벤트
    await event_publisher.publish(job_id, {
        "type": "character_preview",
        "data": {
            "characterKey": result["characterKey"],
            "name": result["name"],
            "dialog": result["dialog"],
            "matched": result["matched"],
        },
    })
    
    await event_publisher.publish(job_id, {
        "type": "progress",
        "stage": "character_preview",
        "status": "completed",
    })
    
    # Answer 노드에서 사용할 컨텍스트
    if result["matched"]:
        context = (
            f"'{middle_category}' 분리배출하면 "
            f"**{result['name']}** 캐릭터를 얻을 수 있어요! "
            f"{result['name']}: \"{result['dialog']}\""
        )
    else:
        context = (
            f"'{middle_category}'와 매칭되는 캐릭터가 아직 없어요. "
            f"기본 캐릭터 이코를 받게 됩니다! 🌱"
        )
    
    return {
        **state,
        "character_preview": result,
        "context": context,
    }
        "context": result,
    }


async def extract_category_from_text(message: str) -> str | None:
    """텍스트에서 품목 중분류를 추출합니다."""
    
    # 품목 매핑 (간단한 키워드 매칭)
    CATEGORY_KEYWORDS = {
        "페트병": "무색페트병",
        "플라스틱": "플라스틱류",
        "유리병": "유리병",
        "캔": "금속류",
        "종이": "종이류",
        "옷": "의류",
        "전자제품": "소형가전",
        "배터리": "전지류",
    }
    
    for keyword, category in CATEGORY_KEYWORDS.items():
        if keyword in message:
            return category
    
    # 키워드 없으면 LLM으로 추출
    prompt = f"""
    다음 문장에서 분리배출 품목을 추출해주세요.
    품목이 없으면 "없음"이라고 답해주세요.
    
    문장: {message}
    
    가능한 품목: 무색페트병, 유색페트병, 플라스틱류, 유리병, 
    금속류, 종이류, 의류, 소형가전, 전지류, 형광등, 음식물
    
    품목:
    """
    
    response = await llm.ainvoke(prompt)
    category = response.content.strip()
    
    return None if category == "없음" else category
```

### 8.7 예시 대화

**케이스 1: 이미지 + 질문**
```
사용자: [이미지: 페트병] 이거 분리배출하면 어떤 캐릭터?

[Input: image + "캐릭터"]
[Vision → classification: {middle_category: "무색페트병"}]
[Character Preview Tool]

봇: 🔮 캐릭터 확인 중...

🎉 '무색페트병' 분리배출하면 **페티** 캐릭터를 얻을 수 있어요!

타입: 플라스틱
대사: "투명하게 분리해줘서 고마워!"
```

**케이스 2: 텍스트 질문**
```
사용자: 캔 버리면 무슨 캐릭터 얻어?

[Intent: character_preview]
[Extract: "캔" → "금속류"]
[Character Preview Tool]

봇: 🔮 캐릭터 확인 중...

🎉 '금속류' 분리배출하면 **캐니** 캐릭터를 얻을 수 있어요!

타입: 금속
대사: "찌그러뜨려서 버려줘!"
```

### 8.8 라우팅 로직 업데이트

```python
def route_by_input_type(state: ChatState) -> str:
    """입력 유형에 따른 1차 분기."""
    has_image = bool(state.get("image_url"))
    message = state.get("message", "").lower()
    
    # 이미지 + 캐릭터 질문
    if has_image and any(kw in message for kw in [
        "캐릭터", "뭐 얻", "무슨 캐릭", "어떤 캐릭"
    ]):
        return "vision_for_character"  # Vision → Character Preview
    
    # 이미지만
    if has_image:
        return "vision_node"  # Vision → Rule → Answer
    
    # 텍스트
    return "intent_classifier"


def route_after_vision(state: ChatState) -> str:
    """Vision 결과 후 분기."""
    # 캐릭터 미리보기 모드였는지 확인
    if state.get("preview_mode"):
        return "character_preview_node"
    return "rule_rag_node"
```

---

## 9. Tool Calling 선택 이유

### 9.1 왜 규칙 기반(Bash)이 아닌 Tool Calling인가?

**고려했던 대안: 규칙 기반 라우팅**

| 방식 | 컨텍스트 | 지연 시간 | 적용 가능 환경 |
|------|---------|----------|--------------|
| 규칙 기반 (Bash/로컬) | 적음 | 빠름 | ❌ 로컬 컴퓨팅만 |
| Tool Calling | 많음 | 보통 | ✅ 웹/앱 환경 |

### 9.2 규칙 기반을 선택할 수 없는 이유

```
⚠️ Eco² Chat은 웹/앱 기반 서비스

┌─────────────────────────────────────────────────┐
│  클라이언트 (웹 브라우저 / 모바일 앱)            │
│  - JavaScript/Swift/Kotlin 환경                │
│  - Bash 실행 불가                              │
│  - 서버 명령어 실행 권한 없음                   │
└─────────────────────────────────────────────────┘
                      │
                      │ HTTP/WebSocket
                      v
┌─────────────────────────────────────────────────┐
│  서버 (FastAPI + LangGraph)                     │
│  - Tool Calling으로 외부 서비스 연동            │
│  - LLM이 도구 선택 및 파라미터 결정             │
└─────────────────────────────────────────────────┘
```

**규칙 기반이 적합한 환경:**
- Cursor, VSCode 등 IDE 내 AI 어시스턴트
- CLI 기반 로컬 챗봇
- 서버 사이드 배치 처리

**Tool Calling이 필수인 환경:**
- ✅ 웹 애플리케이션
- ✅ 모바일 앱 (iOS, Android)
- ✅ 외부 API 연동이 필요한 경우
- ✅ 사용자 인터랙션 기반 서비스

### 9.3 Tool Calling의 장점

```python
# Tool Calling: LLM이 상황에 맞는 도구와 파라미터를 선택
@tool
async def search_nearby_centers(
    latitude: float,
    longitude: float,
    store_category: str = "all",
) -> str:
    """주변 재활용 센터를 검색합니다."""
    ...

# LLM이 자연어를 파싱하여 적절한 파라미터 결정
# "강남역 근처 제로웨이스트샵" 
# → latitude=37.498, longitude=127.028, store_category="refill_zero"
```

**장점:**
1. **유연한 파라미터 추출**: LLM이 자연어에서 파라미터 추출
2. **확장 용이**: 새 Tool 추가 시 코드 변경 최소화
3. **복잡한 질의 처리**: "강남역 근처 페트병 버릴 수 있는 곳" 등

### 9.4 Programmatic Tool Calling 도입 검토

> **참고**: [Anthropic - Advanced Tool Use (2025-11-24)](https://www.anthropic.com/engineering/advanced-tool-use)

**기존 Tool Calling의 문제점:**

```
[문제 1: 컨텍스트 오염]

User: "강남역 근처 재활용센터랑 페트병 캐릭터 알려줘"

기존 방식:
  LLM → search_nearby_centers → [10개 센터 전체 JSON]
                                    ↓ 컨텍스트 +2000토큰
  LLM → preview_character → [캐릭터 상세 JSON]
                                    ↓ 컨텍스트 +500토큰
  LLM → 답변 생성

문제: 중간 결과 전체가 컨텍스트에 누적
```

**Programmatic Tool Calling 적용:**

```python
# Claude가 작성하고 실행하는 코드
# (코드 실행 환경에서 동작, 컨텍스트에는 결과만)

centers = search_nearby_centers(
    lat=37.498, lon=127.028,
    store_category="public_dropbox"
)
character = preview_character(
    middle_category="무색페트병"
)

# 필요한 정보만 추출하여 반환
return {
    "top_centers": [
        {"name": c["name"], "dist": c["distance"]}
        for c in sorted(centers, key=lambda x: x["distance"])[:3]
    ],
    "character": {
        "name": character["name"],
        "dialog": character["dialog"]
    }
}
```

**효과:**

| 항목 | 기존 | Programmatic |
|------|------|-------------|
| Inference 횟수 | 3회 | 1회 + 코드 실행 |
| 컨텍스트 증가 | ~2500 토큰 | ~200 토큰 |
| 병렬 처리 | ❌ | ✅ |
| 데이터 변환 | LLM이 처리 | 코드로 처리 |

**구현 방식 (Claude API + LangGraph):**

```python
async def multi_tool_node(state: ChatState) -> ChatState:
    """Programmatic Tool Calling 노드."""
    
    response = await client.beta.messages.create(
        betas=["advanced-tool-use-2025-11-20"],
        model="claude-sonnet-4-5-20250929",
        tools=[
            {
                "type": "code_execution_20250825",
                "name": "code_execution"
            },
            {
                "name": "search_nearby_centers",
                "description": "주변 재활용 센터 검색",
                "allowed_callers": ["code_execution"],
                "input_schema": {...}
            },
            {
                "name": "preview_character",
                "description": "분리배출 시 획득 가능 캐릭터",
                "allowed_callers": ["code_execution"],
                "input_schema": {...}
            },
        ],
        messages=[{"role": "user", "content": state["message"]}]
    )
    
    # Claude가 코드를 작성하고 실행한 결과만 반환됨
    return {**state, "tool_results": response.content}
```

**적용 대상 Tool:**

| Tool | 적용 | 이유 |
|------|-----|------|
| `search_nearby_centers` | ✅ | 결과 필터링/정렬 필요 |
| `preview_character` | ✅ | 다른 Tool과 병렬 호출 가능 |
| `get_user_characters` | ✅ | 목록 데이터 추출 필요 |

**주의사항:**
- Beta 기능 (2025-11-24 발표)
- Claude API 직접 호출 필요
- LangGraph 노드 내에서 통합 사용

### 9.5 최종 아키텍처

```
Chat Service (Programmatic Tool Calling)
========================================

[Client (Web/App)]
       │
       │ POST /chat/messages
       v
[Chat API] ──────────────────────────────────────┐
       │                                         │
       v                                         │
[LangGraph Pipeline]                             │
       │                                         │
       ├── Intent Node                           │
       │      └── 의도 분류                      │
       │                                         │
       ├── Multi-Tool Node (Programmatic)        │
       │      ├── Claude Code Execution          │
       │      │     └── 코드로 Tool 호출         │
       │      ├── search_nearby_centers          │
       │      ├── preview_character              │
       │      └── 결과 요약만 반환               │
       │                                         │
       └── Answer Generation                     │
              └── 요약 기반 답변 생성            │
                                                 │
[Redis Streams] <────────────────────────────────┘
       │
       v
[SSE Gateway] → [Client]
```

### 9.6 모델별 Tool Calling 전략

**문제: Provider별 Tool Calling 방식 차이**

| Provider | 방식 | 실행 주체 | 특징 |
|----------|------|----------|------|
| Anthropic | Programmatic | Claude 샌드박스 | 코드로 병렬 실행, 요약 반환 |
| OpenAI | Function Calling | 개발자 코드 | 순차/병렬 요청, 결과 전달 |
| Google | Function Calling | 개발자 코드 | OpenAI와 유사 |

**해결: Port/Adapter 패턴으로 추상화**

```python
# Port: Tool Calling 인터페이스
class ToolCallerPort(Protocol):
    """모델별 Tool Calling 추상화."""
    
    async def call_tools(
        self,
        message: str,
        tools: list[Tool],
        context: dict,
    ) -> ToolResult:
        """Tool 호출 및 결과 반환."""
        ...


# Adapter: Claude (Programmatic Tool Calling)
class ClaudeToolCaller(ToolCallerPort):
    """Claude Programmatic Tool Calling."""
    
    async def call_tools(
        self,
        message: str,
        tools: list[Tool],
        context: dict,
    ) -> ToolResult:
        response = await self._client.beta.messages.create(
            betas=["advanced-tool-use-2025-11-20"],
            model=self._model,
            tools=[
                {"type": "code_execution_20250825", 
                 "name": "code_execution"},
                *[self._to_claude_tool(t) for t in tools]
            ],
            messages=[{"role": "user", "content": message}]
        )
        # Claude가 코드 작성 → 실행 → 요약 반환
        return self._parse_response(response)
    
    def _to_claude_tool(self, tool: Tool) -> dict:
        return {
            "name": tool.name,
            "description": tool.description,
            "allowed_callers": ["code_execution"],
            "input_schema": tool.schema,
        }


# Adapter: OpenAI (Function Calling)
class OpenAIToolCaller(ToolCallerPort):
    """OpenAI Function Calling."""
    
    async def call_tools(
        self,
        message: str,
        tools: list[Tool],
        context: dict,
    ) -> ToolResult:
        response = await self._client.chat.completions.create(
            model=self._model,
            tools=[self._to_openai_tool(t) for t in tools],
            tool_choice="auto",
            parallel_tool_calls=True,
            messages=[{"role": "user", "content": message}]
        )
        
        # 개발자가 직접 실행해야 함
        tool_calls = response.choices[0].message.tool_calls
        results = await self._execute_tools(tool_calls)
        
        # 결과를 다시 LLM에 전달하여 답변 생성
        return await self._get_final_response(
            message, tool_calls, results
        )
    
    async def _execute_tools(
        self, 
        tool_calls: list
    ) -> list[dict]:
        """Tool 실행 (개발자 코드에서)."""
        tasks = []
        for tc in tool_calls:
            executor = self._tool_executors[tc.function.name]
            args = json.loads(tc.function.arguments)
            tasks.append(executor(**args))
        
        return await asyncio.gather(*tasks)


# Adapter: Gemini (Function Calling)
class GeminiToolCaller(ToolCallerPort):
    """Gemini Function Calling - OpenAI와 유사."""
    
    async def call_tools(
        self,
        message: str,
        tools: list[Tool],
        context: dict,
    ) -> ToolResult:
        response = await self._model.generate_content_async(
            message,
            tools=[self._to_gemini_tool(t) for t in tools],
        )
        
        # OpenAI와 동일하게 개발자가 실행
        function_calls = response.candidates[0].function_calls
        results = await self._execute_tools(function_calls)
        
        return await self._get_final_response(
            message, function_calls, results
        )
```

**Factory로 선택:**

```python
class ToolCallerFactory:
    """모델별 Tool Caller 생성."""
    
    _callers = {
        "claude": ClaudeToolCaller,
        "gpt": OpenAIToolCaller,
        "gemini": GeminiToolCaller,
    }
    
    @classmethod
    def create(
        cls,
        provider: str,
        model: str,
        tool_executors: dict[str, Callable],
    ) -> ToolCallerPort:
        caller_cls = cls._callers[provider]
        return caller_cls(model, tool_executors)
```

**LangGraph 노드에서 사용:**

```python
async def multi_tool_node(
    state: ChatState,
    tool_caller: ToolCallerPort,  # DI
) -> ChatState:
    """모델에 무관한 Tool Calling 노드."""
    
    result = await tool_caller.call_tools(
        message=state["message"],
        tools=state["available_tools"],
        context=state.get("context", {}),
    )
    
    return {**state, "tool_results": result}
```

**흐름 비교:**

```
Claude (Programmatic):
┌────────┐    ┌──────────────────┐    ┌────────┐
│ Intent │ →  │ Claude 코드 실행  │ →  │ Answer │
└────────┘    │ (Tool 병렬 호출)  │    └────────┘
              └──────────────────┘
              API 호출: 1회

GPT/Gemini (Function Calling):
┌────────┐    ┌────────┐    ┌────────┐    ┌────────┐
│ Intent │ →  │ LLM    │ →  │ 개발자  │ →  │ Answer │
└────────┘    │ 요청   │    │ 실행   │    └────────┘
              └────────┘    └────────┘
              API 호출: 2회+
```

**설계 원칙:**
1. **Port로 추상화**: 노드는 `ToolCallerPort`만 의존
2. **Adapter로 구현**: Provider별 차이를 숨김
3. **Factory로 선택**: 런타임에 적절한 Adapter 생성
4. **DI로 주입**: 테스트/교체 용이

---

## 10. Subagent 아키텍처

### 10.1 Evaluator-Optimizer (선택적)

```python
# 답변 품질 검증 노드
def add_evaluator(graph):
    graph.add_node("evaluator", evaluate_answer_node)
    
    # answer → evaluator → (pass) → END
    #                    → (fail) → answer
    graph.add_edge("answer_node", "evaluator")
    graph.add_conditional_edges(
        "evaluator",
        route_by_evaluation,
        {"pass": END, "retry": "answer_node"}
    )
```

### 10.2 Context 오염 문제와 Subagent 결정

#### 10.2.1 문제: Context Window 오염

복잡한 질문 처리 시 컨텍스트 윈도우가 빠르게 포화됩니다.

```
"페트병, 유리병, 캔, 종이, 의류 각각 어떻게 버려?"

단순 처리 시 컨텍스트 증가:
┌─────────────────────────────────────────────────┐
│ RAG 결과 1: 페트병 규정 (~500 토큰)              │
│ RAG 결과 2: 유리병 규정 (~500 토큰)              │
│ RAG 결과 3: 캔 규정 (~500 토큰)                  │
│ RAG 결과 4: 종이 규정 (~500 토큰)                │
│ RAG 결과 5: 의류 규정 (~500 토큰)                │
│ Tool 결과: location (~300 토큰)                  │
│ Tool 결과: character 5개 (~500 토큰)            │
├─────────────────────────────────────────────────┤
│ 총 컨텍스트 증가: ~3,300+ 토큰                   │
│ + 대화 히스토리가 길어지면 더 심각               │
└─────────────────────────────────────────────────┘
```

#### 10.2.2 해결 옵션 비교

| 접근 방식 | 설명 | 컨텍스트 관리 | 구현 복잡도 |
|----------|------|-------------|------------|
| **RLM** | 재귀적 자기 호출 | 프롬프트를 환경으로 | 높음 (실험적) |
| **Subagent** | 별도 에이전트 위임 | 컨텍스트 격리 | 중간 (LangGraph 네이티브) |

#### 10.2.3 RLM vs Subagent

**RLM (Recursive Language Models):**

```
[논문 기반 접근]
Main LLM
  ├─ Inspect: 프롬프트 분석
  ├─ Search: 관련 부분 탐색
  └─ Recursive Call: LLM(sub_prompt)
       └─ ... (재귀)
  └─ Synthesize

장점: 이론적 우아함, 동일 모델 재사용
단점: 실험적, 재귀 깊이 관리 복잡, 디버깅 어려움
```

**Subagent (Deep Agents):**

> 참고: [LangChain Deep Agents Harness](https://docs.langchain.com/oss/python/deepagents/harness)

```
[LangGraph 네이티브 접근]
Main Agent
  ├─ Decompose: 서브 질문 분해
  ├─ task(sub_q1) → Subagent 1 (격리된 컨텍스트)
  ├─ task(sub_q2) → Subagent 2 (병렬 실행 가능)
  └─ Synthesize: 결과 합성 (압축된 결과만)

장점: 컨텍스트 격리 명확, 병렬 실행, LangGraph 통합
단점: 서브에이전트 관리 오버헤드
```

#### 10.2.4 Eco² 환경에서의 결정

**현재 인프라:**

```
Eco² (준프로덕션 규모)
├── 24-nodes K8s 클러스터
├── 3-Tier Redis (Streams + Pub/Sub + State KV)
├── Istio + Jaeger 분산 트레이싱
├── 2,500 VU → RPS 1,500+ Baseline
└── Clean Architecture 마이그레이션 완료 (Chat 제외)
```

**결정: Subagent 선택**

| 기준 | RLM | Subagent | Eco² 적합성 |
|------|-----|----------|------------|
| LangGraph 통합 | 커스텀 필요 | 네이티브 | **Subagent** ✅ |
| 기존 Redis 활용 | 가능 | 자연스러움 | **Subagent** ✅ |
| SSE 이벤트 흐름 | 복잡 | 명확 | **Subagent** ✅ |
| Jaeger 트레이싱 | 어려움 | 노드별 span | **Subagent** ✅ |
| 병렬 처리 | 가능 | 명시적 지원 | **Subagent** ✅ |
| 운영 안정성 | 실험적 | 검증된 패턴 | **Subagent** ✅ |

**선택 이유:**
1. **LangGraph 네이티브**: `task` tool이 자연스럽게 통합
2. **Observability**: Jaeger에서 서브에이전트별 span 추적
3. **SSE 흐름 명확**: 서브에이전트 진행 상황을 개별 이벤트로 발행
4. **기존 인프라**: 3-Tier Redis 구조와 호환
5. **운영 안정성**: 준프로덕션 규모에서 실험적 접근 지양

### 10.3 Subagent 도입 대상

#### 노드별 Subagent 분리 결정:

| 노드 | 위치 | Subagent 분리 | 이유 |
|------|------|-------------|------|
| `vision_node` | 메인 | ❌ | 단순 분류, 빠른 응답 필요 |
| `intent_classifier` | 메인 | ❌ | 라우팅 핵심, 메인 유지 |
| `waste_rag_node` | 메인/Subagent | ✅ 조건부 | 멀티 카테고리 시 `waste_expert` |
| `location_tool` | Subagent | ✅ | `location_expert`로 격리 |
| `character_preview` | Subagent | ✅ | `character_expert`로 격리 |
| `answer_node` | 메인 | ❌ | 최종 합성, 스트리밍 |

#### Subagent 분리 시나리오:

```
시나리오: 복합 질문 + 멀티 Tool

User: "페트병이랑 캔 어떻게 버려? 
       근처 재활용센터도 알려주고, 
       각각 무슨 캐릭터 얻는지도!"

현재 (메인 컨텍스트 오염):
┌─────────────────────────────────────────────┐
│ Main Agent Context                          │
│ ├─ RAG: 페트병 규정 (+500)                   │
│ ├─ RAG: 캔 규정 (+500)                       │
│ ├─ Tool: location 결과 (+300)               │
│ ├─ Tool: 페트병 캐릭터 (+100)                │
│ ├─ Tool: 캔 캐릭터 (+100)                    │
│ └─ 총: +1,500 토큰 (컨텍스트 오염)           │
└─────────────────────────────────────────────┘

Subagent 분리 후:
┌─────────────────────────────────────────────┐
│ Main Agent Context (깔끔)                   │
│ └─ 서브에이전트 결과 요약만 (+200 토큰)       │
└─────────────────────────────────────────────┘
        │
        ├─ Subagent 1: waste_expert
        │   └─ (격리) 페트병+캔 RAG → 요약 반환
        │
        ├─ Subagent 2: location_expert  
        │   └─ (격리) 위치 검색 → 상위 3개만 반환
        │
        └─ Subagent 3: character_expert
            └─ (격리) 캐릭터 조회 → 이름+대사만 반환
```

### 10.4 Subagent 구현 설계

```python
# Subagent 정의
SUBAGENTS = {
    "waste_expert": {
        "description": "분리배출 규정 전문가",
        "tools": [waste_rag_tool],
        "system_prompt": "분리배출 규정을 검색하고 요약합니다.",
    },
    "location_expert": {
        "description": "주변 센터 검색 전문가", 
        "tools": [search_nearby_centers],
        "system_prompt": "가까운 재활용센터를 찾아 상위 3개만 반환합니다.",
    },
    "character_expert": {
        "description": "캐릭터 정보 전문가",
        "tools": [preview_character, get_user_characters],
        "system_prompt": "캐릭터 정보를 조회하고 핵심만 반환합니다.",
    },
}


# Main Agent의 task tool
@tool
async def delegate_to_expert(
    expert: Literal["waste", "location", "character"],
    query: str,
) -> str:
    """전문 서브에이전트에게 태스크 위임.
    
    컨텍스트 격리: 서브에이전트 작업이 메인 컨텍스트 오염 X
    결과 압축: 필요한 정보만 요약하여 반환
    """
    subagent = create_subagent(SUBAGENTS[f"{expert}_expert"])
    result = await subagent.ainvoke({"query": query})
    return result["summary"]  # 압축된 결과만


# 복잡한 질문 라우팅
def route_by_complexity(state: ChatState) -> str:
    """복잡도에 따른 처리 경로 결정."""
    
    message = state["message"]
    
    # 복잡한 질문 감지
    if count_categories(message) >= 2:
        return "decompose_node"  # Subagent로 분해
    
    if needs_multiple_tools(message):
        return "multi_tool_node"  # Subagent 병렬 호출
    
    return "simple_workflow"  # 기존 단순 경로
```

### 10.5 SSE 이벤트 (Subagent)

```
┌─────────────────────────────────────────────┐
│  SSE: decompose                             │
│  "🔄 3개 전문가에게 질문 분배 중..."          │
└─────────────────────────────────────────────┘
        │
        v
┌─────────────────────────────────────────────┐
│  SSE: subagent_start                        │
│  {"expert": "waste", "status": "started"}   │
│  {"expert": "location", "status": "started"}│
│  {"expert": "character", "status": "started"}│
└─────────────────────────────────────────────┘
        │ (병렬 실행)
        v
┌─────────────────────────────────────────────┐
│  SSE: subagent_done                         │
│  {"expert": "location", "status": "done"}   │
│  {"expert": "waste", "status": "done"}      │
│  {"expert": "character", "status": "done"}  │
└─────────────────────────────────────────────┘
        │
        v
┌─────────────────────────────────────────────┐
│  SSE: synthesize                            │
│  "📝 답변 합성 중..."                        │
└─────────────────────────────────────────────┘
        │
        v
┌─────────────────────────────────────────────┐
│  SSE: delta (토큰 스트리밍)                  │
└─────────────────────────────────────────────┘
```

### 10.6 RLM 통합 (선택적 확장)

매우 복잡한 질문(긴 규정, 긴 대화 히스토리)에서 필요시 RLM 원칙을 서브에이전트 내부에 적용:

```
Subagent + RLM 하이브리드:
├─ 일반 질문: Subagent 기본 처리
└─ 매우 긴 컨텍스트: Subagent 내부에서 RLM 적용
   └─ waste_expert가 긴 규정을 재귀적으로 처리
```

**상세**: `docs/blogs/async/foundations/17-recursive-language-models.md`

### 10.7 시스템 프롬프트 설계

scan_worker 프롬프트 스타일을 참고하여 Chat 서비스 프롬프트 설계.

> **참고**: `apps/scan_worker/infrastructure/assets/prompts/`

#### 10.7.1 입력 형식 결정: XML vs 마크다운

**scan에서 XML 사용 이유:**
```xml
<context id="classification">...</context>
<context id="lite_rag">...</context>
```

**평가:**

| 방식 | 토큰 비용 | LLM 이해도 | 권장 |
|------|----------|-----------|------|
| XML | 높음 (태그 오버헤드) | 좋음 | ❌ |
| **마크다운** | **낮음** | **좋음** | ✅ |
| JSON | 중간 | 좋음 | △ |

**결정: 마크다운 사용**
- 최신 LLM(Claude, GPT, Gemini)은 마크다운을 잘 이해
- 토큰 효율성 높음
- 가독성 좋음

#### 10.7.2 프롬프트 파일 구조

```
apps/chat_worker/infrastructure/assets/prompts/
├── system_prompt.txt           # Main Agent (이코 페르소나)
├── intent_classifier.txt       # 의도 분류 전용
├── subagent_waste_expert.txt   # Subagent: 분리배출 전문가
├── subagent_location_expert.txt # Subagent: 위치 검색 전문가
└── subagent_character_expert.txt # Subagent: 캐릭터 전문가
```

#### 10.7.3 Main Agent 시스템 프롬프트 (system_prompt.txt)

> scan의 `answer_generation_prompt.txt`에서 이코 페르소나 발췌.
> JSON 출력 강제 없이 자연어 답변 + SSE 스트리밍.

```text
# Identity
당신은 대한민국 생활폐기물 분리배출 도우미 **이코**입니다.
친절하고 전문적으로 분리배출 방법을 안내합니다.

# Capabilities
1. 분리배출 방법 안내 (이미지/텍스트)
2. 주변 재활용센터/제로웨이스트샵 검색
3. 캐릭터 정보 제공 (수집한 캐릭터, 미리보기)
4. 환경 관련 일반 질문 답변

# 핵심 개념
**제로웨이스트**: 폐기물 발생을 최소화하는 생활 방식.
리필 용기 사용, 무포장 제품 구매 등을 통해 쓰레기 배출을 줄입니다.

**리필스테이션**: 세제, 샴푸 등을 개인 용기에 리필할 수 있는 매장.

**업사이클링**: 폐기물을 새로운 가치 있는 제품으로 재탄생시키는 것.

# Guidelines
- 친근하고 간결한 어투 사용
- 이모지 적절히 활용
- 분리배출 질문이 아니면 자연스럽게 유도
- 불확실한 정보는 "확인이 필요해요"로 안내
```

#### 10.7.4 의도 분류 프롬프트 (intent_classifier.txt)

```text
# Identity
당신은 사용자 메시지의 의도를 분류합니다.

# Instructions
다음 의도 중 하나를 선택합니다:
- waste: 분리배출 방법 질문
- character: 캐릭터 관련 질문 (보유, 정보)
- character_preview: 분리배출 시 얻을 캐릭터 미리보기
- location: 주변 재활용센터/샵 검색
- general: 일반 대화, 환경 관련 질문

의도 문자열만 출력합니다.

# Examples
- "페트병 어떻게 버려?" → waste
- "근처 재활용센터 알려줘" → location
- "이거 버리면 무슨 캐릭터?" → character_preview
- "내가 가진 캐릭터 보여줘" → character
- "제로웨이스트가 뭐야?" → general
```

#### 10.7.5 Subagent: waste_expert (subagent_waste_expert.txt)

```text
# Identity
당신은 분리배출 규정 전문가입니다.
RAG 결과를 기반으로 정확한 배출 방법을 안내합니다.

# Instructions
주어진 RAG 결과와 분류 결과를 활용하여 핵심 배출 방법을 요약합니다.

## 분류 결과
{classification}

## RAG 검색 결과
{lite_rag}

# Guidelines
- RAG 결과와 다른 내용 생성 금지
- 불확실한 경우 "확인이 필요합니다" 명시
- 핵심만 간결하게
```

#### 10.7.6 Subagent: location_expert (subagent_location_expert.txt)

```text
# Identity
당신은 주변 재활용센터 및 제로웨이스트샵 검색 전문가입니다.

# Instructions
위치 검색 결과를 사용자 친화적으로 요약합니다.

## 검색 결과
{location_results}

## 사용자 위치
{user_location}

# Guidelines
- 가까운 순으로 상위 3개 안내
- 검색 결과 없으면 "주변에 검색 결과가 없어요" 안내
- 위치 정보 없으면 위치 공유 요청
```

#### 10.7.7 Subagent: character_expert (subagent_character_expert.txt)

```text
# Identity
당신은 Eco² 캐릭터 정보 전문가입니다.

# Instructions
캐릭터 관련 질문에 답변합니다.

## 캐릭터 카탈로그
{character_catalog}

## 사용자 보유 캐릭터
{user_characters}

## 품목 중분류 (미리보기 시)
{middle_category}

# Guidelines
- 캐릭터 이름, 대사 포함
- 미리보기: "~를 분리배출하면 **{name}**를 얻을 수 있어요!"
- 친근한 어투

# 캐릭터 목록 (참고)
| Key | Name | WasteName |
|-----|------|-----------|
| eco | 이코 | 메인 캐릭터 |
| paper | 페이피 | 종이 |
| paperProduct | 팩토리 | 종이팩 |
| pet | 페티 | 무색페트병 |
| vinyl | 비니 | 비닐류 |
| glass | 글래시 | 유리병 |
| clothes | 코튼 | 의류·원단 |
| plastic | 플리 | 플라스틱류 |
| metal | 메탈리 | 금속류 |
| battery | 배리 | 전지 |
| lighting | 라이티 | 조명제품 |
| monitor | 일렉 | 전기전자 |
| styrofoam | 폼이 | 발포합성수지 |
```

#### 10.7.8 SSE Streaming API (Provider별)

> **Note**: 모든 Provider에서 `stream=True` 또는 `.stream()` 메서드로 SSE 스트리밍 지원.
> 자연어 답변을 토큰 단위로 스트리밍.

**OpenAI (GPT):**

```python
from openai import AsyncOpenAI

client = AsyncOpenAI()

async def stream_gpt(prompt: str, system: str):
    """GPT SSE 스트리밍."""
    stream = await client.chat.completions.create(
        model="gpt-5.2",
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ],
        stream=True,
    )
    async for chunk in stream:
        if chunk.choices[0].delta.content:
            yield chunk.choices[0].delta.content
```

**Anthropic (Claude):**

```python
from anthropic import AsyncAnthropic

client = AsyncAnthropic()

async def stream_claude(prompt: str, system: str):
    """Claude SSE 스트리밍."""
    async with client.messages.stream(
        model="claude-sonnet-4-5-20250929",
        system=system,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=1024,
    ) as stream:
        async for text in stream.text_stream:
            yield text
```

**Google (Gemini):**

```python
import google.generativeai as genai

async def stream_gemini(prompt: str, system: str):
    """Gemini SSE 스트리밍."""
    model = genai.GenerativeModel(
        "gemini-3.0-flash",
        system_instruction=system,
    )
    response = await model.generate_content_async(
        prompt,
        stream=True,
    )
    async for chunk in response:
        if chunk.text:
            yield chunk.text
```

#### 10.7.9 Port/Adapter 통합

```python
class LLMStreamPort(Protocol):
    """LLM 스트리밍 포트."""
    
    async def stream(
        self,
        prompt: str,
        system: str,
    ) -> AsyncIterator[str]:
        """토큰 단위 스트리밍."""
        ...


class GPTStreamAdapter(LLMStreamPort):
    async def stream(self, prompt: str, system: str):
        async for token in stream_gpt(prompt, system):
            yield token


class ClaudeStreamAdapter(LLMStreamPort):
    async def stream(self, prompt: str, system: str):
        async for token in stream_claude(prompt, system):
            yield token


class GeminiStreamAdapter(LLMStreamPort):
    async def stream(self, prompt: str, system: str):
        async for token in stream_gemini(prompt, system):
            yield token
```

#### 10.7.10 프롬프트 로딩 패턴

```python
from pathlib import Path


class PromptLoader:
    """프롬프트 로더."""
    
    def __init__(self, prompts_dir: Path | None = None):
        self.prompts_dir = prompts_dir or (
            Path(__file__).parent.parent / "assets" / "prompts"
        )
        self._cache: dict[str, str] = {}
    
    def load(self, name: str) -> str:
        """프롬프트 로드 (캐싱)."""
        if name not in self._cache:
            path = self.prompts_dir / f"{name}.txt"
            self._cache[name] = path.read_text(encoding="utf-8")
        return self._cache[name]
    
    @property
    def system_prompt(self) -> str:
        return self.load("system_prompt")
    
    @property
    def intent_classifier(self) -> str:
        return self.load("intent_classifier")
    
    def subagent_prompt(self, expert: str) -> str:
        return self.load(f"subagent_{expert}_expert")
    
    def format_prompt(self, name: str, **kwargs) -> str:
        """프롬프트 로드 + 변수 치환."""
        template = self.load(name)
        return template.format(**kwargs)
```

---

## 11. 결론

### 11.1 선택된 패턴

| 패턴 | 적용 위치 | 목적 |
|------|----------|------|
| **Routing** | 입력 유형/의도 분기 | 유연한 파이프라인 |
| **Prompt Chaining** | 이미지/텍스트 파이프라인 | 순차 처리 + 검증 |
| **Subagent** | 복잡한 멀티 질문 처리 | 컨텍스트 격리 + 병렬 처리 |
| **Tool Calling** | 외부 서비스 연동 | 웹/앱 환경 호환 |
| **LLM 의도 분류** | Intent Classification | 자연어 이해 기반 |

### 11.2 핵심 설계 원칙

1. **웹/앱 환경 호환**: Tool Calling 기반 외부 서비스 연동
2. **예측 가능성**: Workflow 기반으로 디버깅 용이
3. **확장성**: 새로운 의도/노드/Tool 추가 용이
4. **실시간 피드백**: 모든 노드에서 SSE 이벤트 발행
5. **기존 서비스 재사용**: location, character 등 Tool로 연동
6. **비동기 Job 처리**: Taskiq + RabbitMQ로 장시간 파이프라인 처리
7. **컨텍스트 격리**: Subagent로 복잡한 질문의 컨텍스트 오염 방지

### 11.3 다음 단계

1. ~~`apps/chat` 디렉토리 구조 생성~~ ✅ 완료
2. ~~`apps/chat_worker` 디렉토리 구조 생성 (Taskiq)~~ ✅ 완료
3. `ChatState` 및 의도 분류 노드 구현
4. **Subagent 정의** (waste_expert, location_expert, character_expert)
5. Tool 정의 (search_nearby_centers, preview_character 등)
6. 각 노드 구현 (DI 패턴)
7. **복잡도 라우팅 함수** (`route_by_complexity`) 구현
8. 그래프 팩토리 구현 (Subagent 포함)
9. Taskiq Task 구현 (`chat.process`)
10. SSE 이벤트 통합 테스트 (Subagent 이벤트 포함)

---

## 참고 문서

| 문서 | 설명 |
|------|------|
| `03-chat-langgraph-architecture.md` | 전체 아키텍처 설계 |
| `05-async-job-queue-decision.md` | Worker 분리 (Taskiq + RabbitMQ) |
| `01-langgraph-reference.md` | LangGraph 기본 레퍼런스 |
| `02-langgraph-streaming-patterns.md` | SSE 스트리밍 패턴 |

---

**작성일**: 2026-01-12
**최종 수정**: 2026-01-13 (Subagent 초기 설계 반영, GPT-5.2/Gemini 3.0 모델 업데이트)

