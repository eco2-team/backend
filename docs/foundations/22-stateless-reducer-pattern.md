# Stateless Reducer Pattern for AI Agents

> "Make your agent a stateless reducer"
> 
> 에이전트를 **상태를 직접 관리하지 않는 순수 함수**로 설계하여 테스트 용이성, 재현성, 확장성을 확보하는 패턴

---

## 1. 개요

### 1.1 전통적인 Stateful Agent의 문제점

```python
# ❌ Anti-pattern: Stateful Agent
class StatefulAgent:
    def __init__(self):
        self.messages = []           # 내부 상태
        self.current_step = "start"  # 내부 상태
        self.results = {}            # 내부 상태
        self.llm = OpenAI()
    
    def run(self, user_input: str):
        self.messages.append({"role": "user", "content": user_input})
        
        while self.current_step != "done":
            response = self.llm.chat(self.messages)
            self.messages.append(response)
            
            if response.tool_calls:
                for tool_call in response.tool_calls:
                    result = self.execute_tool(tool_call)
                    self.results[tool_call.name] = result  # 상태 변경
                    self.messages.append({"role": "tool", "content": result})
            else:
                self.current_step = "done"
        
        return self.results
```

**문제점:**

| 문제 | 설명 |
|------|------|
| **재현 불가능** | 동일 입력에 다른 결과 (내부 상태 의존) |
| **테스트 어려움** | 상태 초기화, mock 설정 복잡 |
| **병렬 처리 불가** | 공유 상태로 race condition 발생 |
| **디버깅 어려움** | 어느 시점에 상태가 변경되었는지 추적 불가 |
| **복구 불가능** | 중간 상태 저장/복원 어려움 |

### 1.2 Stateless Reducer 패턴

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                     Stateless Reducer Pattern                                │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│   Redux에서 영감을 받은 패턴:                                                │
│                                                                              │
│   (previousState, action) => newState                                       │
│                                                                              │
│   LangGraph 적용:                                                            │
│                                                                              │
│   (currentState) => stateUpdate                                             │
│                                                                              │
│   • 노드는 상태를 직접 수정하지 않음                                         │
│   • 노드는 상태의 "업데이트"만 반환                                          │
│   • StateGraph가 업데이트를 상태에 병합                                      │
│   • 모든 상태 변경은 추적 가능                                               │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. 핵심 원칙

### 2.1 순수 함수 (Pure Function)

```python
# ✅ 순수 함수: 동일 입력 → 동일 출력
def vision_node(state: ScanState) -> dict:
    """Vision 분석 노드 - 순수 함수.
    
    특징:
    - 입력: state (읽기 전용)
    - 출력: 업데이트할 필드만 포함한 dict
    - 부작용 없음 (상태 직접 수정 X)
    - 외부 상태 의존 없음
    """
    # state를 읽기만 함
    image_url = state["image_url"]
    user_input = state["user_input"]
    
    # 분석 실행 (외부 API 호출은 허용)
    result = analyze_image(image_url, user_input)
    
    # 업데이트만 반환 (state 수정 X)
    return {
        "classification_result": result,
        "current_stage": "vision_completed",
        "progress": 25,
    }
```

### 2.2 상태 불변성 (Immutability)

```python
from typing import TypedDict
from dataclasses import dataclass, field
from typing import Annotated

# 방법 1: TypedDict (LangGraph 권장)
class AgentState(TypedDict):
    messages: list
    context: dict
    step: str

# 방법 2: Frozen Dataclass (완전 불변)
@dataclass(frozen=True)
class ImmutableState:
    task_id: str
    messages: tuple  # list 대신 tuple (불변)
    context: frozenset  # set 대신 frozenset (불변)

# 방법 3: Pydantic with frozen=True
from pydantic import BaseModel

class FrozenState(BaseModel):
    task_id: str
    messages: list
    
    class Config:
        frozen = True  # 수정 시도 시 에러 발생
```

### 2.3 Reducer 함수

