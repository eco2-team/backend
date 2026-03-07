# LangGraph Deep Dive: 상태관리, SSE, 오케스트레이션, 비동기 태스크

> LangGraph의 핵심 기능을 심층 분석하고, 기존 인프라(Redis Streams, RabbitMQ, SSE Gateway)와의 호환성을 검토합니다.
> 
> **참고**: [LangGraph 공식 문서](https://langchain-ai.github.io/langgraph/), [LangGraph Concepts](https://langchain-ai.github.io/langgraph/concepts/)

---

## 목차

1. [LangGraph 개요](#1-langgraph-개요)
2. [상태 관리 (State Management)](#2-상태-관리-state-management)
3. [그래프 오케스트레이션 (Graph Orchestration)](#3-그래프-오케스트레이션-graph-orchestration)
4. [스트리밍 (Streaming & SSE)](#4-스트리밍-streaming--sse)
5. [비동기 태스크 (Async Tasks)](#5-비동기-태스크-async-tasks)
6. [체크포인트 & 지속성 (Persistence)](#6-체크포인트--지속성-persistence)
7. [Human-in-the-Loop](#7-human-in-the-loop)
8. [기존 인프라와의 호환성 분석](#8-기존-인프라와의-호환성-분석)

---

## 1. LangGraph 개요

### 1.1 LangGraph란?

LangGraph는 LangChain 팀이 개발한 **상태 기반 멀티액터 오케스트레이션 프레임워크**입니다. 복잡한 에이전트 워크플로우를 **방향 그래프(Directed Graph)**로 모델링하여, 각 노드가 독립적인 액터로 동작하고 엣지가 상태 전이를 정의합니다.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                          LangGraph Architecture                              │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│                      ┌─────────────────────────┐                            │
│                      │      StateGraph         │                            │
│                      │    (상태 컨테이너)       │                            │
│                      └──────────┬──────────────┘                            │
│                                 │                                            │
│           ┌─────────────────────┼─────────────────────┐                     │
│           │                     │                     │                      │
│           ▼                     ▼                     ▼                      │
│   ┌───────────────┐    ┌───────────────┐    ┌───────────────┐              │
│   │   Node A      │───▶│   Node B      │───▶│   Node C      │              │
│   │  (Actor)      │    │  (Actor)      │    │  (Actor)      │              │
│   └───────────────┘    └───────────────┘    └───────────────┘              │
│           │                     │                     │                      │
│           └─────────────────────┴─────────────────────┘                     │
│                                 │                                            │
│                                 ▼                                            │
│                      ┌─────────────────────────┐                            │
│                      │      Checkpointer       │                            │
│                      │    (상태 지속성)         │                            │
│                      └─────────────────────────┘                            │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 1.2 핵심 개념

| 개념 | 설명 |
|------|------|
| **StateGraph** | 상태를 관리하는 그래프 컨테이너 |
| **Node** | 그래프의 노드, 상태를 입력받아 업데이트를 반환하는 함수 |
| **Edge** | 노드 간의 연결, 조건부 라우팅 가능 |
| **State** | 그래프 전체에서 공유되는 상태 (TypedDict 또는 Pydantic) |
| **Checkpointer** | 상태 스냅샷 저장/복원 (Redis, PostgreSQL 등) |
| **Thread** | 대화 세션, 체크포인트의 키 |

### 1.3 설치

```bash
pip install langgraph langgraph-checkpoint langgraph-checkpoint-postgres
pip install langchain-openai langchain-anthropic
```

---

## 2. 상태 관리 (State Management)

### 2.1 State 정의

LangGraph의 상태는 **TypedDict** 또는 **Pydantic BaseModel**로 정의합니다.

```python
from typing import Annotated, TypedDict, Sequence
from langgraph.graph.message import add_messages
from langchain_core.messages import BaseMessage

# 방법 1: TypedDict (권장)
class AgentState(TypedDict):
    """에이전트 상태 스키마."""
    messages: Annotated[Sequence[BaseMessage], add_messages]  # 메시지 리스트
    current_step: str                                          # 현재 단계
    context: dict                                              # 추가 컨텍스트
    iteration_count: int                                       # 반복 횟수

# 방법 2: Pydantic (더 강력한 검증)
from pydantic import BaseModel, Field

class ScanState(BaseModel):
    """스캔 파이프라인 상태."""
    task_id: str
    user_id: str
    image_url: str
    user_input: str | None = None
    
    # 파이프라인 결과
    classification_result: dict | None = None
    disposal_rules: dict | None = None
    final_answer: dict | None = None
    reward: dict | None = None
    
    # 메타데이터
    current_stage: str = "queued"
    progress: int = 0
    error: str | None = None
    
    class Config:
        arbitrary_types_allowed = True
```

### 2.2 Reducer 함수

**Reducer**는 상태 업데이트 방식을 정의합니다. 기본적으로 새 값이 이전 값을 덮어쓰지만, `Annotated`로 커스텀 가능합니다.

```python
from typing import Annotated
from operator import add

class CounterState(TypedDict):
    # 기본: 덮어쓰기
    current_value: int
    
    # 커스텀: 리스트에 추가
    history: Annotated[list[int], add]  # [1] + [2] = [1, 2]
    
    # 커스텀: 메시지 누적 (LangGraph 내장)
    messages: Annotated[list[BaseMessage], add_messages]

# 커스텀 Reducer 정의
def merge_dicts(existing: dict | None, new: dict) -> dict:
    """딕셔너리 병합 Reducer."""
    if existing is None:
        return new
    return {**existing, **new}

class MergeState(TypedDict):
    metadata: Annotated[dict, merge_dicts]
```

### 2.3 State 업데이트 패턴

```python
from langgraph.graph import StateGraph, START, END

def vision_node(state: ScanState) -> dict:
    """Vision 분석 노드 - 상태의 일부만 업데이트."""
    # 분석 로직...
    classification = analyze_image(state.image_url)
    
    # 업데이트할 필드만 반환 (나머지는 자동 유지)
    return {
        "classification_result": classification,
        "current_stage": "vision_completed",
        "progress": 25,
    }

def rule_node(state: ScanState) -> dict:
    """Rule 검색 노드."""
    rules = get_disposal_rules(state.classification_result)
    
    return {
        "disposal_rules": rules,
        "current_stage": "rule_completed",
        "progress": 50,
    }

# 그래프 구성
builder = StateGraph(ScanState)
builder.add_node("vision", vision_node)
builder.add_node("rule", rule_node)

builder.add_edge(START, "vision")
builder.add_edge("vision", "rule")
builder.add_edge("rule", END)

graph = builder.compile()
```

### 2.4 상태 스키마 버전 관리

```python
from pydantic import BaseModel, field_validator

class ScanStateV2(BaseModel):
    """스캔 상태 v2 - 스키마 마이그레이션 지원."""
    schema_version: str = "2.0"
    
    task_id: str
    user_id: str
    image_url: str
    
    # v2에서 추가된 필드
    model_used: str = "gpt-4o"  # LLM 모델 정보
    latency_ms: dict[str, float] = {}  # 각 단계별 지연 시간
    
    @field_validator("schema_version")
    @classmethod
    def validate_version(cls, v):
        if v not in ["1.0", "2.0"]:
            raise ValueError(f"Unsupported schema version: {v}")
        return v
```

---

## 3. 그래프 오케스트레이션 (Graph Orchestration)

### 3.1 기본 그래프 구조

```python
from langgraph.graph import StateGraph, START, END

# StateGraph 생성
builder = StateGraph(AgentState)

# 노드 추가
builder.add_node("agent", agent_node)
builder.add_node("tools", tool_executor_node)

# 엣지 추가 (순차)
builder.add_edge(START, "agent")
builder.add_edge("tools", "agent")

# 조건부 엣지 (분기)
def should_continue(state: AgentState) -> str:
    """다음 노드 결정."""
    last_message = state["messages"][-1]
    if last_message.tool_calls:
        return "tools"
    return END

builder.add_conditional_edges(
    "agent",
    should_continue,
    {"tools": "tools", END: END}
)

# 그래프 컴파일
graph = builder.compile()
```

### 3.2 서브그래프 (Subgraph)

복잡한 워크플로우를 서브그래프로 모듈화합니다.

```python
# 서브그래프 정의
def create_vision_subgraph() -> CompiledGraph:
    """Vision 분석 서브그래프."""
    builder = StateGraph(VisionState)
    
    builder.add_node("preprocess", preprocess_image)
    builder.add_node("analyze", analyze_with_llm)
    builder.add_node("postprocess", postprocess_result)
    
    builder.add_edge(START, "preprocess")
    builder.add_edge("preprocess", "analyze")
    builder.add_edge("analyze", "postprocess")
    builder.add_edge("postprocess", END)
    
    return builder.compile()

# 메인 그래프에서 서브그래프 사용
vision_subgraph = create_vision_subgraph()

main_builder = StateGraph(ScanState)
main_builder.add_node("vision", vision_subgraph)  # 서브그래프를 노드로 추가
main_builder.add_node("rule", rule_node)
main_builder.add_node("answer", answer_node)
```

### 3.3 병렬 실행 (Parallel Execution)

```python
from langgraph.graph import StateGraph, START, END
from typing import Annotated
from operator import add

class ParallelState(TypedDict):
    input: str
    # 병렬 결과를 리스트로 수집
    results: Annotated[list[dict], add]

def task_a(state: ParallelState) -> dict:
    return {"results": [{"source": "task_a", "data": "..."}]}

def task_b(state: ParallelState) -> dict:
    return {"results": [{"source": "task_b", "data": "..."}]}

def task_c(state: ParallelState) -> dict:
    return {"results": [{"source": "task_c", "data": "..."}]}

def aggregate(state: ParallelState) -> dict:
    """병렬 결과 집계."""
    all_results = state["results"]
    return {"final_result": merge_results(all_results)}

builder = StateGraph(ParallelState)
builder.add_node("task_a", task_a)
builder.add_node("task_b", task_b)
builder.add_node("task_c", task_c)
builder.add_node("aggregate", aggregate)

# 병렬 분기
builder.add_edge(START, "task_a")
builder.add_edge(START, "task_b")
builder.add_edge(START, "task_c")

# 병렬 결과 수집
builder.add_edge("task_a", "aggregate")
builder.add_edge("task_b", "aggregate")
builder.add_edge("task_c", "aggregate")
builder.add_edge("aggregate", END)

graph = builder.compile()
```

### 3.4 조건부 라우팅 (Conditional Routing)

```python
from typing import Literal

def route_by_complexity(state: ScanState) -> Literal["simple", "complex", "error"]:
    """복잡도에 따른 라우팅."""
    if state.get("error"):
        return "error"
    
    classification = state.get("classification_result", {})
    if classification.get("complexity") == "high":
        return "complex"
    return "simple"

builder.add_conditional_edges(
    "classify",
    route_by_complexity,
    {
        "simple": "simple_handler",
        "complex": "complex_handler",
        "error": "error_handler",
    }
)
```

### 3.5 동적 노드 추가

```python
from langgraph.graph import StateGraph

def create_dynamic_graph(steps: list[str]) -> CompiledGraph:
    """동적으로 노드를 추가하는 그래프."""
    builder = StateGraph(PipelineState)
    
    # 동적으로 노드 추가
    for i, step in enumerate(steps):
        builder.add_node(step, create_step_handler(step))
        
        if i == 0:
            builder.add_edge(START, step)
        else:
            builder.add_edge(steps[i-1], step)
    
    builder.add_edge(steps[-1], END)
    
    return builder.compile()

# 사용
graph = create_dynamic_graph(["vision", "rule", "answer", "reward"])
```

---

## 4. 스트리밍 (Streaming & SSE)

### 4.1 스트리밍 모드 개요

LangGraph는 4가지 스트리밍 모드를 지원합니다:

| 모드 | 설명 | 사용 사례 |
|------|------|----------|
| **`values`** | 각 노드 완료 후 전체 상태 스트리밍 | 상태 변화 추적 |
| **`updates`** | 각 노드의 업데이트만 스트리밍 | 증분 업데이트 |
| **`messages`** | LLM 메시지만 스트리밍 | 채팅 UI |
| **`events`** | 모든 내부 이벤트 스트리밍 | 상세 디버깅 |

### 4.2 stream_mode="values"

```python
# 각 노드 완료 후 전체 상태 반환
async for state in graph.astream(
    {"messages": [HumanMessage(content="Hello")]},
    stream_mode="values"
):
    print(f"Current state: {state}")
    # 출력 예:
    # {"messages": [...], "current_step": "agent"}
    # {"messages": [...], "current_step": "tools"}
    # {"messages": [...], "current_step": "agent"}
```

### 4.3 stream_mode="updates"

```python
# 각 노드에서 변경된 부분만 반환
async for update in graph.astream(
    {"messages": [HumanMessage(content="Hello")]},
    stream_mode="updates"
):
    node_name = list(update.keys())[0]
    node_output = update[node_name]
    print(f"Node '{node_name}' output: {node_output}")
    # 출력 예:
    # Node 'agent' output: {"messages": [...]}
    # Node 'tools' output: {"messages": [...]}
```

### 4.4 stream_mode="messages"

```python
# LLM 메시지 토큰 단위 스트리밍 (채팅 UI용)
async for msg, metadata in graph.astream(
    {"messages": [HumanMessage(content="Hello")]},
    stream_mode="messages"
):
    if msg.content:
        print(msg.content, end="", flush=True)
    # 출력 예: "Hello! How can I help you today?"
```

### 4.5 astream_events (가장 상세)

`astream_events`는 **모든 내부 이벤트**를 스트리밍합니다. SSE 구현에 가장 적합합니다.

```python
async for event in graph.astream_events(
    {"messages": [HumanMessage(content="Analyze this image")]},
    version="v2"
):
    kind = event["event"]
    
    if kind == "on_chain_start":
        # 체인 시작
        print(f"Starting: {event['name']}")
        
    elif kind == "on_chain_end":
        # 체인 완료
        print(f"Finished: {event['name']}, output: {event['data']['output']}")
        
    elif kind == "on_chat_model_start":
        # LLM 호출 시작
        print(f"LLM call started: {event['name']}")
        
    elif kind == "on_chat_model_stream":
        # LLM 토큰 스트리밍
        content = event["data"]["chunk"].content
        if content:
            print(content, end="", flush=True)
            
    elif kind == "on_chat_model_end":
        # LLM 호출 완료
        print(f"\nLLM call finished")
        
    elif kind == "on_tool_start":
        # 도구 실행 시작
        print(f"Tool started: {event['name']}")
        
    elif kind == "on_tool_end":
        # 도구 실행 완료
        print(f"Tool finished: {event['data']['output']}")
```

### 4.6 이벤트 종류 (v2)

```python
# astream_events v2에서 발생하는 모든 이벤트 종류
EVENT_TYPES = {
    # Chain Events
    "on_chain_start": "체인 시작",
    "on_chain_end": "체인 완료",
    "on_chain_stream": "체인 스트리밍",
    
    # Chat Model Events
    "on_chat_model_start": "LLM 호출 시작",
    "on_chat_model_stream": "LLM 토큰 스트리밍",
    "on_chat_model_end": "LLM 호출 완료",
    
    # Tool Events
    "on_tool_start": "도구 실행 시작",
    "on_tool_end": "도구 실행 완료",
    
    # Retriever Events
    "on_retriever_start": "검색 시작",
    "on_retriever_end": "검색 완료",
    
    # Custom Events
    "on_custom_event": "사용자 정의 이벤트",
}
```

### 4.7 FastAPI + SSE 통합

```python
from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from langchain_core.messages import HumanMessage
import json

app = FastAPI()

async def sse_generator(graph, input_data: dict):
    """LangGraph 이벤트를 SSE 형식으로 변환."""
    async for event in graph.astream_events(input_data, version="v2"):
        kind = event["event"]
        
        # SSE 형식으로 변환
        if kind == "on_chain_end":
            node_name = event.get("name", "unknown")
            output = event["data"].get("output", {})
            
            sse_data = {
                "step": node_name,
                "status": "completed",
                "progress": calculate_progress(node_name),
                "data": output,
            }
            yield f"event: stage\ndata: {json.dumps(sse_data)}\n\n"
            
        elif kind == "on_chat_model_stream":
            content = event["data"]["chunk"].content
            if content:
                yield f"event: token\ndata: {json.dumps({'content': content})}\n\n"
                
        elif kind == "on_chain_end" and event.get("name") == "LangGraph":
            # 최종 완료
            final_output = event["data"]["output"]
            yield f"event: done\ndata: {json.dumps(final_output)}\n\n"

@app.post("/api/v1/scan/stream")
async def scan_stream(request: ScanRequest):
    """스캔 요청 + SSE 스트리밍."""
    input_data = {
        "task_id": str(uuid4()),
        "user_id": request.user_id,
        "image_url": request.image_url,
        "user_input": request.user_input,
    }
    
    return StreamingResponse(
        sse_generator(graph, input_data),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        }
    )
```

### 4.8 커스텀 이벤트 발행

```python
from langchain_core.callbacks import adispatch_custom_event

async def vision_node(state: ScanState) -> dict:
    """Vision 분석 노드 - 커스텀 이벤트 발행."""
    
    # 시작 이벤트
    await adispatch_custom_event(
        "stage_started",
        {"step": "vision", "progress": 0}
    )
    
    # 분석 실행
    result = await analyze_image(state.image_url)
    
    # 완료 이벤트
    await adispatch_custom_event(
        "stage_completed",
        {"step": "vision", "progress": 25, "result": result}
    )
    
    return {"classification_result": result, "progress": 25}

# 커스텀 이벤트 수신
async for event in graph.astream_events(input_data, version="v2"):
    if event["event"] == "on_custom_event":
        name = event["name"]
        data = event["data"]
        print(f"Custom event: {name}, data: {data}")
```

---

## 5. 비동기 태스크 (Async Tasks)

### 5.1 비동기 노드 정의

```python
from langgraph.graph import StateGraph
import asyncio

async def async_vision_node(state: ScanState) -> dict:
    """비동기 Vision 분석 노드."""
    # 비동기 HTTP 호출
    async with httpx.AsyncClient() as client:
        response = await client.post(
            "https://api.openai.com/v1/chat/completions",
            json={...}
        )
        result = response.json()
    
    return {"classification_result": result}

async def async_rule_node(state: ScanState) -> dict:
    """비동기 Rule 검색 노드."""
    # 비동기 DB 쿼리
    async with async_session() as session:
        rules = await session.execute(select(DisposalRule).where(...))
    
    return {"disposal_rules": rules}

# 비동기 노드 추가
builder = StateGraph(ScanState)
builder.add_node("vision", async_vision_node)
builder.add_node("rule", async_rule_node)
```

### 5.2 비동기 그래프 실행

```python
# 방법 1: await
result = await graph.ainvoke(input_data)

# 방법 2: asyncio.run
result = asyncio.run(graph.ainvoke(input_data))

# 방법 3: 스트리밍
async for event in graph.astream(input_data, stream_mode="updates"):
    print(event)

# 방법 4: 이벤트 스트리밍
async for event in graph.astream_events(input_data, version="v2"):
    process_event(event)
```

### 5.3 병렬 비동기 실행

```python
import asyncio
from langgraph.graph import StateGraph

async def parallel_node(state: ParallelState) -> dict:
    """여러 비동기 작업 병렬 실행."""
    
    # 병렬 실행
    results = await asyncio.gather(
        fetch_data_a(state.input),
        fetch_data_b(state.input),
        fetch_data_c(state.input),
        return_exceptions=True,  # 예외도 결과로 반환
    )
    
    # 결과 처리
    successful_results = [r for r in results if not isinstance(r, Exception)]
    
    return {"results": successful_results}
```

### 5.4 타임아웃 및 재시도

```python
import asyncio
from tenacity import retry, stop_after_attempt, wait_exponential

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=10),
)
async def async_llm_call(messages: list) -> dict:
    """재시도 로직이 포함된 LLM 호출."""
    async with asyncio.timeout(30):  # 30초 타임아웃
        response = await llm.ainvoke(messages)
        return response

async def robust_vision_node(state: ScanState) -> dict:
    """견고한 Vision 노드."""
    try:
        result = await async_llm_call(build_messages(state))
        return {"classification_result": result}
    except asyncio.TimeoutError:
        return {"error": "Vision analysis timeout"}
    except Exception as e:
        return {"error": str(e)}
```

### 5.5 백그라운드 태스크 (Fire & Forget)

```python
import asyncio
from typing import TypedDict

class BackgroundState(TypedDict):
    task_id: str
    background_task_ids: list[str]

async def spawn_background_task(state: BackgroundState) -> dict:
    """백그라운드 태스크 생성."""
    
    async def background_work(task_id: str):
        """백그라운드에서 실행될 작업."""
        await asyncio.sleep(5)
        print(f"Background task {task_id} completed")
    
    # Fire & Forget
    task = asyncio.create_task(background_work(state["task_id"]))
    
    return {
        "background_task_ids": [str(id(task))]
    }
```

---

## 6. 체크포인트 & 지속성 (Persistence)

### 6.1 Checkpointer 개요

LangGraph의 **Checkpointer**는 그래프 상태를 저장하고 복원하는 메커니즘입니다.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                          Checkpointer Architecture                           │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│   Graph Execution                                                            │
│        │                                                                     │
│        ▼                                                                     │
│   ┌─────────────┐    ┌─────────────┐    ┌─────────────┐                    │
│   │   Node A    │───▶│   Node B    │───▶│   Node C    │                    │
│   └──────┬──────┘    └──────┬──────┘    └──────┬──────┘                    │
│          │                  │                  │                            │
│          ▼                  ▼                  ▼                            │
│   ┌────────────────────────────────────────────────────────────────────┐   │
│   │                      Checkpointer                                   │   │
│   │  ┌────────────┐  ┌────────────┐  ┌────────────┐                   │   │
│   │  │ Checkpoint │  │ Checkpoint │  │ Checkpoint │                   │   │
│   │  │   v1       │  │   v2       │  │   v3       │                   │   │
│   │  │ (Node A)   │  │ (Node B)   │  │ (Node C)   │                   │   │
│   │  └────────────┘  └────────────┘  └────────────┘                   │   │
│   └────────────────────────────────────────────────────────────────────┘   │
│          │                                                                  │
│          ▼                                                                  │
│   ┌────────────────────────────────────────────────────────────────────┐   │
│   │  Storage Backend                                                    │   │
│   │  • MemorySaver (개발용)                                             │   │
│   │  • PostgresCheckpointer (프로덕션)                                  │   │
│   │  • RedisSaver (빠른 액세스)                                         │   │
│   └────────────────────────────────────────────────────────────────────┘   │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 6.2 MemorySaver (개발용)

```python
from langgraph.checkpoint.memory import MemorySaver

# 메모리 기반 체크포인터 (테스트용)
checkpointer = MemorySaver()

# 그래프에 체크포인터 연결
graph = builder.compile(checkpointer=checkpointer)

# 실행 (thread_id로 세션 구분)
config = {"configurable": {"thread_id": "user-123"}}
result = await graph.ainvoke(input_data, config=config)

# 같은 thread_id로 재개
result = await graph.ainvoke(new_input, config=config)  # 이전 상태 유지
```

### 6.3 PostgresCheckpointer (프로덕션)

```python
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
import asyncpg

# PostgreSQL 연결
async def get_checkpointer():
    conn = await asyncpg.connect(
        "postgresql://user:pass@localhost:5432/langgraph"
    )
    return AsyncPostgresSaver(conn)

# 사용
checkpointer = await get_checkpointer()
graph = builder.compile(checkpointer=checkpointer)

# 체크포인트 테이블 자동 생성
await checkpointer.setup()
```

### 6.4 RedisSaver

```python
from langgraph.checkpoint.redis import RedisSaver
import redis

# Redis 연결
redis_client = redis.Redis(host="localhost", port=6379, db=0)
checkpointer = RedisSaver(redis_client)

graph = builder.compile(checkpointer=checkpointer)
```

### 6.5 체크포인트 상태 조회

```python
# 현재 상태 조회
current_state = await graph.aget_state(config)
print(current_state.values)  # 현재 상태 값
print(current_state.next)    # 다음 실행될 노드

# 상태 히스토리 조회
async for state in graph.aget_state_history(config):
    print(f"Checkpoint: {state.config}")
    print(f"Values: {state.values}")
    print(f"Next: {state.next}")
```

### 6.6 특정 체크포인트로 복원

```python
# 체크포인트 ID로 복원
config_with_checkpoint = {
    "configurable": {
        "thread_id": "user-123",
        "checkpoint_id": "checkpoint-abc-123",  # 특정 체크포인트
    }
}

# 해당 시점부터 재실행
result = await graph.ainvoke(None, config=config_with_checkpoint)
```

### 6.7 TTL 설정 (Redis)

```python
from langgraph.checkpoint.redis import RedisSaver

# TTL이 있는 체크포인터
checkpointer = RedisSaver(
    redis_client,
    ttl=3600,  # 1시간 후 자동 삭제
)
```

---

## 7. Human-in-the-Loop

### 7.1 Interrupt 메커니즘

```python
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver

class ApprovalState(TypedDict):
    request: str
    analysis: dict | None
    approved: bool | None
    final_result: str | None

async def analyze_node(state: ApprovalState) -> dict:
    """분석 수행."""
    analysis = await perform_analysis(state["request"])
    return {"analysis": analysis}

async def execute_node(state: ApprovalState) -> dict:
    """승인 후 실행."""
    if not state["approved"]:
        return {"final_result": "Rejected by user"}
    
    result = await execute_action(state["analysis"])
    return {"final_result": result}

# 그래프 구성
builder = StateGraph(ApprovalState)
builder.add_node("analyze", analyze_node)
builder.add_node("execute", execute_node)

builder.add_edge(START, "analyze")
builder.add_edge("analyze", "execute")  # 여기서 interrupt
builder.add_edge("execute", END)

# interrupt_before로 특정 노드 전에 멈춤
graph = builder.compile(
    checkpointer=MemorySaver(),
    interrupt_before=["execute"],  # execute 전에 중단
)
```

### 7.2 중단 및 재개

```python
# 1단계: 분석까지 실행 후 중단
config = {"configurable": {"thread_id": "approval-123"}}
result = await graph.ainvoke(
    {"request": "Delete all users"},
    config=config
)

# 상태 확인
state = await graph.aget_state(config)
print(f"Analysis: {state.values['analysis']}")
print(f"Next node: {state.next}")  # ['execute']

# 2단계: 사용자 승인 후 재개
await graph.aupdate_state(
    config,
    {"approved": True},  # 상태 업데이트
)

# 3단계: 중단점부터 재개
final_result = await graph.ainvoke(None, config=config)
print(f"Final: {final_result}")
```

### 7.3 여러 중단점

```python
builder = builder.compile(
    checkpointer=MemorySaver(),
    interrupt_before=["execute", "notify"],  # 여러 노드 전에 중단
    interrupt_after=["analyze"],             # 노드 후에 중단
)
```

---

## 8. 기존 인프라와의 호환성 분석

### 8.1 현재 인프라 구조

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                       현재 인프라 (Celery + Redis Streams)                   │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│   Client                                                                     │
│     │                                                                        │
│     ▼                                                                        │
│   scan-api ─────────▶ RabbitMQ (Celery Broker)                             │
│     │                      │                                                 │
│     │                      ▼                                                 │
│     │               scan-worker (Celery)                                    │
│     │                 ┌────────────────────────────────────────┐            │
│     │                 │ vision → rule → answer → reward        │            │
│     │                 └──────────────────────┬─────────────────┘            │
│     │                                        │                              │
│     │                                        ▼                              │
│     │                              Redis Streams (XADD)                     │
│     │                                        │                              │
│     │                                        ▼                              │
│     │                              Event Router (Consumer)                  │
│     │                                        │                              │
│     │                          ┌─────────────┴─────────────┐               │
│     │                          ▼                           ▼                │
│     │                   State KV (복구용)          Pub/Sub (실시간)         │
│     │                                                      │                │
│     │                                                      ▼                │
│     └──────────────────────────────────────────▶  SSE Gateway              │
│                                                      │                      │
│                                                      ▼                      │
│                                                   Client (SSE)              │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 8.2 LangGraph 전환 시 인프라 변화

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                      LangGraph 전환 시 인프라 비교                            │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│   구성 요소          현재 (Celery)              LangGraph 전환 시            │
│   ──────────────────────────────────────────────────────────────────────────│
│                                                                              │
│   ┌─────────────┐                                                           │
│   │ RabbitMQ    │    Celery Broker              ❌ 불필요 (단일 프로세스)    │
│   │             │    태스크 큐 라우팅           또는                          │
│   │             │                               🔄 Background Task용 유지    │
│   └─────────────┘                                                           │
│                                                                              │
│   ┌─────────────┐                                                           │
│   │ Redis       │    - Streams (이벤트)        🔄 대체 가능:                 │
│   │ Streams     │    - State KV (복구)         - astream_events로 직접 SSE  │
│   │             │                               - Checkpointer로 상태 저장   │
│   └─────────────┘                                                           │
│                                                                              │
│   ┌─────────────┐                                                           │
│   │ Event       │    Redis Streams 소비        ❌ 불필요                     │
│   │ Router      │    → Pub/Sub 변환            LangGraph가 직접 이벤트 발행  │
│   └─────────────┘                                                           │
│                                                                              │
│   ┌─────────────┐                                                           │
│   │ SSE         │    Pub/Sub 구독              🔄 유지 가능:                 │
│   │ Gateway     │    → 클라이언트 전달         - astream_events → SSE 변환  │
│   │             │                               - 또는 FastAPI 직접 처리     │
│   └─────────────┘                                                           │
│                                                                              │
│   ┌─────────────┐                                                           │
│   │ Celery      │    분산 태스크 실행          ❌ 불필요 (LangGraph 내장)    │
│   │ Workers     │    Chain 오케스트레이션      StateGraph가 대체            │
│   └─────────────┘                                                           │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 8.3 각 인프라 구성 요소별 분석

#### RabbitMQ (Celery Broker)

| 항목 | 현재 역할 | LangGraph 전환 후 |
|------|----------|------------------|
| **태스크 큐** | Celery 태스크 분배 | ❌ 불필요 - LangGraph 단일 프로세스 |
| **분산 처리** | 여러 Worker에 분배 | ⚠️ 제한적 - LangGraph는 기본적으로 단일 프로세스 |
| **재시도** | Celery 자동 재시도 | 🔄 LangGraph 노드 내 구현 필요 |
| **우선순위 큐** | 태스크 우선순위 | ❌ 불필요 |

**결론**: LangGraph 전환 시 RabbitMQ는 **대부분 불필요**. 단, Fire & Forget 백그라운드 태스크가 필요하면 유지.

#### Redis Streams

| 항목 | 현재 역할 | LangGraph 전환 후 |
|------|----------|------------------|
| **이벤트 발행** | 파이프라인 진행 상황 | 🔄 `astream_events`로 대체 가능 |
| **이벤트 지속성** | Consumer Group 재처리 | 🔄 Checkpointer로 대체 |
| **샤딩** | MD5 기반 샤드 분배 | ❌ 불필요 - 단일 스트림 |

**결론**: `astream_events`가 직접 SSE로 변환 가능하므로 **대체 가능**. 단, 대규모 분산 환경에서는 Redis Streams 유지 권장.

#### Event Router

| 항목 | 현재 역할 | LangGraph 전환 후 |
|------|----------|------------------|
| **Streams 소비** | XREADGROUP | ❌ 불필요 |
| **Pub/Sub 변환** | Streams → Pub/Sub | ❌ 불필요 |
| **State KV 갱신** | 복구용 상태 저장 | 🔄 Checkpointer로 대체 |

**결론**: **완전 대체 가능**. LangGraph가 이벤트를 직접 발행.

#### SSE Gateway

| 항목 | 현재 역할 | LangGraph 전환 후 |
|------|----------|------------------|
| **Pub/Sub 구독** | Redis Pub/Sub 구독 | 🔄 변경: LangGraph 직접 SSE 또는 유지 |
| **클라이언트 연결** | SSE 연결 관리 | ✅ 유지 가능 |
| **Sticky Session** | Istio 라우팅 | ✅ 유지 가능 |

**결론**: **유지 가능하나 선택적**. FastAPI에서 직접 SSE 처리도 가능.

### 8.4 전환 옵션별 인프라 사용

#### Option 1: 완전 전환 (LangGraph Only)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    Option 1: 완전 전환 (LangGraph Only)                      │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│   Client                                                                     │
│     │                                                                        │
│     ▼                                                                        │
│   scan-api (FastAPI + LangGraph)                                            │
│     │                                                                        │
│     ├── POST /scan → graph.ainvoke() → 결과 반환                            │
│     │                                                                        │
│     └── GET /scan/stream → graph.astream_events() → SSE 직접 반환          │
│                │                                                             │
│                ▼                                                             │
│         PostgreSQL (Checkpointer)                                           │
│                                                                              │
│   사용 인프라:                                                               │
│   ✅ PostgreSQL (Checkpointer)                                              │
│   ❌ RabbitMQ (불필요)                                                       │
│   ❌ Redis Streams (불필요)                                                  │
│   ❌ Event Router (불필요)                                                   │
│   ❌ SSE Gateway (불필요 - FastAPI 직접 처리)                               │
│                                                                              │
│   장점: 인프라 단순화, 의존성 감소                                           │
│   단점: 분산 처리 불가, 대규모 트래픽 처리 제한                              │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

#### Option 2: 하이브리드 (LangGraph + 기존 인프라)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    Option 2: 하이브리드 (권장)                               │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│   Client                                                                     │
│     │                                                                        │
│     ▼                                                                        │
│   scan-api                                                                   │
│     │                                                                        │
│     ├── POST /scan → Celery Task 발행 ────────▶ RabbitMQ                   │
│     │                                                │                       │
│     │                                                ▼                       │
│     │                                          scan-worker                  │
│     │                                       ┌──────────────────┐            │
│     │                                       │ LangGraph 실행    │            │
│     │                                       │ (단일 Worker 내)  │            │
│     │                                       └────────┬─────────┘            │
│     │                                                │                       │
│     │                                                ▼                       │
│     │                                       Custom Callback                 │
│     │                                       → Redis Streams XADD            │
│     │                                                │                       │
│     │                                                ▼                       │
│     │                                          Event Router                 │
│     │                                                │                       │
│     └──────────────────────────────────────▶  SSE Gateway ◀────────────────┘
│                                                      │                       │
│                                                      ▼                       │
│                                                   Client                     │
│                                                                              │
│   사용 인프라:                                                               │
│   ✅ RabbitMQ (Celery Broker - 분산 처리)                                   │
│   ✅ Redis Streams (이벤트 발행 - Custom Callback)                          │
│   ✅ Event Router (기존 유지)                                               │
│   ✅ SSE Gateway (기존 유지)                                                │
│   ✅ PostgreSQL (LangGraph Checkpointer)                                    │
│                                                                              │
│   장점: 분산 처리 유지, 점진적 마이그레이션 가능                             │
│   단점: 인프라 복잡도 유지                                                   │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

#### Option 3: LangGraph + Redis (경량화)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    Option 3: LangGraph + Redis (경량화)                      │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│   Client                                                                     │
│     │                                                                        │
│     ▼                                                                        │
│   scan-api (FastAPI + LangGraph)                                            │
│     │                                                                        │
│     ├── POST /scan → graph.ainvoke() in BackgroundTask                     │
│     │                                                                        │
│     └── GET /scan/stream ─────────────────────────────────┐                │
│                                                            │                │
│     graph.astream_events()                                 │                │
│           │                                                │                │
│           ▼                                                │                │
│     Custom Callback                                        │                │
│     → Redis Pub/Sub PUBLISH ───────────────────────────▶  │                │
│                                                            │                │
│                                                            ▼                │
│                                               SSE Gateway (기존 유지)       │
│                                                            │                │
│                                                            ▼                │
│                                                         Client              │
│                                                                              │
│   사용 인프라:                                                               │
│   ❌ RabbitMQ (불필요)                                                       │
│   ❌ Redis Streams (Pub/Sub로 대체)                                         │
│   ❌ Event Router (불필요)                                                   │
│   ✅ Redis Pub/Sub (경량 이벤트 전달)                                       │
│   ✅ SSE Gateway (기존 유지)                                                │
│   ✅ Redis (LangGraph Checkpointer)                                         │
│                                                                              │
│   장점: 인프라 경량화, RabbitMQ 제거                                         │
│   단점: 분산 Worker 불가 (BackgroundTask 사용)                              │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 8.5 Custom Callback으로 기존 인프라 연동

```python
from langchain_core.callbacks import BaseCallbackHandler
from langgraph.graph import StateGraph
import redis

class RedisStreamsCallback(BaseCallbackHandler):
    """LangGraph 이벤트를 Redis Streams로 발행하는 Callback."""
    
    def __init__(self, redis_client: redis.Redis, stream_key: str):
        self.redis = redis_client
        self.stream_key = stream_key
    
    def on_chain_start(self, serialized, inputs, **kwargs):
        """체인 시작."""
        self.redis.xadd(self.stream_key, {
            "event": "chain_start",
            "data": json.dumps({"inputs": str(inputs)}),
        })
    
    def on_chain_end(self, outputs, **kwargs):
        """체인 완료."""
        self.redis.xadd(self.stream_key, {
            "event": "chain_end",
            "data": json.dumps({"outputs": str(outputs)}),
        })
    
    def on_llm_start(self, serialized, prompts, **kwargs):
        """LLM 호출 시작."""
        self.redis.xadd(self.stream_key, {
            "event": "llm_start",
            "data": json.dumps({"model": serialized.get("name")}),
        })
    
    def on_llm_end(self, response, **kwargs):
        """LLM 호출 완료."""
        self.redis.xadd(self.stream_key, {
            "event": "llm_end",
            "data": json.dumps({"response": str(response)}),
        })

# 사용
callback = RedisStreamsCallback(redis_client, f"scan:events:{task_id}")
result = await graph.ainvoke(
    input_data,
    config={"callbacks": [callback]}
)
```

### 8.6 최종 권장 사항

| 시나리오 | 권장 옵션 | 이유 |
|----------|----------|------|
| **소규모 트래픽** | Option 1 (완전 전환) | 인프라 단순화, 관리 부담 감소 |
| **중규모 트래픽** | Option 3 (경량화) | RabbitMQ 제거, Redis만 유지 |
| **대규모 트래픽** | Option 2 (하이브리드) | 분산 처리 필수, 기존 인프라 활용 |
| **점진적 마이그레이션** | Option 2 → Option 3 | 단계적 인프라 제거 |

---

## 요약

### LangGraph가 대체 가능한 것

| 현재 구성 요소 | LangGraph 대체 기능 | 대체 여부 |
|---------------|-------------------|----------|
| Celery Chain | StateGraph + Edges | ✅ 완전 대체 |
| Redis Streams (이벤트) | astream_events | ✅ 완전 대체 |
| Event Router | Custom Callback | ✅ 완전 대체 |
| State KV (복구) | Checkpointer | ✅ 완전 대체 |

### LangGraph가 대체하기 어려운 것

| 현재 구성 요소 | 제한 사항 | 권장 |
|---------------|----------|------|
| RabbitMQ (분산 처리) | LangGraph는 단일 프로세스 | 대규모 시 유지 |
| SSE Gateway (다중 연결) | 클러스터 환경 필요 | 유지 권장 |
| gevent pool (높은 동시성) | asyncio 기반 | 테스트 필요 |

### 마이그레이션 로드맵 (권장)

```
Phase 1: LangChain LLM만 도입 (현재 인프라 유지)
    │
    ▼
Phase 2: Celery Task 내에서 LangGraph 실행 (하이브리드)
    │
    ▼
Phase 3: RabbitMQ 제거, Redis Pub/Sub로 전환 (경량화)
    │
    ▼
Phase 4: SSE Gateway → FastAPI 직접 처리 (완전 전환) [선택]
```

---

## 참고 자료

- [LangGraph 공식 문서](https://langchain-ai.github.io/langgraph/)
- [LangGraph Concepts](https://langchain-ai.github.io/langgraph/concepts/)
- [LangGraph Tutorials](https://langchain-ai.github.io/langgraph/tutorials/)
- [LangGraph How-to Guides](https://langchain-ai.github.io/langgraph/how-tos/)
- [LangGraph API Reference](https://langchain-ai.github.io/langgraph/reference/)
- [LangGraph Checkpoint](https://langchain-ai.github.io/langgraph/concepts/persistence/)
- [LangGraph Streaming](https://langchain-ai.github.io/langgraph/concepts/streaming/)

