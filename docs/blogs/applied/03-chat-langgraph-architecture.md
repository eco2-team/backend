# Chat 서비스 LangGraph 기반 클린 아키텍처 설계

> Intent-Routed Workflow with Subagent 패턴으로 설계한 LangGraph 기반 Chat 서비스 아키텍처
>
> SSE 스트리밍, 컨텍스트 격리, 멀티 모델 지원

---

## 1. 배경과 목표

### 1.1 기존 구조의 한계

기존 `domains/chat` 서비스는 다음과 같은 문제가 있었습니다:

| 문제 | 설명 |
|------|------|
| **단일 파이프라인** | 이미지/텍스트 구분 없이 동일한 처리 흐름 |
| **의도 분류 부재** | 모든 요청을 폐기물 질문으로 처리 |
| **UX 피드백 없음** | 처리 진행 상황을 사용자에게 알릴 수 없음 |
| **모델 하드코딩** | OpenAI만 지원, 멀티 모델 확장 어려움 |

### 1.2 목표

1. **LangGraph 도입**: 조건부 분기가 가능한 파이프라인 구축
2. **Intent-Routed + Subagent**: 의도 기반 분기 + 복잡한 질문 컨텍스트 격리
3. **SSE 스트리밍**: 실시간 진행 상황 및 토큰 스트리밍
4. **멀티 모델 지원**: GPT-5.2, Gemini 3.0, Claude 4.5 등 Provider 추상화
5. **클린 아키텍처**: Port/Adapter 패턴으로 테스트 용이성 확보

---

## 2. 아키텍처 결정

### 2.1 핵심 의사결정

| 항목 | 결정 | 근거 |
|------|------|------|
| **파이프라인 엔진** | LangGraph | 조건부 분기, 상태 관리, 스트리밍 지원 |
| **Workflow 패턴** | Intent-Routed + Subagent | 의도 기반 분기 + 컨텍스트 격리 |
| **Celery 대체** | ✅ Taskiq | asyncio 네이티브, RabbitMQ 재사용 |
| **SSE 방식** | Redis Streams + Pub/Sub | 기존 인프라 재사용 |
| **모델 추상화** | Port/Adapter | scan_worker 패턴 재사용 |

### 2.2 왜 LangGraph인가?

**Celery Chain vs LangGraph 비교:**

```
Celery Chain:
task1 | task2 | task3 → 순차 실행만 가능

LangGraph:
START → 조건 분기 → 노드A / 노드B / 노드C → 합류 → END
        (의도 분류)   (waste) (location) (character)
```

LangGraph의 장점:
- **조건부 라우팅**: 의도 분류 결과에 따라 다른 노드로 분기
- **상태 공유**: TypedDict로 타입 안전한 상태 관리
- **스트리밍 내장**: StreamWriter로 실시간 이벤트 발행
- **단일 프로세스**: 노드 간 전환이 빠르고 디버깅 용이

---

## 3. 전체 아키텍처

### 3.1 시스템 구성

```
Chat SSE 아키텍처
=================

[Client]
    |
    | (1) POST /chat/messages
    v
[Chat API]
    |
    | (2) job_id 발급
    | (3) Background: LangGraph 시작
    v
[LangGraph] ---> [Redis Streams]
    |                   |
    |                   v
    |            [Event Router]
    |                   |
    |                   v
    |            [Redis Pub/Sub]
    |                   |
    v                   v
[완료]           [SSE Gateway]
                       |
                       v
                 [Client SSE]
```

### 3.2 컴포넌트 역할

> **scan/scan_worker 패턴 적용**: API와 Worker 분리

| 컴포넌트 | 역할 | 변경 여부 |
|---------|------|----------|
| **chat (API)** | Taskiq에 작업 위임, job_id 발급 | ✅ 신규 |
| **chat_worker** | LangGraph 실행, 이벤트 발행 | ✅ 신규 |
| **event_router** | Redis Streams → Pub/Sub | ❌ 기존 재사용 |
| **sse_gateway** | Pub/Sub → SSE | ❌ 기존 재사용 |

**분리 구조 (scan/scan_worker 패턴):**
```
[Client]
    │
    │ POST /chat
    v
[chat (API)] ──── Taskiq 발행 ────▶ [chat_worker]
    │                                     │
    │ job_id 반환                         │ LangGraph 실행
    v                                     v
[Client SSE] ◀──── Redis Streams ◀─── [이벤트 발행]
```

