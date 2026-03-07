# Chat 서비스 구현 Phase 2: Application Layer 설계

> CQRS 패턴 적용, Commands · Queries · Services · DTOs · Ports

---

## 1. Application Layer란?

Clean Architecture에서 Application Layer는 **비즈니스 규칙의 조율자**입니다:

```
     의존성 방향: 외부 → 내부 (Port/Adapter로 역전)

외부 레이어 ═══════════════════════════════════
┌────────────────────┐    ┌────────────────────┐
│  Presentation      │    │  Infrastructure    │
│  (Controllers,     │    │  (LLM, Redis,      │
│   Tasks)           │    │   RabbitMQ)        │
└─────────┬──────────┘    └─────────┬──────────┘
          │                         │
          │   구현      Port를 구현 │
          ▼                         ▼
내부 레이어 ═══════════════════════════════════
┌─────────────────────────────────────────────┐
│           Application Layer                 │
│  ┌─────────┐ ┌──────────┐ ┌──────┐ ┌─────┐ │
│  │Commands │ │ Services │ │ DTOs │ │Ports│ │
│  └────┬────┘ └────┬─────┘ └──────┘ └──┬──┘ │
│       │           │                    ▲    │
│       └───────────┤    Infrastructure가 │    │
│                   │    Port를 구현     │    │
└───────────────────┼────────────────────┼────┘
                    │                    │
                    ▼ (최하위)           │
┌─────────────────────────────────────────────┐
│           Domain Layer                      │
│  Chat 고유: Intent, QueryComplexity (Enum)  │
│  재사용: DisposalRule(scan), Character(char)│
└─────────────────────────────────────────────┘
```

**의존성 역전 (DIP)**:
- Application은 Port(인터페이스)를 정의
- Infrastructure는 Port를 구현 (Adapter)
- Application은 Infrastructure를 모름 → **테스트 용이**

**Application Layer의 5가지 구성 요소 (CQRS):**

| 구성 요소 | 역할 | 예시 |
|----------|------|------|
| **Commands** | 상태 변경 (쓰기) | `SubmitChatCommand`, `ProcessChatCommand` |
| **Queries** | 상태 조회 (읽기) | `GetJobStatusQuery` |
| **Services** | 순수 비즈니스 로직 | `IntentClassifier` |
| **DTOs** | 계층 간 데이터 전송 | `ChatContext` |
| **Ports** | 외부 의존성 추상화 | `LLMPort`, `JobSubmitterPort` |

**CQRS (Command Query Responsibility Segregation):**

```
┌─────────────────────────────────────────────┐
│           Application Layer                 │
│                                             │
│   ┌─────────────┐     ┌─────────────┐       │
│   │  Commands   │     │   Queries   │       │
│   │ (쓰기/변경) │     │ (읽기/조회) │       │
│   └──────┬──────┘     └──────┬──────┘       │
│          │                   │              │
│          ▼                   ▼              │
│   ┌─────────────────────────────────┐       │
│   │    Services / Ports / DTOs      │       │
│   └─────────────────────────────────┘       │
└─────────────────────────────────────────────┘

장점:
- Command/Query 독립적으로 스케일링
- 읽기 최적화 (캐싱, 별도 DB)
- 복잡도 분산
```

---

## 2. Domain Layer는 어디에?

### 2.1 Chat Domain의 특수성

Chat 서비스는 **Orchestration + 경량 Domain**입니다:

```
일반적인 도메인 서비스:
┌─────────────────────────────────────────┐
│           Application Layer             │
│  Order → PriceCalculator → Discount     │
│          ↓                              │
│  ┌─────────────────────────────────┐    │
│  │        Domain Layer             │    │
│  │  Order, Product, Money, ...     │    │
│  │  복잡한 비즈니스 규칙 (많음)    │    │
│  └─────────────────────────────────┘    │
└─────────────────────────────────────────┘

Chat 서비스:
┌─────────────────────────────────────────┐
│           Application Layer             │
│  User Message                           │
│      ↓                                  │
│  Intent → RAG → LLM → Answer            │
│                                         │
│  ┌─────────────────────────────────┐    │
│  │  Domain Layer (경량)            │    │
│  │  Intent, QueryComplexity (Enum) │    │
│  │  ChatIntent (Value Object)      │    │
│  └─────────────────────────────────┘    │
└─────────────────────────────────────────┘
```

