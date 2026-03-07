# LangGraph 레퍼런스 가이드

> LangGraph 핵심 개념, API, 그리고 Chat 서비스 마이그레이션에 적용할 패턴 정리
> 
> **참고 문서**: [LangGraph 공식 문서](https://docs.langchain.com/oss/python/langgraph)

---

## 1. LangGraph 개요

LangGraph는 **복잡한 생성형 AI 워크플로우**를 구축하기 위한 그래프 기반 오케스트레이션 프레임워크입니다.

### 1.1 핵심 특징

| 특징 | 설명 |
|------|------|
| **명시적 상태 모델링** | 노드별 입력/출력 정의로 흐름 추적 및 디버깅 용이 |
| **조건부 분기/루프** | 상태 간 조건 분기와 재귀적 루프 설정 가능 |
| **LLM 통합 추상화** | OpenAI, Anthropic, Gemini 등 다양한 LLM 지원 |
| **내장 Persistence** | 체크포인트 기반 상태 저장/복원 |
| **스트리밍 지원** | 노드별 이벤트 및 토큰 스트리밍 |

### 1.2 Workflow vs Agent

```
Workflow (정적 흐름):
┌─────┐    ┌─────┐    ┌─────┐
│ A   │ →  │ B   │ →  │ C   │
└─────┘    └─────┘    └─────┘
※ 코드 경로가 미리 정해져 있음

Agent (동적 흐름):
┌─────┐    ┌─────┐    ┌─────┐
│ LLM │ ⇄  │Tool │ ⇄  │ LLM │  → (반복)
└─────┘    └─────┘    └─────┘
※ LLM이 다음 액션을 동적으로 결정
```

**Chat 서비스 적용**: 
- **이미지 파이프라인** → Workflow (vision → rag → answer)
- **텍스트 파이프라인** → Workflow + Routing (intent에 따른 분기)

---

## 2. Graph API vs Functional API

LangGraph는 두 가지 API 스타일을 제공합니다.

### 2.1 Graph API (권장 - Chat 서비스 적용)

```python
from langgraph.graph import StateGraph, START, END
from typing import TypedDict


class ChatState(TypedDict):
    """그래프 상태 정의."""
    job_id: str
    message: str
    image_url: str | None
    intent: str | None
    answer: str | None


# 노드 함수 정의
async def vision_node(state: ChatState) -> ChatState:
    """이미지 분류 노드."""
    result = await classify_image(state["image_url"])
    return {**state, "classification": result}


async def intent_node(state: ChatState) -> ChatState:
    """의도 분류 노드."""
    intent = await classify_intent(state["message"])
    return {**state, "intent": intent}


# 라우팅 함수
def route_by_input(state: ChatState) -> str:
    """이미지 유무에 따라 분기."""
    return "vision_node" if state["image_url"] else "intent_node"


# 그래프 구성
graph = StateGraph(ChatState)
graph.add_node("vision_node", vision_node)
graph.add_node("intent_node", intent_node)
graph.add_node("rag_node", rag_node)
graph.add_node("answer_node", answer_node)

graph.set_entry_point("start")
graph.add_conditional_edges("start", route_by_input)
graph.add_edge("vision_node", "rag_node")
graph.add_edge("intent_node", "rag_node")
graph.add_edge("rag_node", "answer_node")
graph.add_edge("answer_node", END)

# 컴파일
app = graph.compile()
```

### 2.2 Functional API (기존 코드 통합 시)

```python
from langgraph.func import entrypoint, task


@task
async def classify_image(image_url: str) -> dict:
    """이미지 분류 태스크."""
    return await vision_model.classify(image_url)


@task
async def search_rules(classification: dict) -> dict:
    """규정 검색 태스크."""
    return retriever.get_disposal_rules(classification)


@entrypoint()
async def chat_pipeline(message: str, image_url: str | None = None):
    """Chat 파이프라인 엔트리포인트."""
    if image_url:
        classification = await classify_image(image_url)
    else:
        classification = await classify_text(message)
    
    rules = await search_rules(classification)
    answer = await generate_answer(classification, rules, message)
    
    return {"answer": answer}
```

### 2.3 API 선택 기준

| 기준 | Graph API | Functional API |
|------|-----------|----------------|
| **시각화** | ✅ 그래프 다이어그램 자동 생성 | ❌ 지원 안 됨 |
| **조건부 분기** | ✅ `add_conditional_edges` | ⚠️ Python if/else |
| **기존 코드 통합** | ⚠️ 노드로 래핑 필요 | ✅ 데코레이터만 추가 |
| **복잡한 워크플로우** | ✅ 명시적 엣지 정의 | ⚠️ 코드 복잡도 증가 |

**결론**: Chat 서비스는 **Graph API** 사용 권장 (intent 분기, 시각화 필요)

---

## 3. 스트리밍 (Streaming)

LangGraph는 세 가지 스트리밍 모드를 제공합니다.

### 3.1 스트리밍 모드

```python
# 1. values: 전체 State 스트리밍 (매 노드 후)
async for state in app.astream(input, stream_mode="values"):
    print(state)

# 2. updates: State 변경분만 스트리밍
async for update in app.astream(input, stream_mode="updates"):
    print(update)  # {"node_name": {"key": "new_value"}}

# 3. custom: 노드 내부에서 직접 이벤트 emit
async for event in app.astream(input, stream_mode="custom"):
    print(event)
```

### 3.2 Custom 이벤트 스트리밍

```python
from langgraph.types import StreamWriter


async def answer_node(
    state: ChatState, 
    writer: StreamWriter
) -> ChatState:
    """답변 생성 노드 - 토큰 스트리밍."""
    
    # 진행 상황 이벤트
    writer({"type": "progress", "stage": "answer", "status": "started"})
    
    full_answer = ""
    async for token in llm.astream(state["prompt"]):
        full_answer += token
        # 토큰 단위 이벤트
        writer({"type": "delta", "content": token})
    
    writer({"type": "progress", "stage": "answer", "status": "completed"})
    
    return {**state, "answer": full_answer}
```

### 3.3 Chat 서비스 SSE 통합

```python
# presentation/http/controllers/chat.py
from sse_starlette.sse import EventSourceResponse


@router.post("/messages")
async def send_message(payload: ChatMessageRequest):
    """채팅 메시지 - SSE 스트리밍 응답."""
    
    async def event_generator():
        async for event in app.astream(
            {"message": payload.message, "image_url": payload.image_url},
            stream_mode="custom",
        ):
            yield {
                "event": event.get("type", "message"),
                "data": json.dumps(event),
            }
    
    return EventSourceResponse(event_generator())
```

---

## 4. Persistence (상태 저장)

LangGraph는 체크포인터를 통해 상태를 저장하고 복원할 수 있습니다.

### 4.1 Memory Checkpointer (개발용)

```python
from langgraph.checkpoint.memory import MemorySaver

checkpointer = MemorySaver()
app = graph.compile(checkpointer=checkpointer)

# 실행 (thread_id로 세션 구분)
config = {"configurable": {"thread_id": "user-123"}}
result = await app.ainvoke(input, config=config)

# 상태 복원
state = await app.aget_state(config)
```

### 4.2 Redis Checkpointer (프로덕션)

```python
from langgraph.checkpoint.redis import RedisSaver

checkpointer = RedisSaver.from_url("redis://localhost:6379")
app = graph.compile(checkpointer=checkpointer)
```

### 4.3 Chat 서비스 적용

```python
# 멀티턴 대화를 위한 대화 히스토리 저장
config = {
    "configurable": {
        "thread_id": f"chat-{user_id}",  # 사용자별 세션
    }
}

# 이전 대화 컨텍스트 포함하여 실행
result = await app.ainvoke(
    {"message": "그럼 플라스틱은요?"},  # 이전 대화 맥락 유지
    config=config,
)
```

---

## 5. 서브그래프 (Subgraphs)

복잡한 워크플로우를 모듈화하여 관리합니다.

### 5.1 서브그래프 정의

```python
# 이미지 파이프라인 서브그래프
image_subgraph = StateGraph(ImageState)
image_subgraph.add_node("vision", vision_node)
image_subgraph.add_node("rag", rag_node)
image_subgraph.add_edge("vision", "rag")
image_pipeline = image_subgraph.compile()


# 텍스트 파이프라인 서브그래프
text_subgraph = StateGraph(TextState)
text_subgraph.add_node("intent", intent_node)
text_subgraph.add_node("rag", rag_node)
text_subgraph.add_conditional_edges("intent", route_by_intent)
text_pipeline = text_subgraph.compile()


# 메인 그래프에서 서브그래프 사용
main_graph = StateGraph(ChatState)
main_graph.add_node("image_pipeline", image_pipeline)
main_graph.add_node("text_pipeline", text_pipeline)
main_graph.add_node("answer", answer_node)
```

### 5.2 Chat 서비스 모듈 구조

```
apps/chat/application/pipeline/
├── graph.py              # 메인 그래프 (entry point)
├── state.py              # ChatState 정의
├── subgraphs/
│   ├── image_pipeline.py # 이미지 파이프라인 서브그래프
│   └── text_pipeline.py  # 텍스트 파이프라인 서브그래프
└── nodes/
    ├── vision_node.py
    ├── intent_node.py
    ├── rag_node.py
    └── answer_node.py
```

---

## 6. 에러 핸들링

### 6.1 노드 레벨 에러 핸들링

```python
async def vision_node(state: ChatState) -> ChatState:
    """이미지 분류 노드 - 에러 핸들링 포함."""
    try:
        result = await vision_model.classify(state["image_url"])
        return {**state, "classification": result}
    except VisionModelError as e:
        # 에러 상태로 전환
        return {**state, "error": str(e), "error_stage": "vision"}


def route_on_error(state: ChatState) -> str:
    """에러 발생 시 에러 핸들링 노드로 라우팅."""
    if state.get("error"):
        return "error_handler"
    return "next_node"
```

### 6.2 재시도 로직

```python
from tenacity import retry, stop_after_attempt, wait_exponential


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=10),
)
async def vision_node_with_retry(state: ChatState) -> ChatState:
    """재시도 로직이 포함된 Vision 노드."""
    result = await vision_model.classify(state["image_url"])
    return {**state, "classification": result}
```

---

## 7. Chat 서비스 아키텍처 적용

### 7.1 기존 Celery Chain vs LangGraph

```
Celery Chain (분산 Worker):
┌─────────┐     ┌─────────────┐     ┌─────────┐     ┌─────────┐
│ API     │ →   │ RabbitMQ    │ →   │ Worker1 │ →   │ Worker2 │
└─────────┘     └─────────────┘     │ (Vision)│     │ (RAG)   │
                                    └─────────┘     └─────────┘
※ 네트워크 + 큐 대기 오버헤드

LangGraph (단일 프로세스):
┌─────────────────────────────────────────────────┐
│              Chat API (BackgroundTasks)          │
│  ┌────────┐    ┌────────┐    ┌────────┐         │
│  │ Vision │ →  │  RAG   │ →  │ Answer │         │
│  │ Node   │    │ Node   │    │ Node   │         │
│  └────────┘    └────────┘    └────────┘         │
│       └──────────── EventPublisher ─────────────┤→ Redis Streams
└─────────────────────────────────────────────────┘
※ 메모리 내 즉시 실행, 노드 전환 지연 없음
```

### 7.2 이벤트 발행 통합

```python
# 노드에서 EventPublisher 사용
async def vision_node(
    state: ChatState,
    event_publisher: EventPublisherPort,  # DI
) -> ChatState:
    """Vision 노드 - 기존 EventPublisher 재사용."""
    
    # 시작 이벤트 (Redis Streams → Event Router → SSE Gateway)
    event_publisher.publish_stage_event(
        task_id=state["job_id"],
        stage="vision",
        status="started",
    )
    
    result = await vision_model.classify(state["image_url"])
    
    # 완료 이벤트
    event_publisher.publish_stage_event(
        task_id=state["job_id"],
        stage="vision",
        status="completed",
        result={"classification": result},
    )
    
    return {**state, "classification": result}
```

### 7.3 전체 흐름

```
1. Client: POST /chat/messages
2. Chat API: job_id 발급, 202 Accepted 응답
3. BackgroundTasks: LangGraph 실행
4. 각 노드: EventPublisher → Redis Streams
5. Event Router: Redis Streams → Pub/Sub (기존)
6. SSE Gateway: Pub/Sub → Client SSE (기존)
7. Client: EventSource로 실시간 진행 상황 수신
```

---

## 8. 권장 프로젝트 구조

```
apps/chat/
├── application/
│   ├── pipeline/
│   │   ├── __init__.py
│   │   ├── graph.py          # create_chat_graph()
│   │   ├── state.py          # ChatState TypedDict
│   │   ├── nodes/
│   │   │   ├── __init__.py
│   │   │   ├── start_node.py
│   │   │   ├── vision_node.py
│   │   │   ├── intent_node.py
│   │   │   ├── rag_node.py
│   │   │   ├── answer_node.py  # StreamWriter 사용
│   │   │   └── end_node.py
│   │   └── routing.py        # 라우팅 함수들
│   └── chat/
│       ├── ports/
│       │   ├── event_publisher.py
│       │   ├── llm_client.py
│       │   └── vision_model.py
│       └── dto/
│           └── chat_dto.py
│
├── infrastructure/
│   ├── llm/
│   │   ├── gpt/
│   │   └── gemini/
│   └── messaging/
│       └── redis_event_publisher.py  # scan_worker 복사
│
├── presentation/
│   └── http/
│       └── controllers/
│           └── chat.py       # POST /messages → SSE
│
└── setup/
    ├── config.py
    └── dependencies.py       # 그래프 DI 설정
```

---

## 9. 참고 자료

- **LangGraph 공식 문서**: https://docs.langchain.com/oss/python/langgraph
- **Workflows and Agents**: https://docs.langchain.com/oss/python/langgraph/workflows-agents
- **Persistence**: https://docs.langchain.com/oss/python/langgraph/persistence
- **Streaming**: https://docs.langchain.com/oss/python/langgraph/streaming
- **Application Structure**: https://docs.langchain.com/oss/python/langgraph/application-structure
- **Graph API**: https://docs.langchain.com/oss/python/langgraph/graph-api
- **Functional API**: https://docs.langchain.com/oss/python/langgraph/functional-api

---

**작성일**: 2026-01-09  
**적용 서비스**: `apps/chat`  
**관련 문서**: `docs/plans/chat-clean-architecture-migration-plan.md`

