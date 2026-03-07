# 이코에코(Eco²) Agent #13: Infrastructure Layer

> Chat Worker의 Infrastructure Layer 설계 — 외부 시스템 연동과 의사결정 기록

| 항목 | 값 |
|-----|-----|
| **작성일** | 2026-01-14 |
| **커밋** | `32af7717` |

---

## 1. 개요

### 1.1 Infrastructure Layer의 역할

Clean Architecture에서 Infrastructure Layer는 **외부 세계와의 접점**입니다.

```
┌─────────────────────────────────────────────────────────────┐
│                      Chat Worker                            │
│  ┌───────────────────────────────────────────────────────┐  │
│  │             Application Layer (Services)              │  │
│  │                                                       │  │
│  │   IntentClassifier  AnswerGenerator  HumanInteraction │  │
│  │           │               │               │           │  │
│  │           ▼               ▼               ▼           │  │
│  │   ┌─────────────────────────────────────────────────┐ │  │
│  │   │                   Ports (추상)                   │ │  │
│  │   │  LLMClientPort  ProgressNotifierPort  Retriever │ │  │
│  │   └──────────────────────┬──────────────────────────┘ │  │
│  └──────────────────────────┼────────────────────────────┘  │
│                             │                               │
│  ┌──────────────────────────▼────────────────────────────┐  │
│  │            Infrastructure Layer (구현체)              │  │
│  │                                                       │  │
│  │  ┌─────────────┐  ┌───────────────┐  ┌─────────────┐  │  │
│  │  │   events/   │  │ integrations/ │  │ retrieval/  │  │  │
│  │  │  (Redis)    │  │   (gRPC)      │  │   (JSON)    │  │  │
│  │  └──────┬──────┘  └───────┬───────┘  └──────┬──────┘  │  │
│  │         │                 │                 │         │  │
│  │  ┌──────▼──────┐  ┌───────▼───────┐  ┌──────▼──────┐  │  │
│  │  │    llm/     │  │ interaction/  │  │orchestration│  │  │
│  │  │ (OpenAI등)  │  │   (Redis)     │  │ (LangGraph) │  │  │
│  │  └─────────────┘  └───────────────┘  └─────────────┘  │  │
│  └───────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

### 1.2 디렉토리 구조

```
apps/chat_worker/infrastructure/
├── events/                     # 이벤트 발행
│   ├── redis_progress_notifier.py      # SSE 진행 이벤트
│   └── redis_stream_domain_event_bus.py # 시스템 이벤트
│
├── integrations/               # 외부 도메인 연동
│   ├── character/              # Character API gRPC
│   │   ├── grpc_client.py
│   │   └── proto/
│   └── location/               # Location API gRPC
│       ├── grpc_client.py
│       └── proto/
│
├── interaction/                # Human-in-the-Loop 상태
│   ├── redis_input_requester.py
│   └── redis_interaction_state_store.py
│
├── llm/                        # LLM 클라이언트
│   ├── clients/
│   │   ├── openai_client.py
│   │   └── gemini_client.py
│   └── policies/
│       └── default_policy.py
│
├── orchestration/              # LangGraph 워크플로우
│   └── langgraph/
│       ├── factory.py          # 그래프 생성
│       ├── checkpointer.py     # 체크포인팅
│       └── nodes/              # 노드 구현체
│
├── retrieval/                  # RAG 검색
│   └── local_asset_retriever.py
│
└── assets/                     # 정적 에셋
    └── data/source/            # 폐기물 규정 JSON
```

---

## 2. Events — Redis Streams 이벤트 발행

### 2.1 문제: 단일 EventPublisher의 책임 과다

초기 설계에서는 모든 이벤트를 하나의 `EventPublisher`가 처리했습니다.

```python
# 초기 설계 (문제)
class EventPublisher:
    async def publish_stage(...)     # SSE UI 이벤트
    async def publish_token(...)     # 토큰 스트리밍
    async def publish_status(...)    # 시스템 이벤트
    async def publish_completed(...) # 완료 이벤트