| 특성 | 도메인 중심 서비스 | Chat 서비스 |
|------|------------------|-------------|
| **핵심 로직** | 복잡한 비즈니스 규칙 | 외부 시스템 조율 |
| **Entities** | User, Order, Product | 없음 (상태 없음) |
| **Value Objects** | Money, Email | ChatIntent |
| **Enums** | OrderStatus | Intent, QueryComplexity |
| **Domain Services** | PriceCalculator | 없음 (LLM이 처리) |

### 2.2 Chat에도 Domain Layer가 필요한가?

**기존 도메인 현황:**
```
apps/scan/domain/
├── entities/scan_task.py
├── enums/waste_category.py, pipeline_stage.py
└── value_objects/disposal_rule.py, classification.py

apps/character/domain/
├── entities/character.py, character_ownership.py
├── enums/character.py
└── (match_label 기반 캐릭터 매칭 규칙)
```

**Chat 고유 도메인 개념:**

| 개념 | 설명 | Domain Layer? |
|-----|------|--------------|
| **Intent** | waste/character/location/general | ✅ Enum |
| **QueryComplexity** | simple/complex (Subagent 필요 여부) | ✅ Enum |
| **ChatIntent** | Intent + Complexity + Confidence | ✅ Value Object |
| DisposalRule | 분리배출 규칙 | ❌ scan 도메인 재사용 |
| Character | 캐릭터 정보 | ❌ character 도메인 재사용 |

### 2.3 Chat Domain Layer 구조

```
apps/chat_worker/
├── domain/                        # Chat 고유 개념
│   ├── enums/
│   │   ├── intent.py              # Intent Enum
│   │   └── query_complexity.py    # Simple/Complex
│   └── value_objects/
│       └── chat_intent.py         # Intent + Confidence VO
├── application/
│   └── chat/
│       └── services/
│           └── intent_classifier.py  # Domain 사용
```

**코드 예시:**

```python
# domain/enums/intent.py
from enum import Enum

class Intent(str, Enum):
    """사용자 질문 의도."""
    WASTE = "waste"           # 분리배출 질문
    CHARACTER = "character"   # 캐릭터 관련
    LOCATION = "location"     # 위치 기반
    GENERAL = "general"       # 일반 대화

class QueryComplexity(str, Enum):
    """질문 복잡도 - Subagent 분기 결정."""
    SIMPLE = "simple"   # 단일 의도 → 직접 응답
    COMPLEX = "complex" # 다중 단계 → Subagent
```

```python
# domain/value_objects/chat_intent.py
@dataclass(frozen=True)
class ChatIntent:
    """분류된 사용자 의도 (Immutable)."""
    intent: Intent
    complexity: QueryComplexity
    confidence: float = 1.0
    
    @property
    def needs_subagent(self) -> bool:
        return self.complexity == QueryComplexity.COMPLEX
```

**면접 질문**: "Domain Layer를 어떻게 설계했나요?"

> "Chat 서비스는 Orchestration이 주된 역할이지만, Intent와 QueryComplexity는 
> Chat 고유의 비즈니스 개념입니다. 이들을 Domain Layer에 Enum과 Value Object로 정의해
> Application Layer(IntentClassifier)에서 사용합니다.
> 
> DisposalRule과 Character는 각각 scan/character 도메인에 이미 정의되어 있으므로,
> Chat에서 중복 정의하지 않고 해당 도메인의 API/Worker를 Tool Calling으로 호출합니다."

---

## 3. chat vs chat_worker 분리

### 3.1 책임 분리 원칙

```
┌─────────────────────────────────────────────┐
│              chat (API)                      │
│  "얇게" - 요청 수신 + 작업 위임만            │
│                                              │
│  Commands: SubmitChatCommand                 │
│  Ports: JobSubmitterPort (enqueue 전용)      │
└─────────────────┬───────────────────────────┘
                  │ RabbitMQ
                  ▼
┌─────────────────────────────────────────────┐
│           chat_worker                        │
│  "두껍게" - 모든 비즈니스 로직               │
│                                              │
│  Services: IntentClassifier, ...             │
│  DTOs: ChatContext                           │
│  Ports: LLMPort, RetrieverPort, ...          │
└─────────────────────────────────────────────┘
```