```python
from typing import Annotated
from operator import add

# Reducer: 상태 업데이트 방식을 정의
def merge_messages(existing: list, new: list) -> list:
    """메시지 병합 Reducer."""
    return existing + new

def increment_counter(existing: int, new: int) -> int:
    """카운터 증가 Reducer."""
    return existing + new

def update_latest(existing: any, new: any) -> any:
    """최신 값으로 대체 Reducer (기본값)."""
    return new

class ReducerState(TypedDict):
    # 기본: 덮어쓰기 (update_latest)
    current_step: str
    
    # 커스텀: 메시지 누적
    messages: Annotated[list, merge_messages]
    
    # 커스텀: 카운터 증가
    iteration_count: Annotated[int, increment_counter]
    
    # 내장: add (리스트 연결)
    results: Annotated[list, add]
```

---

## 3. LangGraph에서의 구현

### 3.1 기본 구조

```python
from langgraph.graph import StateGraph, START, END
from typing import TypedDict, Annotated
from langgraph.graph.message import add_messages
from langchain_core.messages import BaseMessage

# 1. 상태 스키마 정의
class AgentState(TypedDict):
    """에이전트 상태 - Reducer 패턴 적용."""
    messages: Annotated[list[BaseMessage], add_messages]
    current_step: str
    tool_results: Annotated[list[dict], lambda a, b: a + b]

# 2. Stateless Node 정의 (순수 함수)
def agent_node(state: AgentState) -> dict:
    """에이전트 노드 - 상태를 읽고 업데이트만 반환."""
    messages = state["messages"]
    
    # LLM 호출
    response = llm.invoke(messages)
    
    # 업데이트만 반환
    return {
        "messages": [response],  # Reducer가 기존 메시지에 추가
        "current_step": "agent_responded",
    }

def tool_node(state: AgentState) -> dict:
    """도구 실행 노드 - 상태를 읽고 업데이트만 반환."""
    last_message = state["messages"][-1]
    
    results = []
    for tool_call in last_message.tool_calls:
        result = execute_tool(tool_call)
        results.append({"tool": tool_call.name, "result": result})
    
    return {
        "messages": [create_tool_message(results)],
        "tool_results": results,  # Reducer가 기존 결과에 추가
        "current_step": "tool_executed",
    }

# 3. 그래프 구성
builder = StateGraph(AgentState)
builder.add_node("agent", agent_node)
builder.add_node("tools", tool_node)

builder.add_edge(START, "agent")
builder.add_conditional_edges("agent", should_continue)
builder.add_edge("tools", "agent")

graph = builder.compile()
```

### 3.2 Scan Pipeline을 Stateless Reducer로

