# 이코에코(Eco²) Agent #12: Subagent gRPC 통합

> Chat Subagent의 Character/Location 도메인 연동을 gRPC로 구현

---

## 1. 배경

### 1.1 문제 정의

Chat Worker의 LangGraph 파이프라인에서 다른 도메인 API를 호출해야 한다.

```
Intent Router
    │
    ├─ waste     → RAG (로컬)
    ├─ character → ??? (Character API 호출 필요)
    ├─ location  → ??? (Location API 호출 필요)
    └─ general   → LLM
```

### 1.2 HTTP vs gRPC

| 항목 | HTTP/JSON | gRPC/Protobuf |
|------|-----------|---------------|
| 지연 시간 | ~5-10ms | ~1-3ms |
| 페이로드 | 텍스트 (크다) | 바이너리 (작다) |
| 타입 안전성 | 런타임 | 컴파일 타임 |
| 적합 환경 | 외부 API | 내부 통신 |

**선택: gRPC** — 내부 마이크로서비스 통신에 최적화

### 1.3 Direct Call vs Queue-based

| 항목 | Direct Call (gRPC) | Queue-based (Celery) |
|------|---------------------|----------------------|
| 호출 방식 | 직접 호출 + `await` | 큐 발행 → 폴링/콜백 |
| 결과 수신 | non-blocking 대기 | 블로킹 `.get()` or 폴링 |
| asyncio 호환 | ✅ `grpc.aio` | ❌ 이벤트 루프 충돌 |
| 적합 패턴 | 즉시 응답 필요 | Fire & Forget |
| LangGraph 노드 | ✅ 자연스러움 | ❌ 부적합 |

**선택: Direct Call (gRPC)** — LangGraph의 asyncio 오케스트레이션과 호환

```python
# Direct Call: non-blocking await (LangGraph 호환)
async def character_subagent(state):
    character = await grpc_client.GetCharacterByMatch(request)  # ✅ non-blocking
    return {**state, "character": character}

# Queue-based: 결과 대기 불가 (LangGraph 부적합)
async def character_subagent(state):
    task = character_task.delay(...)  # 큐에 발행
    result = task.get()  # ❌ 블로킹! asyncio 이벤트 루프 멈춤
```

---

## 2. 아키텍처

### 2.1 DI + Port/Adapter 패턴

```
┌────────────────────────────────────────────────────────────┐
│                      Chat Worker                           │
│  ┌──────────────────────────────────────────────────────┐  │
│  │              LangGraph Pipeline                      │  │
│  │                                                      │  │
│  │  Intent → Router → [Character / Location] → Answer   │  │
│  │                         │                            │  │
│  │              CharacterClientPort (추상)              │  │
│  │              LocationClientPort (추상)               │  │
│  └─────────────────────────┬────────────────────────────┘  │
│                            │                               │
│  ┌─────────────────────────▼────────────────────────────┐  │
│  │           dependencies.py (DI Factory)               │  │
│  │                                                      │  │
│  │  get_character_client() → CharacterGrpcClient        │  │
│  │  get_location_client()  → LocationGrpcClient         │  │
│  └─────────────────────────┬────────────────────────────┘  │
│                            │                               │
│  ┌─────────────────────────▼────────────────────────────┐  │
│  │         Infrastructure (gRPC Adapters)               │  │
│  └───────────┬─────────────────────────┬────────────────┘  │
└──────────────┼─────────────────────────┼───────────────────┘
               │ grpc.aio                │ grpc.aio
               ▼                         ▼
        Character API             Location API
        (LocalCache)              (PostGIS)
```

**핵심:**
- 노드는 Port(추상)에만 의존 → 구현체를 모름
- DI Factory가 gRPC 구현체 주입
- 테스트 시 Mock 주입 가능

### 2.2 핵심 코드

**Port 정의 (추상):**

```python
# apps/chat_worker/application/chat/ports/character_client.py
class CharacterClientPort(ABC):
    @abstractmethod
    async def get_character_by_waste_category(
        self, waste_category: str
    ) -> CharacterDTO | None:
        pass
```

**Adapter 구현 (gRPC):**

```python
# apps/chat_worker/infrastructure/tool_clients/character_grpc.py
class CharacterGrpcClient(CharacterClientPort):
    async def get_character_by_waste_category(self, waste_category: str):
        stub = await self._get_stub()
        request = character_pb2.GetByMatchRequest(match_label=waste_category)
        response = await stub.GetCharacterByMatch(request)
        return CharacterDTO(...) if response.found else None
```

**DI 주입:**

```python
# apps/chat_worker/setup/dependencies.py
async def get_character_client() -> CharacterClientPort:  # Port 반환
    return CharacterGrpcClient(host, port)  # 구현체 생성

async def get_chat_graph():
    character_client = await get_character_client()  # DI
    return create_chat_graph(character_client=character_client)
```

