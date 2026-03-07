# ADR: Chat Worker Production Architecture

> **상태**: Reviewed (타임아웃 검증 완료)
> **일자**: 2026-01-16
> **관련 ADR**:
> - [multi-intent-enhancement-adr.md](./multi-intent-enhancement-adr.md)
> - [chat-worker-prompt-strategy-adr.md](./chat-worker-prompt-strategy-adr.md)
>
> **리뷰 히스토리**:
> | 날짜 | 내용 |
> |------|------|
> | 2026-01-16 | 초안 작성 (5가지 리뷰 피드백 반영) |
> | 2026-01-16 | 타임아웃 검증: 실제 클라이언트 구현 기반으로 NodePolicy 테이블 수정, P0 항목 추가 |

---

## 1. Overview (개요)

Chat Worker의 "의도 분류 → 라우팅 → 병렬 실행 → 집계 → 답변" 파이프라인을 Production 환경에서 안정적으로 운영하기 위한 아키텍처 명세입니다.

### 1.1 핵심 설계 원칙

| 원칙 | 설명 |
|------|------|
| **Fail-Safe** | 부분 실패 시에도 서비스 유지 |
| **Observable** | 각 단계의 상태/지연/오류 추적 가능 |
| **Graceful Degradation** | 외부 API 장애 시 품질을 낮추되 응답 보장 |
| **Bounded Latency** | 전체 응답 시간 SLA 보장 (P95 < 5s) |

---

## 2. IntentResult Schema (의도 분류 결과 스키마)

### 2.1 현재 vs 개선

```python
# AS-IS: 기본 필드만 존재
@dataclass(frozen=True)
class IntentResult:
    intent: Intent
    complexity: QueryComplexity
    confidence: float
    raw_response: str | None

# TO-BE: 판단 근거 + 신호 분리
@dataclass(frozen=True)
class IntentResult:
    intent: Intent
    complexity: QueryComplexity
    confidence: float                    # 0.0 ~ 1.0
    rationale: str                       # LLM 판단 근거
    signals: IntentSignals               # 신뢰도 구성 요소
    additional_intents: list[Intent]     # Multi-Intent 시 추가 의도
    raw_response: str | None

@dataclass(frozen=True)
class IntentSignals:
    """신뢰도 계산에 기여한 신호들."""
    llm_confidence: float       # LLM 원본 신뢰도
    keyword_boost: float        # 키워드 매칭 보정치 (-0.3 ~ +0.2)
    transition_boost: float     # Chain-of-Intent 보정치 (0 ~ 0.15)
    length_penalty: float       # 짧은 메시지 패널티 (0 ~ -0.2)

    @property
    def final_confidence(self) -> float:
        """최종 신뢰도 계산."""
        raw = self.llm_confidence + self.keyword_boost + self.transition_boost + self.length_penalty
        return max(0.0, min(1.0, raw))
```

### 2.2 Rationale 추출 전략

```python
# Structured Output으로 판단 근거 강제
class IntentClassificationSchema(BaseModel):
    intent: str = Field(description="분류된 의도")
    confidence: float = Field(ge=0.0, le=1.0)
    rationale: str = Field(
        description="판단 근거를 한 문장으로 설명",
        examples=["사용자가 폐기물 분류 방법을 물어봄"]
    )
```

### 2.3 Fallback 분기 정책

```
┌─────────────────────────────────────────────────────────────────┐
│                    Confidence-based Routing                      │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  confidence >= 0.8  ──────────────────▶  Primary Node 실행       │
│                                                                  │
│  0.6 <= confidence < 0.8  ────────────▶  Primary Node 실행       │
│                                          + Fallback 준비         │
│                                                                  │
│  0.4 <= confidence < 0.6  ────────────▶  Web Search로 보강       │
│                                          + Clarification 고려    │
│                                                                  │
│  confidence < 0.4  ───────────────────▶  Clarification 요청      │
│                                          (재질문)                │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## 3. NodePolicy (노드 실행 정책)

### 3.1 정책 스키마

```python
@dataclass(frozen=True)
class NodePolicy:
    """노드별 실행 정책."""
    node_name: str
    timeout_ms: int              # 개별 노드 타임아웃
    retry_count: int             # 재시도 횟수
    retry_backoff_ms: int        # 재시도 간격
    circuit_breaker_threshold: int  # 연속 실패 허용 횟수
    circuit_breaker_reset_ms: int   # 회로 차단기 리셋 시간
    fail_mode: FailMode          # FAIL_OPEN | FAIL_CLOSE | FAIL_FALLBACK
    fallback_node: str | None    # 실패 시 대체 노드
    is_required: bool            # 필수 노드 여부
    max_concurrency: int         # 동시 실행 제한