```python
from typing import TypedDict, Annotated
from langgraph.graph import StateGraph, START, END

# 상태 스키마 (불변 패턴)
class ScanState(TypedDict):
    """Scan Pipeline 상태 - Stateless Reducer 패턴."""
    # 입력 (변경 안됨)
    task_id: str
    user_id: str
    image_url: str
    user_input: str | None
    
    # 파이프라인 결과 (각 노드가 업데이트)
    classification_result: dict | None
    disposal_rules: dict | None
    final_answer: dict | None
    reward: dict | None
    
    # 메타데이터 (Reducer로 누적)
    stage_history: Annotated[list[str], lambda a, b: a + b]
    latencies: Annotated[dict, lambda a, b: {**a, **b}]
    
    # 진행 상태
    progress: int
    error: str | None


# Stateless Nodes (순수 함수)
def vision_node(state: ScanState) -> dict:
    """Vision 분석 - Stateless Reducer."""
    start = time.perf_counter()
    
    result = analyze_image(
        state["image_url"],
        state["user_input"] or "이 폐기물을 어떻게 분리배출해야 하나요?"
    )
    
    elapsed = time.perf_counter() - start
    
    # 상태 업데이트만 반환 (state 수정 X)
    return {
        "classification_result": result,
        "stage_history": ["vision"],
        "latencies": {"vision_ms": elapsed * 1000},
        "progress": 25,
    }


def rule_node(state: ScanState) -> dict:
    """Rule 검색 - Stateless Reducer."""
    start = time.perf_counter()
    
    # 이전 노드 결과 읽기 (수정 X)
    classification = state["classification_result"]
    rules = get_disposal_rules(classification)
    
    elapsed = time.perf_counter() - start
    
    return {
        "disposal_rules": rules,
        "stage_history": ["rule"],
        "latencies": {"rule_ms": elapsed * 1000},
        "progress": 50,
    }


def answer_node(state: ScanState) -> dict:
    """Answer 생성 - Stateless Reducer."""
    start = time.perf_counter()
    
    classification = state["classification_result"]
    rules = state["disposal_rules"]
    
    answer = generate_answer(classification, rules)
    
    elapsed = time.perf_counter() - start
    
    return {
        "final_answer": answer,
        "stage_history": ["answer"],
        "latencies": {"answer_ms": elapsed * 1000},
        "progress": 75,
    }


def reward_node(state: ScanState) -> dict:
    """Reward 처리 - Stateless Reducer."""
    start = time.perf_counter()
    
    classification = state["classification_result"]
    rules = state["disposal_rules"]
    answer = state["final_answer"]
    
    reward = process_reward(
        state["user_id"],
        classification,
        rules,
        answer
    )
    
    elapsed = time.perf_counter() - start
    
    return {
        "reward": reward,
        "stage_history": ["reward"],
        "latencies": {"reward_ms": elapsed * 1000},
        "progress": 100,
    }


# 그래프 구성
builder = StateGraph(ScanState)
builder.add_node("vision", vision_node)
builder.add_node("rule", rule_node)
builder.add_node("answer", answer_node)
builder.add_node("reward", reward_node)

builder.add_edge(START, "vision")
builder.add_edge("vision", "rule")
builder.add_edge("rule", "answer")
builder.add_edge("answer", "reward")
builder.add_edge("reward", END)

graph = builder.compile()
```

---

## 4. 장점

### 4.1 테스트 용이성

```python
import pytest

# ✅ 단위 테스트가 매우 간단해짐
def test_vision_node():
    """Vision 노드 단위 테스트."""
    # Given: 초기 상태
    state = {
        "task_id": "test-123",
        "user_id": "user-456",
        "image_url": "https://example.com/image.jpg",
        "user_input": "이것을 어떻게 버려야 하나요?",
        "classification_result": None,
        "disposal_rules": None,
        "final_answer": None,
        "reward": None,
        "stage_history": [],
        "latencies": {},
        "progress": 0,
        "error": None,
    }
    
    # When: 노드 실행
    update = vision_node(state)
    
    # Then: 업데이트 검증
    assert "classification_result" in update
    assert update["progress"] == 25
    assert "vision" in update["stage_history"]
    assert "vision_ms" in update["latencies"]
    
    # 원본 상태가 변경되지 않았는지 확인
    assert state["classification_result"] is None
    assert state["progress"] == 0


def test_rule_node_with_empty_classification():
    """빈 분류 결과로 Rule 노드 테스트."""
    state = {
        "classification_result": {},
        "stage_history": [],
        "latencies": {},
        "progress": 25,
    }
    
    update = rule_node(state)
    
    assert update["disposal_rules"] is None or update["disposal_rules"] == {}


# Mock 없이 테스트 가능 (순수 함수)
def test_full_pipeline():
    """전체 파이프라인 통합 테스트."""
    initial_state = create_test_state()
    
    # 순차적으로 노드 실행 (상태 직접 관리)
    state = initial_state
    
    state = {**state, **vision_node(state)}
    assert state["progress"] == 25
    
    state = {**state, **rule_node(state)}
    assert state["progress"] == 50
    
    state = {**state, **answer_node(state)}
    assert state["progress"] == 75
    
    state = {**state, **reward_node(state)}
    assert state["progress"] == 100
    
    assert len(state["stage_history"]) == 4
```

### 4.2 재현성 (Reproducibility)

