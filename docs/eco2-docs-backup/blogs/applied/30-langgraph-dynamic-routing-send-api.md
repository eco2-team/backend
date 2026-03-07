# LangGraph Send API 기반 동적 라우팅

> Multi-Intent 처리와 컨텍스트 Enrichment를 위한 병렬 서브에이전트 실행 구현
>
> **핵심**: `Send API`로 런타임에 여러 노드를 동적으로 결정하고 병렬 실행
>
> **참고 논문**: arxiv:2304.11384 (Multi-Intent ICL), arxiv:2411.14252 (Chain-of-Intent, CIKM '25)

---

## 1. 배경: 정적 라우팅의 한계

### 1.1 기존 단일 Intent 라우팅

기존 Chat Worker는 Intent 분류 결과에 따라 **하나의 서브에이전트만** 실행했습니다.

```python
# 정적 라우팅 (Legacy)
def route_by_intent(state: dict) -> str:
    """단일 노드만 반환."""
    return state.get("intent", "general")

graph.add_conditional_edges(
    "router",
    route_by_intent,
    {
        "waste": "waste_rag",
        "character": "character",
        "location": "location",
        # ...
    },
)
```

**문제점**:

| 문제 | 설명 |
|------|------|
| **Multi-Intent 불가** | "종이 어떻게 버려? 그리고 수거함도 알려줘" → `waste`만 처리됨 |
| **컨텍스트 부족** | 분리배출 안내 시 날씨 정보가 없어 "비 오는 날 주의" 팁 제공 불가 |
| **순차 실행** | 여러 서브에이전트가 필요해도 하나씩만 실행 |

### 1.2 목표

```
사용자: "종이 어떻게 버려? 그리고 수거함도 알려줘"

기대 결과:
  - 종이 분리배출 방법 (waste_rag)
  - 근처 의류/폐지 수거함 위치 (collection_point)
  - 날씨 팁: "오늘 비 예보니 종이류는 젖지 않게 보관하세요" (weather)

→ 3개 노드를 병렬로 실행!
```

---

## 2. 라우팅 아키텍처 전문

### 2.1 전체 흐름

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         chat_worker 라우팅 아키텍처                       │
└─────────────────────────────────────────────────────────────────────────┘

  사용자 메시지
       │
       ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                       IntentClassifierService                           │
│  ┌───────────────────────────────────────────────────────────────────┐  │
│  │  키워드 맵 기반 신뢰도 보정                                         │  │
│  │  ├─ WASTE:            버려, 버리, 분리, 재활용, 쓰레기, 폐기        │  │
│  │  ├─ CHARACTER:        캐릭터, 얻, 모아, 컬렉션                      │  │
│  │  ├─ LOCATION:         어디, 근처, 위치, 제로웨이스트                │  │
│  │  ├─ BULK_WASTE:       대형폐기물, 소파, 냉장고, 가전, 수수료        │  │
│  │  ├─ RECYCLABLE_PRICE: 시세, 가격, 고철, 폐지, 매입                  │  │
│  │  ├─ COLLECTION_POINT: 수거함, 의류수거, 폐건전지, 폐형광등          │  │
│  │  ├─ WEB_SEARCH:       최신, 뉴스, 정책, 규제, 발표                  │  │
│  │  ├─ IMAGE_GENERATION: 이미지, 그림, 인포그래픽, 보여줘              │  │
│  │  └─ GENERAL:          안녕, 뭐야, 왜, 어때                          │  │
│  └───────────────────────────────────────────────────────────────────┘  │
│                                   │                                      │
│                                   ▼                                      │
│  ┌───────────────────────────────────────────────────────────────────┐  │
│  │  LLM (intent.txt 프롬프트)                                         │  │
│  │  → 9개 카테고리 중 하나 출력                                        │  │
│  └───────────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────┘
                                   │
                                   ▼
                        ┌────────────────────┐
                        │   Intent (Enum)    │
                        │   9개 값           │
                        └────────────────────┘
                                   │
                                   ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                    Dynamic Router (Send API)                            │
│                                                                         │
│  ┌───────────────────────────────────────────────────────────────────┐  │
│  │  INTENT_TO_NODE 매핑                                               │  │
│  │  ┌──────────────────┬────────────────────┬──────────────────────┐ │  │
│  │  │ Intent           │ Node               │ 외부 API              │ │  │
│  │  ├──────────────────┼────────────────────┼──────────────────────┤ │  │
│  │  │ waste            │ waste_rag          │ Local JSON Asset     │ │  │
│  │  │ character        │ character          │ gRPC (Character Svc) │ │  │
│  │  │ location         │ location           │ Kakao Local API      │ │  │
│  │  │ bulk_waste       │ bulk_waste         │ 행정안전부 API        │ │  │
│  │  │ recyclable_price │ recyclable_price   │ 한국환경공단 API      │ │  │
│  │  │ collection_point │ collection_point   │ KECO API             │ │  │
│  │  │ web_search       │ web_search         │ DuckDuckGo / Tavily  │ │  │
│  │  │ image_generation │ image_generation   │ OpenAI Responses API │ │  │
│  │  │ general          │ general            │ LLM Only             │ │  │
│  │  │ (weather)        │ weather            │ 기상청 API (Enrich)  │ │  │
│  │  └──────────────────┴────────────────────┴──────────────────────┘ │  │
│  └───────────────────────────────────────────────────────────────────┘  │
│                                                                         │
│  ┌───────────────────────────────────────────────────────────────────┐  │
│  │  Enrichment Rules (자동 보조 노드 추가)                            │  │
│  │  ├─ waste      → + weather (날씨 기반 분리배출 팁)                 │  │
│  │  └─ bulk_waste → + weather (대형폐기물 배출 날씨 팁)               │  │
│  └───────────────────────────────────────────────────────────────────┘  │
│                                                                         │
│  ┌───────────────────────────────────────────────────────────────────┐  │
│  │  Conditional Enrichment (state 조건)                               │  │
│  │  └─ user_location 있음 + intent ∉ {weather, general, character}   │  │
│  │     → + weather 자동 추가                                          │  │
│  └───────────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────┘
                                   │
           ┌───────────────────────┼───────────────────────┐
           │                       │                       │
           ▼                       ▼                       ▼
  ┌─────────────────┐   ┌─────────────────┐   ┌─────────────────┐
  │  Send(node_1)   │   │  Send(node_2)   │   │  Send(node_3)   │
  │  주 Intent 노드  │   │  Multi-Intent   │   │  Enrichment     │
  └────────┬────────┘   └────────┬────────┘   └────────┬────────┘
           │                     │                     │
           └─────────────────────┼─────────────────────┘
                                 │  병렬 실행
                                 ▼
                       ┌─────────────────┐
                       │ aggregator_node │  결과 수집
                       └────────┬────────┘
                                │
                                ▼
                        ┌──────────────┐
                        │ answer_node  │  최종 답변 생성
                        └──────┬───────┘
                               │
                               ▼
                          ┌─────────┐
                          │   END   │
                          └─────────┘
```

### 2.2 외부 API 매핑 상세

| Intent | Node | 외부 API | 설명 |
|--------|------|----------|------|
| `waste` | waste_rag | Local JSON Asset | 분리배출 규정 검색 (로컬 JSON) |
| `character` | character | gRPC (Character Service) | 캐릭터 정보 조회 |
| `location` | location | Kakao Local API | 장소 검색 (제로웨이스트샵 등) |
| `bulk_waste` | bulk_waste | 행정안전부 API | 대형폐기물 배출 정보 |
| `recyclable_price` | recyclable_price | 한국환경공단 API | 재활용자원 시세 |
| `collection_point` | collection_point | KECO API | 수거함 위치 검색 |
| `web_search` | web_search | DuckDuckGo / Tavily | 실시간 웹 검색 (기본: DDG) |
| `image_generation` | image_generation | OpenAI Responses API | 이미지 생성 |
| `weather` | weather | 기상청 API | 날씨 정보 (Enrichment) |
| `general` | general | LLM Only | 일반 대화 |

> **Note**: RAG는 현재 로컬 JSON 기반. Vector DB (Qdrant 등) 마이그레이션은 향후 계획.

---

## 3. Intent 분류 시스템

### 3.1 IntentClassifierService 구조

```python
class IntentClassifierService:
    """의도 분류 서비스 (순수 로직).

    Port 의존 없이 순수 비즈니스 로직만 담당:
    - 프롬프트 구성
    - LLM 응답 파싱
    - 신뢰도 계산
    - 복잡도 판단
    """
```

### 3.2 키워드 맵 기반 신뢰도 보정

LLM 응답의 신뢰도를 **키워드 매칭**으로 보정합니다.

```python
keyword_map = {
    Intent.WASTE: ["버려", "버리", "분리", "재활용", "쓰레기", "폐기"],
    Intent.CHARACTER: ["캐릭터", "얻", "모아", "컬렉션"],
    Intent.LOCATION: ["어디", "근처", "가까", "위치", "샵", "제로웨이스트", "재활용센터"],
    Intent.BULK_WASTE: [
        "대형폐기물", "대형", "소파", "냉장고", "세탁기",
        "가구", "수수료", "신청", "가전", "매트리스", "침대"
    ],
    Intent.RECYCLABLE_PRICE: ["시세", "가격", "얼마", "고철", "폐지", "매입", "kg", "킬로"],
    Intent.COLLECTION_POINT: [
        "수거함", "의류수거", "폐건전지", "폐형광등",
        "형광등", "건전지", "의류"
    ],
    Intent.WEB_SEARCH: ["최신", "최근", "뉴스", "정책", "규제", "발표", "공지"],
    Intent.IMAGE_GENERATION: ["이미지", "그림", "인포그래픽", "시각", "보여줘", "그려"],
    Intent.GENERAL: ["안녕", "뭐야", "왜", "어때"],
}

# 키워드 매칭 시 신뢰도 +0.1 (최대 +0.2)
# 키워드 불일치 시 신뢰도 -0.1
```

### 3.3 Intent Transition Boost (Chain-of-Intent)

**CIKM '25 논문** 기반으로 **이전 대화 맥락**에 따라 신뢰도를 부스트합니다.

> ⚠️ **구현 상태**: 로직은 구현됨 (`IntentClassifierService`), 하지만 **이전 턴의 intent를 저장/전달하는 통합 코드 미완료**. 현재는 `conversation_history` (메시지 배열)를 전달하지만, `previous_intents` (intent 문자열 배열)가 필요함.

```python
INTENT_TRANSITION_BOOST: dict[Intent, dict[Intent, float]] = {
    # WASTE에서 자주 전이되는 패턴
    Intent.WASTE: {
        Intent.LOCATION: 0.15,           # "버리고 싶은데 센터 어디야?"
        Intent.CHARACTER: 0.05,
        Intent.COLLECTION_POINT: 0.10,   # "어디서 버려?" → 수거함
    },

    # BULK_WASTE에서 자주 전이되는 패턴
    Intent.BULK_WASTE: {
        Intent.LOCATION: 0.12,           # "대형폐기물 센터 어디야?"
        Intent.RECYCLABLE_PRICE: 0.08,   # "냉장고 팔 수 있어?"
    },

    # RECYCLABLE_PRICE에서 자주 전이되는 패턴
    Intent.RECYCLABLE_PRICE: {
        Intent.LOCATION: 0.10,           # "어디서 팔아?"
        Intent.COLLECTION_POINT: 0.08,
    },

    # COLLECTION_POINT에서 자주 전이되는 패턴
    Intent.COLLECTION_POINT: {
        Intent.WASTE: 0.10,              # "어떻게 버려?"
        Intent.LOCATION: 0.08,
    },

    # GENERAL에서 자주 전이되는 패턴
    Intent.GENERAL: {
        Intent.WASTE: 0.10,
        Intent.CHARACTER: 0.05,
        Intent.LOCATION: 0.08,
    },

    # CHARACTER에서 자주 전이되는 패턴
    Intent.CHARACTER: {
        Intent.WASTE: 0.08,
    },
}
```

**예시**:

```
대화 흐름:
  Turn 1: "플라스틱 어떻게 버려?" → intent=WASTE
  Turn 2: "근처 재활용센터는?"

Turn 2 분류:
  - LLM 응답: "location" (confidence=0.75)
  - Transition Boost: WASTE → LOCATION = +0.15
  - 최종 confidence: 0.90 ✅
```

---

## 4. LangGraph Send API

### 4.1 Send API란?

LangGraph의 `Send`는 **조건부 엣지에서 여러 목적지를 동적으로 생성**하는 메커니즘입니다.

```python
from langgraph.types import Send

def dynamic_router(state: dict) -> list[Send]:
    """list[Send] 반환 → 병렬 실행."""
    sends = []

    # 주 intent
    sends.append(Send("waste_rag", state))

    # 추가 intents (있다면)
    for intent in state.get("additional_intents", []):
        sends.append(Send(intent, state))

    return sends

# 조건부 엣지에 연결
graph.add_conditional_edges("router", dynamic_router)
```

### 4.2 Send API vs 일반 라우팅

| 구분 | 일반 라우팅 | Send API |
|------|------------|----------|
| **반환 타입** | `str` (단일 노드) | `list[Send]` (다중 노드) |
| **실행 방식** | 순차 (하나만) | 병렬 (동시 실행) |
| **state 전달** | 자동 (현재 state) | `Send(node, state)` 명시 |
| **결과 병합** | N/A | LangGraph가 자동 병합 |

---

## 5. Dynamic Router 구현

### 5.1 Enrichment Rule 정의

```python
@dataclass(frozen=True)
class EnrichmentRule:
    """Intent 기반 Enrichment 규칙."""
    intent: str
    enrichments: tuple[str, ...]
    description: str = ""


@dataclass
class ConditionalEnrichment:
    """조건부 Enrichment 규칙."""
    node: str
    condition: Callable[[dict[str, Any]], bool]
    exclude_intents: tuple[str, ...] = ()
    description: str = ""
```

### 5.2 규칙 설정

```python
# Intent → 자동 추가할 enrichment 노드들
ENRICHMENT_RULES: dict[str, EnrichmentRule] = {
    "waste": EnrichmentRule(
        intent="waste",
        enrichments=("weather",),
        description="분리배출 질문 시 날씨 팁 추가",
    ),
    "bulk_waste": EnrichmentRule(
        intent="bulk_waste",
        enrichments=("weather",),
        description="대형폐기물 질문 시 날씨 팁 추가",
    ),
}

# 조건부 Enrichment (state 기반)
CONDITIONAL_ENRICHMENTS: list[ConditionalEnrichment] = [
    ConditionalEnrichment(
        node="weather",
        condition=lambda state: (
            state.get("user_location") is not None
            and state.get("intent") not in ("weather", "general", "character")
        ),
        exclude_intents=("weather", "image_generation"),
        description="위치 정보가 있고 관련 intent면 날씨 추가",
    ),
]
```

### 5.3 Router Factory

```python
def create_dynamic_router(
    enable_multi_intent: bool = True,
    enable_enrichment: bool = True,
    enable_conditional: bool = True,
):
    """동적 라우터 팩토리."""

    def dynamic_router(state: dict[str, Any]) -> list[Send]:
        """Send API로 동적 병렬 라우팅.

        실행 순서:
        1. 주 intent → 해당 노드
        2. additional_intents → 각각 노드 (multi-intent fanout)
        3. enrichment 규칙 → 보조 노드 자동 추가
        4. 조건부 enrichment → state 조건 만족 시 추가
        """
        sends: list[Send] = []
        activated_nodes: set[str] = set()

        primary_intent = state.get("intent", "general")
        additional_intents = state.get("additional_intents", [])

        # 1. 주 intent 노드
        primary_node = INTENT_TO_NODE.get(primary_intent, "general")
        sends.append(Send(primary_node, state))
        activated_nodes.add(primary_node)

        # 2. Multi-intent fanout (추가 intents)
        if enable_multi_intent and additional_intents:
            for intent in additional_intents:
                node = INTENT_TO_NODE.get(intent, intent)
                if node not in activated_nodes:
                    sends.append(Send(node, state))
                    activated_nodes.add(node)

        # 3. Intent 기반 Enrichment
        if enable_enrichment and primary_intent in enrichment_rules:
            rule = enrichment_rules[primary_intent]
            for enrichment_node in rule.enrichments:
                if enrichment_node not in activated_nodes:
                    sends.append(Send(enrichment_node, state))
                    activated_nodes.add(enrichment_node)

        # 4. 조건부 Enrichment
        if enable_conditional:
            for rule in conditional_enrichments:
                if rule.node not in activated_nodes:
                    if primary_intent not in rule.exclude_intents:
                        if rule.condition(state):
                            sends.append(Send(rule.node, state))
                            activated_nodes.add(rule.node)

        return sends

    return dynamic_router
```

---

## 6. 예시 시나리오 상세

### 6.1 Multi-Intent + Enrichment 전체 흐름

```
사용자: "종이 어떻게 버려? 그리고 수거함도 알려줘"

┌─────────────────────────────────────────────────────────────────────────┐
│ Step 1: Intent Classification                                           │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  IntentClassifierService:                                               │
│    - 키워드 감지: "버려" (WASTE), "수거함" (COLLECTION_POINT)           │
│    - Multi-Intent 후보 키워드: "그리고" ✅                              │
│    - LLM 호출 → Structured Output                                       │
│                                                                         │
│  결과:                                                                   │
│    - intent: "waste"                                                    │
│    - additional_intents: ["collection_point"]                           │
│    - is_multi: true                                                     │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
                                   │
                                   ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ Step 2: Dynamic Router                                                  │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  1. 주 Intent:      waste → Send("waste_rag", state)                    │
│  2. Multi-Intent:   collection_point → Send("collection_point", state)  │
│  3. Enrichment:     waste → weather → Send("weather", state)            │
│                                                                         │
│  결과: 3개 노드 병렬 Send                                                │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
                                   │
                                   ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ Step 3: 병렬 실행                                                        │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  ┌──────────────┐     ┌──────────────────┐     ┌─────────────┐         │
│  │  waste_rag   │     │ collection_point │     │   weather   │         │
│  │  (Qdrant)    │     │   (KECO API)     │     │ (기상청 API) │         │
│  └──────┬───────┘     └────────┬─────────┘     └──────┬──────┘         │
│         │                      │                      │                 │
│         ▼                      ▼                      ▼                 │
│  "종이는 물기 없이     "강남구 의류수거함 3곳:    "오늘 오후 비 예보    │
│   펴서 묶어 배출"      역삼동, 논현동, 삼성동"    (강수확률 80%)"       │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
                                   │
                                   ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ Step 4: Aggregation & Answer                                            │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  Aggregator:                                                            │
│    - disposal_rules: "종이는 물기 없이 펴서 묶어 배출"                   │
│    - collection_point_context: "강남구 의류수거함 3곳..."               │
│    - weather_context: "오늘 오후 비 예보 (강수확률 80%)"                │
│                                                                         │
│  Answer Node (LLM):                                                     │
│    "종이류는 물기를 제거하고 펴서 묶어 배출해주세요.                     │
│                                                                         │
│     근처 수거함 위치:                                                    │
│     - 역삼동 OO아파트 앞                                                 │
│     - 논현동 XX빌딩 옆                                                   │
│     - 삼성동 YY공원 입구                                                 │
│                                                                         │
│     오늘 오후 비가 예보되어 있으니 종이류가 젖지 않게 보관해주세요!"    │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

### 6.2 Chain-of-Intent 예시 (계획)

> ⚠️ 아래 시나리오는 `previous_intents` 통합 완료 후 동작 예정

```
┌─────────────────────────────────────────────────────────────────────────┐
│ 멀티턴 대화 예시 (통합 완료 후)                                           │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  Turn 1:                                                                │
│    User: "냉장고 버리려면 어떻게 해?"                                    │
│    Intent: BULK_WASTE (confidence: 0.85)                                │
│    → bulk_waste 노드 실행                                               │
│                                                                         │
│  Turn 2:                                                                │
│    User: "팔 수 있어?"                                                   │
│    - LLM 응답: "recyclable_price" (base confidence: 0.65)               │
│    - Transition Boost: BULK_WASTE → RECYCLABLE_PRICE = +0.08           │
│    - 최종 confidence: 0.73 ✅                                           │
│    → recyclable_price 노드 실행                                         │
│                                                                         │
│  Turn 3:                                                                │
│    User: "근처에 어디서 팔아?"                                           │
│    - LLM 응답: "location" (base confidence: 0.70)                       │
│    - Transition Boost: RECYCLABLE_PRICE → LOCATION = +0.10             │
│    - 최종 confidence: 0.80 ✅                                           │
│    → location 노드 실행                                                 │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 7. Aggregator Node 구현

Send API로 병렬 실행된 결과들은 LangGraph가 자동으로 state에 병합합니다.
Aggregator는 이 병합된 결과를 **검증하고 로깅**합니다.

```python
async def aggregator_node(state: dict[str, Any]) -> dict[str, Any]:
    """병렬 실행 결과 수집 및 정리."""

    # 수집된 컨텍스트 필드들
    context_fields = {
        "disposal_rules": "RAG 검색 결과",
        "character_context": "캐릭터 정보",
        "location_context": "장소 정보",
        "web_search_results": "웹 검색 결과",
        "bulk_waste_context": "대형폐기물 정보",
        "recyclable_price_context": "재활용 시세",
        "weather_context": "날씨 정보",
        "collection_point_context": "수거함 위치",
        "image_generation_context": "이미지 생성",
    }

    # 수집된 컨텍스트 확인 및 로깅
    collected = []
    for field, description in context_fields.items():
        value = state.get(field)
        if value is not None:
            if isinstance(value, dict):
                if value.get("success", True):
                    collected.append(description)
            else:
                collected.append(description)

    logger.info(
        "Aggregator: contexts collected",
        extra={"job_id": job_id, "collected": collected},
    )

    return state  # 병합은 이미 LangGraph가 처리
```

---

## 8. 테스트

### 8.1 테스트 구조

**파일**: `tests/unit/infrastructure/orchestration/langgraph/routing/test_dynamic_router.py`

```python
class TestDynamicRouter:
    """동적 라우터 테스트."""

    def test_primary_intent_routing(self):
        """주 intent → 해당 노드로 라우팅."""
        router = create_dynamic_router(
            enable_multi_intent=False,
            enable_enrichment=False,
            enable_conditional=False,
        )
        state = {"intent": "waste", "job_id": "test-123"}
        sends = router(state)

        assert len(sends) == 1
        assert sends[0].node == "waste_rag"

    def test_multi_intent_fanout(self):
        """Multi-intent → 여러 노드 병렬 Send."""
        router = create_dynamic_router(enable_multi_intent=True)
        state = {
            "intent": "waste",
            "additional_intents": ["collection_point", "character"],
        }
        sends = router(state)

        assert len(sends) == 3
        nodes = {s.node for s in sends}
        assert nodes == {"waste_rag", "collection_point", "character"}

    def test_enrichment_waste_adds_weather(self):
        """waste intent → weather enrichment 자동 추가."""
        router = create_dynamic_router(enable_enrichment=True)
        state = {"intent": "waste"}
        sends = router(state)

        assert len(sends) == 2
        nodes = {s.node for s in sends}
        assert nodes == {"waste_rag", "weather"}
```

### 8.2 테스트 커버리지

| 테스트 케이스 | 검증 내용 |
|-------------|----------|
| `test_primary_intent_routing` | 주 intent만 라우팅 |
| `test_multi_intent_fanout` | additional_intents 병렬 처리 |
| `test_multi_intent_deduplication` | 중복 intent 제거 |
| `test_enrichment_waste_adds_weather` | waste → weather 자동 추가 |
| `test_enrichment_bulk_waste_adds_weather` | bulk_waste → weather 자동 추가 |
| `test_conditional_enrichment_with_location` | user_location 있으면 weather 추가 |
| `test_conditional_enrichment_excluded_intent` | 제외 intent면 enrichment 안 함 |
| `test_full_dynamic_routing` | 모든 기능 통합 테스트 |

**총 17개 테스트 케이스** (langgraph 미설치 시 자동 skip)

---

## 9. 설계 결정

### 9.1 왜 Send API인가?

| 대안 | 장점 | 단점 |
|------|------|------|
| **순차 실행** | 단순함 | 느림 (N번 대기) |
| **asyncio.gather** | 병렬 가능 | LangGraph 상태 관리 불가 |
| **Send API** | 병렬 + 상태 자동 병합 | LangGraph 의존 |

**결론**: Send API는 LangGraph 생태계 내에서 **가장 자연스럽게 병렬 처리**를 지원합니다.

### 9.2 규칙 기반 Enrichment

```python
# ❌ 하드코딩
if intent == "waste":
    sends.append(Send("weather", state))

# ✅ 규칙 기반
ENRICHMENT_RULES = {
    "waste": EnrichmentRule(intent="waste", enrichments=("weather",)),
}
```

**장점**: 규칙 추가/수정이 쉬움, 테스트 시 규칙 주입 가능, 로깅에 규칙 설명 포함

### 9.3 중복 제거 전략

```python
activated_nodes: set[str] = set()

# 노드 추가 전 항상 체크
if node not in activated_nodes:
    sends.append(Send(node, state))
    activated_nodes.add(node)
```

---

## 10. 향후 계획

| 항목 | 설명 | 우선순위 |
|------|------|---------|
| **Chain-of-Intent 통합** | `previous_intents` 저장/전달 로직 완성 | P1 |
| **Vector DB 마이그레이션** | Local JSON → Qdrant 등 Vector DB | P2 |
| **Intent 캐싱** | 동일 질문 반복 시 LLM 호출 스킵 | P2 |
| **Conditional Node Skip** | 클라이언트 미제공 시 노드 자체 스킵 | P3 |
| **Enrichment 우선순위** | 여러 enrichment 중 우선순위 지정 | P4 |
| **A/B 테스트** | 정적 vs 동적 라우팅 품질 비교 | P4 |

---

## 11. 참고 자료

### 논문
- **Multi-Intent ICL**: arxiv:2304.11384
- **Chain-of-Intent**: arxiv:2411.14252 (CIKM '25)

### LangGraph
- **Send API**: [Branching and Merging](https://langchain-ai.github.io/langgraph/how-tos/branching/)
- **Multi-Agent Workflows**: [Multi-Agent Systems](https://langchain-ai.github.io/langgraph/tutorials/multi_agent/)
- **LangGraph 1.0 Release**: [What's New](https://blog.langchain.dev/langgraph-1-0/)

---

**작성일**: 2026-01-16
**적용 서비스**: `apps/chat_worker`
**관련 커밋**: `54f71eab` (feat: add dynamic routing with Send API), `4b207c70` (feat: extend intent classification)
**테스트**: `tests/unit/.../routing/test_dynamic_router.py` (17 cases)