```

### 3.2 노드별 정책 테이블

> **Note**: 타임아웃 값은 실제 클라이언트 구현 기반으로 산정됨 (2026-01-16 검증)

| Node | Timeout | Retry | CB Threshold | Fail Mode | Fallback | Required | 근거 |
|------|---------|-------|--------------|-----------|----------|----------|------|
| **waste_rag** | 1000ms | 1 | 5 | FAIL_FALLBACK | web_search | Yes | 로컬 파일 캐싱 (즉시) |
| **bulk_waste** | 10000ms | 2 | 5 | FAIL_FALLBACK | web_search | Yes | MOIS API: 15s 설정 |
| **character** | 3000ms | 1 | 3 | FAIL_OPEN | None | No | gRPC (LocalCache ~1-3ms) |
| **location** | 3000ms | 2 | 5 | FAIL_FALLBACK | general | Yes | gRPC (PostGIS ~100ms) |
| **collection_point** | 10000ms | 2 | 5 | FAIL_FALLBACK | web_search | No | KECO API: 15s 설정 |
| **weather** | 5000ms | 1 | 3 | FAIL_OPEN | None | No | KMA API: 10s 설정 |
| **web_search** | 10000ms | 2 | 5 | FAIL_FALLBACK | general | No | DDG: 10s, Tavily 기본값 |
| **image_generation** | 30000ms | 1 | 3 | FAIL_OPEN | None | No | DALL-E 생성: 10-30초 |
| **general** | 30000ms | 2 | 3 | FAIL_CLOSE | None | Yes | LLM API: 60s (read) |

#### 타임아웃 산정 원칙

1. **클라이언트 설정의 50-70%**: 여유를 두되 전체 SLA를 넘지 않도록
2. **공공데이터 API**: 응답 지연이 잦아 클라이언트 설정에 가깝게 (KECO, MOIS, KMA)
3. **LLM 호출 노드**: 스트리밍이 아닌 경우 최소 30초 확보 (general, answer)
4. **로컬 처리 노드**: 1초 미만 (waste_rag - 파일 캐싱)

### 3.3 Fail Mode 설명

| Mode | 동작 | 사용 케이스 |
|------|------|------------|
| **FAIL_OPEN** | 실패해도 다음 단계 진행, 해당 컨텍스트만 빠짐 | weather, character (보조 정보) |
| **FAIL_CLOSE** | 실패 시 전체 파이프라인 중단 | general (최후의 보루) |
| **FAIL_FALLBACK** | fallback_node로 대체 실행 | RAG 노드들 (핵심 정보) |

### 3.4 Circuit Breaker 상태 다이어그램

```
                          성공
                    ┌──────────────┐
                    │              │
                    ▼              │
┌─────────┐    ┌─────────┐    ┌─────────┐
│ CLOSED  │───▶│  OPEN   │───▶│HALF_OPEN│
│ (정상)  │    │ (차단)  │    │ (테스트)│
└─────────┘    └─────────┘    └─────────┘
     ▲              │              │
     │              │              │
     │         reset_ms 후         │
     │              │              │
     └──────────────┴──────────────┘
                 실패
```

---

## 4. Dynamic Router (동적 라우팅)

### 4.1 Intent → Node 매핑

```python
INTENT_TO_NODE: dict[str, str] = {
    "waste": "waste_rag",
    "bulk_waste": "bulk_waste",
    "character": "character",
    "location": "location",
    "collection_point": "collection_point",
    "weather": "weather",
    "web_search": "web_search",
    "recyclable_price": "recyclable_price",
    "image_generation": "image_generation",
    "general": "general",
}
```

### 4.2 Enrichment Rules (보강 규칙)

```python
@dataclass
class EnrichmentRule:
    """자동 보강 노드 규칙."""
    trigger_intents: set[str]     # 트리거 의도
    enrichment_nodes: list[str]   # 추가 실행 노드
    condition: Callable[[State], bool] | None  # 조건 (선택)
    is_soft_dependency: bool      # 늦으면 skip 가능 여부