### 3.3 SSE 이벤트 흐름

```
SSE 이벤트 예시:
  queued  -> { status: "started" }
  vision  -> { status: "started" }
  rag     -> { status: "started" }
  answer  -> { status: "started" }
  delta   -> { content: "페" }
  delta   -> { content: "트" }
  delta   -> { content: "병" }
  done    -> { user_answer: "..." }
```

---

## 4. LangGraph 파이프라인 설계

### 4.1 Intent-Routed Workflow with Subagent

> **패턴**: 의도 기반 라우팅 + 복잡한 질문은 Subagent로 분해

```
Chat LangGraph Pipeline (Subagent 포함)
=======================================

START
  │
  ├─ image ──────────────▶ Vision → Rule RAG → Answer
  │
  └─ text ──▶ Intent Classifier
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


Simple Path (단일 노드)
-----------------------
intent → waste_rag / char_node / loc_tool / llm → answer


Complex Path (Subagent 분해)
----------------------------
intent → decomposer → [experts 병렬] → synthesizer → answer
```

**Subagent 적용 기준:**
- **단순 질문**: 단일 노드로 처리 (기존 방식)
- **복잡한 질문**: Subagent로 분해 → 병렬 처리 → 합성

> **상세 설계**: `04-chat-workflow-pattern-decision.md` 섹션 3.2, 10 참조

### 4.2 의도 분류 (Intent Classification)

| 의도 | 설명 | 파이프라인 |
|------|------|-----------|
| `waste` | 분리수거/폐기물 질문 | RAG → Answer (Streaming) |
| `character` | 캐릭터 관련 질문 | Character API → Answer |
| `character_preview` | 분리배출 시 얻을 캐릭터 | Classification → Character Match |
| `location` | 주변 재활용센터/샵 검색 | Location Tool → Answer |
| `general` | 기타 일반 대화/환경 질문 | LLM 답변 생성 (Streaming) |

> **Note**: `eco` 의도는 제거됨 (제로웨이스트 등 기본 환경 정보는 LLM 기본 지식으로 처리)

### 4.3 노드별 이벤트 발행

| 노드 | 발행 이벤트 | stage 값 | UX 피드백 |
|------|-----------|----------|----------|
| `start_node` | 작업 시작 | `queued` | 작업 대기열 등록 |
| `vision_node` | 이미지 분류 | `vision` | "🔍 이미지 분류 중..." |
| `intent_node` | 의도 분류 | `intent` | "🤔 질문 분석 중..." |
| `rag_node` | 규정 검색 | `rag` | "📚 규정 찾는 중..." |
| `location_node` | 위치 검색 | `location` | "📍 주변 검색 중..." |
| `character_node` | 캐릭터 조회 | `character` | "🎭 캐릭터 조회 중..." |
| `answer_node` | 답변 생성 | `answer` + `delta` | "✍️ 답변 작성 중..." + 실시간 타이핑 |
| `end_node` | 완료 | `done` | 결과 전송 |

---

## 5. ChatState 설계

### 5.1 상태 정의

```python
from typing import TypedDict, Literal, Annotated, Any
from langgraph.graph.message import add_messages

class ChatState(TypedDict, total=False):
    """LangGraph 상태 정의."""
    
    # 필수 필드
    job_id: str
    user_id: str
    message: str
    
    # 선택 필드
    image_url: str | None
    user_location: dict | None  # {"lat": 37.5, "lon": 126.9}
    
    # 대화 히스토리 (LangGraph Checkpointer)
    messages: Annotated[list, add_messages]
    
    # 파이프라인 진행 중 채워지는 필드
    intent: Literal["waste", "character", "character_preview",
                    "location", "general"] | None
    classification_result: dict | None
    disposal_rules: dict | None
    tool_results: dict[str, Any] | None
    answer: str | None
    
    # 컨텍스트 사용량 추적
    token_usage: dict | None  # {"input": N, "output": M, "total": T}
    
    # 메타데이터
    pipeline_type: Literal["image", "text"] | None
    error: str | None
    error_stage: str | None
```

