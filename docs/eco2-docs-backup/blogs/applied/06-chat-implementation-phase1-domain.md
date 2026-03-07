# 이코에코(Eco²) Agent #6: Domain Layer 설계

> Chat Worker의 Domain Layer — 외부 의존성 없는 순수 비즈니스 개념 정의

| 항목 | 값 |
|-----|-----|
| **작성일** | 2026-01-14 (업데이트) |
| **커밋** | `32af7717` |
| **브랜치** | `refactor/reward-fanout-exchange` |

---

## 1. 왜 Domain Layer부터 시작하는가?

Clean Architecture에서 Domain Layer는 **가장 안쪽 원**입니다.

```
┌─────────────────────────────────────────┐
│          Infrastructure                  │
│    ┌───────────────────────────────┐    │
│    │        Application            │    │
│    │    ┌───────────────────┐      │    │
│    │    │      Domain       │      │    │  ← 여기서 시작
│    │    │   (Enums,         │      │    │
│    │    │    Value Objects) │      │    │
│    │    └───────────────────┘      │    │
│    └───────────────────────────────┘    │
└─────────────────────────────────────────┘
```

**Domain Layer를 먼저 정의하는 이유:**

1. **의존성 방향**: 모든 외부 계층이 Domain을 바라봄
2. **비즈니스 로직 중심**: 프레임워크/라이브러리와 무관
3. **불변성 보장**: Value Object는 frozen dataclass로 구현

---

## 2. 디렉토리 구조

```
apps/chat_worker/domain/
├── __init__.py
├── enums/
│   ├── __init__.py
│   ├── intent.py           # Intent Enum
│   ├── query_complexity.py # QueryComplexity Enum
│   └── input_type.py       # InputType Enum (HITL)
└── value_objects/
    ├── __init__.py
    ├── chat_intent.py      # ChatIntent VO
    └── human_input.py      # HITL Value Objects
```

### 초기 설계 vs 최종 구현

| 항목 | 초기 설계 | 최종 구현 | 변경 이유 |
|-----|----------|----------|----------|
| **LLMProvider** | Enum | 삭제 | Infrastructure Layer에서 처리 |
| **ChatState** | TypedDict | 삭제 | LangGraph에서 dict 직접 사용 |
| **QueryComplexity** | - | 추가 | Subagent 분기 결정 |
| **InputType** | - | 추가 | Human-in-the-Loop 패턴 |
| **ChatIntent** | - | 추가 | Intent 분류 결과 VO |
| **HumanInput** | - | 추가 | HITL 요청/응답 VO |

---

## 3. Intent Enum: 의도 분류의 첫 번째 관문

Chat 서비스의 핵심은 **사용자 의도 파악**입니다.

```python
# apps/chat_worker/domain/enums/intent.py
class Intent(str, Enum):
    """사용자 질문 의도.

    LangGraph의 Intent Node에서 분류되어
    라우팅 결정에 사용됩니다.
    """

    WASTE = "waste"
    """분리배출 질문.
    - 이 쓰레기 어떻게 버려?
    - 플라스틱 분리배출 방법
    - (이미지 첨부) 이거 뭐야?
    """

    CHARACTER = "character"
    """캐릭터 관련 질문.
    - 이 쓰레기로 어떤 캐릭터 얻어?
    - 플라스틱 버리면 누가 나와?
    """

    LOCATION = "location"
    """위치 기반 질문.
    - 근처 재활용센터 어디야?
    - 제로웨이스트샵 찾아줘
    """

    GENERAL = "general"
    """일반 대화 (그 외).
    - 안녕
    - 환경 보호에 대해 알려줘
    """

    @classmethod
    def from_string(cls, value: str) -> "Intent":
        """문자열에서 Intent 생성.

        Returns:
            매칭된 Intent, 없으면 GENERAL
        """
        try:
            return cls(value.lower())
        except ValueError:
            return cls.GENERAL
```

### 왜 4가지인가?

| Intent | 근거 | 파이프라인 |
|--------|------|-----------|
| `waste` | 핵심 기능, scan 서비스와 연계 | RAG → Answer |
| `character` | 게이미피케이션 요소 | Character gRPC → Answer |
| `location` | 실용적 가치, 차별화 | Location gRPC → Answer |
| `general` | 폴백, 환경 관련 일반 지식 | LLM 직접 답변 |

### CHARACTER_PREVIEW를 제거한 이유

```
초기 설계:
  character_preview → "버리면 뭐 얻어?" 패턴
                    → Vision/Text → Match

최종 결정:
  character 의도에 통합.
  "버리면 뭐 얻어?"와 "캐릭터 정보" 질문은
  동일한 Character gRPC 호출로 처리.
  불필요한 분기 제거.
```

### ECO 의도를 제외한 이유