---

## 3. Proto 정의

### 3.1 Character (확장)

```protobuf
// apps/character/proto/character.proto
service CharacterService {
  rpc GetCharacterByMatch (GetByMatchRequest) returns (GetByMatchResponse) {}
}

message GetByMatchRequest {
  string match_label = 1;  // "플라스틱", "종이류"
}

message GetByMatchResponse {
  bool found = 1;
  string character_name = 2;
  string character_type = 3;
  string character_dialog = 4;
}
```

### 3.2 Location (신규)

```protobuf
// apps/location/proto/location.proto
service LocationService {
  rpc SearchNearby (SearchNearbyRequest) returns (SearchNearbyResponse) {}
}

message SearchNearbyRequest {
  double latitude = 1;
  double longitude = 2;
  int32 radius = 3;
  int32 limit = 4;
}

message SearchNearbyResponse {
  repeated LocationEntry entries = 1;
}
```

---

## 4. Subagent 노드

### 4.1 LangGraph 파이프라인 흐름

```
┌────────────────────────────────────────────────────────────────┐
│                    LangGraph Pipeline                          │
│                                                                │
│  START ──▶ Intent ──▶ Router                                   │
│                          │                                     │
│            ┌─────────────┼─────────────┬─────────────┐         │
│            ▼             ▼             ▼             ▼         │
│       ┌────────┐   ┌──────────┐  ┌──────────┐  ┌─────────┐     │
│       │ Waste  │   │Character │  │ Location │  │ General │     │
│       │  RAG   │   │ Subagent │  │ Subagent │  │ (pass)  │     │
│       └───┬────┘   └────┬─────┘  └────┬─────┘  └────┬────┘     │
│           │             │             │             │          │
│           │        gRPC │        gRPC │             │          │
│           │             ▼             ▼             │          │
│           │      Character API  Location API       │          │
│           │             │             │             │          │
│           └─────────────┴──────┬──────┴─────────────┘          │
│                                ▼                               │
│                            Answer ──▶ END                      │
└────────────────────────────────────────────────────────────────┘
```

### 4.2 Character Subagent

```
┌─────────────────────────────────────────────────────┐
│              Character Subagent 노드                 │
│                                                     │
│  1. SSE 이벤트 발행                                  │
│     "🎭 캐릭터 정보를 찾고 있어요..."                │
│                    │                                │
│                    ▼                                │
│  2. LLM으로 카테고리 추출                            │
│     "플라스틱 버리면?" → "플라스틱"                  │
│                    │                                │
│                    ▼                                │
│  3. gRPC 호출 (CharacterClientPort)                 │
│     GetCharacterByMatch("플라스틱")                  │
│                    │                                │
│                    ▼                                │
│  4. state에 character_context 추가                  │
│     {found: true, name: "플라", dialog: "..."}      │
└─────────────────────────────────────────────────────┘
```

**실제 구현 (요약):**

```python
# apps/chat_worker/infrastructure/langgraph/nodes/character_subagent.py
def create_character_subagent_node(llm, character_client, event_publisher):
    async def character_subagent(state: dict) -> dict:
        # 1. SSE 진행 이벤트
        await event_publisher.publish_stage_event(
            stage="character", message="🎭 캐릭터 정보를 찾고 있어요..."
        )
        
        # 2. LLM으로 폐기물 카테고리 추출
        waste_category = await llm.generate(
            EXTRACT_CATEGORY_PROMPT.format(message=state["message"])
        )
        
        # 3. gRPC 호출 (Port 인터페이스 - 구현체 모름)
        character = await character_client.get_character_by_waste_category(
            waste_category.strip()
        )
        
        # 4. 컨텍스트 반환
        if character is None:
            return {**state, "character_context": {"found": False}}
        
        return {**state, "character_context": {
            "found": True, "name": character.name, "dialog": character.dialog
        }}
    
    return character_subagent
```

### 4.3 Location Subagent

```
┌─────────────────────────────────────────────────────┐
│              Location Subagent 노드                  │
│                                                     │
│  1. SSE 이벤트 발행                                  │
│     "📍 주변 재활용 센터를 찾고 있어요..."           │
│                    │                                │
│                    ▼                                │
│  2. user_location 확인                              │
│     없으면 → subagent_error 반환                    │
│                    │                                │
│                    ▼                                │
│  3. gRPC 호출 (LocationClientPort)                  │
│     SearchNearby(lat, lon, radius=5000)             │
│                    │                                │
│                    ▼                                │
│  4. state에 location_context 추가                   │
│     {found: true, count: 3, centers: [...]}         │
└─────────────────────────────────────────────────────┘
```