> **상세**: 컨텍스트 관리 및 토큰 추적은 `04-chat-workflow-pattern-decision.md` 섹션 4.2, 4.5 참조

### 5.2 라우팅 함수

```python
def route_by_input(state: ChatState) -> Literal["vision", "intent_classifier"]:
    """이미지 유무에 따라 라우팅."""
    if state.get("image_url"):
        return "vision"
    return "intent_classifier"


def route_by_complexity(state: ChatState) -> str:
    """복잡도에 따른 라우팅.
    
    단순 질문: 단일 노드 처리
    복잡한 질문: Subagent 분해 → 병렬 처리
    """
    message = state["message"]
    intent = state.get("intent", "general")
    
    # 복잡한 질문 감지 (멀티 카테고리, 멀티 도구)
    if is_complex_query(message):
        return "complex"
    
    # 단순 질문 → 단일 노드
    return f"simple_{intent}"


def is_complex_query(message: str) -> bool:
    """복잡한 질문 여부 판단."""
    # 멀티 도구 필요 감지
    needs_location = any(kw in message for kw in ["근처", "주변", "가까운"])
    needs_character = any(kw in message for kw in ["캐릭터", "얻"])
    needs_waste = any(kw in message for kw in ["버려", "분리배출", "재활용"])
    
    tool_count = sum([needs_location, needs_character, needs_waste])
    return tool_count >= 2
```

---

## 6. 노드 구현 패턴

### 6.1 BaseNode 추상 클래스

모든 노드가 일관된 이벤트 발행 패턴을 따르도록 강제합니다:

```python
from abc import ABC, abstractmethod
from langgraph.types import StreamWriter

class BaseNode(ABC):
    """노드 기본 클래스."""
    
    def __init__(self, event_publisher: EventPublisherPort):
        self._events = event_publisher
    
    @property
    @abstractmethod
    def stage_name(self) -> str:
        """노드의 stage 이름."""
        pass
    
    async def __call__(
        self, 
        state: ChatState, 
        writer: StreamWriter,
    ) -> ChatState:
        """노드 실행 - 이벤트 발행 래핑."""
        
        # 시작 이벤트
        self._events.publish_stage_event(
            task_id=state["job_id"],
            stage=self.stage_name,
            status="started",
        )
        
        try:
            result = await self.execute(state, writer)
            
            # 완료 이벤트
            self._events.publish_stage_event(
                task_id=state["job_id"],
                stage=self.stage_name,
                status="completed",
            )
            return result
            
        except Exception as e:
            # 에러 이벤트
            self._events.publish_stage_event(
                task_id=state["job_id"],
                stage=self.stage_name,
                status="failed",
                result={"error": str(e)},
            )
            return {**state, "error": str(e)}
    
    @abstractmethod
    async def execute(
        self, 
        state: ChatState, 
        writer: StreamWriter,
    ) -> ChatState:
        """실제 노드 로직 구현."""
        pass
```

### 6.2 Answer 노드 (토큰 스트리밍)

```python
class AnswerNode(BaseNode):
    """답변 생성 노드 - 토큰 스트리밍 지원."""
    
    stage_name = "answer"
    
    def __init__(
        self, 
        event_publisher: EventPublisherPort,
        llm: LLMPort,
        batch_size: int = 5,
    ):
        super().__init__(event_publisher)
        self._llm = llm
        self._batch_size = batch_size
    
    async def execute(
        self, 
        state: ChatState, 
        writer: StreamWriter,
    ) -> ChatState:
        """답변 생성 - 토큰 스트리밍."""
        
        full_answer = ""
        token_buffer: list[str] = []
        
        async for token in self._llm.generate_stream(
            classification=state["classification_result"],
            disposal_rules=state["disposal_rules"],
            user_input=state["message"],
        ):
            full_answer += token
            token_buffer.append(token)
            
            # 배치 단위로 이벤트 발행
            if len(token_buffer) >= self._batch_size:
                combined = "".join(token_buffer)
                
                self._events.publish_stage_event(
                    task_id=state["job_id"],
                    stage="delta",
                    status="streaming",
                    result={"content": combined},
                )
                
                token_buffer.clear()
        
        # 남은 토큰 플러시
        if token_buffer:
            combined = "".join(token_buffer)
            self._events.publish_stage_event(
                task_id=state["job_id"],
                stage="delta",
                status="streaming",
                result={"content": combined},
            )
        
        return {**state, "answer": full_answer}
```