```

**문제점:**
- SSE 이벤트와 시스템 이벤트가 혼재
- 실패 모드가 다름 (SSE는 손실 허용, 시스템은 보장 필요)
- 테스트 시 관심사 분리 어려움

### 2.2 해결: Progress Notifier vs Domain Event Bus

| 구분 | ProgressNotifier | DomainEventBus |
|-----|------------------|----------------|
| 용도 | SSE/UI 표시 | 시스템 상태 변경 |
| 전달 보장 | Best-effort (손실 허용) | At-least-once |
| 소비자 | Frontend (SSE) | 내부 시스템 |
| Redis 구조 | Streams + Pub/Sub | Streams (Consumer Group) |

```
┌──────────────────────────────────────────────────────────┐
│                     Application Service                  │
│                            │                             │
│            ┌───────────────┴───────────────┐             │
│            ▼                               ▼             │
│   ProgressNotifierPort              DomainEventBusPort   │
│   (SSE 진행 이벤트)                 (시스템 이벤트)      │
│            │                               │             │
└────────────┼───────────────────────────────┼─────────────┘
             │                               │
             ▼                               ▼
┌────────────────────────┐    ┌────────────────────────────┐
│  RedisProgressNotifier │    │ RedisStreamDomainEventBus  │
│                        │    │                            │
│  chat:events:{task_id} │    │  domain:events (Stream)    │
│  → event_router        │    │  → Consumer Group          │
│  → Redis Pub/Sub       │    └────────────────────────────┘
│  → SSE Gateway         │
└────────────────────────┘
```

### 2.3 구현

**ProgressNotifierPort (SSE용):**

```python
# application/ports/events/progress_notifier.py
class ProgressNotifierPort(ABC):
    @abstractmethod
    async def notify_stage(
        self, task_id: str, stage: str, status: str,
        progress: int | None, result: dict | None, message: str | None
    ) -> str: ...
    
    @abstractmethod
    async def notify_token(self, task_id: str, content: str) -> str: ...
    
    @abstractmethod
    async def notify_needs_input(
        self, task_id: str, input_type: str, message: str, timeout: int
    ) -> str: ...
```

**RedisProgressNotifier (구현체):**

```python
# infrastructure/events/redis_progress_notifier.py
class RedisProgressNotifier(ProgressNotifierPort):
    def __init__(self, redis: Redis, stream_prefix: str = "chat:events"):
        self._redis = redis
        self._stream_prefix = stream_prefix
    
    async def notify_stage(self, task_id: str, stage: str, ...):
        stream_name = f"{self._stream_prefix}:{task_id}"
        event_id = str(uuid4())
        
        await self._redis.xadd(
            stream_name,
            {"event_type": "stage_update", "payload": json.dumps(payload)},
            maxlen=1000
        )
        return event_id