```
초기 설계:
  eco → eco_rag_node → 환경 관련 정보 RAG

최종 결정:
  GPT-5.2, Gemini 3.0 등 최신 모델은 제로웨이스트,
  업사이클링 등 기본 환경 정보를 이미 학습.
  별도 RAG 없이 general로 처리.
```

---

## 4. QueryComplexity Enum: Subagent 분기 결정

```python
# apps/chat_worker/domain/enums/query_complexity.py
class QueryComplexity(str, Enum):
    """질문 복잡도.

    LangGraph의 라우팅 결정에 사용됩니다.
    - SIMPLE: 직접 응답
    - COMPLEX: Subagent 호출
    """

    SIMPLE = "simple"
    """단순 질문 - 직접 응답 가능.

    - 단일 의도
    - 단일 Tool 호출 또는 LLM만으로 해결
    - 예: "플라스틱 어떻게 버려?"
    """

    COMPLEX = "complex"
    """복잡한 질문 - Subagent 필요.

    - 다중 의도 또는 다중 단계
    - 여러 Tool 조합 필요
    - 예: "이 쓰레기 버리면 어떤 캐릭터 얻고, 근처 재활용센터도 알려줘"
    """

    @classmethod
    def from_bool(cls, is_complex: bool) -> "QueryComplexity":
        """bool에서 QueryComplexity 생성."""
        return cls.COMPLEX if is_complex else cls.SIMPLE
```

### 복잡도 판단 기준

```
단순 질문: "페트병 어떻게 버려?"
  → QueryComplexity.SIMPLE
  → 단일 노드 (waste_rag → answer)

복잡한 질문: "페트병이랑 캔 어떻게 버려? 근처 센터도 알려줘"
  → QueryComplexity.COMPLEX
  → Subagent 분해 (decomposer → experts 병렬 → synthesizer)
```

**복잡도 판단 로직 (IntentClassifier):**

```python
COMPLEX_KEYWORDS = ["그리고", "또한", "차이", "비교", "여러", "같이"]
MAX_SIMPLE_LENGTH = 100

def _determine_complexity(self, message: str) -> QueryComplexity:
    # 1. 복잡도 키워드 포함
    if any(kw in message for kw in COMPLEX_KEYWORDS):
        return QueryComplexity.COMPLEX

    # 2. 메시지 길이
    if len(message) > MAX_SIMPLE_LENGTH:
        return QueryComplexity.COMPLEX

    return QueryComplexity.SIMPLE
```

---

## 5. InputType Enum: Human-in-the-Loop

Human-in-the-Loop(HITL) 패턴에서 사용자에게 요청할 수 있는 입력 종류입니다.

```python
# apps/chat_worker/domain/enums/input_type.py
class InputType(str, Enum):
    """Human-in-the-Loop 입력 타입."""

    LOCATION = "location"
    """위치 정보 요청 (Geolocation API)."""

    CONFIRMATION = "confirmation"
    """확인 요청 (Yes/No)."""

    SELECTION = "selection"
    """선택 요청 (Multiple Choice)."""

    CANCEL = "cancel"
    """사용자 취소."""

    @classmethod
    def from_string(cls, value: str) -> "InputType":
        """문자열에서 InputType으로 변환."""
        value_lower = value.lower().strip()
        for input_type in cls:
            if input_type.value == value_lower:
                return input_type
        raise ValueError(f"Invalid input type: {value}")

    def requires_data(self) -> bool:
        """이 입력 타입이 추가 데이터를 필요로 하는지."""
        return self in {InputType.LOCATION, InputType.SELECTION}
```

### HITL 흐름

```
┌────────────────────────────────────────────────────────────┐
│  Location Subagent                                         │
│                                                            │
│  1. 위치 정보 확인                                          │
│     user_location = state.get("user_location")             │
│                    │                                       │
│                    ▼                                       │
│  2. 위치 없음 → HITL 요청                                   │
│     InputType.LOCATION                                     │
│     "📍 주변 센터를 찾으려면 위치 정보가 필요해요."         │
│                    │                                       │
│              (SSE → Frontend)                              │
│                    │                                       │
│  3. Frontend에서 위치 수집                                  │
│     POST /chat/{job_id}/input                              │
│                    │                                       │
│  4. 파이프라인 재개                                         │
│     LocationData(latitude=37.5, longitude=127.0)           │
└────────────────────────────────────────────────────────────┘
```

---

## 6. ChatIntent Value Object: 의도 분류 결과

Intent와 QueryComplexity를 묶은 **불변 객체**입니다.