---

## 7. Port/Adapter 패턴

### 7.1 LLM Port 정의

```python
from abc import ABC, abstractmethod
from typing import Any, AsyncGenerator

class LLMPort(ABC):
    """LLM 모델 포트."""

    @abstractmethod
    def generate_answer(
        self,
        classification: dict[str, Any],
        disposal_rules: dict[str, Any],
        user_input: str,
    ) -> dict[str, Any]:
        """답변 생성."""
        pass
    
    @abstractmethod
    def classify_intent(self, message: str) -> str:
        """의도 분류."""
        pass

    @abstractmethod
    async def generate_answer_stream(
        self,
        classification: dict[str, Any],
        disposal_rules: dict[str, Any],
        user_input: str,
    ) -> AsyncGenerator[str, None]:
        """스트리밍 답변 생성."""
        pass
```

### 7.2 지원 모델 목록

> **기준일**: 2026-01-13 (GPT-5.2, Gemini 3.0, Claude 4.5 시리즈 반영)

| Provider | 모델 ID | Context | 권장 용도 |
|----------|---------|---------|----------|
| **OpenAI** | `gpt-5.2` | 128K | Vision, Answer |
| | `gpt-5.2-mini` | 32K | Intent 분류 |
| **Google** | `gemini-3.0-pro` | 1M | Vision, Answer |
| | `gemini-3.0-flash` | 1M | Intent 분류 |
| **Anthropic** | `claude-opus-4-5` | 200K | 복잡한 추론 |
| | `claude-sonnet-4-5` | 200K/1M | 균형 (Tool Calling) |

### 7.3 Model → Provider 매핑

```python
MODEL_PROVIDER_MAP: dict[str, str] = {
    # OpenAI
    "gpt-5.2": "openai",
    "gpt-5.2-thinking": "openai",
    "gpt-5.2-mini": "openai",
    # Google Gemini
    "gemini-3.0-pro": "gemini",
    "gemini-3.0-flash": "gemini",
    # Anthropic Claude
    "claude-opus-4-5": "anthropic",
    "claude-sonnet-4-5": "anthropic",
    "claude-haiku-4-5": "anthropic",
}
```

---

## 8. 그래프 팩토리

### 8.1 그래프 생성

```python
from langgraph.graph import StateGraph, START, END

def create_chat_graph(
    event_publisher: EventPublisherPort,
    llm: LLMPort,
    vision_model: VisionModelPort,
    retriever: RetrieverPort,
    subagents: dict,  # Subagent 추가
) -> StateGraph:
    """Chat LangGraph 그래프 생성 (Subagent 포함)."""
    
    # 메인 노드
    vision_node = VisionNode(event_publisher, vision_model)
    intent_node = IntentNode(event_publisher, llm)
    rag_node = RagNode(event_publisher, llm, retriever)
    answer_node = AnswerNode(event_publisher, llm)
    end_node = EndNode(event_publisher)
    
    # Subagent 노드
    decomposer = DecomposerNode(event_publisher, llm)
    synthesizer = SynthesizerNode(event_publisher, llm)
    
    # 그래프 구성
    graph = StateGraph(ChatState)
    
    # 메인 노드 추가
    graph.add_node("vision", vision_node)
    graph.add_node("intent", intent_node)
    graph.add_node("rag", rag_node)
    graph.add_node("answer", answer_node)
    graph.add_node("end", end_node)
    
    # Subagent 노드 추가
    graph.add_node("decomposer", decomposer)
    graph.add_node("waste_expert", subagents["waste_expert"])
    graph.add_node("location_expert", subagents["location_expert"])
    graph.add_node("character_expert", subagents["character_expert"])
    graph.add_node("synthesizer", synthesizer)
    
    # 1차 라우팅 (입력 유형)
    graph.set_entry_point(START)
    graph.add_conditional_edges(START, route_by_input)
    
    # 이미지 파이프라인
    graph.add_edge("vision", "rag")
    graph.add_edge("rag", "answer")
    
    # 2차 라우팅 (복잡도 기반)
    graph.add_conditional_edges("intent", route_by_complexity)
    
    # Simple Path → Answer
    graph.add_edge("simple_waste", "answer")
    graph.add_edge("simple_character", "answer")
    graph.add_edge("simple_location", "answer")
    graph.add_edge("simple_general", "end")
    
    # Complex Path → Subagent 병렬 → Synthesizer
    graph.add_edge("decomposer", "waste_expert")
    graph.add_edge("decomposer", "location_expert")
    graph.add_edge("decomposer", "character_expert")
    graph.add_edge("waste_expert", "synthesizer")
    graph.add_edge("location_expert", "synthesizer")
    graph.add_edge("character_expert", "synthesizer")
    graph.add_edge("synthesizer", "answer")
    
    # 종료
    graph.add_edge("answer", "end")
    graph.add_edge("end", END)
    
    return graph.compile()
```

