# asyncio 네이티브 Job Queue 선택: Taskiq vs FastStream

> **작성일**: 2026-01-13
> **관련 문서**: `04-chat-workflow-pattern-decision.md`
> **참고**: [Taskiq GitHub](https://github.com/taskiq-python/taskiq), [FastStream GitHub](https://github.com/ag2ai/faststream)

---

## 1. 배경: 왜 Job 기반 큐잉이 필요한가?

### 1.1 Chat 서비스 요구사항

Chat 서비스는 LangGraph 파이프라인을 실행하는 **장시간 작업**입니다.

```
사용자 요청 → LangGraph 파이프라인 (5~30초) → 응답

파이프라인 단계:
1. Intent Classification (0.5초)
2. RAG/Tool Calling (1~5초)
3. LLM Generation (3~20초)
4. Subagent 실행 (선택적, 5~15초)
```

### 1.2 동기 처리의 문제

```python
# ❌ 문제: HTTP 타임아웃, 커넥션 점유
@router.post("/chat")
async def chat(request: ChatRequest):
    result = await run_langgraph(request)  # 30초 blocking
    return result
```

| 문제 | 설명 |
|------|------|
| HTTP 타임아웃 | 30초 초과 시 504 Gateway Timeout |
| 커넥션 점유 | Worker 스레드 고갈 |
| 스케일링 어려움 | API 서버 = Worker 강결합 |
| 재시도 불가 | 실패 시 클라이언트가 재요청 |

### 1.3 비동기 Job 처리의 필요성

```
┌─────────────────────────────────────────────────────────────┐
│  비동기 Job 처리 패턴                                        │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  1. 제출 (즉시 반환)                                         │
│     POST /chat → job_id 반환 (200ms 이내)                   │
│                                                             │
│  2. 처리 (백그라운드)                                        │
│     Worker가 RabbitMQ에서 Job 소비 → LangGraph 실행         │
│                                                             │
│  3. 스트리밍 (실시간)                                        │
│     Worker → Redis Streams → SSE Gateway → 클라이언트       │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## 2. 이벤트 스트림 vs Job 큐

### 2.1 패러다임 차이

| 항목 | 이벤트 스트림 | Job 큐 |
|------|-------------|--------|
| **목적** | 도메인 간 이벤트 통신 | **작업 실행 및 스케줄링** |
| **패턴** | Pub/Sub, Event Bus | **Task/Worker** |
| **결과** | Fire-and-forget | **결과 반환 필요** |
| **재시도** | 선택적 | **필수** |
| **타임아웃** | 없음 | **필수** |
| **예시** | Kafka, Redis Streams | **Celery, Taskiq** |

### 2.2 Eco² 현황

```
┌─────────────────────────────────────────────────────────────┐
│  Eco² 메시징 현황                                           │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  이벤트 버스 (도메인 간):                                    │
│  ┌─────────────┐     ┌─────────────┐                       │
│  │ scan_worker │────▶│ Redis       │────▶ SSE Gateway      │
│  │ (Celery)    │     │ Streams     │                       │
│  └─────────────┘     └─────────────┘                       │
│        │                                                    │
│        │ ✅ 이미 구현됨 (이벤트 발행)                        │
│                                                             │
│  작업 큐 (Job 실행):                                         │
│  ┌─────────────┐     ┌─────────────┐     ┌─────────────┐   │
│  │ Scan API    │────▶│ RabbitMQ    │────▶│ scan_worker │   │
│  └─────────────┘     └─────────────┘     │ (Celery)    │   │
│                                          └─────────────┘   │
│        │                                                    │
│        │ ✅ 이미 구현됨 (Celery + RabbitMQ)                  │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### 2.3 Chat 서비스에 필요한 것

```
Chat 서비스 = Job 큐 + 이벤트 버스 (둘 다 필요)

Job 큐 역할:
├── 작업 제출 및 실행
├── 재시도/타임아웃 관리
├── Worker 스케일링
└── 결과 반환

이벤트 버스 역할 (기존 재사용):
├── SSE 이벤트 발행
└── 진행 상황 스트리밍
```

---

## 3. FastStream vs Taskiq 비교

### 3.1 핵심 차이

| 항목 | FastStream | Taskiq |
|------|------------|--------|
| **GitHub** | [ag2ai/faststream](https://github.com/ag2ai/faststream) (⭐ 4.9K) | [taskiq-python/taskiq](https://github.com/taskiq-python/taskiq) (⭐ 1.8K) |
| **패러다임** | **이벤트 스트림** | **작업 큐 (Job)** |
| **설계 목적** | Kafka/RabbitMQ 메시징 | **Celery 대체** |
| **결과 반환** | △ (별도 구현) | ✅ `TaskiqResult` |
| **재시도** | △ (별도 구현) | ✅ `retry_on_error` |
| **타임아웃** | △ | ✅ `timeout` |
| **스케줄링** | ❌ | ✅ cron, interval |
| **asyncio** | ✅ | ✅ |
| **RabbitMQ** | ✅ | ✅ |

### 3.2 Chat 서비스 관점

| 요구사항 | FastStream | Taskiq |
|----------|------------|--------|
| LangGraph Job 실행 | △ | ✅ |
| 결과 반환 | 별도 구현 | **내장** |
| 실패 재시도 | 별도 구현 | **내장** |
| 타임아웃 | 별도 구현 | **내장** |
| Worker 스케일링 | ✅ | ✅ |
| SSE 이벤트 | 별도 구현 | 별도 구현 |

### 3.3 결론

```
FastStream: 이벤트 스트림 특화 (Pub/Sub)
           → Eco²는 이미 Redis Streams로 구현

Taskiq:    Job 큐 특화 (Celery 대체)
           → Chat Worker에 적합 ✅
```

---

## 4. Taskiq 상세

### 4.1 핵심 특징

[Taskiq](https://github.com/taskiq-python/taskiq)는 **asyncio 네이티브 분산 작업 큐**입니다.

| 특징 | 설명 |
|------|------|
| **asyncio 네이티브** | async/await 완벽 지원 |
| **다중 브로커** | RabbitMQ, Redis, NATS, Kafka |
| **결과 저장** | Redis, PostgreSQL 등 |
| **재시도/타임아웃** | 데코레이터로 설정 |
| **의존성 주입** | FastAPI 스타일 DI |
| **타입 힌트** | PEP-612 지원 |

### 4.2 브로커 옵션

| 브로커 | 패키지 | Eco² 호환 |
|--------|--------|----------|
| **RabbitMQ** | `taskiq-aio-pika` | ✅ 기존 재사용 |
| Redis | `taskiq-redis` | ✅ |
| NATS | `taskiq-nats` | - |
| Kafka | `taskiq-kafka` | - |

### 4.3 기본 사용법

```python
from taskiq_aio_pika import AioPikaBroker

# 기존 RabbitMQ 재사용
broker = AioPikaBroker(
    "amqp://eco2-rabbitmq:5672/eco2"
)


@broker.task(
    retry_on_error=True,    # 실패 시 재시도
    max_retries=3,          # 최대 3회
    timeout=300,            # 5분 타임아웃
)
async def process_chat(
    job_id: str,
    session_id: str,
    message: str,
) -> dict:
    """LangGraph 파이프라인 실행."""
    result = await run_langgraph(session_id, message)
    return {"answer": result["answer"]}
```

---

## 5. LangGraph + Taskiq 통합

### 5.1 왜 LangGraph에 Job 큐가 필요한가?

LangGraph 파이프라인은 **장시간 실행**되며, **상태 관리**가 필요합니다.

```python
# LangGraph 파이프라인 특성
async for event in graph.astream(input_state, config):
    # 1. 각 노드별 이벤트 발생 (vision, rag, answer...)
    # 2. 실행 시간: 5~30초
    # 3. 중간에 실패 가능
    # 4. SSE로 스트리밍 필요
    pass
```

| LangGraph 특성 | Job 큐 필요성 |
|----------------|--------------|
| 장시간 실행 (5~30초) | HTTP 타임아웃 회피 |
| 노드별 이벤트 | SSE 스트리밍 |
| 실패 가능성 | 재시도 메커니즘 |
| Checkpointing | 상태 복구 |

### 5.2 아키텍처

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

### 5.3 흐름 상세

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

## 6. 구현 설계

### 6.1 디렉토리 구조

> **구현 완료**: scan/scan_worker 패턴 적용

```
apps/chat_worker/
├── main.py                    # Taskiq 앱 엔트리포인트
├── presentation/
│   └── tasks/
│       └── process_task.py    # @broker.task 정의
├── application/
│   └── pipeline/
│       └── graph.py           # LangGraph 정의
├── infrastructure/
│   ├── messaging/
│   │   └── event_publisher.py # Redis Streams (기존 패턴)
│   └── llm/
│       └── adapters.py        # LLM 클라이언트
└── setup/
    ├── config.py
    ├── broker.py              # Taskiq 브로커 설정
    └── dependencies.py
```

### 6.2 브로커 설정

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
    # 결과 저장 (선택적)
    RedisResultBackend(settings.redis_cache_url)
)
```

### 6.3 Task 정의

```python
# apps/chat_worker/presentation/tasks/process_task.py
from typing import Any

from chat_worker.setup.broker import broker
from chat_worker.setup.dependencies import (
    get_chat_graph,
    get_event_publisher,
)


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
    """LangGraph 채팅 파이프라인 실행.
    
    Args:
        job_id: 작업 ID (SSE 이벤트 키)
        session_id: 세션 ID (LangGraph thread_id)
        message: 사용자 메시지
        image_url: 이미지 URL (선택)
        location: 위치 정보 (선택)
        model: LLM 모델
    
    Returns:
        처리 결과 (answer, metadata)
    """
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
            "metadata": final_result.get("metadata", {}),
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

### 6.4 Chat API (제출)

```python
# apps/chat/presentation/http/controllers/chat.py
from fastapi import APIRouter, Depends
from pydantic import BaseModel, HttpUrl
import uuid

router = APIRouter(prefix="/chat", tags=["chat"])


class UserLocation(BaseModel):
    lat: float
    lon: float


class ChatRequest(BaseModel):
    session_id: str
    message: str
    image_url: HttpUrl | None = None
    location: UserLocation | None = None
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

### 6.5 Worker 실행

```bash
# 개발
taskiq worker chat_worker.setup.broker:broker --reload

# 프로덕션 (멀티프로세스)
taskiq worker chat_worker.setup.broker:broker --workers 4
```

---

## 7. Celery vs Taskiq 비교

### 7.1 scan_worker (Celery) 현황

```python
# 현재 scan_worker - Celery + Gevent
@celery_app.task(bind=True)
def classify_task(self, job_id: str, image_url: str):
    # 동기 코드 (Gevent로 비동기화)
    result = classify_image(image_url)
    return result
```

### 7.2 차이점

| 항목 | Celery (scan) | Taskiq (chat) |
|------|---------------|---------------|
| **asyncio** | ❌ (Gevent) | ✅ 네이티브 |
| **LangGraph** | △ 호환 문제 | ✅ 완벽 호환 |
| **async/await** | 불가 | ✅ |
| **브로커** | RabbitMQ | RabbitMQ (동일) |
| **성숙도** | 높음 | 중간 |

### 7.3 마이그레이션 필요성

```
scan_worker: Celery 유지 (기존 코드 안정)
chat_worker: Taskiq 신규 (LangGraph asyncio 필수)

향후 고려:
- scan_worker도 Taskiq로 마이그레이션 가능
- 점진적 전환 (브로커 공유)
```

---

## 8. 기존 인프라 통합

### 8.1 인프라 재사용

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

### 8.2 환경변수

```yaml
# Chat Worker
RABBITMQ_URL: amqp://eco2-rabbitmq:5672/eco2
REDIS_STREAMS_URL: redis://rfr-streams-redis:6379/0
REDIS_CACHE_URL: redis://rfr-cache-redis:6379/0

# LLM API Keys
OPENAI_API_KEY: ${OPENAI_API_KEY}
GEMINI_API_KEY: ${GEMINI_API_KEY}
ANTHROPIC_API_KEY: ${ANTHROPIC_API_KEY}
```

---

## 9. 배포

### 9.1 Dockerfile

```dockerfile
FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY apps/chat_worker ./chat_worker

# Taskiq Worker 실행
CMD ["taskiq", "worker", "chat_worker.setup.broker:broker", "--workers", "2"]
```

### 9.2 Kubernetes Deployment

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
            - name: REDIS_STREAMS_URL
              valueFrom:
                secretKeyRef:
                  name: chat-secret
                  key: redis-streams-url
          resources:
            requests:
              memory: "512Mi"
              cpu: "250m"
            limits:
              memory: "1Gi"
              cpu: "500m"
```

---

## 10. 테스트

### 10.1 단위 테스트

```python
import pytest
from taskiq import InMemoryBroker

from chat_worker.tasks.chat_task import process_chat_task


@pytest.fixture
def test_broker():
    """테스트용 인메모리 브로커."""
    return InMemoryBroker()


@pytest.mark.asyncio
async def test_process_chat_task(test_broker):
    """채팅 Task 테스트."""
    # Task 실행
    result = await process_chat_task.kiq(
        job_id="test-job",
        session_id="test-session",
        message="페트병 어떻게 버려?",
    )
    
    # 결과 대기
    task_result = await result.wait_result(timeout=60)
    
    assert task_result.is_err is False
    assert "answer" in task_result.return_value
```

### 10.2 통합 테스트

```python
@pytest.mark.asyncio
async def test_full_pipeline(docker_compose):
    """전체 파이프라인 통합 테스트."""
    from chat_worker.setup.broker import broker
    
    async with broker:
        result = await process_chat_task.kiq(
            job_id="integ-test",
            session_id="integ-session",
            message="유리병 분리수거 방법",
        )
        
        task_result = await result.wait_result(timeout=120)
        
        assert task_result.is_err is False
        assert len(task_result.return_value["answer"]) > 0
```

---

## 11. 결론

### 11.1 선택 근거

| 요구사항 | FastStream | Taskiq | 선택 |
|----------|------------|--------|------|
| Job 기반 스케일링 | △ | ✅ | Taskiq |
| asyncio + LangGraph | ✅ | ✅ | - |
| 결과 반환 | 별도 구현 | ✅ 내장 | Taskiq |
| 재시도/타임아웃 | 별도 구현 | ✅ 내장 | Taskiq |
| RabbitMQ 재사용 | ✅ | ✅ | - |
| 이벤트 버스 | ✅ 특화 | △ | 기존 Redis Streams |

### 11.2 최종 스택

```
┌─────────────────────────────────────────────────────────────┐
│  Eco² Chat 최종 스택                                        │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  Job 큐:      Taskiq + RabbitMQ (기존)                      │
│  파이프라인:   LangGraph (asyncio)                          │
│  상태 저장:   RedisSaver (rfr-cache-redis)                  │
│  이벤트 버스: Redis Streams (rfr-streams-redis, 기존)       │
│  API:        FastAPI                                        │
│                                                             │
│  ✅ 기존 인프라 100% 재사용                                  │
│  ✅ asyncio 네이티브 (LangGraph 완벽 호환)                   │
│  ✅ Job 재시도/타임아웃 내장                                 │
│  ✅ scan_worker와 브로커 공유                                │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## 참고 자료

- [Taskiq GitHub](https://github.com/taskiq-python/taskiq) (⭐ 1.8K)
- [Taskiq Documentation](https://taskiq-python.github.io/)
- [taskiq-aio-pika (RabbitMQ)](https://github.com/taskiq-python/taskiq-aio-pika)
- [FastStream GitHub](https://github.com/ag2ai/faststream) (⭐ 4.9K) - 이벤트 스트림 참고