```python
# apps/chat_worker/domain/value_objects/chat_intent.py
@dataclass(frozen=True, slots=True)
class ChatIntent:
    """분류된 사용자 의도 (Immutable).

    IntentClassifier 서비스의 출력으로 사용되며,
    LangGraph의 라우팅 결정에 활용됩니다.

    Attributes:
        intent: 분류된 의도
        complexity: 질문 복잡도
        confidence: 분류 신뢰도 (0.0 ~ 1.0)
    """

    intent: Intent
    complexity: QueryComplexity
    confidence: float = 1.0

    def __post_init__(self) -> None:
        """Validation."""
        if not 0.0 <= self.confidence <= 1.0:
            object.__setattr__(
                self, "confidence", max(0.0, min(1.0, self.confidence))
            )

    @property
    def needs_subagent(self) -> bool:
        """Subagent 호출이 필요한지 여부."""
        return self.complexity == QueryComplexity.COMPLEX

    @property
    def is_high_confidence(self) -> bool:
        """높은 신뢰도인지 여부 (>= 0.8)."""
        return self.confidence >= 0.8

    @classmethod
    def simple_waste(cls, confidence: float = 1.0) -> "ChatIntent":
        """단순 분리배출 질문 생성."""
        return cls(
            intent=Intent.WASTE,
            complexity=QueryComplexity.SIMPLE,
            confidence=confidence,
        )

    @classmethod
    def simple_general(cls, confidence: float = 1.0) -> "ChatIntent":
        """단순 일반 질문 생성."""
        return cls(
            intent=Intent.GENERAL,
            complexity=QueryComplexity.SIMPLE,
            confidence=confidence,
        )

    def to_dict(self) -> dict:
        """딕셔너리로 변환."""
        return {
            "intent": self.intent.value,
            "complexity": self.complexity.value,
            "confidence": self.confidence,
            "needs_subagent": self.needs_subagent,
        }
```

### frozen=True를 사용한 이유

```python
# Mutable (문제)
class ChatIntent:
    intent: Intent
    confidence: float

intent = ChatIntent(Intent.WASTE, 0.9)
intent.confidence = 0.1  # ❌ 외부에서 변경 가능

# Immutable (권장)
@dataclass(frozen=True)
class ChatIntent:
    intent: Intent
    confidence: float

intent = ChatIntent(Intent.WASTE, 0.9)
intent.confidence = 0.1  # ❌ FrozenInstanceError
```

**Value Object 불변성의 이점:**
- 스레드 안전
- 예측 가능한 상태
- 디버깅 용이

---

## 7. Human Input Value Objects: HITL 요청/응답

```python
# apps/chat_worker/domain/value_objects/human_input.py

@dataclass(frozen=True)
class LocationData:
    """위치 정보 (Geolocation API 형식)."""

    latitude: float
    longitude: float

    def is_valid(self) -> bool:
        """유효한 좌표인지 검증."""
        return -90 <= self.latitude <= 90 and -180 <= self.longitude <= 180


@dataclass(frozen=True)
class HumanInputRequest:
    """사용자 입력 요청.

    Worker가 사용자에게 추가 입력을 요청할 때 사용.
    """

    job_id: str
    input_type: InputType
    message: str
    timeout: int = 60
    options: tuple[str, ...] | None = None  # SELECTION용

    def __post_init__(self):
        """유효성 검증."""
        if self.input_type == InputType.SELECTION and not self.options:
            raise ValueError("SELECTION type requires options")
        if self.timeout <= 0:
            raise ValueError("timeout must be positive")


@dataclass(frozen=True)
class HumanInputResponse:
    """사용자 입력 응답."""

    input_type: InputType
    data: dict[str, Any] | None = None
    cancelled: bool = False
    timed_out: bool = False

    @property
    def is_successful(self) -> bool:
        """성공적인 응답인지."""
        return not self.cancelled and not self.timed_out and self.data is not None

    def get_location(self) -> LocationData | None:
        """위치 데이터 추출."""
        if self.input_type != InputType.LOCATION or not self.data:
            return None
        try:
            return LocationData.from_dict(self.data)
        except (KeyError, ValueError):
            return None

    @classmethod
    def cancelled_response(cls, input_type: InputType) -> "HumanInputResponse":
        """취소 응답 생성."""
        return cls(input_type=input_type, cancelled=True)

    @classmethod
    def timeout_response(cls, input_type: InputType) -> "HumanInputResponse":
        """타임아웃 응답 생성."""
        return cls(input_type=input_type, timed_out=True)

    @classmethod
    def success_response(
        cls, input_type: InputType, data: dict[str, Any]
    ) -> "HumanInputResponse":
        """성공 응답 생성."""
        return cls(input_type=input_type, data=data)
```

---

## 8. ChatState TypedDict를 제거한 이유

### 초기 설계

```python
class ChatState(TypedDict, total=False):
    job_id: str
    user_id: str
    session_id: str
    message: str
    messages: Annotated[list, add_messages]
    intent: Literal["waste", "character", ...] | None
    is_complex: bool | None
    classification_result: dict | None
    disposal_rules: dict | None
    tool_results: dict[str, Any] | None
    subagent_results: dict[str, Any] | None
    answer: str | None
    token_usage: dict | None
```