---

## 9. OpenAI Streaming 구현

### 9.1 GPT Adapter

```python
from openai import OpenAI
from typing import AsyncGenerator

class GPTLLMAdapter(LLMPort):
    """GPT LLM API 구현체 - 스트리밍 지원."""

    def __init__(self, model: str = "gpt-5.2", api_key: str | None = None):
        self._client = OpenAI(api_key=api_key)
        self._model = model

    async def generate_answer_stream(
        self,
        classification: dict,
        disposal_rules: dict,
        user_input: str,
        system_prompt: str | None = None,
    ) -> AsyncGenerator[str, None]:
        """스트리밍 답변 생성."""
        
        if system_prompt is None:
            system_prompt = "당신은 폐기물 분리배출 전문가입니다."

        user_message = self._build_user_message(
            classification, disposal_rules, user_input
        )

        # stream=True로 스트리밍 활성화
        stream = self._client.responses.create(
            model=self._model,
            input=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            stream=True,
        )

        for event in stream:
            if event.type == "response.output_text.delta":
                yield event.delta
            elif event.type == "response.completed":
                break
```

---

## 10. FastAPI 엔드포인트

### 10.1 메시지 전송 API

```python
from fastapi import APIRouter, BackgroundTasks
from fastapi.responses import JSONResponse
import uuid

router = APIRouter(prefix="/chat", tags=["chat"])

@router.post("/messages")
async def send_message(
    payload: ChatMessageRequest,
    user: CurrentUser,
    background_tasks: BackgroundTasks,
    pipeline: ChatPipelineDep,
) -> JSONResponse:
    """채팅 메시지 전송.
    
    Returns:
        { "job_id": "abc-123-..." }
    
    SSE 구독:
        EventSource('/api/v1/chat/abc-123/events')
    """
    job_id = str(uuid.uuid4())
    
    background_tasks.add_task(
        pipeline.execute,
        job_id=job_id,
        payload=payload,
        user_id=user.user_id,
    )
    
    return JSONResponse(
        content={"job_id": job_id},
        status_code=202,
    )
```

### 10.2 클라이언트 구현

```javascript
async function sendChatMessage(message, imageUrl = null) {
  // 1. 메시지 전송 (job_id 획득)
  const response = await fetch('/api/v1/chat/messages', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message, image_url: imageUrl }),
  });
  
  const { job_id } = await response.json();
  
  // 2. SSE Gateway 연결
  const eventSource = new EventSource(
    `/api/v1/chat/${job_id}/events`
  );
  
  // 진행 상황 이벤트
  eventSource.addEventListener('vision', (e) => {
    const { status } = JSON.parse(e.data);
    if (status === 'started') 
      showProgress('🔍 이미지 분류 중...');
  });
  
  eventSource.addEventListener('rag', (e) => {
    showProgress('📋 규정 찾는 중...');
  });
  
  eventSource.addEventListener('answer', (e) => {
    showProgress('💭 답변 고민 중...');
  });
  
  // LLM 토큰 스트리밍
  eventSource.addEventListener('delta', (e) => {
    const { content } = JSON.parse(e.data);
    appendToChat(content);
  });
  
  // 완료
  eventSource.addEventListener('done', (e) => {
    const result = JSON.parse(e.data);
    finalizeChat(result.user_answer);
    eventSource.close();
  });
}
```

---

## 11. 의존성 주입

### 11.1 Dependencies 설정