```

---

## 3. Checkpointer — 세션 영속성

### 3.1 문제: RedisSaver의 TTL 한계

LangGraph 기본 `RedisSaver`는 TTL 기반으로 동작합니다.

```python
# 기본 RedisSaver (문제)
saver = RedisSaver.from_conn_info(redis_url)
# 기본 TTL: 1시간 → 세션 만료
```

**문제점:**
- Cursor처럼 장기 세션 불가
- TTL 연장 없이 대화 컨텍스트 손실
- 사용자가 며칠 후 돌아와도 이어서 대화 불가

### 3.2 선택지 비교

| 방식 | 영속성 | 읽기 속도 | 복잡도 |
|-----|-------|----------|-------|
| RedisSaver (TTL) | ❌ 1시간 | ~1ms | 낮음 |
| PostgresSaver | ✅ 영구 | ~10ms | 중간 |
| **Cache-Aside** | ✅ 영구 | ~1ms | 높음 |

### 3.3 해결: Cache-Aside 패턴

Redis를 L1 캐시, PostgreSQL을 L2 영속 저장소로 사용합니다.

```
┌──────────────────────────────────────────────────────────┐
│                   CachedPostgresSaver                    │
│                                                          │
│   PUT (저장)                      GET (조회)             │
│       │                               │                  │
│       ▼                               ▼                  │
│   ┌───────┐                     ┌──────────┐             │
│   │ Redis │◄── Write-Through ──│  Check   │             │
│   │  (L1) │                     │   L1?    │             │
│   └───────┘                     └────┬─────┘             │
│       │                              │                   │
│       │ async                   ┌────┴────┐              │
│       ▼                         │ HIT     │ MISS         │
│   ┌────────────┐                ▼         ▼              │
│   │ PostgreSQL │◄───────  [Return]  [Query L2]           │
│   │    (L2)    │                         │               │
│   └────────────┘                         ▼               │
│                                    [Populate L1]         │
│                                         │                │
│                                         ▼                │
│                                    [Return]              │
└──────────────────────────────────────────────────────────┘
```

**구현:**

```python
# infrastructure/orchestration/langgraph/checkpointer.py
class CachedPostgresSaver(BaseCheckpointSaver):
    def __init__(self, postgres_saver: PostgresSaver, redis: Redis):
        self._pg = postgres_saver
        self._redis = redis
        self._ttl = 3600  # L1 캐시 TTL
    
    async def aget(self, config: RunnableConfig) -> Checkpoint | None:
        thread_id = config["configurable"]["thread_id"]
        cache_key = f"checkpoint:{thread_id}"
        
        # L1 체크
        cached = await self._redis.get(cache_key)
        if cached:
            return Checkpoint.model_validate_json(cached)
        
        # L2 폴백
        checkpoint = await self._pg.aget(config)
        if checkpoint:
            # L1 채우기
            await self._redis.setex(
                cache_key, self._ttl, checkpoint.model_dump_json()
            )
        return checkpoint
    
    async def aput(self, config: RunnableConfig, checkpoint: Checkpoint) -> None:
        # Write-Through: L1 + L2 동시 저장
        thread_id = config["configurable"]["thread_id"]
        cache_key = f"checkpoint:{thread_id}"
        
        await self._redis.setex(cache_key, self._ttl, checkpoint.model_dump_json())
        await self._pg.aput(config, checkpoint)
```

### 3.4 왜 Cache-Aside인가?

| 선택지 | 장점 | 단점 |
|-------|------|------|
| Redis Only | 빠름 | TTL 후 손실 |
| PostgreSQL Only | 영속 | 매 요청 DB 쿼리 |
| **Cache-Aside** | 빠름 + 영속 | 구현 복잡 |

**결론:** 장기 세션 지원 + 빠른 응답 = Cache-Aside

---

## 4. Interaction — Human-in-the-Loop 상태 관리

### 4.1 문제: Blocking Wait는 안티패턴

초기 설계에서 `InputWaiterPort`가 직접 대기했습니다.

```python
# 초기 설계 (문제)
class InputWaiterPort(ABC):
    async def wait_for_input(self, job_id: str) -> HumanInputResponse:
        # Redis Pub/Sub 구독 + 블로킹 대기
        # ❌ 타임아웃 시 리소스 점유
```

**문제점:**
- Application Layer에 Blocking I/O 로직
- 테스트 어려움 (타임아웃 모킹 복잡)
- 리소스 점유 (Worker 스레드 블로킹)

### 4.2 해결: 상태 기반 재개 패턴

"대기"를 버리고 "상태 저장 + 재개"로 전환합니다.

```
기존: Node → 대기(블로킹) → 응답 → 계속
개선: Node → 상태 저장 → 종료 → (Frontend 입력) → 재개
```

**Port 분리:**

```python
# InputRequesterPort: 요청 발행만
class InputRequesterPort(ABC):
    @abstractmethod
    async def request_input(self, job_id: str, input_type: InputType, ...) -> str:
        """needs_input 이벤트 발행, 대기 없음"""
    
    @abstractmethod
    async def save_waiting_state(self, job_id: str, state: dict, resume_node: str):
        """파이프라인 상태 스냅샷 저장"""

# InteractionStateStorePort: 상태 저장/조회
class InteractionStateStorePort(ABC):
    @abstractmethod
    async def save_pending_request(self, job_id: str, request: HumanInputRequest): ...
    
    @abstractmethod
    async def get_pending_request(self, job_id: str) -> HumanInputRequest | None: ...