### 제거 이유

1. **LangGraph와의 통합**: LangGraph는 기본적으로 `dict`를 상태로 사용
2. **유연성**: 노드별로 다른 키를 추가/제거 가능
3. **타입 검증 위치**: Domain이 아닌 Application Layer에서 검증

```python
# 현재 구현: LangGraph factory에서 dict 직접 사용
def create_chat_graph(...) -> StateGraph:
    graph = StateGraph(dict)  # ChatState 대신 dict

    async def intent_node(state: dict) -> dict:
        # 타입 검증은 Application Service에서
        chat_intent = await classifier.classify(state["message"])
        return {**state, "intent": chat_intent.intent.value}
```

---

## 9. LLMProvider Enum을 제거한 이유

### 초기 설계

```python
class LLMProvider(str, Enum):
    OPENAI = "openai"
    GEMINI = "gemini"
    ANTHROPIC = "anthropic"
```

### 제거 이유

1. **Infrastructure 관심사**: 모델 선택은 비즈니스 로직이 아님
2. **LLM Policy 분리**: `infrastructure/llm/policies/`에서 처리
3. **설정 기반**: 환경변수로 모델 선택

```python
# 현재 구현: Infrastructure Layer에서 처리
# apps/chat_worker/infrastructure/llm/config.py
MODEL_CONTEXT_WINDOWS = {
    "gpt-5.2-turbo": 128_000,
    "gemini-3-flash-preview": 1_000_000,
    "gemini-3-pro-preview": 2_000_000,
}
```

---

## 10. 공개 인터페이스

```python
# apps/chat_worker/domain/__init__.py
from chat_worker.domain.enums import InputType, Intent, QueryComplexity
from chat_worker.domain.value_objects import (
    ChatIntent,
    HumanInputRequest,
    HumanInputResponse,
    LocationData,
)

__all__ = [
    # Enums
    "InputType",
    "Intent",
    "QueryComplexity",
    # Value Objects
    "ChatIntent",
    "HumanInputRequest",
    "HumanInputResponse",
    "LocationData",
]
```

### 사용 예시

```python
# Application Layer에서 Domain 타입 사용
from chat_worker.domain import Intent, ChatIntent, QueryComplexity

class IntentClassifier:
    async def classify(self, message: str) -> ChatIntent:
        intent_str = await self._llm.generate(...)
        intent = Intent.from_string(intent_str)
        complexity = self._determine_complexity(message)

        return ChatIntent(
            intent=intent,
            complexity=complexity,
            confidence=1.0,
        )
```

---

## 11. 의사결정 요약

| 결정 | 선택 | 근거 |
|-----|------|------|
| Intent 종류 | 4개 (waste, character, location, general) | eco, character_preview 제거 |
| QueryComplexity | 추가 | Subagent 분기 결정 명확화 |
| InputType | 추가 | HITL 패턴 도메인 모델링 |
| ChatIntent | 추가 | Intent 분류 결과 캡슐화 |
| ChatState | 제거 | LangGraph dict 직접 사용 |
| LLMProvider | 제거 | Infrastructure 관심사로 이동 |
| 불변성 | frozen=True | 스레드 안전, 예측 가능성 |

---

## 12. 테스트

```python
# tests/unit/domain/test_intent.py
def test_intent_from_string():
    assert Intent.from_string("waste") == Intent.WASTE
    assert Intent.from_string("WASTE") == Intent.WASTE
    assert Intent.from_string("unknown") == Intent.GENERAL

# tests/unit/domain/test_chat_intent.py
def test_chat_intent_immutable():
    intent = ChatIntent.simple_waste(confidence=0.9)

    with pytest.raises(FrozenInstanceError):
        intent.confidence = 0.1

def test_needs_subagent():
    simple = ChatIntent(Intent.WASTE, QueryComplexity.SIMPLE)
    complex = ChatIntent(Intent.WASTE, QueryComplexity.COMPLEX)

    assert simple.needs_subagent is False
    assert complex.needs_subagent is True
```

---

## 파일 구조 최종

```
apps/chat_worker/domain/
├── __init__.py
│   └── __all__ = [Intent, QueryComplexity, InputType,
│                   ChatIntent, HumanInputRequest, ...]
├── enums/
│   ├── __init__.py
│   ├── intent.py           # Intent: WASTE, CHARACTER, LOCATION, GENERAL
│   ├── query_complexity.py # QueryComplexity: SIMPLE, COMPLEX
│   └── input_type.py       # InputType: LOCATION, CONFIRMATION, ...
└── value_objects/
    ├── __init__.py
    ├── chat_intent.py      # ChatIntent (Intent + Complexity + Confidence)
    └── human_input.py      # HumanInputRequest, HumanInputResponse, LocationData
```