**왜 분리하는가?**

| 측면 | chat (API) | chat_worker |
|------|-----------|-------------|
| **응답 시간** | <100ms 목표 | 2~30초 허용 |
| **스케일링** | 요청 수 기준 | LLM 처리량 기준 |
| **장애 격리** | API 다운 ≠ 파이프라인 중단 | Worker 다운 ≠ 요청 거부 |
| **이벤트 발행** | ✗ (제출만) | ✓ (source of truth) |

---

## 3. Commands: Use Case 진입점

### 3.1 SubmitChatCommand (API)

```python
class SubmitChatCommand:
    """채팅 작업 제출 Command.
    
    책임:
    - job_id 생성
    - JobSubmitter를 통해 Worker에 작업 전달
    - stream_url 반환
    
    책임 아님 (Worker에서 수행):
    - 이벤트 발행 (queued, progress, done)
    - 상태 관리
    """
    
    def __init__(self, job_submitter: JobSubmitterPort):
        self._job_submitter = job_submitter
    
    async def execute(self, request: SubmitChatRequest) -> SubmitChatResponse:
        # 1. Job ID 생성
        job_id = str(uuid4())
        
        # 2. Worker에 작업 제출
        await self._job_submitter.submit(
            job_id=job_id,
            session_id=request.session_id,
            message=request.message,
            ...
        )
        
        # 3. 응답 반환 (status: "submitted", NOT "queued")
        return SubmitChatResponse(
            job_id=job_id,
            stream_url=f"/api/v1/chat/{job_id}/events",
            status="submitted",
        )
```

**왜 `status: "submitted"`인가?**

```
문제: API가 "queued"를 반환하면?
  - Worker가 아직 작업을 수신하지 않았는데
  - 클라이언트는 "작업 시작됨"으로 착각

해결: API는 "submitted", Worker가 "queued" 발행
  - 실제로 Worker가 작업을 수신한 시점에 queued
  - 상태의 source of truth = Worker
```

### 4.2 Command 패턴의 장점

```python
# Controller (Presentation)
@router.post("/messages")
async def submit_chat(
    request: ChatMessageRequest,
    command: SubmitChatCommand = Depends(get_submit_command),
):
    return await command.execute(SubmitChatRequest(...))

# 테스트
async def test_submit_chat():
    mock_submitter = MockJobSubmitter()
    command = SubmitChatCommand(mock_submitter)
    
    result = await command.execute(request)
    
    assert mock_submitter.submit_called
    assert result.status == "submitted"
```

- **단일 책임**: 하나의 Use Case만 처리
- **테스트 용이**: Port를 mock으로 교체
- **의존성 명시**: 생성자에서 필요한 것만 받음

### 4.3 ProcessChatCommand (Worker)

```python
class ProcessChatCommand:
    """Chat 파이프라인 실행 Command (CQRS).
    
    책임:
    - 파이프라인 실행 조율 (상태 변경)
    - 시작/완료/실패 이벤트 발행
    - 결과 포맷팅
    """
    
    def __init__(
        self,
        pipeline: ChatPipelinePort,  # LangGraph 추상화
        event_publisher: EventPublisherPort,
    ):
        self._pipeline = pipeline
        self._event_publisher = event_publisher
    
    async def execute(self, request: ProcessChatRequest) -> ProcessChatResponse:
        # 1. queued 이벤트 발행
        await self._event_publisher.publish_stage_event(...)
        
        # 2. 파이프라인 실행
        result = await self._pipeline.ainvoke(initial_state)
        
        # 3. done 이벤트 발행
        await self._event_publisher.publish_stage_event(...)
        
        return ProcessChatResponse(...)
```

**왜 Command가 필요한가?**

```
문제: Task에서 직접 LangGraph 호출
  Task (Presentation) → LangGraph (Infrastructure)
  
  ⚠️ Application Layer가 건너뛰어짐
  ⚠️ 테스트 시 Taskiq 필요
  ⚠️ 이벤트 발행 로직이 Task에 노출

해결: Command로 분리
  Task (Presentation) → Command (Application) → LangGraph (Infrastructure)
  
  ✓ 계층 분리 명확
  ✓ Command 단독 테스트 가능
  ✓ 이벤트 발행 로직 캡슐화
```