```python
from functools import lru_cache
from typing import Annotated
from fastapi import Depends

@lru_cache
def get_event_publisher() -> EventPublisherPort:
    """이벤트 발행 포트."""
    settings = get_settings()
    return RedisEventPublisher(
        redis_url=settings.redis_streams_url,
        shard_count=settings.sse_shard_count,
    )


def get_llm(settings: Settings = Depends(get_settings)) -> LLMPort:
    """LLM 포트 - 모델 설정에 따라 동적 선택."""
    provider = settings.resolve_provider(settings.default_llm_model)
    
    if provider == "gemini":
        return GeminiLLMAdapter(
            model=settings.default_llm_model,
            api_key=settings.gemini_api_key,
        )
    
    return GPTLLMAdapter(
        model=settings.default_llm_model,
        api_key=settings.openai_api_key,
    )


def get_chat_graph(
    event_publisher: Annotated[EventPublisherPort, Depends(get_event_publisher)],
    llm: Annotated[LLMPort, Depends(get_llm)],
    vision_model: Annotated[VisionModelPort, Depends(get_vision_model)],
    retriever: Annotated[RetrieverPort, Depends(get_retriever)],
):
    """Chat LangGraph 그래프."""
    return create_chat_graph(
        event_publisher=event_publisher,
        llm=llm,
        vision_model=vision_model,
        retriever=retriever,
    )
```

---

## 12. 클린 아키텍처 디렉토리 구조

> **scan/scan_worker 패턴 적용**: API와 Worker 분리

### 12.1 chat (API) - 작업 제출만

```
apps/chat/
├── application/
│   └── chat/
│       ├── commands/
│       │   └── submit_chat.py      # Taskiq에 작업 위임
│       └── ports/
│           └── event_publisher.py  # 이벤트 발행 Port
│
├── infrastructure/
│   ├── messaging/
│   │   └── redis_client.py         # Redis 클라이언트
│   └── persistence/
│       └── event_publisher.py      # Redis Streams Adapter
│
├── presentation/
│   └── http/controllers/
│       └── chat.py                 # POST /chat, GET /events
│
├── setup/
│   ├── config.py
│   └── dependencies.py
│
├── main.py
├── Dockerfile
└── requirements.txt
```

### 12.2 chat_worker - 모든 비즈니스 로직

```
apps/chat_worker/
├── application/
│   └── chat/
│       ├── dto/
│       │   └── chat_context.py     # 파이프라인 컨텍스트
│       └── ports/
│           ├── event_publisher.py  # 이벤트 발행 Port
│           ├── llm_client.py       # LLM Port
│           └── retriever.py        # RAG Port
│
├── infrastructure/
│   ├── langgraph/
│   │   ├── factory.py              # 그래프 생성
│   │   └── nodes/
│   │       ├── intent.py           # 의도 분류
│   │       ├── rag.py              # RAG 검색
│   │       └── answer.py           # 답변 생성
│   ├── llm/
│   │   ├── openai/client.py        # OpenAI Adapter
│   │   └── gemini/client.py        # Gemini Adapter
│   ├── persistence/
│   │   ├── event_publisher.py      # Redis Streams Adapter
│   │   └── retriever.py            # JSON RAG Adapter
│   └── assets/
│       ├── data/source/            # 배출 규정 JSON
│       └── prompts/
│
├── presentation/
│   └── tasks/
│       └── process_task.py         # @broker.task
│
├── setup/
│   ├── broker.py                   # Taskiq RabbitMQ
│   ├── config.py
│   └── dependencies.py
│
├── main.py
├── Dockerfile
└── requirements.txt
```

### 12.3 scan/scan_worker와 비교

| 구분 | scan | chat |
|------|------|------|
| **API** | Celery Chain 발행 | Taskiq Task 발행 |
| **Worker** | Celery Tasks | Taskiq + LangGraph |
| **파이프라인** | Vision→Rule→Answer→Reward | Intent→RAG→Answer |
| **이벤트** | Redis Streams | Redis Streams |

---

## 13. Worker 분리 설계 (asyncio 네이티브)

> **상세 설계**: `05-async-job-queue-decision.md` 참조

### 13.1 왜 Celery가 아닌가?

**LangGraph는 asyncio 네이티브**입니다:

```python
# LangGraph 기본 실행 방식
result = await graph.ainvoke(state)   # async
async for chunk in graph.astream(state):  # async generator
    yield chunk
```