```

**흐름:**

```
┌────────────────────────────────────────────────────────────┐
│  1. Location Subagent                                      │
│     위치 없음 감지 → HumanInputService.request_location()  │
│                            │                               │
│                            ▼                               │
│  2. InputRequesterPort.request_input()                     │
│     → needs_input SSE 이벤트 발행                          │
│                            │                               │
│                            ▼                               │
│  3. InputRequesterPort.save_waiting_state()                │
│     → 파이프라인 상태 + resume_node 저장                   │
│                            │                               │
│                            ▼                               │
│  4. Node 종료 (상태: waiting_human)                        │
│                                                            │
│  ─────────── (Frontend에서 위치 수집) ───────────          │
│                                                            │
│  5. POST /chat/{job_id}/input                              │
│     → InteractionStateStorePort.get_pending_request()      │
│     → 파이프라인 재개 (resume_node부터)                    │
└────────────────────────────────────────────────────────────┘
```

---

## 5. LLM Clients — 순수 호출 vs 정책 분리

### 5.1 문제: 클라이언트에 비즈니스 로직 혼재

초기 설계에서 LLM 클라이언트가 의도 분류, 답변 생성까지 담당했습니다.

```python
# 초기 설계 (문제)
class OpenAIClient:
    async def classify_intent(self, message: str) -> str:
        # 프롬프트 구성 + API 호출 + 파싱
    
    async def generate_answer(self, prompt: str, context: dict) -> str:
        # 시스템 프롬프트 + API 호출
```

**문제점:**
- 인프라 계층에 비즈니스 로직 (프롬프트 템플릿)
- 모델 교체 시 프롬프트도 함께 교체해야 함
- 리트라이 정책이 클라이언트마다 다름

### 5.2 해결: LLM Client vs LLM Policy 분리

| 구분 | LLMClientPort | LLMPolicyPort |
|-----|---------------|---------------|
| 책임 | 순수 API 호출 | 프롬프트, 모델 선택, 리트라이 |
| 계층 | Infrastructure | Application (Policy) |
| 테스트 | Mock 쉬움 | 정책 단위 테스트 |

```
┌──────────────────────────────────────────────────────────┐
│                    Application Layer                     │
│                                                          │
│   IntentClassifier ─────┬───────▶ LLMPolicyPort          │
│                         │         (모델 선택, 프롬프트)  │
│                         │                │               │
│                         │                ▼               │
│                         └───────▶ LLMClientPort          │
│                                   (순수 호출)            │
└──────────────────────────────────────────────────────────┘
                                         │
┌────────────────────────────────────────▼─────────────────┐
│                  Infrastructure Layer                    │
│                                                          │
│   ┌────────────────┐  ┌────────────────┐                 │
│   │ OpenAIClient   │  │  GeminiClient  │                 │
│   │ generate()     │  │  generate()    │                 │
│   │ generate_stream│  │  generate_stream                 │
│   └────────────────┘  └────────────────┘                 │
└──────────────────────────────────────────────────────────┘
```

**LLMClientPort (순수 호출):**

```python
# application/ports/llm/llm_client.py
class LLMClientPort(ABC):
    @abstractmethod
    async def generate(
        self, prompt: str, system_prompt: str | None = None,
        context: dict | None = None, max_tokens: int | None = None,
        temperature: float | None = None
    ) -> str: ...
    
    @abstractmethod
    async def generate_stream(
        self, prompt: str, system_prompt: str | None = None, context: dict | None = None
    ) -> AsyncIterator[str]: ...
```

**LLMPolicyPort (정책):**

```python
# application/ports/llm/llm_policy.py
class LLMPolicyPort(ABC):
    @abstractmethod
    def select_model(self, task_type: TaskType, tier: ModelTier) -> str: ...
    
    @abstractmethod
    def format_prompt(self, template_name: str, **kwargs) -> str: ...
    
    @abstractmethod
    async def execute_with_retry(self, operation: Callable, max_retries: int) -> T: ...