ENRICHMENT_RULES: list[EnrichmentRule] = [
    # waste/bulk_waste → weather (날씨에 따른 분리배출 팁)
    EnrichmentRule(
        trigger_intents={"waste", "bulk_waste"},
        enrichment_nodes=["weather"],
        condition=lambda s: s.get("user_location") is not None,
        is_soft_dependency=True,  # 늦으면 없이 진행
    ),
    # location → weather (방문 시 날씨 정보)
    EnrichmentRule(
        trigger_intents={"location", "collection_point"},
        enrichment_nodes=["weather"],
        condition=lambda s: s.get("user_location") is not None,
        is_soft_dependency=True,
    ),
]
```

### 4.3 중복 호출 방지

```python
def dynamic_router(state: dict[str, Any]) -> list[Send]:
    """Send API 기반 동적 라우팅."""
    sends: list[Send] = []
    activated_nodes: set[str] = set()  # 중복 방지

    # 1. Primary Intent
    primary_node = INTENT_TO_NODE[state["intent"]]
    if primary_node not in activated_nodes:
        sends.append(Send(primary_node, state))
        activated_nodes.add(primary_node)

    # 2. Multi-Intent Fanout
    for intent in state.get("additional_intents", []):
        node = INTENT_TO_NODE.get(intent)
        if node and node not in activated_nodes:
            sends.append(Send(node, state))
            activated_nodes.add(node)

    # 3. Enrichment (조건부)
    for rule in ENRICHMENT_RULES:
        if state["intent"] in rule.trigger_intents:
            if rule.condition is None or rule.condition(state):
                for enrich_node in rule.enrichment_nodes:
                    if enrich_node not in activated_nodes:
                        sends.append(Send(enrich_node, state))
                        activated_nodes.add(enrich_node)

    return sends
```

---

## 5. Aggregation Rules (집계 규칙)

### 5.1 NodeResult 표준 스키마

```python
@dataclass
class NodeResult:
    """노드 실행 결과 표준 형식."""
    node_name: str
    status: NodeStatus           # SUCCESS | FAILED | TIMEOUT | SKIPPED
    data: dict[str, Any] | None  # 성공 시 데이터
    error: str | None            # 실패 시 에러 메시지
    latency_ms: int              # 실행 시간
    retry_count: int             # 재시도 횟수
    timestamp: datetime

class NodeStatus(Enum):
    SUCCESS = "success"
    FAILED = "failed"
    TIMEOUT = "timeout"
    SKIPPED = "skipped"          # soft dependency가 늦어서 skip
```

### 5.2 Required vs Optional 분류

```python
# 의도별 필수/선택 노드 정의
REQUIRED_CONTEXTS: dict[str, set[str]] = {
    "waste": {"disposal_rules"},           # RAG 결과 필수
    "bulk_waste": {"bulk_waste_context"},  # 대형폐기물 정보 필수
    "location": {"location_context"},      # 위치 정보 필수
    "collection_point": {"collection_point_context"},
    "web_search": {"web_search_results"},
    "general": set(),                      # 필수 없음
}

OPTIONAL_CONTEXTS: set[str] = {
    "weather_context",
    "character_context",
    "image_generation_context",
    "recyclable_price_context",
}
```

### 5.3 Aggregator 로직

```python
async def aggregator_node(state: dict[str, Any]) -> dict[str, Any]:
    """병렬 실행 결과 집계 및 검증."""
    results: list[NodeResult] = state.get("node_results", [])
    intent = state["intent"]

    # 1. Required 컨텍스트 검증
    required_fields = REQUIRED_CONTEXTS.get(intent, set())
    missing_required = []

    for field in required_fields:
        if not state.get(field):
            missing_required.append(field)

    # 2. Required 누락 시 Fallback 트리거
    if missing_required:
        logger.warning(f"Missing required: {missing_required}")
        state["trigger_fallback"] = True
        state["fallback_reason"] = FallbackReason.MISSING_REQUIRED_CONTEXT
        return state

    # 3. Optional 컨텍스트 수집 (없어도 진행)
    collected_optional = [
        field for field in OPTIONAL_CONTEXTS
        if state.get(field) is not None
    ]

    # 4. 메트릭 기록
    state["aggregation_metadata"] = {
        "total_nodes": len(results),
        "successful_nodes": sum(1 for r in results if r.status == NodeStatus.SUCCESS),
        "failed_nodes": sum(1 for r in results if r.status == NodeStatus.FAILED),
        "skipped_nodes": sum(1 for r in results if r.status == NodeStatus.SKIPPED),
        "total_latency_ms": sum(r.latency_ms for r in results),
        "collected_optional": collected_optional,
    }

    return state