**Task와 Command의 관계**:

```python
# Task (Presentation) - Taskiq에 종속
@broker.task(task_name="chat.process")
async def process_chat(job_id, session_id, message, ...):
    command = await get_process_chat_command()
    request = ProcessChatRequest(job_id, session_id, message, ...)
    response = await command.execute(request)
    return response.to_dict()

# Command (Application) - 프레임워크 독립
class ProcessChatCommand:
    async def execute(self, request): ...
```

---

## 4. Queries: 상태 조회 (CQRS)

### 4.1 GetJobStatusQuery (API)

```python
class GetJobStatusQuery:
    """작업 상태 조회 Query (CQRS).
    
    읽기 전용 작업:
    - Redis Streams에서 최신 이벤트 조회
    - 상태 변경 없음
    """
    
    def __init__(self, redis_client):
        self._redis = redis_client
    
    async def execute(self, job_id: str) -> JobStatusResponse:
        # Redis Streams에서 최신 이벤트 조회
        events = await self._redis.xrevrange(
            f"chat:events:{job_id}",
            count=1,
        )
        
        # 상태 매핑 및 반환
        return JobStatusResponse(
            job_id=job_id,
            status=...,
            progress=...,
            current_stage=...,
        )
```

### 5.2 Command vs Query 구분

| 측면 | Command | Query |
|------|---------|-------|
| **목적** | 상태 변경 (쓰기) | 상태 조회 (읽기) |
| **부작용** | 있음 (이벤트 발행) | 없음 |
| **반환값** | 실행 결과 | 조회 데이터 |
| **캐싱** | 불가 | 가능 |
| **예시** | `SubmitChatCommand` | `GetJobStatusQuery` |

```
Command 흐름:
  POST /chat/messages
    → SubmitChatCommand.execute()
    → JobSubmitter.submit()
    → RabbitMQ Queue
    → ProcessChatCommand.execute()
    → LangGraph Pipeline

Query 흐름:
  GET /chat/jobs/{job_id}/status
    → GetJobStatusQuery.execute()
    → Redis Streams 조회
    → 캐시 가능
```

---

## 5. Services: 순수 비즈니스 로직

### 4.1 IntentClassifier (Worker)

```python
@dataclass(frozen=True)
class IntentResult:
    """의도 분류 결과 (불변)."""
    intent: str
    is_complex: bool
    confidence: float = 1.0


class IntentClassifier:
    """의도 분류 서비스.
    
    순수 비즈니스 로직만 포함.
    LangGraph, FastAPI 등 프레임워크 의존성 없음.
    """
    
    def __init__(self, llm: LLMPort):
        self._llm = llm
    
    async def classify(self, message: str) -> IntentResult:
        # 1. LLM 호출
        intent_str = await self._llm.classify_intent(
            message=message,
            system_prompt=INTENT_CLASSIFIER_PROMPT,
        )
        
        # 2. 유효성 검증
        intent = intent_str.strip().lower()
        if intent not in VALID_INTENTS:
            intent = "general"
        
        # 3. 복잡도 판단
        is_complex = self._is_complex_query(message)
        
        # 4. 불변 결과 반환
        return IntentResult(intent=intent, is_complex=is_complex)
```

### 6.2 Services vs Nodes

```
LangGraph Node (Infrastructure):
  ┌─────────────────────────────────────┐
  │ async def intent_node(state):       │
  │   # 1. 이벤트 발행 (시작)            │
  │   await publisher.publish_stage()   │
  │                                     │
  │   # 2. 서비스 호출 (비즈니스 로직)   │
  │   result = await classifier.classify() │
  │                                     │
  │   # 3. state 업데이트              │
  │   return {**state, "intent": ...}  │
  └─────────────────────────────────────┘
                    │
                    │ 호출
                    ▼
Service (Application):
  ┌─────────────────────────────────────┐
  │ class IntentClassifier:            │
  │   async def classify(message):     │
  │     # 순수 비즈니스 로직            │
  │     # 프레임워크 의존성 없음         │
  │     return IntentResult(...)       │
  └─────────────────────────────────────┘
```

**왜 분리하는가?**