```python
# 동일한 초기 상태 → 동일한 결과 (결정론적)
def test_reproducibility():
    """재현성 테스트."""
    state = create_fixed_test_state()
    
    result1 = vision_node(state)
    result2 = vision_node(state)
    
    # 동일한 입력 → 동일한 출력
    assert result1 == result2


# Snapshot Testing
def test_snapshot():
    """스냅샷 테스트."""
    state = create_fixed_test_state()
    update = vision_node(state)
    
    # 스냅샷과 비교
    expected = load_snapshot("vision_node_output")
    assert update == expected
```

### 4.3 디버깅 용이성

```python
# 모든 상태 변경이 추적 가능
async def debug_pipeline():
    """디버깅을 위한 상태 추적."""
    config = {"configurable": {"thread_id": "debug-session"}}
    
    # 실행 + 상태 히스토리 수집
    states = []
    async for state in graph.astream(initial_state, config, stream_mode="values"):
        states.append(state.copy())
        print(f"Stage: {state.get('stage_history', [])[-1] if state.get('stage_history') else 'start'}")
        print(f"Progress: {state.get('progress', 0)}%")
        print(f"Latencies: {state.get('latencies', {})}")
        print("---")
    
    # 히스토리에서 특정 시점 분석
    for i, state in enumerate(states):
        print(f"Checkpoint {i}: {json.dumps(state, indent=2)}")
```

### 4.4 Time Travel Debugging

```python
# 체크포인터로 Time Travel 디버깅
async def time_travel_debug(thread_id: str, checkpoint_id: str):
    """특정 체크포인트로 돌아가서 재실행."""
    
    # 1. 체크포인트 히스토리 조회
    config = {"configurable": {"thread_id": thread_id}}
    
    async for state in graph.aget_state_history(config):
        print(f"Checkpoint: {state.config['configurable']['checkpoint_id']}")
        print(f"State: {state.values}")
    
    # 2. 특정 체크포인트로 복원
    restore_config = {
        "configurable": {
            "thread_id": thread_id,
            "checkpoint_id": checkpoint_id,
        }
    }
    
    # 3. 해당 시점부터 재실행
    result = await graph.ainvoke(None, config=restore_config)
    return result
```

### 4.5 병렬 처리

```python
import asyncio

# Stateless이므로 안전하게 병렬 실행 가능
async def parallel_processing(inputs: list[dict]) -> list[dict]:
    """여러 입력을 병렬 처리."""
    tasks = [
        graph.ainvoke(input_data)
        for input_data in inputs
    ]
    
    # 각 실행이 독립적 (상태 공유 없음)
    results = await asyncio.gather(*tasks)
    return results


# 배치 처리
async def batch_processing(inputs: list[dict], batch_size: int = 10):
    """배치 단위 병렬 처리."""
    results = []
    
    for i in range(0, len(inputs), batch_size):
        batch = inputs[i:i + batch_size]
        batch_results = await parallel_processing(batch)
        results.extend(batch_results)
    
    return results
```

---

## 5. 패턴 비교

### 5.1 Redux vs LangGraph

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         Redux vs LangGraph                                   │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│   Redux (Frontend State Management)                                          │
│   ─────────────────────────────────                                          │
│   (state, action) => newState                                               │
│                                                                              │
│   const counterReducer = (state = 0, action) => {                           │
│     switch (action.type) {                                                  │
│       case 'INCREMENT':                                                     │
│         return state + 1;  // 새 상태 반환                                  │
│       default:                                                               │
│         return state;                                                        │
│     }                                                                        │
│   };                                                                         │
│                                                                              │
│   ─────────────────────────────────────────────────────────────────────────  │
│                                                                              │
│   LangGraph (AI Agent State Management)                                      │
│   ─────────────────────────────────────                                      │
│   (state) => stateUpdate                                                    │
│                                                                              │
│   def vision_node(state: ScanState) -> dict:                                │
│       result = analyze(state["image_url"])                                  │
│       return {"classification_result": result}  # 업데이트만 반환          │
│                                                                              │
│   ─────────────────────────────────────────────────────────────────────────  │
│                                                                              │
│   공통점:                                                                    │
│   • 순수 함수 (부작용 없음)                                                  │
│   • 불변 상태 (직접 수정 X)                                                  │
│   • 예측 가능한 상태 변화                                                    │
│                                                                              │
│   차이점:                                                                    │
│   • Redux: 액션 기반, 동기 처리                                              │
│   • LangGraph: 노드 기반, 비동기 처리                                        │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 5.2 전통적 OOP vs Stateless Reducer