```

### 5.4 Soft Dependency 처리 (Weather 예시)

```python
async def weather_node_with_timeout(state: dict[str, Any]) -> dict[str, Any]:
    """Weather는 soft dependency - 늦으면 skip."""
    policy = NODE_POLICIES["weather"]

    try:
        async with asyncio.timeout(policy.timeout_ms / 1000):
            weather_data = await fetch_weather(state["user_location"])
            return {"weather_context": weather_data, "weather_status": "success"}
    except asyncio.TimeoutError:
        logger.info("Weather timeout - skipping (soft dependency)")
        return {"weather_context": None, "weather_status": "skipped"}
    except Exception as e:
        logger.warning(f"Weather failed: {e}")
        return {"weather_context": None, "weather_status": "failed"}
```

---

## 6. Chain-of-Intent Boost (의도 전이 부스트)

### 6.1 전이 확률 테이블

```python
INTENT_TRANSITION_BOOST: dict[Intent, dict[Intent, float]] = {
    Intent.WASTE: {
        Intent.LOCATION: 0.15,           # "버리고 싶은데 센터 어디?"
        Intent.COLLECTION_POINT: 0.10,   # "버리고 싶은데 수거함 어디?"
        Intent.CHARACTER: 0.05,          # "버렸어, 캐릭터는?"
        Intent.BULK_WASTE: 0.08,         # "이건 대형폐기물?"
    },
    Intent.LOCATION: {
        Intent.WASTE: 0.10,              # "센터 갔는데, 이건 어떻게?"
        Intent.WEATHER: 0.08,            # "센터 가려는데 날씨는?"
    },
    Intent.GENERAL: {
        Intent.WASTE: 0.10,              # 인사 후 본론
        Intent.CHARACTER: 0.08,
        Intent.WEB_SEARCH: 0.05,
    },
    Intent.CHARACTER: {
        Intent.WASTE: 0.10,              # "캐릭터 봤어, 이건 어떻게 버려?"
        Intent.LOCATION: 0.08,
    },
    Intent.BULK_WASTE: {
        Intent.LOCATION: 0.12,           # "대형폐기물인데 어디서 버려?"
        Intent.WASTE: 0.10,              # "대형은 아니고 일반 폐기물이야"
    },
    Intent.COLLECTION_POINT: {
        Intent.WASTE: 0.10,              # "수거함 갔는데, 이건?"
        Intent.WEATHER: 0.05,
    },
}
```

### 6.2 부스트 적용 규칙

```python
MAX_TRANSITION_BOOST = 0.15          # 부스트 상한
MIN_LAST_INTENT_CONFIDENCE = 0.7     # 이전 의도 신뢰도 최소값

def _apply_transition_boost(
    self,
    intent: Intent,
    previous_intents: list[tuple[str, float]],  # (intent, confidence)
) -> float:
    """이전 의도 기반 신뢰도 보정 (오류 전파 방지 포함)."""
    if not previous_intents:
        return 0.0

    last_intent_str, last_confidence = previous_intents[-1]

    # 오류 전파 방지: 이전 의도 신뢰도가 낮으면 부스트 미적용
    if last_confidence < MIN_LAST_INTENT_CONFIDENCE:
        logger.debug(f"Skip boost: last confidence {last_confidence:.2f} < {MIN_LAST_INTENT_CONFIDENCE}")
        return 0.0

    last_intent = Intent.from_string(last_intent_str)
    transitions = INTENT_TRANSITION_BOOST.get(last_intent, {})
    boost = transitions.get(intent, 0.0)

    # 상한 적용
    return min(boost, MAX_TRANSITION_BOOST)
