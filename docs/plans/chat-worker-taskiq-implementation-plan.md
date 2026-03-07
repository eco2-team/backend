# Chat Worker Taskiq 구현 계획

> **작성일**: 2026-01-13  
> **상태**: Planning  
> **관련 서비스**: chat, chat_worker  
> **관련 문서**: [05-async-job-queue-decision.md](../blogs/applied/05-async-job-queue-decision.md), [03-chat-langgraph-architecture.md](../blogs/applied/03-chat-langgraph-architecture.md)

---

## 📋 Executive Summary

본 문서는 Chat 서비스의 asyncio 네이티브 Job Queue 구현 계획을 정의합니다.

**핵심 결정사항:**
1. **Job Queue**: Celery → **Taskiq** (asyncio 네이티브)
2. **파이프라인 엔진**: Celery Chain → **LangGraph**
3. **브로커**: RabbitMQ (기존 인프라 재사용)
4. **이벤트 버스**: Redis Streams (기존 인프라 재사용)

---

## 1. 배경

### 1.1 왜 asyncio 네이티브 Job Queue가 필요한가?

LangGraph 파이프라인은 **asyncio 네이티브**로 설계되었습니다:

```python
# LangGraph 기본 실행 방식
result = await graph.ainvoke(state)   # async
async for chunk in graph.astream(state):  # async generator
    yield chunk
```

**Celery의 문제점:**
- Celery는 동기 기반 (gevent/eventlet으로 동시성 처리)
- asyncio 코드 실행 시 매번 `asyncio.run()` 필요
- Event loop 재생성 오버헤드

```python
# ❌ 안티패턴: Celery에서 asyncio 강제 실행
@celery_app.task(...)
def chat_task(self, payload):
    import asyncio
    # 매번 새 event loop 생성 - 비효율적
    result = asyncio.run(graph.ainvoke(state))
```

### 1.2 요구사항

| 요구사항 | 설명 |
|----------|------|
| **asyncio 네이티브** | LangGraph `astream()` 완벽 호환 |
| **Job 기반 스케일링** | HTTP 타임아웃 회피, Worker 독립 스케일링 |
| **결과 반환** | 작업 완료 상태 추적 |
| **재시도/타임아웃** | LLM API 실패 시 자동 재시도 |
| **기존 인프라 재사용** | RabbitMQ, Redis 재사용 |

---

## 2. 기술 선택: Taskiq

### 2.1 왜 Taskiq인가?