```

---

## 6. Integrations — gRPC 외부 도메인 연동

### 6.1 선택: HTTP vs gRPC vs Queue

| 방식 | 지연 | 타입 안전 | asyncio 호환 |
|-----|------|----------|--------------|
| HTTP/JSON | ~10ms | 런타임 | ✅ |
| **gRPC** | ~1-3ms | 컴파일 | ✅ (grpc.aio) |
| Celery Queue | 가변 | ❌ | ❌ (블로킹) |

**선택: gRPC** — LangGraph asyncio와 자연스러운 통합

### 6.2 선택: Direct Call vs Queue-based

| 항목 | Direct Call | Queue-based |
|-----|-------------|-------------|
| 호출 | `await grpc.call()` | `task.delay()` + `.get()` |
| 결과 수신 | non-blocking | 블로킹 or 폴링 |
| LangGraph 호환 | ✅ | ❌ (이벤트 루프 충돌) |
| 적합 패턴 | 즉시 응답 필요 | Fire & Forget |

```python
# Direct Call: non-blocking (LangGraph 호환)
async def character_subagent(state):
    character = await character_client.get_character_by_waste_category("플라스틱")
    return {**state, "character_context": character}

# Queue-based: 블로킹 (LangGraph 부적합)
async def character_subagent(state):
    task = character_task.delay("플라스틱")
    result = task.get()  # ❌ 이벤트 루프 블로킹
```

**선택: Direct Call (gRPC)**

### 6.3 구현: Port/Adapter + DI

**Port 정의:**

```python
# application/integrations/character/ports/character_client.py
@dataclass(frozen=True)
class CharacterDTO:
    name: str
    type_label: str
    dialog: str
    match_label: str

class CharacterClientPort(ABC):
    @abstractmethod
    async def get_character_by_waste_category(
        self, waste_category: str
    ) -> CharacterDTO | None: ...
```

**Adapter 구현:**

```python
# infrastructure/integrations/character/grpc_client.py
class CharacterGrpcClient(CharacterClientPort):
    def __init__(self, host: str = "character-api", port: int = 50051):
        self._address = f"{host}:{port}"
        self._channel: grpc.aio.Channel | None = None
    
    async def _get_stub(self):
        if self._channel is None:
            self._channel = grpc.aio.insecure_channel(self._address)
            self._stub = CharacterServiceStub(self._channel)
        return self._stub
    
    async def get_character_by_waste_category(self, waste_category: str):
        stub = await self._get_stub()
        request = GetByMatchRequest(match_label=waste_category)
        response = await stub.GetCharacterByMatch(request)
        
        if not response.found:
            return None
        
        return CharacterDTO(
            name=response.character_name,
            type_label=response.character_type,
            dialog=response.character_dialog,
            match_label=response.match_label,
        )
```

---

## 7. Retrieval — 로컬 에셋 검색

### 7.1 설계 결정: scan과 동일한 에셋 복사

**선택지:**
1. scan_worker 에셋 공유 (심볼릭 링크)
2. API로 scan에서 조회
3. **chat_worker에 복사** ✅

**선택 이유:**
- 독립 배포 (scan 장애 시에도 chat 동작)
- 에셋 버전 독립 관리
- Kubernetes Pod 격리 원칙

```
apps/
├── scan_worker/infrastructure/assets/data/source/
│   ├── 재활용폐기물.json
│   └── 음식물류폐기물.json
│
└── chat_worker/infrastructure/assets/data/source/
    ├── 재활용폐기물.json     # 복사
    └── 음식물류폐기물.json   # 복사
```

### 7.2 구현

```python
# infrastructure/retrieval/local_asset_retriever.py
class LocalAssetRetriever(RetrieverPort):
    def __init__(self, assets_path: Path | None = None):
        if assets_path is None:
            self._assets_path = Path(__file__).parent.parent / "assets/data/source"
        self._data: dict[str, dict] = {}
        self._load_data()
    
    def search(self, category: str, subcategory: str | None = None):
        # 직접 매칭
        for key, data in self._data.items():
            if category in key:
                return {"key": key, "category": category, "data": data}
        
        # 약어 매핑 (재활용 → 재활용폐기물)
        category_map = {
            "재활용": "재활용폐기물",
            "일반": "일반종량제폐기물",
            "음식물": "음식물류폐기물",
        }
        ...
