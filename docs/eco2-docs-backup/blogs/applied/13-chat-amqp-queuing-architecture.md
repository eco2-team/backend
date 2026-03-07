# 이코에코(Eco²) Chat: AMQP 기반 비동기 큐잉 아키텍처

> Chat API → Chat Worker 간 메시지 큐잉 설계와 Taskiq 선택 이유

## 개요

Chat 서비스는 LLM 기반 대화형 AI입니다. 응답 생성에 수 초~수십 초가 소요되므로 **비동기 처리**가 필수입니다. 이 문서에서는 Chat API와 Chat Worker 간의 큐잉 아키텍처를 설명합니다.

---

## 전체 아키텍처

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        Client (Mobile/Web)                              │
└───────────────────────────────┬─────────────────────────────────────────┘
                                │ POST /chat
                                │ SSE /chat/{job_id}/events
                                ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                           Chat API (FastAPI)                            │
│  ┌──────────────────────────────────────────────────────────────────┐  │
│  │  Presentation Layer (HTTP)                                        │  │
│  │  └── POST /chat → SubmitChatCommand                              │  │
│  │  └── GET /chat/{id}/events → SSE Stream                          │  │
│  ├──────────────────────────────────────────────────────────────────┤  │
│  │  Application Layer                                                │  │
│  │  └── SubmitChatCommand: job_id 생성, 큐 발행                      │  │
│  │  └── GetJobStatusQuery: Redis Stream 읽기                        │  │
│  ├──────────────────────────────────────────────────────────────────┤  │
│  │  Infrastructure Layer                                             │  │
│  │  └── TaskiqJobSubmitter: RabbitMQ 발행                           │  │
│  │  └── RedisEventReader: SSE 이벤트 조회                           │  │
│  └──────────────────────────────────────────────────────────────────┘  │
└───────────────────────────────┬─────────────────────────────────────────┘
                                │
                    ┌───────────┴───────────┐
                    │                       │
                    ▼                       ▼
┌───────────────────────────┐   ┌───────────────────────────┐
│       RabbitMQ            │   │         Redis             │
│  ┌─────────────────────┐  │   │  ┌─────────────────────┐  │
│  │ Exchange: chat_tasks│  │   │  │ Stream: chat:events │  │
│  │ (direct)            │  │   │  │ :{job_id}           │  │
│  ├─────────────────────┤  │   │  │                     │  │
│  │ Queue: chat.process │  │   │  │ - stage: intent     │  │
│  │ - TTL: 1h           │  │   │  │ - stage: rag        │  │
│  │ - DLX: dlx          │  │   │  │ - stage: answer     │  │
│  └─────────────────────┘  │   │  │ - delta: "..."      │  │
│  ┌─────────────────────┐  │   │  └─────────────────────┘  │
│  │ DLQ: dlq.chat.process│ │   │                           │
│  └─────────────────────┘  │   │  Key: chat:result:{id}    │
└───────────────────────────┘   └───────────────────────────┘
                    │
                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                        Chat Worker (Taskiq)                             │
│  ┌──────────────────────────────────────────────────────────────────┐  │
│  │  Presentation Layer (AMQP)                                        │  │
│  │  └── @broker.task("chat.process") → ProcessChatCommand           │  │
│  ├──────────────────────────────────────────────────────────────────┤  │
│  │  Application Layer                                                │  │
│  │  └── ProcessChatCommand: LangGraph 파이프라인 실행               │  │
│  │  └── IntentClassifier: 의도 분류 서비스                          │  │
│  ├──────────────────────────────────────────────────────────────────┤  │
│  │  Infrastructure Layer                                             │  │
│  │  ├── LangGraph: 오케스트레이션                                   │  │
│  │  ├── gRPC Clients: Character, Location                           │  │
│  │  ├── LLM Clients: OpenAI, Gemini                                 │  │
│  │  └── RedisEventPublisher: SSE 이벤트 발행                        │  │
│  └──────────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Celery vs Taskiq 선택

### 문제: Celery의 한계

Scan Worker는 Celery + gevent를 사용합니다. 하지만 Chat Worker에서는 다음 문제가 발생합니다:

