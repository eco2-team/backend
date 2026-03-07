# LangGraph 스트리밍 패턴 심화 가이드

> Chat 서비스의 SSE 스트리밍 구현을 위한 LangGraph 스트리밍 패턴 정리
>
> **참고**: [LangGraph Streaming](https://docs.langchain.com/oss/python/langgraph/streaming)

---

## 1. 스트리밍 모드 비교

LangGraph는 세 가지 스트리밍 모드를 제공합니다.

### 1.1 stream_mode 옵션

| 모드 | 설명 | 사용 케이스 |
|------|------|------------|
| `values` | 전체 State 스트리밍 | 디버깅, 전체 상태 추적 |
| `updates` | State 변경분만 스트리밍 | 노드별 결과 추적 |
| `custom` | 노드 내부 커스텀 이벤트 | **토큰 스트리밍, 진행 상황** |

### 1.2 Chat 서비스 요구사항

```
필요한 이벤트 타입:
├── progress: 단계 진행 상황 (vision, rag, answer 시작/완료)
├── delta: LLM 토큰 스트리밍 (실시간 타이핑 효과)
└── done: 파이프라인 완료
```

**결론**: `stream_mode="custom"` 사용

---

## 2. Custom 스트리밍 구현

### 2.1 StreamWriter 사용

```python
from langgraph.types import StreamWriter
from typing import TypedDict


class ChatState(TypedDict):
    job_id: str
    message: str
    image_url: str | None
    classification: dict | None
    disposal_rules: dict | None
    answer: str | None


async def vision_node(
    state: ChatState,
    writer: StreamWriter,
) -> ChatState:
    """Vision 노드 - 커스텀 이벤트 발행."""
    
    # 진행 상황 이벤트
    writer({
        "type": "progress",
        "stage": "vision",
        "status": "started",
        "message": "🔍 이미지 분류 중...",
    })
    
    result = await vision_model.classify(state["image_url"])
    
    writer({
        "type": "progress",
        "stage": "vision",
        "status": "completed",
        "result": result,
    })
    
    return {**state, "classification": result}


async def answer_node(
    state: ChatState,
    writer: StreamWriter,
) -> ChatState:
    """Answer 노드 - 토큰 스트리밍."""
    
    writer({
        "type": "progress",
        "stage": "answer",
        "status": "started",
        "message": "💭 답변 고민 중...",
    })
    
    full_answer = ""
    async for token in llm.astream(build_prompt(state)):
        full_answer += token
        # 토큰 단위 이벤트
        writer({
            "type": "delta",
            "content": token,
        })
    
    writer({
        "type": "progress",
        "stage": "answer",
        "status": "completed",
    })
    
    return {**state, "answer": full_answer}
```

### 2.2 그래프 실행 및 스트리밍

```python
# 그래프 컴파일
app = graph.compile()

# 스트리밍 실행
async for event in app.astream(
    {"message": "페트병 어떻게 버려요?", "image_url": None},
    stream_mode="custom",
):
    print(event)
    # {"type": "progress", "stage": "intent", "status": "started", ...}
    # {"type": "progress", "stage": "intent", "status": "completed", ...}
    # {"type": "progress", "stage": "rag", "status": "started", ...}
    # ...
    # {"type": "delta", "content": "페"}
    # {"type": "delta", "content": "트"}
    # {"type": "delta", "content": "병"}
    # ...
```

---

## 3. SSE 통합 패턴

### 3.1 방법 1: 직접 SSE 응답 (간단한 케이스)

```python
from fastapi import APIRouter
from sse_starlette.sse import EventSourceResponse
import json


router = APIRouter()


@router.post("/messages/stream")
async def send_message_stream(
    payload: ChatMessageRequest,
    user: CurrentUser,
) -> EventSourceResponse:
    """채팅 메시지 - 직접 SSE 스트리밍."""
    
    async def event_generator():
        input_state = {
            "job_id": str(uuid.uuid4()),
            "message": payload.message,
            "image_url": payload.image_url,
        }
        
        async for event in app.astream(input_state, stream_mode="custom"):
            yield {
                "event": event.get("type", "message"),
                "data": json.dumps(event, ensure_ascii=False),
            }
    
    return EventSourceResponse(
        event_generator(),
        media_type="text/event-stream",
    )
```

**장점**: 구현 간단
**단점**: API 서버에 부하 집중, 수평 확장 어려움

### 3.2 방법 2: Redis Streams 중개 (프로덕션 권장)

```python
@router.post("/messages")
async def send_message(
    payload: ChatMessageRequest,
    user: CurrentUser,
    background_tasks: BackgroundTasks,
) -> JSONResponse:
    """채팅 메시지 - job_id 발급 후 비동기 처리."""
    job_id = str(uuid.uuid4())
    
    # Background에서 파이프라인 실행
    background_tasks.add_task(
        execute_pipeline_with_events,
        job_id=job_id,
        payload=payload,
        user_id=user.user_id,
    )
    
    return JSONResponse({"job_id": job_id}, status_code=202)


async def execute_pipeline_with_events(
    job_id: str,
    payload: ChatMessageRequest,
    user_id: str,
):
    """파이프라인 실행 + Redis Streams 이벤트 발행."""
    
    async for event in app.astream(
        {
            "job_id": job_id,
            "message": payload.message,
            "image_url": payload.image_url,
        },
        stream_mode="custom",
    ):
        # LangGraph 이벤트 → Redis Streams
        event_publisher.publish_stage_event(
            task_id=job_id,
            stage=event.get("stage", event.get("type")),
            status=event.get("status", "streaming"),
            result=event,
        )
```

**흐름**:
```
Client ─POST→ Chat API ─job_id→ Client
                │
                └─BackgroundTasks─→ LangGraph
                                       │
                                       ├─ event → Redis Streams
                                       ├─ event → Redis Streams
                                       └─ event → Redis Streams
                                                     │
                                                Event Router
                                                     │
                                                Redis Pub/Sub
                                                     │
                                                SSE Gateway
                                                     │
Client ←──────── EventSource('/chat/{job_id}/events') ←┘
```

---

## 4. 토큰 스트리밍 최적화

### 4.1 문제: 토큰당 Redis 발행 오버헤드

```python
# 비효율적: 토큰마다 Redis 호출
async for token in llm.astream(prompt):
    event_publisher.publish_stage_event(...)  # 네트워크 RTT
```

### 4.2 해결책 1: 배치 발행

```python
from asyncio import Queue, create_task
import asyncio


class BatchedEventPublisher:
    """토큰 이벤트 배치 발행."""
    
    def __init__(self, publisher: EventPublisherPort, batch_size: int = 5):
        self._publisher = publisher
        self._batch_size = batch_size
        self._buffer: list[str] = []
    
    async def publish_token(self, job_id: str, token: str):
        """토큰 버퍼링 후 배치 발행."""
        self._buffer.append(token)
        
        if len(self._buffer) >= self._batch_size:
            await self._flush(job_id)
    
    async def _flush(self, job_id: str):
        """버퍼 플러시."""
        if self._buffer:
            combined = "".join(self._buffer)
            self._publisher.publish_stage_event(
                task_id=job_id,
                stage="delta",
                status="streaming",
                result={"content": combined},
            )
            self._buffer.clear()
    
    async def finalize(self, job_id: str):
        """남은 버퍼 플러시."""
        await self._flush(job_id)
```

### 4.3 해결책 2: 직접 Pub/Sub 발행 (토큰 전용)

```python
async def answer_node(
    state: ChatState,
    writer: StreamWriter,
    pubsub_client: Redis,  # 직접 Pub/Sub 클라이언트
) -> ChatState:
    """토큰은 Redis Streams 우회, 직접 Pub/Sub."""
    
    channel = f"sse:events:{state['job_id']}"
    
    async for token in llm.astream(build_prompt(state)):
        # Streams 우회, 직접 Pub/Sub (지연 최소화)
        await pubsub_client.publish(
            channel,
            json.dumps({"type": "delta", "content": token}),
        )
        
        # 동시에 custom 스트림에도 emit (로깅/모니터링용)
        writer({"type": "delta", "content": token})
```

### 4.4 권장 전략

| 이벤트 타입 | 발행 방식 | 이유 |
|------------|----------|------|
| `progress` (vision, rag 등) | Redis Streams | 내구성, 멱등성 필요 |
| `delta` (토큰) | 직접 Pub/Sub 또는 배치 | 지연 최소화 |
| `done` | Redis Streams | 최종 결과 저장 |

---

## 5. 에러 핸들링

### 5.1 노드 에러 시 이벤트 발행

```python
async def vision_node(
    state: ChatState,
    writer: StreamWriter,
) -> ChatState:
    """Vision 노드 - 에러 핸들링."""
    
    writer({
        "type": "progress",
        "stage": "vision",
        "status": "started",
    })
    
    try:
        result = await vision_model.classify(state["image_url"])
        
        writer({
            "type": "progress",
            "stage": "vision",
            "status": "completed",
        })
        
        return {**state, "classification": result}
        
    except Exception as e:
        writer({
            "type": "error",
            "stage": "vision",
            "message": str(e),
        })
        
        # 에러 상태로 전환
        return {**state, "error": str(e)}
```

### 5.2 에러 라우팅

```python
def route_on_error(state: ChatState) -> str:
    """에러 발생 시 에러 핸들러로 라우팅."""
    if state.get("error"):
        return "error_handler"
    return "next_node"


async def error_handler(
    state: ChatState,
    writer: StreamWriter,
) -> ChatState:
    """에러 핸들러 - 최종 에러 이벤트."""
    
    writer({
        "type": "error",
        "stage": "done",
        "status": "failed",
        "message": state.get("error", "Unknown error"),
    })
    
    return state
```

---

## 6. 클라이언트 구현 가이드

### 6.1 JavaScript EventSource

```javascript
async function chatWithStreaming(message, imageUrl = null) {
  // 1. 메시지 전송
  const response = await fetch('/api/v1/chat/messages', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message, image_url: imageUrl }),
  });
  
  const { job_id } = await response.json();
  
  // 2. SSE 연결
  const eventSource = new EventSource(`/api/v1/chat/${job_id}/events`);
  
  // 진행 상황 이벤트
  eventSource.addEventListener('progress', (e) => {
    const { stage, status, message } = JSON.parse(e.data);
    updateProgressUI(stage, status, message);
  });
  
  // 토큰 스트리밍
  eventSource.addEventListener('delta', (e) => {
    const { content } = JSON.parse(e.data);
    appendToChat(content);  // 실시간 타이핑 효과
  });
  
  // 완료
  eventSource.addEventListener('done', (e) => {
    const result = JSON.parse(e.data);
    finalizeChatUI(result);
    eventSource.close();
  });
  
  // 에러
  eventSource.addEventListener('error', (e) => {
    if (e.data) {
      const { message } = JSON.parse(e.data);
      showError(message);
    }
    eventSource.close();
  });
}
```

### 6.2 React Hook 예시

```typescript
function useChatStream() {
  const [messages, setMessages] = useState<string[]>([]);
  const [status, setStatus] = useState<'idle' | 'loading' | 'streaming' | 'done'>('idle');
  const [currentAnswer, setCurrentAnswer] = useState('');
  
  const sendMessage = async (message: string, imageUrl?: string) => {
    setStatus('loading');
    setCurrentAnswer('');
    
    const response = await fetch('/api/v1/chat/messages', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message, image_url: imageUrl }),
    });
    
    const { job_id } = await response.json();
    
    const eventSource = new EventSource(`/api/v1/chat/${job_id}/events`);
    
    eventSource.addEventListener('progress', (e) => {
      const { stage, status: progressStatus } = JSON.parse(e.data);
      if (stage === 'answer' && progressStatus === 'started') {
        setStatus('streaming');
      }
    });
    
    eventSource.addEventListener('delta', (e) => {
      const { content } = JSON.parse(e.data);
      setCurrentAnswer(prev => prev + content);
    });
    
    eventSource.addEventListener('done', () => {
      setStatus('done');
      setMessages(prev => [...prev, currentAnswer]);
      eventSource.close();
    });
    
    eventSource.onerror = () => {
      setStatus('idle');
      eventSource.close();
    };
  };
  
  return { messages, status, currentAnswer, sendMessage };
}
```

---

## 7. 성능 고려사항

### 7.1 동시 연결 수

```python
# uvicorn 설정
uvicorn.run(
    app,
    host="0.0.0.0",
    port=8000,
    limit_concurrency=1000,  # 동시 연결 제한
    timeout_keep_alive=120,   # SSE 연결 유지 시간
)
```

### 7.2 메모리 관리

```python
# 스트리밍 중 메모리 누수 방지
async def answer_node(state: ChatState, writer: StreamWriter) -> ChatState:
    chunks = []
    
    async for token in llm.astream(prompt):
        chunks.append(token)
        writer({"type": "delta", "content": token})
        
        # 주기적 가비지 컬렉션 힌트
        if len(chunks) % 100 == 0:
            gc.collect()
    
    return {**state, "answer": "".join(chunks)}
```

---

## 8. 요약

| 항목 | 권장 사항 |
|------|----------|
| **스트리밍 모드** | `stream_mode="custom"` |
| **이벤트 발행** | StreamWriter + Redis Streams |
| **토큰 스트리밍** | 배치 발행 또는 직접 Pub/Sub |
| **에러 핸들링** | 노드 레벨 try-catch + 에러 라우팅 |
| **클라이언트** | EventSource + 이벤트 타입별 핸들러 |

---

**작성일**: 2026-01-09  
**관련 문서**: `01-langgraph-reference.md`

