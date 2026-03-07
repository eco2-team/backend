# 이코에코(Eco²) Agent #7: Application Layer 리팩토링

> Port에 로직이 섞여 있던 구조를 Service + Port 조합으로 개선

[Agent #6](16-chat-interactive-sse.md)에서 Interactive SSE 패턴을 다뤘습니다. 이번 포스팅에서는 **Application Layer의 Port/Service 분리**와 **LangGraph 노드를 Thin Orchestration으로 유지하는 방법**을 설명합니다.

---

## 문제: Port에 비즈니스 로직 혼재

### 기존 구조의 문제점

```
┌──────────────────────────────────────────────┐
│         기존 구조 (Port에 로직 혼재)          │
├──────────────────────────────────────────────┤
│                                              │
│  LLMPort (Application)                       │
│  ├── generate()          # 순수 API 호출    │
│  ├── classify_intent()   # 비즈니스 로직 ❌  │
│  └── generate_answer()   # 비즈니스 로직 ❌  │
│                                              │
│  CharacterClientPort (Application)           │
│  ├── get_by_category()   # 순수 API 호출    │
│  └── to_answer_context() # 변환 로직 ❌      │
│                                              │
│  EventPublisherPort (Application)            │
│  ├── publish_stage()     # SSE 이벤트       │
│  ├── publish_token()     # SSE 이벤트       │
│  ├── publish_needs_input()  # SSE 이벤트    │
│  └── publish_job_completed() # 시스템 이벤트│
│                                              │
│  문제:                                       │
│  1. Port가 "순수 추상화" 역할을 벗어남       │
│  2. 비즈니스 로직이 Port에 섞여 테스트 어려움 │
│  3. 의미론이 다른 이벤트가 한 Port에 혼재    │
│                                              │
└──────────────────────────────────────────────┘
```

### Clean Architecture 원칙

```
┌──────────────────────────────────────────────┐
│         Clean Architecture 원칙              │
├──────────────────────────────────────────────┤
│                                              │
│  Port = 순수 추상화 (외부 의존성 인터페이스)  │
│       │                                      │
│       ├── 무엇을 할 수 있는가? (계약)        │
│       └── 어떻게 하는가? (구현 X)            │
│                                              │
│  Service = 비즈니스 로직 (Port 조합)         │
│       │                                      │
│       ├── Port + Port = Use Case             │
│       └── 도메인 규칙 적용                   │
│                                              │
│  LangGraph Node = Orchestration만            │
│       │                                      │
│       ├── 이벤트 발행                        │
│       ├── Service 호출                       │
│       └── state 업데이트                     │
│                                              │
└──────────────────────────────────────────────┘
```

---

## 개선된 Application Layer 구조

### 전체 디렉토리 구조

```
apps/chat_worker/application/
├── commands/              # 메인 유스케이스 엔트리
│   └── process_chat.py
│
├── intent/                # 의도 분류 단계
│   ├── dto/
│   │   └── intent_result.py
│   └── services/
│       └── intent_classifier.py
│
├── answer/                # 답변 생성 단계
│   ├── dto/
│   │   └── answer_result.py
│   └── services/
│       └── answer_generator.py
│
├── integrations/          # 외부 서비스 연동
│   ├── character/
│   │   ├── ports/
│   │   │   └── character_client.py
│   │   └── services/
│   │       └── character_service.py
│   └── location/
│       ├── ports/
│       │   └── location_client.py
│       └── services/
│           └── location_service.py
│
├── interaction/           # Human-in-the-Loop
│   ├── ports/
│   │   ├── input_requester.py
│   │   └── interaction_state_store.py
│   └── services/
│       └── human_interaction_service.py
│
└── ports/                 # 공용 Port
    ├── llm/
    │   ├── llm_client.py      # 순수 LLM 호출
    │   └── llm_policy.py      # 프롬프트/모델 선택
    ├── events/
    │   ├── progress_notifier.py   # SSE/UI 이벤트
    │   └── domain_event_bus.py    # 시스템 이벤트
    └── retrieval/
        └── retriever.py       # RAG 검색
```

---

## Port 분리 상세

### 1. LLM: Client vs Policy

**기존**: 하나의 Port에 호출 + 정책 혼재

**개선**: `LLMClientPort` (순수 호출) + `LLMPolicyPort` (정책)

```python
# ports/llm/llm_client.py
class LLMClientPort(ABC):
    """순수 LLM API 호출만."""

    @abstractmethod
    async def generate(
        self,
        prompt: str,
        system_prompt: str | None = None,
        context: dict[str, Any] | None = None,
        max_tokens: int | None = None,
        temperature: float | None = None,
    ) -> str:
        """텍스트 생성."""
        pass

    @abstractmethod
    async def generate_stream(
        self,
        prompt: str,
        system_prompt: str | None = None,
        context: dict[str, Any] | None = None,
    ) -> AsyncIterator[str]:
        """스트리밍 텍스트 생성."""
        pass
```

```python
# ports/llm/llm_policy.py
class LLMPolicyPort(ABC):
    """LLM 정책 (프롬프트, 모델 선택, 리트라이)."""

    @abstractmethod
    def select_model(
        self,
        task_type: TaskType,
        preferred_tier: ModelTier = ModelTier.STANDARD,
    ) -> str:
        """작업 타입에 맞는 모델 선택."""
        pass

    @abstractmethod
    def format_prompt(
        self,
        template_name: str,
        **kwargs: Any,
    ) -> str:
        """프롬프트 템플릿 포매팅."""
        pass

    @abstractmethod
    async def execute_with_retry(
        self,
        operation: Callable[[], T],
        max_retries: int = 3,
    ) -> T:
        """리트라이 정책 적용."""
        pass
```

**분리 이유**:
- `LLMClientPort`: 어떤 LLM을 사용하든 동일한 인터페이스
- `LLMPolicyPort`: 프로젝트별 정책 (모델 선택, 비용 최적화)

### 2. Events: ProgressNotifier vs DomainEventBus

**기존**: 모든 이벤트가 `EventPublisherPort` 하나에

**개선**: 의미론 분리

```python
# ports/events/progress_notifier.py
class ProgressNotifierPort(ABC):
    """SSE/UI 진행 이벤트."""

    @abstractmethod
    async def notify_stage(
        self,
        task_id: str,
        stage: str,
        status: str,
        progress: int | None = None,
        message: str | None = None,
    ) -> str:
        """단계 진행 알림."""
        pass

    @abstractmethod
    async def notify_token(
        self,
        task_id: str,
        content: str,
    ) -> str:
        """토큰 스트리밍."""
        pass

    @abstractmethod
    async def notify_needs_input(
        self,
        task_id: str,
        input_type: str,
        message: str,
        timeout: int = 60,
    ) -> str:
        """Human-in-the-Loop 입력 요청."""
        pass
```

```python
# ports/events/domain_event_bus.py
class DomainEventBusPort(ABC):
    """시스템 내부 이벤트 (전달 보장 필요)."""

    @abstractmethod
    async def publish_status_changed(
        self,
        task_id: str,
        old_status: JobStatus,
        new_status: JobStatus,
    ) -> None:
        """상태 변경 이벤트."""
        pass

    @abstractmethod
    async def publish_job_completed(
        self,
        task_id: str,
        session_id: str,
        user_id: str,
        intent: str | None,
        answer: str | None,
    ) -> None:
        """작업 완료 이벤트."""
        pass
```

**분리 이유**:

| Port | 대상 | 전달 보장 | 구현체 |
|------|------|----------|--------|
| `ProgressNotifierPort` | Frontend (SSE) | Best-effort | Redis Pub/Sub |
| `DomainEventBusPort` | 시스템 내부 | 필수 | Redis Streams |

### 3. Integrations: Client vs Service

**기존**: Port에 `to_answer_context()` 같은 변환 로직 포함

**개선**: Port는 순수 호출, Service가 변환

```python
# integrations/character/ports/character_client.py
class CharacterClientPort(ABC):
    """Character API 순수 호출."""

    @abstractmethod
    async def get_character_by_waste_category(
        self,
        waste_category: str,
    ) -> CharacterDTO | None:
        """폐기물 카테고리로 캐릭터 조회."""
        pass

    @abstractmethod
    async def get_catalog(self) -> list[CharacterDTO]:
        """전체 카탈로그 조회."""
        pass
```

```python
# integrations/character/services/character_service.py
class CharacterService:
    """캐릭터 비즈니스 로직.
    
    Port 호출 + 컨텍스트 변환.
    """

    def __init__(self, client: CharacterClientPort):
        self._client = client

    async def find_by_waste_category(
        self,
        waste_category: str,
    ) -> CharacterDTO | None:
        """폐기물 카테고리로 캐릭터 검색."""
        return await self._client.get_character_by_waste_category(
            waste_category
        )

    @staticmethod
    def to_answer_context(char: CharacterDTO) -> dict[str, Any]:
        """Answer 노드용 컨텍스트 변환.
        
        비즈니스 로직: Port가 아닌 Service에서!
        """
        return {
            "character_name": char.name,
            "character_type": char.type_label,
            "character_dialog": char.dialog,
            "match_label": char.match_label,
        }
```

---

## Service 구현 상세

### IntentClassifier Service

```python
# intent/services/intent_classifier.py
class IntentClassifier:
    """의도 분류 비즈니스 로직.
    
    LLMClientPort 호출 + 결과 파싱.
    """

    INTENT_PROMPT = """사용자 메시지의 의도를 분류하세요.
가능한 의도: waste, character, location, general
응답: 의도 단어만 (예: waste)

사용자: {message}
"""

    def __init__(self, llm: LLMClientPort):
        self._llm = llm

    async def classify(self, message: str) -> ChatIntent:
        """의도 분류 → Domain VO 반환."""
        prompt = self.INTENT_PROMPT.format(message=message)
        
        response = await self._llm.generate(
            prompt=prompt,
            max_tokens=20,
            temperature=0.1,
        )
        
        intent_str = response.strip().lower()
        try:
            intent = Intent(intent_str)
        except ValueError:
            intent = Intent.GENERAL
        
        return ChatIntent(
            intent=intent,
            complexity=self._assess_complexity(message),
            confidence=0.9,
        )

    def _assess_complexity(self, message: str) -> Complexity:
        """메시지 복잡도 평가."""
        keywords = ["그리고", "또한", "비교", "차이"]
        if any(k in message for k in keywords):
            return Complexity.MULTI_TURN
        return Complexity.SIMPLE
```

### AnswerGeneratorService

```python
# answer/services/answer_generator.py
class AnswerGeneratorService:
    """답변 생성 비즈니스 로직.
    
    LLMClientPort 호출 + 컨텍스트 조합.
    """

    def __init__(self, llm: LLMClientPort):
        self._llm = llm

    async def generate_stream(
        self,
        context: AnswerContext,
        system_prompt: str,
    ) -> AsyncIterator[str]:
        """스트리밍 답변 생성."""
        user_prompt = context.to_prompt()
        
        async for token in self._llm.generate_stream(
            prompt=user_prompt,
            system_prompt=system_prompt,
        ):
            yield token

    async def generate(
        self,
        context: AnswerContext,
        system_prompt: str,
    ) -> str:
        """일괄 답변 생성."""
        user_prompt = context.to_prompt()
        
        return await self._llm.generate(
            prompt=user_prompt,
            system_prompt=system_prompt,
        )
```

---

## LangGraph Node: Thin Orchestration

### 원칙: 노드는 Orchestration만

```
┌──────────────────────────────────────────────┐
│         LangGraph Node 책임                  │
├──────────────────────────────────────────────┤
│                                              │
│  1. 이벤트 발행 (시작)                        │
│     await notifier.notify_stage(...)         │
│                                              │
│  2. Service 호출 (비즈니스 로직 위임)         │
│     result = await service.execute(...)      │
│                                              │
│  3. state 업데이트                           │
│     return {**state, "result": result}       │
│                                              │
│  4. 이벤트 발행 (완료)                        │
│     await notifier.notify_stage(...)         │
│                                              │
│  ❌ 하지 말아야 할 것:                        │
│  - LLM 직접 호출 (Service 통해서)            │
│  - 복잡한 조건 분기 (Service에서)            │
│  - 데이터 변환 (Service에서)                 │
│                                              │
└──────────────────────────────────────────────┘
```

### Intent Node 예시

```python
# infrastructure/orchestration/langgraph/nodes/intent_node.py
def create_intent_node(
    llm: LLMClientPort,
    event_publisher: ProgressNotifierPort,
):
    """의도 분류 노드 팩토리."""
    
    # Service 인스턴스 (비즈니스 로직)
    classifier = IntentClassifier(llm)

    async def intent_node(state: dict[str, Any]) -> dict[str, Any]:
        """Orchestration Only."""
        job_id = state["job_id"]
        message = state["message"]

        # 1. 이벤트: 시작
        await event_publisher.notify_stage(
            task_id=job_id,
            stage="intent",
            status="started",
            progress=10,
            message="의도 파악 중...",
        )

        # 2. Service 호출 (비즈니스 로직 위임)
        chat_intent = await classifier.classify(message)

        # 3. 이벤트: 완료
        await event_publisher.notify_stage(
            task_id=job_id,
            stage="intent",
            status="completed",
            progress=20,
        )

        # 4. state 업데이트
        return {
            **state,
            "intent": chat_intent.intent.value,
            "is_complex": chat_intent.is_complex,
        }

    return intent_node
```

### Character Subagent 예시

```python
# infrastructure/orchestration/langgraph/nodes/character_node.py
def create_character_subagent_node(
    llm: LLMClientPort,
    character_client: CharacterClientPort,
    event_publisher: ProgressNotifierPort,
):
    """캐릭터 서브에이전트 노드 팩토리."""
    
    # Service 인스턴스들
    character_service = CharacterService(character_client)

    async def character_subagent(state: dict[str, Any]) -> dict[str, Any]:
        """Orchestration Only."""
        job_id = state.get("job_id", "")
        message = state.get("message", "")

        # 1. 이벤트: 시작
        await event_publisher.notify_stage(
            task_id=job_id,
            stage="character",
            status="processing",
            message="캐릭터 정보 검색 중...",
        )

        # 2. 폐기물 카테고리 추출 (LLM)
        waste_category = await _extract_category(llm, message)
        if not waste_category:
            return {**state, "character_context": None}

        # 3. Service 호출
        character = await character_service.find_by_waste_category(
            waste_category
        )
        if not character:
            return {**state, "character_context": None}

        # 4. 컨텍스트 변환 (Service의 static method)
        context = CharacterService.to_answer_context(character)

        # 5. state 업데이트
        return {**state, "character_context": context}

    return character_subagent
```

---

## 의존성 흐름

```
┌──────────────────────────────────────────────┐
│           의존성 방향 (Clean Architecture)    │
├──────────────────────────────────────────────┤
│                                              │
│  Domain Layer                                │
│      ▲                                       │
│      │ (의존)                                │
│      │                                       │
│  Application Layer                           │
│  ├── Services (비즈니스 로직)                │
│  │       ▲                                   │
│  │       │ (의존)                            │
│  │       │                                   │
│  └── Ports (추상화)                          │
│          ▲                                   │
│          │ (구현)                            │
│          │                                   │
│  Infrastructure Layer                        │
│  ├── Adapters (Port 구현체)                  │
│  └── LangGraph Nodes (Orchestration)         │
│          │                                   │
│          │ (사용)                            │
│          ▼                                   │
│  Application Services                        │
│                                              │
└──────────────────────────────────────────────┘
```

### DI 패턴

```python
# setup/dependencies.py

async def get_chat_graph():
    """LangGraph DI 조립."""
    
    # 1. Port 구현체 (Infrastructure)
    llm_client = OpenAILLMClient(model="gpt-5.2-turbo")
    character_client = CharacterGrpcClient()
    progress_notifier = RedisProgressNotifier(redis)
    
    # 2. Service는 노드 팩토리 내부에서 생성
    #    (Port만 주입)
    
    # 3. Graph 생성
    return create_chat_graph(
        llm=llm_client,
        character_client=character_client,
        event_publisher=progress_notifier,
    )
```

---

## 테스트 전략

### Port Mock으로 Service 테스트

```python
# tests/application/intent/test_intent_classifier.py

class MockLLMClient(LLMClientPort):
    def __init__(self, response: str):
        self._response = response

    async def generate(self, prompt, **kwargs) -> str:
        return self._response

    async def generate_stream(self, prompt, **kwargs):
        yield self._response


async def test_classify_waste_intent():
    """waste 의도 분류 테스트."""
    mock_llm = MockLLMClient("waste")
    classifier = IntentClassifier(mock_llm)
    
    result = await classifier.classify("페트병 어떻게 버려?")
    
    assert result.intent == Intent.WASTE
    assert result.confidence > 0.5


async def test_classify_unknown_falls_back_to_general():
    """알 수 없는 응답은 general로."""
    mock_llm = MockLLMClient("unknown_intent")
    classifier = IntentClassifier(mock_llm)
    
    result = await classifier.classify("아무거나")
    
    assert result.intent == Intent.GENERAL
```

### Node 테스트 (Integration)

```python
# tests/infrastructure/langgraph/test_intent_node.py

async def test_intent_node_updates_state():
    """노드가 state를 올바르게 업데이트하는지."""
    mock_llm = MockLLMClient("waste")
    mock_notifier = MockProgressNotifier()
    
    node = create_intent_node(
        llm=mock_llm,
        event_publisher=mock_notifier,
    )
    
    initial_state = {"job_id": "test-1", "message": "페트병"}
    result_state = await node(initial_state)
    
    assert result_state["intent"] == "waste"
    assert mock_notifier.stages == ["started", "completed"]
```

---

## 정리

### Before vs After

| 항목 | Before | After |
|------|--------|-------|
| **LLM** | Port에 classify_intent() | Client + Policy 분리 |
| **Events** | 단일 EventPublisherPort | ProgressNotifier + DomainEventBus |
| **Integrations** | Port에 to_context() | Client + Service 분리 |
| **Node** | 비즈니스 로직 포함 | Orchestration만 |

### 핵심 원칙

1. **Port = 순수 추상화**: 외부 의존성 인터페이스만
2. **Service = 비즈니스 로직**: Port 조합 + 도메인 규칙
3. **Node = Orchestration**: 이벤트 → Service → state

### 장점

- **테스트 용이**: Service는 Port Mock으로 독립 테스트
- **재사용**: Service는 여러 Node에서 재사용 가능
- **유지보수**: 비즈니스 로직 변경 시 Service만 수정
- **확장성**: 새 Port 추가 시 기존 코드 영향 최소화