```python
# ❌ OOP: 상태를 객체 내부에 캡슐화
class TraditionalAgent:
    def __init__(self):
        self._state = {}  # 캡슐화된 상태
    
    def process(self, input_data):
        self._state["input"] = input_data
        self._analyze()
        self._generate()
        return self._state["output"]
    
    def _analyze(self):
        self._state["analysis"] = ...  # 상태 직접 수정
    
    def _generate(self):
        self._state["output"] = ...  # 상태 직접 수정


# ✅ Functional: 상태를 외부에서 관리
def analyze(state: dict) -> dict:
    """순수 함수 - 상태 수정 없이 업데이트 반환."""
    result = perform_analysis(state["input"])
    return {"analysis": result}

def generate(state: dict) -> dict:
    """순수 함수 - 상태 수정 없이 업데이트 반환."""
    output = create_output(state["analysis"])
    return {"output": output}

# 상태 관리는 외부에서
state = {"input": input_data}
state = {**state, **analyze(state)}
state = {**state, **generate(state)}
result = state["output"]
```

---

## 6. 실전 패턴

### 6.1 에러 핸들링

```python
def safe_vision_node(state: ScanState) -> dict:
    """에러 핸들링이 포함된 Stateless Node."""
    try:
        result = analyze_image(state["image_url"])
        return {
            "classification_result": result,
            "stage_history": ["vision"],
            "progress": 25,
            "error": None,
        }
    except TimeoutError:
        return {
            "classification_result": None,
            "stage_history": ["vision_timeout"],
            "progress": 25,
            "error": "Vision analysis timeout",
        }
    except Exception as e:
        return {
            "classification_result": None,
            "stage_history": ["vision_error"],
            "progress": 25,
            "error": str(e),
        }


# 조건부 라우팅으로 에러 핸들링
def should_continue(state: ScanState) -> str:
    """에러 발생 시 에러 핸들러로 라우팅."""
    if state.get("error"):
        return "error_handler"
    return "next_node"
```

### 6.2 이벤트 발행 (부작용 격리)

```python
from langchain_core.callbacks import adispatch_custom_event

async def vision_node_with_events(state: ScanState) -> dict:
    """이벤트 발행이 포함된 노드.
    
    부작용(이벤트 발행)을 노드 내부에서 처리하되,
    상태 업데이트는 여전히 순수 함수 형태로 반환.
    """
    # 시작 이벤트 (부작용)
    await adispatch_custom_event(
        "stage_started",
        {"stage": "vision", "task_id": state["task_id"]}
    )
    
    # 핵심 로직 (순수)
    result = await analyze_image_async(state["image_url"])
    
    # 완료 이벤트 (부작용)
    await adispatch_custom_event(
        "stage_completed",
        {"stage": "vision", "task_id": state["task_id"], "progress": 25}
    )
    
    # 상태 업데이트 반환 (순수)
    return {
        "classification_result": result,
        "progress": 25,
    }
```

### 6.3 의존성 주입