```

---

## 8. Orchestration — LangGraph 워크플로우

### 8.1 Factory 패턴

DI를 통해 모든 의존성을 주입받아 그래프를 생성합니다.

```python
# infrastructure/orchestration/langgraph/factory.py
def create_chat_graph(
    llm: LLMClientPort,
    retriever: RetrieverPort,
    event_publisher: ProgressNotifierPort,
    character_client: CharacterClientPort | None = None,
    location_client: LocationClientPort | None = None,
    input_requester: InputRequesterPort | None = None,
    checkpointer: BaseCheckpointSaver | None = None,
) -> StateGraph:
    
    # 노드 생성 (DI)
    intent_node = create_intent_node(llm, event_publisher)
    rag_node = create_rag_node(retriever, event_publisher)
    answer_node = create_answer_node(llm, event_publisher)
    
    # Subagent 노드
    if character_client:
        character_node = create_character_subagent_node(llm, character_client, event_publisher)
    else:
        character_node = passthrough_node
    
    # 그래프 구성
    graph = StateGraph(dict)
    graph.add_node("intent", intent_node)
    graph.add_node("waste_rag", rag_node)
    graph.add_node("character", character_node)
    graph.add_node("location", location_node)
    graph.add_node("answer", answer_node)
    
    # 라우팅
    graph.set_entry_point("intent")
    graph.add_conditional_edges("intent", route_by_intent, {...})
    
    # 체크포인터 (멀티턴 세션)
    if checkpointer:
        return graph.compile(checkpointer=checkpointer)
    return graph.compile()
```

### 8.2 노드는 Thin Wrapper

노드는 오케스트레이션만 담당, 비즈니스 로직은 Service에 위임합니다.

```python
# infrastructure/orchestration/langgraph/nodes/intent_node.py
def create_intent_node(llm: LLMClientPort, event_publisher: ProgressNotifierPort):
    # Service 인스턴스 (비즈니스 로직 위임)
    classifier = IntentClassifier(llm)
    
    async def intent_node(state: dict) -> dict:
        # 1. 이벤트 발행 (오케스트레이션)
        await event_publisher.notify_stage(task_id=state["job_id"], stage="intent", ...)
        
        # 2. Service 호출 (비즈니스 로직 위임)
        chat_intent = await classifier.classify(state["message"])
        
        # 3. state 업데이트 (오케스트레이션)
        return {**state, "intent": chat_intent.intent.value}
    
    return intent_node
```

---

## 9. 테스트 전략

### 9.1 Port Mock으로 독립 테스트

```python
# tests/unit/infrastructure/events/test_redis_progress_notifier.py
@pytest.fixture
def mock_redis():
    mock = AsyncMock()
    mock.xadd = AsyncMock(return_value="1234-0")
    return mock

@pytest.fixture
def notifier(mock_redis):
    return RedisProgressNotifier(mock_redis, stream_prefix="test:events")

@pytest.mark.asyncio
async def test_notify_stage(notifier, mock_redis):
    event_id = await notifier.notify_stage(
        task_id="job-123", stage="intent", status="started"
    )
    
    assert event_id is not None
    mock_redis.xadd.assert_called_once()
    
    stream_name = mock_redis.xadd.call_args[0][0]
    assert stream_name == "test:events:job-123"