| 항목 | Celery | 문제점 |
|------|--------|--------|
| **런타임** | sync (gevent 패치) | LangGraph는 asyncio 네이티브 |
| **await 지원** | ❌ 제한적 | `async def` 함수 내 `await` 불가 |
| **gRPC.aio** | ❌ 호환 이슈 | gevent monkey-patch 충돌 |

```python
# Celery에서의 문제
@app.task
def process_chat(job_id: str):
    # ❌ await 불가 - Celery는 sync
    result = await langgraph.ainvoke(state)  # SyntaxError
```

### 해결: Taskiq 선택

Taskiq는 asyncio 네이티브 태스크 큐입니다:

| 항목 | Taskiq | 장점 |
|------|--------|------|
| **런타임** | asyncio 네이티브 | LangGraph 완벽 호환 |
| **await 지원** | ✅ 완전 지원 | `async def` + `await` 자유롭게 사용 |
| **gRPC.aio** | ✅ 호환 | 비동기 gRPC 클라이언트 사용 가능 |
| **브로커** | RabbitMQ, Redis, NATS | 기존 인프라 재사용 |

```python
# Taskiq에서의 해결
@broker.task(task_name="chat.process")
async def process_chat(job_id: str):
    # ✅ await 가능 - Taskiq는 asyncio
    result = await langgraph.ainvoke(state)
```

---

## 메시지 플로우

### 1. 작업 제출 (Chat API)

```
┌─────────────────────────────────────────────────────────────┐
│                    Chat API                                 │
│                                                             │
│  POST /chat                                                 │
│  ─────────                                                  │
│  {                                                          │
│    "message": "플라스틱 분리수거 방법",                     │
│    "session_id": "sess_123"                                 │
│  }                                                          │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ SubmitChatCommand.execute()                         │   │
│  │                                                     │   │
│  │ 1. job_id = uuid4()                                │   │
│  │ 2. await job_submitter.submit(                     │   │
│  │       task_name="chat.process",                    │   │
│  │       job_id=job_id,                               │   │
│  │       session_id=session_id,                       │   │
│  │       message=message                              │   │
│  │    )                                               │   │
│  │ 3. return { "job_id": job_id }                     │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
│  Response: { "job_id": "abc-123" }                         │
└─────────────────────────────────────────────────────────────┘
```

### 2. 큐 발행 (RabbitMQ)

```
┌─────────────────────────────────────────────────────────────┐
│                    RabbitMQ                                 │
│                                                             │
│  Exchange: chat_tasks (direct)                              │
│  ────────────────────────────────                           │
│       │                                                     │
│       │ routing_key: chat.process                           │
│       ▼                                                     │
│  Queue: chat.process                                        │
│  ───────────────────                                        │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ Message Payload (JSON)                              │   │
│  │                                                     │   │
│  │ {                                                   │   │
│  │   "task_name": "chat.process",                     │   │
│  │   "args": [],                                      │   │
│  │   "kwargs": {                                      │   │
│  │     "job_id": "abc-123",                           │   │
│  │     "session_id": "sess_123",                      │   │
│  │     "message": "플라스틱 분리수거 방법",           │   │
│  │     "user_id": "user_456",                         │   │
│  │     "image_url": null,                             │   │
│  │     "user_location": null,                         │   │
│  │     "model": "gpt-5.2"                             │   │
│  │   }                                                │   │
│  │ }                                                  │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
│  Queue Settings:                                            │
│  - x-message-ttl: 3600000 (1시간)                          │
│  - x-dead-letter-exchange: dlx                              │
│  - x-dead-letter-routing-key: dlq.chat.process              │
└─────────────────────────────────────────────────────────────┘
```

### 3. 작업 처리 (Chat Worker)