**Celery의 문제점**:
- Celery는 동기 기반 (gevent/eventlet으로 동시성 처리)
- asyncio 코드 실행 시 매번 `asyncio.run()` 필요
- Event loop 재생성 오버헤드

### 13.2 asyncio 네이티브 Worker 옵션

| 옵션 | 브로커 | 장점 | 단점 |
|------|--------|------|------|
| **arq** | Redis | asyncio 네이티브, 경량 | RabbitMQ 미지원 |
| **Taskiq** | RabbitMQ/Redis | asyncio 네이티브, **기존 인프라 재사용** | 상대적으로 새로움 |
| **FastStream** | RabbitMQ/Kafka | 이벤트 스트림 특화 | Job 큐보다 이벤트 버스 |

### 13.3 구현: Taskiq (RabbitMQ 기반) ✅

**기존 RabbitMQ 인프라 재사용**하면서 asyncio 네이티브로 동작:

```python
# chat_worker/setup/broker.py
from taskiq_aio_pika import AioPikaBroker
from chat_worker.setup.config import get_settings

settings = get_settings()
broker = AioPikaBroker(
    url=settings.rabbitmq_url,
    declare_exchange=True,
    exchange_name="chat_tasks",
)
```

```python
# chat_worker/presentation/tasks/process_task.py
from chat_worker.setup.broker import broker
from chat_worker.setup.dependencies import (
    get_chat_graph,
    get_event_publisher,
)

@broker.task(
    task_name="chat.process",
    timeout=120,
    retry_on_error=True,
    max_retries=2,
)
async def process_chat(
    job_id: str,
    session_id: str,
    message: str,
    user_id: str | None = None,
    image_url: str | None = None,
    user_location: dict[str, float] | None = None,
    model: str | None = None,
) -> dict[str, Any]:
    """LangGraph 파이프라인 실행 (asyncio 네이티브)."""
    settings = get_settings()
    event_publisher = await get_event_publisher()
    
    # LangGraph 파이프라인 생성
    graph = await get_chat_graph(
        provider=settings.default_provider,
        model=model,
    )
    
    # 초기 상태 구성
    initial_state = {
        "job_id": job_id,
        "session_id": session_id,
        "user_id": user_id or "anonymous",
        "message": message,
        "image_url": image_url,
        "user_location": user_location,
    }
    
    # LangGraph 파이프라인 실행
    result = await graph.ainvoke(initial_state)
    
    return {
        "job_id": job_id,
        "status": "completed",
        "intent": result.get("intent"),
        "answer": result.get("answer"),
    }
```

### 13.4 전체 아키텍처 (Taskiq 기반)

```
Chat 아키텍처 (Taskiq + LangGraph)
==================================

[Client]
    |
    | (1) POST /chat/messages
    v
[Chat API]
    |
    | (2) job_id 발급
    | (3) process_chat_task.kiq(...)
    v
[RabbitMQ (기존)] -------> [Chat Worker (Taskiq)]
    |                           |
    | (4) job_id 반환           | (5) LangGraph.astream()
    v                           |
[Client]                        | (6) Redis Streams 이벤트
    |                           v
    | (7) SSE 연결        [Redis Streams (기존)]
    v                           |
[SSE Gateway (기존)] <-- [Event Router (기존)]
    |
    | (8) 실시간 이벤트
    v
[Client]
```

### 13.5 Chat API 엔드포인트 (Taskiq 연동)

```python
# presentation/http/controllers/chat.py
from fastapi import APIRouter
import uuid

router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("/messages")
async def send_message(
    payload: ChatMessageRequest,
    user: CurrentUser,
) -> JSONResponse:
    """채팅 메시지 전송.
    
    Taskiq로 비동기 작업 큐잉 후 즉시 job_id 반환.
    """
    from chat_worker.tasks.chat_task import process_chat_task
    
    job_id = str(uuid.uuid4())
    
    # Taskiq 큐에 작업 추가
    await process_chat_task.kiq(
        job_id=job_id,
        session_id=payload.session_id,
        message=payload.message,
        image_url=str(payload.image_url) if payload.image_url else None,
        location=payload.location.model_dump() if payload.location else None,
        model=payload.model,
    )
    
    return JSONResponse(
        content={
            "job_id": job_id,
            "stream_url": f"/api/v1/stream/{job_id}",
        },
        status_code=202,
    )
```