```

### 9.2 테스트 커버리지

| 영역 | 테스트 수 | 커버리지 |
|-----|----------|---------|
| events/ | 10 | 100% |
| interaction/ | 13 | 100% |
| retrieval/ | 14 | 89% |
| integrations/character | 9 | 88% |
| integrations/location | 9 | 83% |
| **Total** | **55** | **88%+** |

---

## 10. 의사결정 요약

| 결정 | 선택 | 근거 |
|-----|------|------|
| 이벤트 분리 | Progress + Domain | 실패 모드 분리, 관심사 분리 |
| 체크포인팅 | Cache-Aside | 장기 세션 + 빠른 응답 |
| HITL 패턴 | 상태 기반 재개 | 블로킹 없음, 테스트 용이 |
| LLM 분리 | Client + Policy | 관심사 분리, 교체 용이 |
| 외부 연동 | gRPC Direct | asyncio 호환, 낮은 지연 |
| 에셋 관리 | 복사 | 독립 배포, Pod 격리 |
| 노드 설계 | Thin Wrapper | 로직은 Service에 위임 |

---

## 11. 파일 구조 최종

```
apps/chat_worker/infrastructure/
├── events/
│   ├── __init__.py
│   ├── redis_progress_notifier.py       # ProgressNotifierPort 구현
│   └── redis_stream_domain_event_bus.py # DomainEventBusPort 구현
│
├── integrations/
│   ├── character/
│   │   ├── grpc_client.py               # CharacterClientPort 구현
│   │   └── proto/                       # protobuf 정의
│   └── location/
│       ├── grpc_client.py               # LocationClientPort 구현
│       └── proto/
│
├── interaction/
│   ├── redis_input_requester.py         # InputRequesterPort 구현
│   └── redis_interaction_state_store.py # InteractionStateStorePort 구현
│
├── llm/
│   ├── clients/
│   │   ├── openai_client.py             # LLMClientPort 구현
│   │   └── gemini_client.py             # LLMClientPort 구현
│   └── policies/
│       └── default_policy.py            # LLMPolicyPort 구현
│
├── orchestration/
│   └── langgraph/
│       ├── factory.py                   # 그래프 생성
│       ├── checkpointer.py              # CachedPostgresSaver
│       └── nodes/                       # 노드 구현체
│
├── retrieval/
│   └── local_asset_retriever.py         # RetrieverPort 구현
│
└── assets/
    └── data/source/                     # 폐기물 규정 JSON
```

---

## 8. Chat - Event Router 정합성

### 8.1 Shard 기반 스트림 아키텍처

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  Chat Worker                                                                │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │  RedisProgressNotifier                                              │   │
│  │  - hash(job_id) % 4 → shard 결정                                    │   │
│  │  - XADD chat:events:{shard}                                         │   │
│  │  - CHAT_SHARD_COUNT=4 (환경 변수)                                   │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  Redis Streams                                                              │
│  ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌─────────┐                        │
│  │ :events │  │ :events │  │ :events │  │ :events │                        │
│  │   :0    │  │   :1    │  │   :2    │  │   :3    │                        │
│  └────┬────┘  └────┬────┘  └────┬────┘  └────┬────┘                        │
└───────┼────────────┼────────────┼────────────┼──────────────────────────────┘
        │            │            │            │
        └────────────┴────────────┴────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  Event Router                                                               │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │  StreamConsumer                                                     │   │
│  │  - XREADGROUP eventrouter                                           │   │
│  │  - stream_configs: [("scan:events", 4), ("chat:events", 4)]        │   │
│  │  - SHARD_COUNT=4, CHAT_SHARD_COUNT=4 (환경 변수)                    │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │  EventProcessor                                                     │   │
│  │  - chat:events:0 → chat:state:{job_id} (State KV)                  │   │
│  │  - PUBLISH sse:events:{job_id} (Pub/Sub)                           │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  Chat API                                                                   │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │  SSE Gateway                                                        │   │
│  │  - GET chat:state:{job_id} (재접속 복구)                            │   │
│  │  - SUBSCRIBE sse:events:{job_id} (실시간)                          │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │  GetJobStatusQuery                                                  │   │
│  │  - GET chat:state:{job_id} (State KV 조회)                         │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 8.2 환경 변수 정합성

| 컴포넌트 | 환경 변수 | 값 | 용도 |
|---------|----------|---|------|
| **chat_worker** | `CHAT_SHARD_COUNT` | 4 | hash(job_id) % 4 |
| **event_router** | `SHARD_COUNT` | 4 | scan:events shard 수 |
| **event_router** | `CHAT_SHARD_COUNT` | 4 | chat:events shard 수 |
| **scan_worker** | `SSE_SHARD_COUNT` | 4 | scan:events shard 수 |

### 8.3 이벤트 필드 정합성

```python
# chat_worker가 발행하는 이벤트 (Lua Script)
{
    "job_id": str,      # 작업 ID
    "stage": str,       # intent, rag, character, location, answer, done
    "status": str,      # started, completed, failed
    "seq": int,         # 단조증가 시퀀스 (멱등성)
    "ts": str,          # 타임스탬프
    "progress": str,    # 진행률 (선택)
    "result": str,      # JSON 결과 (선택)
    "message": str,     # UI 메시지 (선택)
}