| 측면 | Node에 로직 | Node + Service 분리 |
|------|------------|-------------------|
| **테스트** | LangGraph 필요 | Service 단독 테스트 |
| **재사용** | Node 전용 | 다른 파이프라인에서도 사용 |
| **의존성** | infrastructure→application | application만 |

---

## 6. DTOs: 계층 간 데이터 전송

### 5.1 ChatContext (Worker 상태)

```python
@dataclass
class ChatContext:
    """Chat 파이프라인 컨텍스트.
    
    LangGraph State로 사용되며, 각 노드가 읽고 쓰는 데이터.
    """
    
    # === 필수 필드 (요청 시 전달) ===
    job_id: str
    session_id: str
    user_id: str
    message: str
    
    # === 선택 필드 (요청 시 선택) ===
    image_url: str | None = None
    user_location: dict[str, float] | None = None
    llm_provider: str = "openai"
    llm_model: str = "gpt-5.2-turbo"
    
    # === 파이프라인 결과 (노드가 채움) ===
    intent: str | None = None              # intent_node
    is_complex: bool = False               # intent_node
    classification_result: dict | None = None  # vision_node
    disposal_rules: dict | None = None     # rag_node
    tool_results: dict | None = None       # tool_node
    answer: str | None = None              # answer_node
    
    # === 메타데이터 ===
    latencies: dict[str, float] = field(default_factory=dict)
    token_usage: dict[str, int] = field(default_factory=dict)
```

### 7.2 Request/Response DTOs (API)

```python
# 요청 DTO
@dataclass
class SubmitChatRequest:
    session_id: str
    user_id: str
    message: str
    image_url: str | None = None
    user_location: dict[str, float] | None = None
    model: str | None = None

# 응답 DTO
@dataclass
class SubmitChatResponse:
    job_id: str
    session_id: str
    stream_url: str
    status: str  # "submitted"
```

### 7.3 결과 DTOs (Service 반환값)

```python
@dataclass(frozen=True)
class IntentResult:
    """불변 결과 객체.
    
    면접 포인트:
    Q: "Context가 mutable하면 추적/테스트가 어렵지 않나요?"
    A: "서비스 레벨에서는 불변 결과 객체를 반환합니다.
        노드에서 state에 병합할 때만 mutation이 발생하고,
        그 지점은 명확히 추적 가능합니다."
    """
    intent: str
    is_complex: bool
    confidence: float = 1.0
```

---

## 7. Ports: 외부 의존성 추상화

### 6.1 API Ports

```python
# chat/application/chat/ports/job_submitter.py
class JobSubmitterPort(ABC):
    """작업 제출 포트 (enqueue 전용)."""
    
    @abstractmethod
    async def submit(
        self, job_id: str, session_id: str, message: str, ...
    ) -> bool:
        """작업을 큐에 제출."""
        pass
```

**API에는 이 Port만 필요**:
- 이벤트 발행 ✗ (Worker의 책임)
- LLM 호출 ✗ (Worker의 책임)
- RAG 검색 ✗ (Worker의 책임)

### 8.2 Worker Ports

```python
# LLMPort - 자연어 생성
class LLMPort(ABC):
    async def generate(self, prompt, system_prompt, context) -> str
    async def generate_stream(self, ...) -> AsyncIterator[str]
    async def classify_intent(self, message, system_prompt) -> str
    async def generate_answer_stream(self, ...) -> AsyncIterator[str]

# RetrieverPort - RAG 검색
class RetrieverPort(ABC):
    def search(self, category, subcategory) -> dict | None
    def search_by_keyword(self, keyword, limit=3) -> list[dict]

# EventPublisherPort - SSE 이벤트
class EventPublisherPort(ABC):
    async def publish_stage_event(self, task_id, stage, status, ...) -> str
    async def publish_token_event(self, task_id, content) -> str
    async def publish_tool_event(self, task_id, action, ...) -> str
```

### 8.3 Port/Adapter 패턴의 이점