### 13.6 Worker 실행

```bash
# 개발
taskiq worker chat_worker.setup.broker:broker --reload

# 프로덕션
taskiq worker chat_worker.setup.broker:broker --workers 4
```

### 13.7 Dockerfile (Chat Worker)

```dockerfile
# apps/chat_worker/Dockerfile
FROM python:3.12-slim

WORKDIR /app

COPY apps/chat_worker/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY apps/chat_worker /app/chat_worker

ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

# Taskiq worker 실행
CMD ["taskiq", "worker", "chat_worker.setup.broker:broker", "--workers", "2"]
```

### 13.8 requirements.txt

```
# apps/chat_worker/requirements.txt
taskiq>=0.12.0
taskiq-aio-pika>=0.4.0
langgraph>=0.2.0
langgraph-checkpoint-redis>=0.1.0
redis>=5.0.0
openai>=1.50.0
google-generativeai>=0.8.0
anthropic>=0.40.0
pydantic>=2.0.0
pydantic-settings>=2.0.0
```

### 13.9 기존 인프라 재사용

```
┌─────────────────────────────────────────────────┐
│  인프라 재사용                                   │
├─────────────────────────────────────────────────┤
│                                                 │
│  RabbitMQ (eco2-rabbitmq):                      │
│  ├── scan.classify      (Celery, 기존)         │
│  ├── character.match    (Celery, 기존)         │
│  └── chat.process       (Taskiq, 신규) 🆕      │
│                                                 │
│  Redis (rfr-streams-redis):                     │
│  ├── scan:events:*      (SSE, 기존)            │
│  └── chat:events:*      (SSE, 신규) 🆕         │
│                                                 │
│  Redis (rfr-cache-redis):                       │
│  ├── scan:checkpoint:*  (Celery, 기존)         │
│  └── langgraph:*        (RedisSaver, 신규) 🆕  │
│                                                 │
└─────────────────────────────────────────────────┘
```

---

## 14. 토큰 스트리밍 최적화

고빈도 토큰 스트리밍의 경우:
1. **토큰 배치 발행**: 5~10개 토큰마다 한 번에 발행
2. **직접 Pub/Sub 발행**: 토큰은 Redis Streams 우회
3. **하이브리드**: 진행 상황은 Streams, 토큰은 직접 Pub/Sub

---

## 15. Subagent 아키텍처

복잡한 멀티 질문은 Subagent로 분해하여 컨텍스트 격리:

```
START -> intent (복잡도)
            |
    +-------+-------+
    |               |
 simple          complex
    |               |
 single         decomposer
  node              |
    |       +-------+-------+
    |       |       |       |
    |    waste   location  char
    |    expert   expert  expert
    |       |       |       |
    |       +-------+-------+
    |               |
    +--------> synthesizer
                    |
                 answer (streaming)
```

**Subagent 장점:**
- **컨텍스트 격리**: 각 Expert가 독립적인 컨텍스트
- **병렬 처리**: Expert들이 동시 실행 가능
- **토큰 효율**: 메인 컨텍스트에는 요약 결과만

**상세 설계**: `04-chat-workflow-pattern-decision.md` 섹션 10
**RLM 확장**: `docs/blogs/async/foundations/17-recursive-language-models.md`

---

## 참고 자료

### 관련 문서
- `04-chat-workflow-pattern-decision.md` - Intent-Routed Workflow + Subagent 설계, Tool Calling
- `05-async-job-queue-decision.md` - asyncio Job Queue 선택 (Taskiq)

### 코드베이스
- `apps/scan_worker` - Port/Adapter 패턴, LLM 구현
- `apps/event_router` - Redis Streams Consumer
- `apps/sse_gateway` - Redis Pub/Sub → SSE

### 외부 문서
- [LangGraph Documentation](https://python.langchain.com/docs/langgraph)
- [OpenAI Streaming Responses](https://platform.openai.com/docs/guides/streaming-responses)
- [Taskiq Documentation](https://taskiq-python.github.io/)

---

**작성일**: 2026-01-10
**최종 수정**: 2026-01-13 (Intent-Routed + Subagent 패턴, GPT-5.2/Gemini 3.0/Claude 4.5 모델)