```

---

## 7. Failure Scenarios (실패 시나리오)

### 7.1 시나리오 1: RAG 노드 실패

```
┌─────────────────────────────────────────────────────────────────┐
│  Scenario: waste_rag 노드가 Qdrant 연결 실패로 timeout          │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  1. waste_rag 노드 실행 (timeout: 5000ms)                       │
│     └─ Qdrant 연결 실패 → TimeoutError                          │
│                                                                  │
│  2. NodePolicy 확인                                              │
│     └─ fail_mode: FAIL_FALLBACK                                 │
│     └─ fallback_node: "web_search"                              │
│     └─ retry_count: 2 (이미 소진)                               │
│                                                                  │
│  3. Fallback 실행                                                │
│     └─ web_search 노드로 동일 쿼리 전달                         │
│     └─ "페트병 분리배출 방법" 검색                              │
│                                                                  │
│  4. 결과                                                         │
│     └─ web_search 결과로 답변 생성                              │
│     └─ 품질 저하 but 서비스 유지 ✓                              │
│                                                                  │
│  5. 메트릭 기록                                                  │
│     └─ rag_fallback_count++                                     │
│     └─ alert if fallback_rate > 10%                             │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### 7.2 시나리오 2: 외부 API 지연 (Kakao Location)

```
┌─────────────────────────────────────────────────────────────────┐
│  Scenario: Kakao API 응답 지연으로 전체 파이프라인 지연 위험    │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  1. 병렬 실행 시작 (Send API)                                   │
│     ├─ waste_rag: 1200ms 완료 ✓                                 │
│     ├─ location: 3800ms... (timeout 4000ms)                     │
│     └─ weather: skip (location 의존)                            │
│                                                                  │
│  2. Aggregator 동작                                              │
│     └─ required: disposal_rules ✓                               │
│     └─ required: location_context ⏳ (대기)                     │
│                                                                  │
│  3. Circuit Breaker 체크                                         │
│     └─ location 노드: 연속 실패 2회 (threshold: 5)              │
│     └─ 상태: CLOSED (정상)                                      │
│                                                                  │
│  4. Partial Response 전략                                        │
│     └─ location timeout 시:                                     │
│         - fallback to "general" (위치 정보 없이 일반 답변)     │
│         - 또는 캐시된 이전 위치 사용                            │
│                                                                  │
│  5. 결과                                                         │
│     └─ "위치 정보를 가져오지 못했습니다. 일반적인 안내..."     │
│     └─ 전체 응답 시간: 4200ms (SLA 준수)                        │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### 7.3 시나리오 3: Multi-Intent 부분 실패

```
┌─────────────────────────────────────────────────────────────────┐
│  Scenario: "페트병 버리고 캐릭터도 알려줘" - character 실패     │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  Intent 분류 결과:                                               │
│  - primary: waste (confidence: 0.92)                            │
│  - additional: [character] (confidence: 0.85)                   │
│                                                                  │
│  1. 병렬 실행 (Send API)                                        │
│     ├─ waste_rag: 1500ms 완료 ✓                                 │
│     │   └─ disposal_rules: {...}                                │
│     │                                                           │
│     └─ character: gRPC 연결 실패 ✗                              │
│         └─ NodePolicy: fail_mode=FAIL_OPEN                      │
│         └─ is_required: false                                   │
│                                                                  │
│  2. Aggregator 판단                                              │
│     └─ Required for "waste": disposal_rules ✓                   │
│     └─ character_context: None (FAIL_OPEN → skip)               │
│                                                                  │
│  3. Answer 생성                                                  │
│     └─ 컨텍스트: disposal_rules만 사용                          │
│     └─ 답변: "페트병은 라벨을 제거하고..."                      │
│     └─ 부가 메시지: "캐릭터 정보는 잠시 후 다시 시도해주세요"  │
│                                                                  │
│  4. 결과                                                         │
│     └─ Primary intent 답변 완료 ✓                               │
│     └─ Secondary intent 부분 실패 안내 ✓                        │
│     └─ 서비스 유지 ✓                                            │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## 8. LangGraph Pipeline (전체 흐름)