# event_router가 사용하는 필드
# - job_id: State KV 키, Pub/Sub 채널 결정
# - seq: 순서 보장 및 멱등성
# - stage: 메트릭 라벨
```

### 8.4 스케일링 전략

```
┌───────────────────────────────────────────────────────────────┐
│  Shard 수: 고정 (4개)                                         │
│  - 해시 불일치 방지                                           │
│  - 미래 확장: 8개로 마이그레이션                              │
│                                                               │
│  Consumer (Pod) 수: 동적 (1~4개)                              │
│  - HPA/KEDA로 스케일링                                        │
│  - Consumer Group이 자동 분배                                 │
│                                                               │
│  Pod 1개: 모든 shard 처리                                     │
│  Pod 4개: 각 Pod이 1개 shard 처리 (최적)                      │
└───────────────────────────────────────────────────────────────┘
```

---

## 커밋 정보

**Commit**: `32af7717f05758f7bd777774b10f2019970ee2db`

```
feat(chat_worker): implement infrastructure layer adapters

Infrastructure Layer Components:

1. Events (Redis Streams):
   - RedisProgressNotifier: SSE progress events
   - RedisStreamDomainEventBus: System events with delivery guarantee

2. Checkpointer (Cache-Aside Pattern):
   - CachedPostgresSaver: Redis L1 + PostgreSQL L2
   - Long-term session support (vs RedisSaver TTL)

3. Interaction (HITL State):
   - RedisInputRequester: Event publishing without blocking
   - RedisInteractionStateStore: State snapshot for pipeline resume

4. LLM Clients:
   - OpenAILLMClient: GPT-5.2 series
   - GeminiLLMClient: Gemini 3 series
   - DefaultLLMPolicy: Model selection, prompt templates, retry

5. Integrations (gRPC):
   - CharacterGrpcClient: Character API integration
   - LocationGrpcClient: Location API integration

6. Retrieval:
   - LocalAssetRetriever: Waste disposal rules JSON search

7. Orchestration (LangGraph):
   - factory.py: Intent-routed workflow graph
   - nodes/: Thin wrapper nodes delegating to services

Design Decisions:
- Progress vs Domain event bus separation
- Cache-Aside for long-term sessions
- State-based resume instead of blocking wait
- LLM Client vs Policy separation
- gRPC Direct Call for asyncio compatibility
- Asset duplication for independent deployment
```

**Changed Files (65)**

주요 파일:
- `infrastructure/events/redis_progress_notifier.py`
- `infrastructure/events/redis_stream_domain_event_bus.py`
- `infrastructure/orchestration/langgraph/checkpointer.py`
- `infrastructure/orchestration/langgraph/factory.py`
- `infrastructure/interaction/redis_input_requester.py`
- `infrastructure/interaction/redis_interaction_state_store.py`
- `infrastructure/llm/clients/openai_client.py`
- `infrastructure/llm/clients/gemini_client.py`
- `infrastructure/llm/policies/default_policy.py`
- `infrastructure/integrations/character/grpc_client.py`
- `infrastructure/integrations/location/grpc_client.py`
- `infrastructure/retrieval/local_asset_retriever.py`
- `infrastructure/orchestration/langgraph/nodes/*.py`
- `infrastructure/assets/data/source/*.json` (폐기물 규정)
- `infrastructure/assets/prompts/*.txt` (프롬프트 템플릿)