```
┌─────────────────────────────────────────────────────────────┐
│                    Chat Worker                              │
│                                                             │
│  @broker.task("chat.process")                               │
│  async def process_chat(job_id, session_id, message, ...)   │
│  ─────────────────────────────────────────────────────────  │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ ProcessChatCommand.execute()                        │   │
│  │                                                     │   │
│  │ 1. await event_publisher.publish_stage(             │   │
│  │       job_id, "start", "processing"                │   │
│  │    )                                               │   │
│  │                                                     │   │
│  │ 2. result = await pipeline.ainvoke({               │   │
│  │       "job_id": job_id,                            │   │
│  │       "message": message,                          │   │
│  │       ...                                          │   │
│  │    })                                              │   │
│  │                                                     │   │
│  │    ┌─────────────────────────────────────────┐     │   │
│  │    │ LangGraph Pipeline                      │     │   │
│  │    │                                         │     │   │
│  │    │ START                                   │     │   │
│  │    │   │                                     │     │   │
│  │    │   ▼                                     │     │   │
│  │    │ intent ──┬── waste ──────┐              │     │   │
│  │    │          ├── character ──┤              │     │   │
│  │    │          ├── location ───┤              │     │   │
│  │    │          └── general ────┤              │     │   │
│  │    │                          ▼              │     │   │
│  │    │                       answer            │     │   │
│  │    │                          │              │     │   │
│  │    │                          ▼              │     │   │
│  │    │                        END              │     │   │
│  │    └─────────────────────────────────────────┘     │   │
│  │                                                     │   │
│  │ 3. await event_publisher.publish_stage(             │   │
│  │       job_id, "done", "completed", result          │   │
│  │    )                                               │   │
│  └─────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

### 4. SSE 이벤트 스트리밍

```
┌─────────────────────────────────────────────────────────────┐
│                    이벤트 플로우                             │
│                                                             │
│  Chat Worker                  Redis                Client   │
│  ───────────                  ─────                ──────   │
│       │                         │                    │      │
│       │ XADD chat:events:abc-123                    │      │
│       │ stage=intent status=processing              │      │
│       ├────────────────────────►│                    │      │
│       │                         │◄───────────────────┤      │
│       │                         │  GET /events (SSE) │      │
│       │                         │                    │      │
│       │                         │ event: stage       │      │
│       │                         │ data: {"stage":    │      │
│       │                         │   "intent",...}    │      │
│       │                         ├───────────────────►│      │
│       │                         │                    │      │
│       │ XADD chat:events:abc-123                    │      │
│       │ stage=rag status=processing                 │      │
│       ├────────────────────────►│                    │      │
│       │                         │ event: stage       │      │
│       │                         ├───────────────────►│      │
│       │                         │                    │      │
│       │ XADD chat:events:abc-123                    │      │
│       │ delta="플라스틱은..."                        │      │
│       ├────────────────────────►│                    │      │
│       │                         │ event: delta       │      │
│       │                         │ data: "플라스틱은."│      │
│       │                         ├───────────────────►│      │
│       │                         │                    │      │
│       │ XADD chat:events:abc-123                    │      │
│       │ stage=done result={...}                     │      │
│       ├────────────────────────►│                    │      │
│       │                         │ event: done        │      │
│       │                         ├───────────────────►│      │
│       │                         │                    │      │
└─────────────────────────────────────────────────────────────┘
```

---

## Taskiq Broker 설정

### broker.py

```python
"""AMQP/Taskiq Broker Configuration.

RabbitMQ Topology Operator가 Exchange/Queue를 미리 생성하므로
운영 환경에서는 declare_exchange=False로 기존 리소스를 재사용합니다.
"""

from taskiq_aio_pika import AioPikaBroker
from chat_worker.setup.config import get_settings

settings = get_settings()

# 운영 환경: Topology Operator가 미리 생성한 Exchange/Queue 사용
# 로컬 환경: declare_exchange=True로 자동 생성 (fallback)
_is_production = settings.environment in ("production", "staging", "dev")

broker = AioPikaBroker(
    url=settings.rabbitmq_url,
    declare_exchange=not _is_production,  # 운영 환경에서는 기존 사용
    exchange_name="chat_tasks",
    queue_name=settings.rabbitmq_queue,   # chat.process
)
```

### K8s Topology 매니페스트

```yaml
# workloads/rabbitmq/base/topology/exchanges.yaml
apiVersion: rabbitmq.com/v1beta1
kind: Exchange
metadata:
  name: chat-tasks
  namespace: rabbitmq