```
문제: LLM 제공자마다 API가 다름
┌─────────────────────────────────────────────┐
│ OpenAI: response.choices[0].message.content │
│ Gemini: response.text                       │
│ Anthropic: response.content[0].text         │
└─────────────────────────────────────────────┘

해결: Port로 추상화
              ┌────────┐
              │ LLMPort│  ← 인터페이스
              └────────┘
                  ▲
    ┌─────────────┼─────────────┐
    │             │             │
┌───────┐   ┌───────┐   ┌───────────┐
│OpenAI │   │Gemini │   │Anthropic  │
│Adapter│   │Adapter│   │Adapter    │
└───────┘   └───────┘   └───────────┘

# Service는 Port만 알면 됨
class IntentClassifier:
    def __init__(self, llm: LLMPort):  # 어떤 구현체든 OK
        ...
```

---

## 8. 디렉토리 구조

```
apps/chat/application/              # API (CQRS)
├── __init__.py
└── chat/
    ├── commands/
    │   └── submit_chat.py          # SubmitChatCommand
    ├── queries/                    # ← 읽기 작업
    │   └── get_job_status.py       # GetJobStatusQuery
    └── ports/
        └── job_submitter.py        # JobSubmitterPort

apps/chat_worker/application/       # Worker (CQRS)
├── __init__.py
└── chat/
    ├── commands/                   # ← 쓰기 작업
    │   └── process_chat.py         # ProcessChatCommand
    │                               # ChatPipelinePort
    ├── services/
    │   └── intent_classifier.py    # IntentClassifier
    ├── dto/
    │   └── chat_context.py         # ChatContext
    └── ports/
        ├── llm_client.py           # LLMPort
        ├── retriever.py            # RetrieverPort
        └── event_publisher.py      # EventPublisherPort
```

**CQRS 조립 위치**:

```
Task (Presentation)
      │
      ▼
  get_process_chat_command()  ← setup/dependencies.py
      │
      ├── ProcessChatCommand(pipeline, event_publisher)
      │       │
      │       └── ChatPipelinePort (LangGraph)
      │               │
      │               ├── LLMPort
      │               ├── RetrieverPort
      │               └── EventPublisherPort
      │
      └── Services는 LangGraph 노드에서 호출

Controller (Presentation)
      │
      ▼
  get_job_status_query()  ← setup/dependencies.py
      │
      └── GetJobStatusQuery(redis_client)
```

---

## 9. 면접 질문 대비

### Q1: "왜 CQRS를 적용했나요?"

```
문제:
  - 읽기(상태 조회)와 쓰기(파이프라인 실행)의 특성이 다름
  - 쓰기: 복잡한 비즈니스 로직, 이벤트 발행
  - 읽기: 단순 조회, 캐싱 가능

해결:
  - Command: 상태 변경 담당 (SubmitChatCommand, ProcessChatCommand)
  - Query: 상태 조회 담당 (GetJobStatusQuery)
  - 각각 독립적으로 최적화/스케일링 가능
```

### Q2: "Command와 Service의 차이는?"

```
Command:
  - CQRS 진입점 (Presentation에서 호출)
  - 여러 Service/Port 조율
  - 트랜잭션 경계

Service:
  - 단일 비즈니스 로직
  - 재사용 가능 (여러 Command에서 사용)
  - 순수 함수에 가까움
```

### Q3: "DTO가 너무 많지 않나요?"

```
Request DTO: 외부 입력 검증 + 변환
Response DTO: 외부 출력 포맷 정의
Context DTO: 내부 상태 전달
Result DTO: 서비스 결과 (불변)

각각의 목적이 다르므로 분리가 적절함.
한 DTO가 여러 역할을 하면 변경 이유가 여러 개가 됨.
```

### Q4: "API가 이벤트를 발행하면 안 되나요?"

```
가능하지만 권장하지 않음:

API가 queued 발행 → Worker가 아직 미수신 → 불일치
API가 error 발행 → Worker도 error 발행 → 중복

해결책: "상태 변경의 주체 = Worker"
API는 제출만, 모든 이벤트는 Worker가 발행
```

---

## 10. 다음 단계

Phase 3에서는 Port들의 **실제 구현체(Adapter)**를 작성합니다:

```
apps/chat/infrastructure/
────────────────────────────────────────
JobSubmitterPort → TaskiqJobSubmitter

apps/chat_worker/infrastructure/
────────────────────────────────────────
LLMPort          → OpenAILLMClient, GeminiLLMClient
RetrieverPort    → LocalJSONRetriever
EventPublisherPort → RedisEventPublisher
```

---

**작성일**: 2026-01-13  
**Phase**: 2/6 (Application Layer)