[Taskiq](https://github.com/taskiq-python/taskiq)는 **asyncio 네이티브 분산 작업 큐**입니다.

| 항목 | Celery | Taskiq |
|------|--------|--------|
| **asyncio** | ❌ (Gevent) | ✅ 네이티브 |
| **LangGraph** | △ 호환 문제 | ✅ 완벽 호환 |
| **async/await** | 불가 | ✅ |
| **브로커** | RabbitMQ | RabbitMQ (동일) |
| **결과 반환** | ✅ | ✅ `TaskiqResult` |
| **재시도/타임아웃** | ✅ | ✅ 데코레이터 설정 |

### 2.2 FastStream vs Taskiq

| 항목 | FastStream | Taskiq |
|------|------------|--------|
| **GitHub** | [ag2ai/faststream](https://github.com/ag2ai/faststream) (⭐ 4.9K) | [taskiq-python/taskiq](https://github.com/taskiq-python/taskiq) (⭐ 1.8K) |
| **패러다임** | 이벤트 스트림 | **작업 큐 (Job)** |
| **설계 목적** | Kafka/RabbitMQ 메시징 | **Celery 대체** |
| **결과 반환** | △ 별도 구현 | ✅ 내장 |
| **재시도** | △ 별도 구현 | ✅ 내장 |

**결론**: Chat 서비스는 Job 기반 스케일링이 필요하므로 **Taskiq** 선택

---

## 3. 아키텍처

### 3.1 전체 구조

```
┌─────────────────────────────────────────────────────────────┐
│  Chat Service Architecture (Taskiq + LangGraph)             │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌──────────┐  Job 제출   ┌──────────┐  Job 소비  ┌────────┐│
│  │ Chat API │───────────▶│ RabbitMQ │──────────▶│ Taskiq ││
│  │ (FastAPI)│            │  (기존)   │           │ Worker ││
│  └──────────┘            └──────────┘           └────────┘│
│       │                                              │      │
│       │ job_id                                       │      │
│       │                                              │      │
│       │                  ┌──────────┐                │      │
│       │                  │ LangGraph │◀──────────────┘      │
│       │                  │ Pipeline  │                      │
│       │                  └──────────┘                       │
│       │                        │                            │
│       │                        │ 이벤트 발행                 │
│       │                        ▼                            │
│       │                  ┌──────────┐                       │
│       │                  │  Redis   │                       │
│       │                  │ Streams  │                       │
│       │                  │  (기존)   │                       │
│       │                  └──────────┘                       │
│       │                        │                            │
│       │                        ▼                            │
│       │                  ┌──────────┐                       │
│       └─────────────────▶│   SSE    │                       │
│         stream_url       │ Gateway  │                       │
│                          │  (기존)   │                       │
│                          └──────────┘                       │
│                                │                            │
│                                ▼                            │
│                          ┌──────────┐                       │
│                          │ Frontend │                       │
│                          └──────────┘                       │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### 3.2 흐름 상세

```
1. 클라이언트 → Chat API
   POST /chat {session_id, message}

2. Chat API → RabbitMQ
   Job 발행: {job_id, session_id, message}
   즉시 반환: {job_id, stream_url}

3. Taskiq Worker ← RabbitMQ
   Job 소비

4. Taskiq Worker → LangGraph
   async for event in graph.astream(...):
       # 노드별 이벤트 발생

5. Taskiq Worker → Redis Streams
   SSE 이벤트 발행 (기존 인프라)

6. SSE Gateway → 클라이언트
   실시간 스트리밍 (기존 인프라)
```

---

## 4. 구현 설계

### 4.1 디렉토리 구조

```
apps/chat_worker/
├── main.py                    # Taskiq 앱
├── tasks/
│   └── chat_task.py           # 채팅 Task 정의
├── application/
│   └── pipeline/
│       ├── graph.py           # LangGraph 정의
│       ├── state.py           # ChatState TypedDict
│       └── nodes/
│           ├── base.py
│           ├── intent_node.py
│           ├── vision_node.py
│           ├── rag_node.py
│           └── answer_node.py
├── infrastructure/
│   ├── messaging/
│   │   └── event_publisher.py # Redis Streams (기존 패턴)
│   └── llm/
│       ├── ports.py           # LLM Port
│       ├── gpt_adapter.py
│       └── gemini_adapter.py
└── setup/
    ├── config.py
    ├── broker.py              # Taskiq 브로커 설정
    └── dependencies.py
```

### 4.2 브로커 설정

```python
# apps/chat_worker/setup/broker.py
from taskiq_aio_pika import AioPikaBroker
from taskiq_redis import RedisResultBackend

from chat_worker.setup.config import get_settings

settings = get_settings()

# 기존 RabbitMQ 재사용
broker = AioPikaBroker(
    settings.rabbitmq_url,
).with_result_backend(
    RedisResultBackend(settings.redis_cache_url)
)
```

### 4.3 Task 정의

```python
# apps/chat_worker/tasks/chat_task.py
from typing import Any

from chat_worker.setup.broker import broker
from chat_worker.setup.dependencies import get_chat_graph, get_event_publisher


@broker.task(
    task_name="chat.process",
    retry_on_error=True,
    max_retries=3,
    timeout=300,  # 5분
)
async def process_chat_task(
    job_id: str,
    session_id: str,
    message: str,
    image_url: str | None = None,
    location: dict | None = None,
    model: str = "gpt-4o",
) -> dict[str, Any]:
    """LangGraph 채팅 파이프라인 실행."""
    
    graph = await get_chat_graph(model=model)
    publisher = await get_event_publisher()
    
    # 시작 이벤트
    await publisher.publish(job_id, {
        "type": "progress",
        "stage": "started",
        "message": "🤔 질문 분석 중...",
    })
    
    try:
        config = {"configurable": {"thread_id": session_id}}
        input_state = {
            "message": message,
            "image_url": image_url,
            "user_location": location,
        }
        
        final_result = None
        
        # LangGraph 스트리밍 실행
        async for event in graph.astream(input_state, config):
            node_name = list(event.keys())[0]
            node_output = event[node_name]
            
            # 노드별 진행 이벤트
            await publisher.publish(job_id, {
                "type": "progress",
                "stage": node_name,
                "message": _get_stage_message(node_name),
            })
            
            # 토큰 스트리밍 (answer 노드)
            if "delta" in node_output:
                await publisher.publish(job_id, {
                    "type": "delta",
                    "content": node_output["delta"],
                })
            
            final_result = node_output
        
        # 완료 이벤트
        await publisher.publish(job_id, {
            "type": "done",
            "stage": "completed",
        })
        
        return {
            "status": "completed",
            "answer": final_result.get("answer", ""),
        }
        
    except Exception as e:
        # 에러 이벤트
        await publisher.publish(job_id, {
            "type": "error",
            "message": str(e),
        })
        raise


def _get_stage_message(stage: str) -> str:
    """단계별 UX 메시지."""
    messages = {
        "intent_classifier": "🤔 질문 분석 중...",
        "vision_node": "🔍 이미지 분류 중...",
        "waste_rag_node": "📚 규정 검색 중...",
        "location_tool_node": "📍 주변 검색 중...",
        "character_node": "🎭 캐릭터 조회 중...",
        "answer_node": "✍️ 답변 작성 중...",
    }
    return messages.get(stage, f"⏳ {stage} 처리 중...")
```

### 4.4 Chat API (Job 제출)

```python
# apps/chat/presentation/http/controllers/chat.py
from fastapi import APIRouter
from pydantic import BaseModel
import uuid

router = APIRouter(prefix="/chat", tags=["chat"])


class ChatRequest(BaseModel):
    session_id: str
    message: str
    image_url: str | None = None
    model: str = "gpt-4o"


class ChatSubmitResponse(BaseModel):
    job_id: str
    stream_url: str
    status: str


@router.post("", response_model=ChatSubmitResponse)
async def submit_chat(request: ChatRequest):
    """채팅 요청 제출.
    
    즉시 job_id 반환, 백그라운드에서 처리.
    """
    from chat_worker.tasks.chat_task import process_chat_task
    
    job_id = str(uuid.uuid4())
    
    # Taskiq로 Job 제출
    await process_chat_task.kiq(
        job_id=job_id,
        session_id=request.session_id,
        message=request.message,
        image_url=request.image_url,
        model=request.model,
    )
    
    return ChatSubmitResponse(
        job_id=job_id,
        stream_url=f"/api/v1/stream/{job_id}",
        status="queued",
    )
```

---

## 5. 기존 인프라 통합

### 5.1 인프라 재사용

```
┌─────────────────────────────────────────────────────────────┐
│  기존 인프라 재사용                                          │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  RabbitMQ (eco2-rabbitmq):                                  │
│  ├── scan.classify      (Celery, 기존)                     │
│  ├── character.match    (Celery, 기존)                     │
│  └── chat.process       (Taskiq, 신규) 🆕                  │
│                                                             │
│  Redis (rfr-streams-redis):                                 │
│  ├── scan:events:*      (SSE, 기존)                        │
│  └── chat:events:*      (SSE, 신규) 🆕                     │
│                                                             │
│  Redis (rfr-cache-redis):                                   │
│  ├── scan:checkpoint:*  (Celery, 기존)                     │
│  └── langgraph:*        (RedisSaver, 신규) 🆕              │
│                                                             │
│  SSE Gateway (기존):                                        │
│  └── 변경 없음 (scan과 동일 패턴)                           │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### 5.2 환경변수

```yaml
# Chat Worker
RABBITMQ_URL: amqp://eco2-rabbitmq:5672/eco2
REDIS_STREAMS_URL: redis://rfr-streams-redis:6379/0
REDIS_CACHE_URL: redis://rfr-cache-redis:6379/0

# LLM API Keys
OPENAI_API_KEY: ${OPENAI_API_KEY}
GEMINI_API_KEY: ${GEMINI_API_KEY}
```

---

## 6. 배포

### 6.1 Dockerfile

```dockerfile
FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY apps/chat_worker ./chat_worker

# Taskiq Worker 실행
CMD ["taskiq", "worker", "chat_worker.setup.broker:broker", "--workers", "2"]
```

### 6.2 Kubernetes Deployment

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: chat-worker
  namespace: chat
spec:
  replicas: 2
  selector:
    matchLabels:
      app: chat-worker
  template:
    metadata:
      labels:
        app: chat-worker
    spec:
      containers:
        - name: chat-worker
          image: mng990/eco2:chat-worker-latest
          command: ["taskiq", "worker", "chat_worker.setup.broker:broker"]
          env:
            - name: RABBITMQ_URL
              valueFrom:
                secretKeyRef:
                  name: chat-secret
                  key: rabbitmq-url
          resources:
            requests:
              memory: "512Mi"
              cpu: "250m"
            limits:
              memory: "1Gi"
              cpu: "500m"
```

---

## 7. 마이그레이션 계획

### Phase 1: 기반 구축 (1주)
- [ ] `apps/chat_worker` 디렉토리 구조 생성
- [ ] Taskiq 브로커 설정
- [ ] 기본 Task 정의 및 테스트

### Phase 2: LangGraph 통합 (1주)
- [ ] ChatState 정의
- [ ] LangGraph 노드 구현 (intent, vision, rag, answer)
- [ ] 그래프 팩토리 구현

### Phase 3: SSE 연동 (3일)
- [ ] Redis Streams 이벤트 발행 연동
- [ ] 기존 SSE Gateway와 통합 테스트

### Phase 4: 배포 (3일)
- [ ] Dockerfile 작성
- [ ] Kubernetes 매니페스트 작성
- [ ] ArgoCD Application 추가

### Phase 5: 검증 (3일)
- [ ] E2E 테스트
- [ ] 성능 테스트
- [ ] 모니터링 설정

---

## 8. Scan Worker와의 공존

```
┌─────────────────────────────────────────────────────────────┐
│  Worker 공존 전략                                            │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  scan_worker: Celery 유지                                   │
│  ├── 이유: 기존 코드 안정, I/O 바운드에 Gevent 적합         │
│  └── 브로커: RabbitMQ (기존)                                │
│                                                             │
│  chat_worker: Taskiq 신규                                   │
│  ├── 이유: LangGraph asyncio 필수                          │
│  └── 브로커: RabbitMQ (동일, 큐 분리)                       │
│                                                             │
│  향후 고려:                                                  │
│  └── scan_worker도 Taskiq로 점진적 마이그레이션 가능        │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## 9. 결론

### 9.1 최종 스택

| 컴포넌트 | 기술 | 비고 |
|----------|------|------|
| **Job 큐** | Taskiq + RabbitMQ | asyncio 네이티브 |
| **파이프라인** | LangGraph | 조건부 분기, 상태 관리 |
| **상태 저장** | RedisSaver | LangGraph Checkpointer |
| **이벤트 버스** | Redis Streams | 기존 인프라 재사용 |
| **API** | FastAPI | 기존 패턴 유지 |

### 9.2 기대 효과

| 측면 | Before (가상) | After |
|------|---------------|-------|
| **asyncio 호환** | `asyncio.run()` 강제 | ✅ 네이티브 |
| **LangGraph 통합** | △ 제약 | ✅ 완벽 |
| **기존 인프라** | - | ✅ 100% 재사용 |
| **Worker 스케일링** | - | ✅ 독립 스케일링 |

---

## 참고 자료

- [Taskiq GitHub](https://github.com/taskiq-python/taskiq)
- [Taskiq Documentation](https://taskiq-python.github.io/)
- [taskiq-aio-pika (RabbitMQ)](https://github.com/taskiq-python/taskiq-aio-pika)
- [LangGraph Documentation](https://python.langchain.com/docs/langgraph)
- [03-chat-langgraph-architecture.md](../blogs/applied/03-chat-langgraph-architecture.md)