spec:
  name: chat_tasks
  type: direct
  durable: true
  vhost: eco2

---
# workloads/rabbitmq/base/topology/queues.yaml
apiVersion: rabbitmq.com/v1beta1
kind: Queue
metadata:
  name: chat-process-queue
  namespace: rabbitmq
spec:
  name: chat.process
  type: classic
  durable: true
  vhost: eco2
  arguments:
    x-dead-letter-exchange: dlx
    x-dead-letter-routing-key: dlq.chat.process
    x-message-ttl: 3600000  # 1시간

---
# workloads/rabbitmq/base/topology/bindings.yaml
apiVersion: rabbitmq.com/v1beta1
kind: Binding
metadata:
  name: chat-process-binding
  namespace: rabbitmq
spec:
  source: chat_tasks
  destination: chat.process
  destinationType: queue
  routingKey: chat.process
  vhost: eco2
```

---

## Clean Architecture 계층별 역할

### Chat API (요청 수신)

```
presentation/http/
└── controllers/chat.py
    └── POST /chat → SubmitChatCommand

application/chat/
├── commands/
│   └── submit_chat.py      # 작업 제출
└── queries/
    └── get_job_status.py   # 상태 조회

infrastructure/messaging/
└── job_submitter.py        # Taskiq 발행
```

### Chat Worker (작업 처리)

```
presentation/amqp/           # ← 프로토콜 명시
└── process_task.py
    └── @broker.task("chat.process")

application/chat/
├── commands/
│   └── process_chat.py     # 파이프라인 실행
└── services/
    └── intent_classifier.py

infrastructure/
├── grpc/                    # ← 4계층 내 proto
│   ├── proto/
│   │   ├── character_pb2.py
│   │   └── location_pb2.py
│   ├── character_grpc.py
│   └── location_grpc.py
├── langgraph/
│   └── factory.py
└── datasources/
    └── event_publisher.py
```

---

## 장애 처리

### Dead Letter Queue (DLQ)

```
┌─────────────────────────────────────────────────────────────┐
│                    장애 시나리오                             │
│                                                             │
│  chat.process 큐                                            │
│  ───────────────                                            │
│  Message 처리 실패                                          │
│       │                                                     │
│       │ 1. Worker 예외 발생                                 │
│       │ 2. 재시도 (max_retries=2)                          │
│       │ 3. 최종 실패                                        │
│       │                                                     │
│       ▼                                                     │
│  x-dead-letter-exchange: dlx                                │
│       │                                                     │
│       │ routing_key: dlq.chat.process                       │
│       ▼                                                     │
│  dlq.chat.process 큐                                        │
│  ──────────────────                                         │
│  - TTL: 7일 보관                                            │
│  - 수동 검토 후 재처리 또는 폐기                            │
└─────────────────────────────────────────────────────────────┘
```

### 재시도 설정

```python
@broker.task(
    task_name="chat.process",
    timeout=120,          # 2분 타임아웃
    retry_on_error=True,  # 에러 시 재시도
    max_retries=2,        # 최대 2회 재시도
)
async def process_chat(...):
    ...
```

---

## Scan vs Chat 큐잉 비교

| 항목 | Scan Worker | Chat Worker |
|------|-------------|-------------|
| **태스크 큐** | Celery | Taskiq |
| **브로커** | RabbitMQ | RabbitMQ |
| **런타임** | gevent (sync 패치) | asyncio (네이티브) |
| **LLM 호출** | sync (OpenAI/Gemini) | async (await) |
| **파이프라인** | Celery chain | LangGraph |
| **gRPC 호출** | ❌ 미사용 | ✅ grpc.aio |
| **이벤트 발행** | Redis Streams | Redis Streams |

---

## Infrastructure 구조 (Scan vs Chat)

```
=== Scan Worker ===                    === Chat Worker ===
infrastructure/                        infrastructure/
├── asset_loader/       ✅ 동일        ├── asset_loader/      ✅
├── assets/                            ├── assets/
│   ├── data/source/                   │   ├── data/source/
│   └── prompts/                       │   └── prompts/
├── retrievers/                        │       ├── intent_*.txt       🆕
├── persistence_redis/                 │       ├── waste_*.txt        🆕
└── llm/                               │       ├── character_*.txt    🆕
    ├── gemini/                        │       ├── location_*.txt     🆕
    └── gpt/                           │       ├── general_*.txt      🆕
                                       │       └── scan_*.txt (JSON용)
                                       ├── event_bus/         🆕 SSE 발행
                                       ├── grpc/              🆕 Subagent
                                       │   └── proto/
                                       ├── langgraph/         🆕 오케스트레이션
                                       │   └── nodes/
                                       └── llm/
                                           ├── gemini/
                                           └── openai/
