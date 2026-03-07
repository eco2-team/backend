# 이코에코(Eco²) Agent #6: Interactive SSE (Human-in-the-Loop)

> 위치 정보가 필요할 때만 권한 요청하는 대화형 SSE 패턴

[Agent #5](15-chat-checkpointer-state.md)에서 Checkpointer를 다뤘습니다. 이번 포스팅에서는 **서브에이전트가 추가 정보를 필요로 할 때 사용자에게 요청하는 Interactive SSE 패턴**을 Clean Architecture로 설계합니다.

---

## 문제: 위치 정보를 언제 요청할까?

### 기존 방식의 한계

```
┌──────────────────────────────────────────────┐
│         방안 A: 항상 위치 포함                 │
├──────────────────────────────────────────────┤
│                                              │
│  사용자: "페트병 어떻게 버려?"                │
│       │                                      │
│       │ POST /chat                           │
│       │ { message, user_location }  ← 불필요 │
│       ▼                                      │
│  Intent: "waste" (위치 불필요)               │
│                                              │
│  문제:                                       │
│  - 매번 위치 전송 (프라이버시 ❌)             │
│  - 불필요한 권한 요청 (UX ❌)                 │
│                                              │
└──────────────────────────────────────────────┘
```

### 원하는 방식: Interactive SSE

```
┌──────────────────────────────────────────────┐
│         방안 B: Interactive SSE               │
├──────────────────────────────────────────────┤
│                                              │
│  사용자: "주변 재활용 센터 알려줘"            │
│       │                                      │
│       │ POST /chat { message }  ← 위치 없이! │
│       ▼                                      │
│  Intent: "location"                          │
│       │                                      │
│       ▼                                      │
│  Location Subagent: "위치가 필요해요!"       │
│       │                                      │
│       │ SSE: needs_input { type: "location" }│
│       ▼                                      │
│  Frontend: Geolocation API (이때만 권한!)    │
│       │                                      │
│       │ POST /chat/{job_id}/input { ... }    │
│       ▼                                      │
│  Location Subagent: gRPC → 센터 검색         │
│                                              │
│  장점:                                       │
│  - 필요시에만 위치 요청 (프라이버시 ✅)       │
│  - 자연스러운 대화 흐름 (UX ✅)               │
│                                              │
└──────────────────────────────────────────────┘
```

---

## Clean Architecture 구조

### Naive 구현의 문제

```
┌──────────────────────────────────────────────┐
│         Naive 구현 (blocking wait)            │
├──────────────────────────────────────────────┤
│                                              │
│  Location Subagent (Infrastructure)          │
│       │                                      │
│       ├── event_publisher.notify_needs_input │
│       │   (이벤트 발행)                       │
│       │                                      │
│       └── input_waiter.wait_for_input()      │
│           ← blocking wait (문제!)            │
│                                              │
│  문제:                                       │
│  1. blocking wait는 테스트 어려움             │
│  2. 타임아웃 처리가 Infrastructure에 혼재     │
│  3. 상태 관리와 이벤트 발행이 분리 안됨       │
│                                              │
└──────────────────────────────────────────────┘
```

### 개선: SoT 분리 + 이벤트/상태 기반 재개

```
┌──────────────────────────────────────────────┐
│      Clean Architecture (SoT 분리)           │
├──────────────────────────────────────────────┤
│                                              │
│  [Domain Layer]                              │
│  ├── enums/input_type.py    # InputType Enum │
│  └── value_objects/                          │
│      └── human_input.py     # Request/Response│
│                                              │
│  [Application Layer]                         │
│  ├── interaction/                            │
│  │   ├── ports/                              │
│  │   │   ├── input_requester.py   ← 이벤트만 │
│  │   │   └── interaction_state_store.py ← 상태│
│  │   └── services/                           │
│  │       └── human_interaction_service.py    │
│  │                                           │
│  └── ports/events/                           │
│      └── progress_notifier.py                │
│                                              │
│  [Infrastructure Layer]                      │
│  └── interaction/                            │
│      ├── redis_input_requester.py            │
│      └── redis_interaction_state_store.py    │
│                                              │
│  [LangGraph Node]                            │
│  └── location_node.py   # Orchestration only │
│                                              │
└──────────────────────────────────────────────┘
```

### SoT(Source of Truth) 분리 이유

| 역할 | Port | 책임 |
|------|------|------|
| 이벤트 발행 | `InputRequesterPort` | needs_input SSE 이벤트만 |
| 상태 저장 | `InteractionStateStorePort` | 파이프라인 상태 스냅샷 |
| 상태 조회 | `InteractionStateStorePort` | 재개 시 상태 복원 |

**Blocking Wait 제거**: Application은 "이벤트 발행 + 상태 저장"까지만 담당, 실제 "대기/재개"는 Presentation/Infrastructure에서 처리

---

## 구현 상세

### 1. Domain Layer: Value Objects

```python
# chat_worker/domain/enums/input_type.py
class InputType(str, Enum):
    """Human-in-the-Loop 입력 타입."""
    LOCATION = "location"
    CONFIRMATION = "confirmation"
    SELECTION = "selection"
    CANCEL = "cancel"

    def requires_data(self) -> bool:
        return self in {InputType.LOCATION, InputType.SELECTION}
```

```python
# chat_worker/domain/value_objects/human_input.py
class HumanInputRequest(BaseModel):
    """사용자 입력 요청 (Pydantic)."""
    job_id: str
    input_type: InputType
    message: str
    current_state: dict[str, Any] = {}  # 재개용 상태
    resume_node: str = ""               # 재개할 노드

class LocationData(BaseModel):
    """위치 정보."""
    latitude: float
    longitude: float

    def is_valid(self) -> bool:
        return -90 <= self.latitude <= 90 and \
               -180 <= self.longitude <= 180
```

### 2. Application Layer: Port 분리 (SoT)

**기존**: `InputWaiterPort` (이벤트 + blocking wait 혼재)

**개선**: `InputRequesterPort` + `InteractionStateStorePort` (책임 분리)

```python
# application/interaction/ports/input_requester.py
class InputRequesterPort(ABC):
    """사용자 입력 요청 포트.
    
    vs InputWaiterPort:
    - Waiter: blocking wait 포함 (문제)
    - Requester: 이벤트 발행 + 상태 저장만 (권장)
    """

    @abstractmethod
    async def request_input(
        self,
        job_id: str,
        input_type: InputType,
        message: str,
        timeout: int = 60,
    ) -> str:
        """요청 발행, 요청 ID 반환."""
        pass

    @abstractmethod
    async def save_waiting_state(
        self,
        job_id: str,
        state: dict,
        resume_node: str,
    ) -> None:
        """재개를 위한 상태 스냅샷 저장."""
        pass

    @abstractmethod
    async def get_waiting_state(
        self,
        job_id: str,
    ) -> tuple[dict, str] | None:
        """상태 조회 (state, resume_node)."""
        pass
```

```python
# application/interaction/ports/interaction_state_store.py
class InteractionStateStorePort(ABC):
    """HITL 상태 저장/조회 Port.
    
    SoT(Source of Truth) 분리:
    - InputRequester: 이벤트 발행
    - StateStore: 상태 저장/조회
    """

    @abstractmethod
    async def save_pending_request(
        self, job_id: str, request: HumanInputRequest
    ) -> None:
        """보류 중인 요청 저장."""
        pass

    @abstractmethod
    async def get_pending_request(
        self, job_id: str
    ) -> HumanInputRequest | None:
        """보류 중인 요청 조회."""
        pass

    @abstractmethod
    async def mark_completed(self, job_id: str) -> None:
        """완료 표시 (삭제)."""
        pass
```

### 3. Application Layer: Service (No Blocking)

```python
# application/interaction/services/human_interaction_service.py
class HumanInputService:
    """HITL 비즈니스 로직.
    
    "이벤트 발행 + 상태 저장"까지만.
    "대기/재개"는 Infrastructure/Presentation에서.
    """

    def __init__(self, input_requester: InputRequesterPort):
        self._requester = input_requester

    async def request_location(
        self,
        job_id: str,
        current_state: dict[str, Any],
        message: str | None = None,
        timeout: int = 60,
    ) -> str:
        """위치 요청 → 요청 ID 반환.
        
        blocking wait 없음!
        """
        # 1. needs_input 이벤트 발행
        request_id = await self._requester.request_input(
            job_id=job_id,
            input_type=InputType.LOCATION,
            message=message or DEFAULT_MSG,
            timeout=timeout,
        )

        # 2. 재개용 상태 저장
        await self._requester.save_waiting_state(
            job_id=job_id,
            state=current_state,
            resume_node="location_subagent",
        )

        return request_id
```

### 4. Infrastructure Layer: Adapter

```python
# infrastructure/interaction/redis_input_requester.py
class RedisInputRequester(InputRequesterPort):
    """Redis 기반 InputRequesterPort 구현체."""

    def __init__(
        self,
        progress_notifier: ProgressNotifierPort,
        state_store: InteractionStateStorePort,
    ):
        self._notifier = progress_notifier
        self._state_store = state_store

    async def request_input(
        self, job_id: str, input_type: InputType,
        message: str, timeout: int = 60,
    ) -> str:
        # ProgressNotifier로 SSE 이벤트 발행
        return await self._notifier.notify_needs_input(
            task_id=job_id,
            input_type=input_type.value,
            message=message,
            timeout=timeout,
        )

    async def save_waiting_state(
        self, job_id: str, state: dict, resume_node: str,
    ) -> None:
        request = HumanInputRequest(
            job_id=job_id,
            input_type=InputType.LOCATION,
            message="",
            current_state=state,
            resume_node=resume_node,
        )
        await self._state_store.save_pending_request(job_id, request)

    async def get_waiting_state(
        self, job_id: str,
    ) -> tuple[dict, str] | None:
        req = await self._state_store.get_pending_request(job_id)
        return (req.current_state, req.resume_node) if req else None
```

```python
# infrastructure/interaction/redis_interaction_state_store.py
class RedisInteractionStateStore(InteractionStateStorePort):
    """Redis 기반 HITL 상태 저장소."""

    REDIS_KEY_PREFIX = "hitl:pending_request:"
    REDIS_TTL = 3600  # 1시간

    def __init__(self, redis: Redis):
        self._redis = redis

    async def save_pending_request(
        self, job_id: str, request: HumanInputRequest
    ) -> None:
        key = f"{self.REDIS_KEY_PREFIX}{job_id}"
        await self._redis.set(
            key, request.model_dump_json(), ex=self.REDIS_TTL
        )

    async def get_pending_request(
        self, job_id: str
    ) -> HumanInputRequest | None:
        key = f"{self.REDIS_KEY_PREFIX}{job_id}"
        data = await self._redis.get(key)
        if data:
            return HumanInputRequest.model_validate_json(data)
        return None

    async def mark_completed(self, job_id: str) -> None:
        key = f"{self.REDIS_KEY_PREFIX}{job_id}"
        await self._redis.delete(key)
```

### 5. LangGraph Node: Thin Orchestration

```python
# infrastructure/orchestration/langgraph/nodes/location_node.py
def create_location_subagent_node(
    location_client: LocationClientPort,
    event_publisher: ProgressNotifierPort,
    input_requester: InputRequesterPort | None = None,
):
    human_service = (
        HumanInputService(input_requester)
        if input_requester else None
    )

    async def location_subagent(state: dict) -> dict:
        """Orchestration Only."""
        job_id = state.get("job_id", "")
        user_loc = state.get("user_location")

        # 1. 위치 있음 → 바로 검색
        if user_loc:
            return await _search_and_update(state, user_loc)

        # 2. 위치 없음 + HITL 가능 → 요청
        if human_service:
            await human_service.request_location(
                job_id=job_id,
                current_state=state,
            )
            # blocking wait 없이 바로 반환!
            return {
                **state,
                "human_input_pending": True,
                "location_skipped": True,
            }

        # 3. 위치 없음 + HITL 불가 → 스킵
        return {**state, "location_skipped": True}

    return location_subagent
```

---

## 의존성 주입 (DI)

```python
# chat_worker/setup/dependencies.py

# 싱글톤 인스턴스
_state_store: InteractionStateStorePort | None = None
_input_requester: InputRequesterPort | None = None


async def get_interaction_state_store() -> InteractionStateStorePort:
    """HITL 상태 저장소 싱글톤."""
    global _state_store
    if _state_store is None:
        redis = await get_redis()
        _state_store = RedisInteractionStateStore(redis)
    return _state_store


async def get_input_requester() -> InputRequesterPort:
    """InputRequester 싱글톤.
    
    DI 조립:
    - ProgressNotifierPort (이벤트 발행)
    - InteractionStateStorePort (상태 저장)
    """
    global _input_requester
    if _input_requester is None:
        progress_notifier = await get_progress_notifier()
        state_store = await get_interaction_state_store()
        _input_requester = RedisInputRequester(
            progress_notifier=progress_notifier,
            state_store=state_store,
        )
    return _input_requester


async def get_chat_graph(...):
    """Chat LangGraph with DI."""
    input_requester = await get_input_requester()
    
    return create_chat_graph(
        llm=llm,
        event_publisher=event_publisher,
        location_client=location_client,
        input_requester=input_requester,  # Port 주입
    )
```

---

## SSE 이벤트 타입

| 이벤트 | 용도 | 예시 |
|--------|------|------|
| `stage` | 진행 단계 | `{ stage: "intent", status: "completed" }` |
| `token` | 답변 스트리밍 | `{ content: "페트병은..." }` |
| `needs_input` | 추가 입력 요청 | `{ type: "location", message: "..." }` |
| `done` | 작업 완료 | `{ status: "completed" }` |
| `error` | 오류 발생 | `{ error: "...", code: "..." }` |

---

## 시퀀스 다이어그램

```
┌────────┐    ┌────────┐    ┌───────────┐   ┌────────┐
│Frontend│    │Chat API│    │Chat Worker│   │Location│
└───┬────┘    └───┬────┘    └─────┬─────┘   │  API   │
    │             │               │         └───┬────┘
    │ 1. POST /chat               │             │
    │────────────▶│               │             │
    │             │ 2. Taskiq     │             │
    │             │──────────────▶│             │
    │ 3. SSE 연결                 │             │
    │────────────────────────────▶│             │
    │             │               │             │
    │ 4. SSE: needs_input         │             │
    │    {type:"location"}        │             │
    │◀────────────────────────────│             │
    │             │               │             │
    │ (파이프라인 일시중단, 상태 저장)            │
    │             │               │             │
    │ 5. Geolocation API          │             │
    │             │               │             │
    │ 6. POST /chat/{job_id}/input│             │
    │────────────▶│               │             │
    │             │ 7. 상태 복원  │             │
    │             │──────────────▶│             │
    │             │               │ 8. gRPC     │
    │             │               │────────────▶│
    │             │               │◀────────────│
    │ 9. SSE: token               │             │
    │◀────────────────────────────│             │
    │ 10. SSE: done               │             │
    │◀────────────────────────────│             │
```

### 상태 기반 재개 흐름

```
┌─────────────────────────────────────────────┐
│             상태 기반 재개 패턴              │
├─────────────────────────────────────────────┤
│                                             │
│  [Step 1] 위치 필요 감지                    │
│  Location Node: "위치 없음!"                │
│       │                                     │
│       ▼                                     │
│  [Step 2] 이벤트 발행 + 상태 저장            │
│  HumanInputService.request_location()       │
│  - ProgressNotifier: needs_input SSE        │
│  - StateStore: {state, resume_node} 저장    │
│       │                                     │
│       ▼                                     │
│  [Step 3] 파이프라인 일시중단               │
│  return {human_input_pending: True}         │
│       │                                     │
│       ▼                                     │
│  [Step 4] Frontend: 위치 수집               │
│  - Geolocation API 호출                     │
│  - POST /chat/{job_id}/input                │
│       │                                     │
│       ▼                                     │
│  [Step 5] Presentation: 재개 처리           │
│  - StateStore에서 상태 조회                 │
│  - LangGraph 재개 (resume_node부터)         │
│                                             │
└─────────────────────────────────────────────┘
```

---

## Scan vs Chat 비교

| 항목 | Scan | Chat |
|------|------|------|
| **입력 방식** | 단일 요청 (이미지) | Interactive (대화) |
| **추가 입력** | 불필요 | needs_input 이벤트 |
| **Human-in-the-Loop** | N/A | Service + Port 구조 |
| **대기 메커니즘** | N/A | Redis Pub/Sub |

---

## 확장 가능한 Input 타입

| 타입 | 용도 | 예시 |
|------|------|------|
| `location` | 위치 권한 | 주변 센터 검색 |
| `confirmation` | 확인 요청 | "정말 삭제하시겠어요?" |
| `selection` | 선택 요청 | "어느 캐릭터를 원하세요?" |
| `image` | 이미지 추가 요청 | "더 선명한 사진을 올려주세요" |

---

## Blocking Wait vs 상태 기반 재개

| 항목 | Blocking Wait | 상태 기반 재개 |
|------|---------------|---------------|
| **Application 역할** | 이벤트 + 대기 | 이벤트 + 상태 저장만 |
| **대기 처리** | Service에서 | Presentation에서 |
| **테스트** | Mock 필요 | 상태만 검증 |
| **타임아웃** | Service에 혼재 | Presentation 책임 |
| **확장성** | 낮음 | 높음 (상태 기반) |

---

## 결론

Clean Architecture로 Interactive SSE 패턴을 구현했습니다:

### 핵심 변경

| 기존 | 개선 |
|------|------|
| `InputWaiterPort` (blocking) | `InputRequesterPort` + `InteractionStateStorePort` |
| Service가 대기 담당 | Service는 이벤트/상태만, Presentation이 재개 |
| 단일 Port | SoT 분리 (이벤트 ↔ 상태) |

### 4계층 구조

```
Domain      → InputType, HumanInputRequest (VO)
Application → InputRequesterPort, HumanInputService
Infrastructure → RedisInputRequester, RedisStateStore
LangGraph   → Thin orchestration (Service 호출만)
```

### 장점

- **테스트 용이**: blocking wait 없이 상태만 검증
- **확장 가능**: `InputType` Enum으로 새 타입 추가
- **프라이버시**: 필요시에만 위치 요청
- **LangGraph 친화**: 상태 저장 → Checkpointer로 재개