```python
from dataclasses import dataclass
from typing import Callable

# 의존성을 클로저로 주입 (노드는 여전히 순수 함수)
def create_vision_node(
    analyzer: Callable,
    event_publisher: Callable,
) -> Callable:
    """의존성이 주입된 Vision 노드 생성."""
    
    async def vision_node(state: ScanState) -> dict:
        """주입된 의존성 사용, 상태 업데이트만 반환."""
        await event_publisher("vision", "started", state["task_id"])
        
        result = await analyzer(state["image_url"])
        
        await event_publisher("vision", "completed", state["task_id"])
        
        return {
            "classification_result": result,
            "progress": 25,
        }
    
    return vision_node


# 사용
from app.infrastructure.llm import OpenAIAnalyzer
from app.infrastructure.events import RedisEventPublisher

vision_node = create_vision_node(
    analyzer=OpenAIAnalyzer(),
    event_publisher=RedisEventPublisher(),
)

builder.add_node("vision", vision_node)
```

---

## 7. 현재 Celery 파이프라인과의 비교

### 7.1 현재 구조 (Celery Chain)

```python
# 현재: Celery Task (부분적으로 stateful)
@celery_app.task
def vision_task(task_id, user_id, image_url, user_input):
    """Celery Task - 상태를 직접 관리."""
    
    # Redis에서 상태 로드 (부작용)
    state = redis.hgetall(f"scan:state:{task_id}")
    
    # 분석 실행
    result = analyze_image(image_url, user_input)
    
    # Redis에 상태 저장 (부작용)
    redis.hset(f"scan:state:{task_id}", "classification_result", json.dumps(result))
    
    # 이벤트 발행 (부작용)
    publish_stage_event(task_id, "vision", "completed", 25)
    
    # 다음 태스크로 전달
    return {
        "task_id": task_id,
        "user_id": user_id,
        "classification_result": result,
    }
```

### 7.2 Stateless Reducer로 전환

```python
# 전환 후: LangGraph Stateless Reducer
def vision_node(state: ScanState) -> dict:
    """LangGraph Node - 순수 함수."""
    
    # 상태에서 읽기만 (로드 불필요)
    image_url = state["image_url"]
    user_input = state["user_input"]
    
    # 분석 실행 (순수 로직)
    result = analyze_image(image_url, user_input)
    
    # 업데이트만 반환 (저장은 StateGraph가 처리)
    return {
        "classification_result": result,
        "progress": 25,
    }


# 이벤트 발행은 Callback으로 분리
class EventCallback:
    async def on_chain_end(self, outputs, **kwargs):
        node_name = kwargs.get("name")
        task_id = kwargs.get("metadata", {}).get("task_id")
        await publish_stage_event(task_id, node_name, "completed")
```

---

## 8. 요약

### 8.1 Stateless Reducer의 핵심

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                   Stateless Reducer 핵심 원칙                                │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│   1. 순수 함수 (Pure Function)                                               │
│      • 동일 입력 → 동일 출력                                                 │
│      • 부작용 없음 (상태 직접 수정 X)                                        │
│                                                                              │
│   2. 불변 상태 (Immutable State)                                             │
│      • 상태는 읽기 전용                                                      │
│      • 업데이트는 새 객체로 반환                                             │
│                                                                              │
│   3. Reducer 함수                                                            │
│      • (currentState, update) => newState                                   │
│      • StateGraph가 자동으로 병합                                            │
│                                                                              │
│   4. 단방향 데이터 흐름                                                       │
│      • State → Node → Update → New State                                    │
│      • 모든 변경 추적 가능                                                   │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 8.2 체크리스트

```
✅ 노드가 state를 직접 수정하지 않는가?
✅ 노드가 업데이트 dict만 반환하는가?
✅ 동일 입력에 동일 출력이 보장되는가?
✅ 부작용(이벤트, 로깅)이 Callback으로 분리되었는가?
✅ 테스트가 mock 없이 가능한가?
✅ 병렬 실행 시 race condition이 없는가?
```

---

## 참고 자료

- [Redux - Three Principles](https://redux.js.org/understanding/thinking-in-redux/three-principles)
- [LangGraph State Management](https://langchain-ai.github.io/langgraph/concepts/low_level/#state)
- [Pure Functions in JavaScript](https://www.freecodecamp.org/news/what-is-a-pure-function-in-javascript-acb887375dfe/)
- [Immutability in Python](https://realpython.com/python-mutable-vs-immutable-types/)