```

---

## 프롬프트 구조

### Scan vs Chat 프롬프트 비교

| 용도 | Scan Worker | Chat Worker |
|------|-------------|-------------|
| **이미지 분류** | vision_classification.txt | vision_classification.txt ✅ 동일 |
| **텍스트 분류** | text_classification.txt | text_classification.txt ✅ 동일 |
| **답변 생성** | answer_generation.txt (JSON) | ❌ 사용 안함 |
| **의도 분류** | - | intent_classification.txt 🆕 |
| **폐기물 답변** | - | waste_answer.txt (SSE) 🆕 |
| **캐릭터 Subagent** | - | character_subagent.txt 🆕 |
| **위치 Subagent** | - | location_subagent.txt 🆕 |
| **일반 답변** | - | general_answer.txt (SSE) 🆕 |

### 이미지 파이프라인 비교

```
┌─────────────────────────────────────────────────────────────┐
│                    Scan (JSON 출력)                         │
│                                                             │
│  이미지 → Vision 분류 → RAG → Answer (JSON)                 │
│                              │                              │
│                              ▼                              │
│  {                                                          │
│    "disposal_steps": { "단계1": "...", "단계2": "..." },   │
│    "insufficiencies": ["라벨 제거 필요"],                   │
│    "user_answer": "페트병은..."  ← 이것만 필요              │
│  }                                                          │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│                    Chat (SSE 스트리밍)                       │
│                                                             │
│  이미지 → Vision 분류 → RAG → Answer (SSE)                  │
│           (동일)       (동일)    │                          │
│                                  ▼                          │
│  "페트병이네요! 투명 페트병 전용 수거함에..."               │
│  (토큰 단위 스트리밍)                                       │
│                                                             │
│  ❌ JSON 구조 없음                                          │
│  ✅ user_answer에 해당하는 내용만 자연어로                  │
└─────────────────────────────────────────────────────────────┘
```

### 핵심 차이

| 항목 | Scan | Chat |
|------|------|------|
| **분류 단계** | ✅ 동일 (Vision/Text Classification) | ✅ 동일 |
| **RAG 단계** | ✅ 동일 (규정 검색) | ✅ 동일 |
| **Answer 출력** | JSON (구조화) | **SSE 자연어** |
| **사용 정보** | disposal_steps + insufficiencies + user_answer | **user_answer만** |

---

## 결론

Chat 서비스는 **Taskiq + RabbitMQ** 조합으로 asyncio 네이티브 큐잉을 구현했습니다:

1. **Taskiq 선택**: LangGraph의 asyncio 네이티브 특성과 완벽 호환
2. **RabbitMQ 재사용**: 기존 인프라 활용, Topology Operator로 선언적 관리
3. **Redis Streams**: SSE 이벤트 스트리밍으로 실시간 진행 상황 전달
4. **Clean Architecture**: presentation/amqp로 프로토콜 명시, infrastructure/grpc로 gRPC 클라이언트 배치
5. **프롬프트 분리**: Scan(JSON)과 Chat(SSE) 목적별 프롬프트 구분

이 구조는 **asyncio 에코시스템**(LangGraph, grpc.aio, aiohttp)과 자연스럽게 통합되며, Celery의 동기 제약에서 벗어나 더 유연한 파이프라인 구성이 가능합니다.