**실제 구현 (요약):**

```python
# apps/chat_worker/infrastructure/langgraph/nodes/location_subagent.py
def create_location_subagent_node(location_client, event_publisher):
    async def location_subagent(state: dict) -> dict:
        # 1. SSE 진행 이벤트
        await event_publisher.publish_stage_event(
            stage="location", message="📍 주변 재활용 센터를 찾고 있어요..."
        )
        
        # 2. 위치 정보 확인
        user_location = state.get("user_location")
        if not user_location:
            return {**state, "subagent_error": "위치 정보가 필요해요."}
        
        # 3. gRPC 호출 (Port 인터페이스)
        centers = await location_client.search_recycling_centers(
            lat=user_location["latitude"],
            lon=user_location["longitude"],
            radius=5000, limit=5
        )
        
        # 4. 컨텍스트 반환
        return {**state, "location_context": {
            "found": len(centers) > 0,
            "count": len(centers),
            "centers": [{"name": c.name, "distance": c.distance_text} for c in centers]
        }}
    
    return location_subagent
```

### 4.4 LangGraph Factory (노드 등록)

```python
# apps/chat_worker/infrastructure/langgraph/factory.py
def create_chat_graph(llm, retriever, event_publisher, character_client, location_client):
    # 노드 생성
    intent_node = create_intent_node(llm, event_publisher)
    rag_node = create_rag_node(retriever, event_publisher)
    answer_node = create_answer_node(llm, event_publisher)
    character_node = create_character_subagent_node(llm, character_client, event_publisher)
    location_node = create_location_subagent_node(location_client, event_publisher)
    
    # 그래프 구성
    graph = StateGraph(dict)
    graph.add_node("intent", intent_node)
    graph.add_node("waste_rag", rag_node)
    graph.add_node("character", character_node)
    graph.add_node("location", location_node)
    graph.add_node("answer", answer_node)
    
    # 라우팅
    graph.set_entry_point("intent")
    graph.add_conditional_edges("intent", route_by_intent, {
        "waste": "waste_rag", "character": "character",
        "location": "location", "general": "answer"
    })
    
    return graph.compile()
```

---

## 5. 테스트

### 5.1 DI 덕분에 Mock 주입 가능

```python
# tests/unit/.../test_character_subagent.py
@pytest.mark.asyncio
async def test_character_found():
    # Mock 주입 (Port 인터페이스)
    mock_client = AsyncMock()
    mock_client.get_character_by_waste_category = AsyncMock(
        return_value=CharacterDTO(name="플라", ...)
    )
    
    node = create_character_subagent_node(
        llm=mock_llm,
        character_client=mock_client,  # Mock 주입
        event_publisher=mock_publisher,
    )
    
    result = await node(state)
    
    assert result["character_context"]["found"] is True
```

### 5.2 테스트 구조

```
apps/chat_worker/tests/
└── unit/
    └── infrastructure/
        ├── tool_clients/
        │   ├── test_character_grpc.py
        │   └── test_location_grpc.py
        └── langgraph/nodes/
            ├── test_character_subagent.py
            └── test_location_subagent.py
```

---

## 6. 구현 현황

| Phase | 항목 | 상태 |
|-------|------|------|
| **1** | Character Proto 확장 | ✅ |
| **1** | Character Cache 메서드 | ✅ |
| **1** | Character Servicer | ✅ |
| **2** | Location Proto 신규 | ✅ |
| **2** | Location Servicer | ✅ |
| **2** | Location Server | ✅ |
| **3** | gRPC Clients | ✅ |
| **3** | Subagent Nodes | ✅ |
| **3** | DI 연결 | ✅ |
| **4** | 단위 테스트 | ✅ |
| **4** | K8s gRPC 포트 | 🔜 |

---

## 7. 핵심 정리

| 결정 | 선택 | 근거 |
|------|------|------|
| 프로토콜 | gRPC | 내부 통신 최적화, 타입 안전 |
| 호출 방식 | Direct Call | non-blocking await, 큐 오버헤드 없음 |
| 패턴 | Port/Adapter + DI | 테스트 용이, 구현 교체 가능 |

**파일 구조:**

```
apps/chat_worker/
├── application/chat/ports/
│   ├── character_client.py   # Port (추상)
│   └── location_client.py    # Port (추상)
├── infrastructure/tool_clients/
│   ├── character_grpc.py     # Adapter (gRPC)
│   └── location_grpc.py      # Adapter (gRPC)
├── infrastructure/langgraph/nodes/
│   ├── character_subagent.py # Port 의존
│   └── location_subagent.py  # Port 의존
└── setup/
    └── dependencies.py       # DI Factory
```