```
┌─────────────────────────────────────────────────────────────────┐
│                    Chat Worker Pipeline                          │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  [START]                                                         │
│     │                                                            │
│     ▼                                                            │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │  Intent Node                                             │    │
│  │  ├─ Two-Stage Detection (Rule → LLM)                    │    │
│  │  ├─ Chain-of-Intent Boost                               │    │
│  │  └─ Output: IntentResult (intent, confidence, signals)  │    │
│  └─────────────────────────────────────────────────────────┘    │
│     │                                                            │
│     │  confidence < 0.4? → Clarification Node                   │
│     │                                                            │
│     ▼                                                            │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │  Dynamic Router (Send API)                               │    │
│  │  ├─ Intent → Node 매핑                                  │    │
│  │  ├─ Multi-Intent Fanout                                 │    │
│  │  ├─ Enrichment Rules 적용                               │    │
│  │  └─ 중복 호출 방지 (activated_nodes)                    │    │
│  └─────────────────────────────────────────────────────────┘    │
│     │                                                            │
│     ▼                                                            │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │  Parallel Execution (Fan-out)                            │    │
│  │                                                          │    │
│  │  ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐       │    │
│  │  │waste_rag│ │character│ │location │ │ weather │       │    │
│  │  │ (RAG)   │ │ (gRPC)  │ │ (HTTP)  │ │  (API)  │       │    │
│  │  └────┬────┘ └────┬────┘ └────┬────┘ └────┬────┘       │    │
│  │       │           │           │           │             │    │
│  │       │     NodePolicy 적용 (timeout/retry/CB)          │    │
│  │       │           │           │           │             │    │
│  │  ┌────▼────┐ ┌────▼────┐ ┌────▼────┐ ┌────▼────┐       │    │
│  │  │Feedback │ │  Pass   │ │  Pass   │ │  Pass   │       │    │
│  │  │ (RAG용) │ │         │ │         │ │ (soft)  │       │    │
│  │  └────┬────┘ └────┬────┘ └────┬────┘ └────┬────┘       │    │
│  │       │           │           │           │             │    │
│  │       └───────────┴───────────┴───────────┘             │    │
│  │                       │                                  │    │
│  └───────────────────────┼──────────────────────────────────┘    │
│                          ▼                                       │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │  Aggregator (Fan-in)                                     │    │
│  │  ├─ NodeResult 수집                                     │    │
│  │  ├─ Required 컨텍스트 검증                              │    │
│  │  ├─ Missing Required → Fallback 트리거                  │    │
│  │  └─ Metadata 기록 (latency, success_rate)               │    │
│  └─────────────────────────────────────────────────────────┘    │
│     │                                                            │
│     │  trigger_fallback? → Fallback Chain                       │
│     │                                                            │
│     ▼                                                            │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │  Answer Node                                             │    │
│  │  ├─ 수집된 컨텍스트 기반 답변 생성                      │    │
│  │  ├─ 부분 실패 안내 (있으면)                             │    │
│  │  └─ SSE 스트리밍 출력                                   │    │
│  └─────────────────────────────────────────────────────────┘    │
│     │                                                            │
│     ▼                                                            │
│  [END]                                                           │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## 9. Observability (관측성)

### 9.1 핵심 메트릭

| 메트릭 | 설명 | 알림 기준 |
|--------|------|----------|
| `intent_confidence_histogram` | 의도 분류 신뢰도 분포 | P50 < 0.6 |
| `node_latency_ms` | 노드별 지연 시간 | P95 > timeout * 0.8 |
| `node_success_rate` | 노드별 성공률 | < 95% |
| `circuit_breaker_state` | 회로 차단기 상태 | OPEN 전환 시 |
| `fallback_rate` | Fallback 발생률 | > 10% |
| `aggregation_missing_required` | 필수 컨텍스트 누락 | > 5% |
| `e2e_latency_ms` | 전체 응답 시간 | P95 > 5000ms |

### 9.2 분산 추적 (OpenTelemetry)

```python
# 각 노드에 span 추가
@tracer.start_as_current_span("waste_rag_node")
async def waste_rag_node(state: dict[str, Any]) -> dict[str, Any]:
    span = trace.get_current_span()
    span.set_attribute("intent", state["intent"])
    span.set_attribute("user_id", state.get("user_id"))

    # ... 노드 로직 ...

    span.set_attribute("latency_ms", latency)
    span.set_attribute("status", result.status.value)
    return state
```

---

## 10. Interview FAQ (면접 예상 질문)

### Q1: "LLM이 틀린 intent를 뱉었을 때 시스템이 어떻게 복구하나요?"

**A**: 3단계 복구 전략을 사용합니다:

1. **Confidence 기반 분기**: 신뢰도 < 0.4면 Clarification 노드로 재질문
2. **Fallback Chain**: Primary 노드 실패 시 web_search → general 순으로 시도
3. **RAG Feedback Loop**: 답변 품질 평가 후 낮으면 다른 소스로 재시도

### Q2: "Kakao API가 느려지면 전체 답변이 같이 느려지나요? 부분 답변 전략은요?"

**A**: 느려지지 않습니다. 전략:

1. **NodePolicy timeout**: location 노드 4000ms 타임아웃
2. **FAIL_FALLBACK**: 타임아웃 시 general 노드로 대체
3. **Soft Dependency**: weather처럼 없어도 되는 건 skip 처리
4. **Circuit Breaker**: 연속 5회 실패 시 해당 노드 일시 차단

### Q3: "이 전이 부스트 때문에 오분류가 누적되면 어떻게 디버깅하나요?"

**A**: 오류 전파 방지 + 로깅 전략:

1. **Boost 상한**: MAX_TRANSITION_BOOST = 0.15
2. **이전 신뢰도 체크**: last_confidence < 0.7이면 boost 미적용
3. **IntentSignals 기록**: 각 신호 기여도 분리 저장 (llm, keyword, transition)
4. **Offline Eval**: 로그 분석으로 전이 테이블 주기적 튜닝

### Q4: "노드 간 의존성(location→weather)이 있는데 항상 병렬이 답인가요?"

**A**: 아닙니다. 의존성에 따라 분리:

1. **독립 노드**: waste_rag, character → 완전 병렬
2. **Soft Dependency**: weather → location 없어도 실행, 결과 있으면 더 좋은 답변
3. **Hard Dependency**: 현재 없음 (있으면 2-phase 그래프로 모델링)

### Q5: "중복 Send/중복 정보 발생은 어떻게 방지하나요?"

**A**: `activated_nodes` set으로 추적:

```python
activated_nodes: set[str] = set()
if node not in activated_nodes:
    sends.append(Send(node, state))
    activated_nodes.add(node)
```

Multi-intent에서 같은 노드가 여러 번 매핑되어도 1회만 실행됩니다.

---

## 11. Implementation Checklist (구현 체크리스트)

### P0: 즉시 수정 필요 (Critical Gap)

> **2026-01-16 타임아웃 검증 결과** 발견된 문제

- [ ] **gRPC 클라이언트 timeout 추가** (`character/grpc_client.py`, `location/grpc_client.py`)
  - 현재: timeout 파라미터 없이 호출 (무제한 대기 가능)
  - 수정: `stub.GetCharacterByMatch(request, timeout=3.0)` 형태로 변경
- [ ] **Image Generator timeout 추가** (`openai_responses.py`)
  - 현재: AsyncOpenAI 기본값 (10분)
  - 수정: `httpx.Timeout(connect=5.0, read=60.0)` 또는 SDK 옵션 설정

### P1: 필수 (Production Critical)

- [ ] `IntentResult`에 `rationale`, `signals` 필드 추가
- [ ] `NodePolicy` 데이터클래스 및 테이블 구현
- [ ] `NodeResult` 표준 스키마 적용
- [ ] Aggregator에 required/optional 검증 로직 추가
- [ ] Circuit Breaker 구현 (per-node)

### P2: 권장 (면접 대비)

- [ ] Soft dependency timeout 처리 (weather)
- [ ] Chain-of-Intent 부스트 상한 명시
- [ ] IntentSignals 기반 confidence 계산 분리
- [ ] OpenTelemetry span 속성 추가

### P3: 선택 (운영 고도화)

- [ ] Dynamic Policy Adjustment (A/B 테스트)
- [ ] Offline Eval 파이프라인 (전이 테이블 튜닝)
- [ ] Partial Response 전략 (일부만 준비되면 먼저 응답)

---

## 12. References (참고 자료)

- [LangGraph Send API](https://langchain-ai.github.io/langgraph/concepts/low_level/#send)
- [Circuit Breaker Pattern](https://martinfowler.com/bliki/CircuitBreaker.html)
- [OpenAI Structured Outputs](https://platform.openai.com/docs/guides/structured-outputs)
- [arxiv:2304.11384](https://arxiv.org/abs/2304.11384) - Multi-Intent ICL
- [arxiv:2411.14252](https://arxiv.org/abs/2411.14252) - Chain-of-Intent
