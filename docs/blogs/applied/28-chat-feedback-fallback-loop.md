# 이코에코(Eco²) Agent #14: Feedback Loop & Fallback Chain

> RAG 품질 평가와 다단계 Fallback 체인으로 답변 신뢰성 확보

| 항목 | 값 |
|-----|-----|
| **작성일** | 2026-01-15 |
| **버전** | v2.0 |
| **시리즈** | Eco² Agent 시리즈 |

---

## 1. 도입 배경: 왜 Feedback Loop가 필요한가?

### 1.1 RAG 시스템의 한계

분리수거 챗봇은 **RAG(Retrieval-Augmented Generation)** 기반으로 동작합니다. 사용자 질문에 맞는 규정을 검색하고, 이를 바탕으로 답변을 생성하죠.

하지만 RAG에는 근본적인 한계가 있습니다:

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    RAG 실패 시나리오                                     │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  [사용자] "오염된 배달용기 어떻게 버려?"                                │
│                                                                         │
│  ❌ 시나리오 1: 검색 결과 없음                                          │
│     → "배달용기"가 규정 DB에 없음                                       │
│     → 답변 불가                                                         │
│                                                                         │
│  ❌ 시나리오 2: 검색 결과 품질 낮음                                      │
│     → "플라스틱류" 규정은 찾았지만 "오염" 관련 정보 부족                │
│     → 불완전한 답변                                                     │
│                                                                         │
│  ❌ 시나리오 3: 질문 의도 불명확                                         │
│     → "버려"가 분리수거인지, 대형폐기물 신청인지 불분명                 │
│     → 잘못된 답변                                                       │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

### 1.2 업계 표준: Feedback Loop 패턴

이 문제를 해결하기 위해 **Feedback Loop** 패턴을 도입했습니다.

> **논문 참조**: "What Makes Large Language Models Reason in (Multi-Turn) Code Generation?"
> - RAG 결과 품질 평가 후 Fallback 결정
> - 저품질 → Web Search → General LLM 체인

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    Feedback Loop 패턴                                    │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  [질문] → [RAG 검색] → [품질 평가] → 충분? ─Yes→ [답변 생성]            │
│                              │                                          │
│                              No                                         │
│                              │                                          │
│                              ▼                                          │
│                       [Fallback 실행]                                   │
│                              │                                          │
│                    ┌─────────┼─────────┐                               │
│                    ▼         ▼         ▼                               │
│               Web Search  Clarify  General LLM                         │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 2. 핵심 의사결정

### 2.1 "Fallback 판단에 LLM을 쓰지 않는다"

가장 중요한 의사결정입니다.

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    Fallback 역할 분리                                    │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │  판단 (언제 Fallback?)          │  표현 (어떻게 응답?)          │   │
│  │  ─────────────────────          │  ─────────────────────        │   │
│  │  ✅ 규칙/상태/에러코드           │  ✅ 템플릿 (기본)             │   │
│  │  ✅ 신뢰도 임계값                │  ⚡ 경량 LLM (선택적)         │   │
│  │  ✅ 반복 실패 횟수               │                               │   │
│  │                                  │                               │   │
│  │  ❌ LLM 추측 금지                │  ❌ 복잡한 추론 금지          │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                                                                         │
│  이유: "Fallback에서까지 LLM을 믿으면, 불확실성 위에 불확실성"          │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

**왜?**
- LLM은 "모른다"고 말하기 어려움 (환각 위험)
- Fallback은 **안전망**이므로 결정론적이어야 함
- 비용/지연 시간 절약

### 2.2 품질 등급 체계

점수를 5단계로 나눠 명확한 행동을 정의합니다:

```python
class FeedbackQuality(str, Enum):
    """RAG 결과 품질 등급."""
    
    EXCELLENT = "excellent"  # 0.9+ → 바로 답변
    GOOD = "good"            # 0.7-0.9 → 바로 답변
    PARTIAL = "partial"      # 0.4-0.7 → LLM 정밀 평가 고려
    POOR = "poor"            # 0.2-0.4 → Fallback 필요
    NONE = "none"            # 0-0.2 → 즉시 Fallback
```

| 등급 | 점수 범위 | 행동 |
|------|----------|------|
| **EXCELLENT** | 0.9+ | 바로 답변 생성 |
| **GOOD** | 0.7-0.9 | 바로 답변 생성 |
| **PARTIAL** | 0.4-0.7 | (선택적) LLM 정밀 평가 |
| **POOR** | 0.2-0.4 | **Fallback 실행** |
| **NONE** | 0-0.2 | **즉시 Fallback** |

### 2.3 Fallback 사유별 전략

```python
class FallbackReason(str, Enum):
    """Fallback 사유."""
    
    RAG_NO_RESULT = "rag_no_result"           # → web_search
    RAG_LOW_QUALITY = "rag_low_quality"       # → web_search
    INTENT_LOW_CONFIDENCE = "intent_low_confidence"  # → clarify
    SUBAGENT_FAILURE = "subagent_failure"     # → retry
    LLM_ERROR = "llm_error"                   # → retry
    TIMEOUT = "timeout"                       # → retry
```

| 사유 | 1차 전략 | 2차 전략 |
|------|---------|---------|
| RAG 결과 없음 | Web Search | General LLM |
| RAG 품질 낮음 | Web Search | General LLM |
| Intent 불확실 | **Clarify** | General |
| Subagent 실패 | Retry (2회) | Skip |
| Timeout | Retry (1회) | Skip |

---

## 3. Fallback Chain 워크플로우

### 3.1 전체 흐름

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    Fallback Chain Flow                                   │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  START → intent → router                                                │
│                      │                                                  │
│          ┌───────────┼───────────┬───────────┬───────────┐             │
│          ▼           ▼           ▼           ▼           ▼             │
│       waste      character   location   web_search   general           │
│       (RAG)       (gRPC)     (gRPC)    (DuckDuckGo)  (pass)            │
│          │           │           │           │           │             │
│          ▼           │           │           │           │             │
│     [feedback]       │           │           │           │             │
│          │           │           │           │           │             │
│    score >= 0.7? ────┼───────────┼───────────┼───────────┤             │
│          │ No        │           │           │           │             │
│          ▼           │           │           │           │             │
│    [web_search]      │           │           │           │             │
│          │           │           │           │           │             │
│    results? ─────────┼───────────┼───────────┼───────────┤             │
│          │ No        │           │           │           │             │
│          ▼           │           │           │           │             │
│    [general_llm]     │           │           │           │             │
│          │           │           │           │           │             │
│          └───────────┴───────────┴───────────┴───────────┘             │
│                                  │                                      │
│                                  ▼                                      │
│                               answer → END                              │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

### 3.2 Fallback Chain 정의

```python
# 체인 정의: 각 실패 유형별 다음 전략
FALLBACK_CHAIN = {
    "rag": ["web_search", "general_llm"],      # RAG 실패 → 웹 → 일반 LLM
    "web_search": ["general_llm"],              # 웹 실패 → 일반 LLM
    "character": ["retry", "skip"],             # 캐릭터 실패 → 재시도 → 스킵
    "location": ["retry", "skip"],              # 위치 실패 → 재시도 → 스킵
    "intent": ["clarify", "general"],           # 의도 불명 → 질문 → 일반
}
```

### 3.3 Clarification 메시지 (템플릿)

```python
CLARIFICATION_MESSAGES = {
    "waste": "어떤 물건의 분리수거 방법이 궁금하신가요? 🤔 "
             "조금 더 구체적으로 알려주시면 정확히 안내해드릴게요!",
    
    "location": "어떤 위치 정보가 필요하신가요? "
                "수거함 위치, 대형폐기물 신청처 등 구체적으로 알려주세요! 📍",
    
    "character": "이코에 대해 더 알고 싶으신 점이 있으신가요? "
                 "무엇이든 물어보세요! 🌱",
    
    "general": "죄송해요, 질문을 정확히 이해하지 못했어요. "
               "조금 더 자세히 설명해주시겠어요? 🙏",
}
```

---

## 4. 품질 평가 로직

### 4.1 Rule 기반 빠른 평가

LLM 호출 없이 규칙으로 빠르게 평가합니다:

```python
class FeedbackEvaluatorService:
    """규칙 기반 품질 평가 (Port 의존 없음)."""

    def evaluate_by_rules(
        self,
        query: str,
        rag_results: dict | None,
    ) -> FeedbackResult:
        """규칙 기반 품질 평가.
        
        평가 기준 (총 1.0점):
        1. 결과 존재 여부 (0.3)
        2. 카테고리 매칭 (0.2)
        3. 정보 풍부도 (0.2)
        4. 키워드 매칭 (0.3)
        """
        if not rag_results:
            return FeedbackResult.no_result()

        score = 0.0
        
        # 1. 데이터 존재 여부 (0.3)
        data = rag_results.get("data", {})
        if data:
            score += 0.3

        # 2. 카테고리 매칭 (0.2)
        if rag_results.get("category"):
            score += 0.2

        # 3. 세부 정보 풍부도 (0.2)
        disposal_info = data.get("disposal_info", [])
        if disposal_info and len(disposal_info) > 0:
            score += 0.2

        # 4. 키워드 매칭 (0.3)
        query_keywords = set(query.lower().split())
        content_str = str(data).lower()
        matched = sum(1 for kw in query_keywords if kw in content_str)
        keyword_ratio = matched / max(len(query_keywords), 1)
        score += 0.3 * keyword_ratio

        return FeedbackResult.from_score(score)
```

### 4.2 LLM 정밀 평가 (선택적)

경계선 품질(PARTIAL, POOR)일 때만 LLM을 호출합니다:

```python
def needs_llm_evaluation(self, rule_result: FeedbackResult) -> bool:
    """LLM 정밀 평가 필요 여부.
    
    GOOD 이상이면 LLM 평가 불필요 (비용 절약).
    """
    return rule_result.quality not in (
        FeedbackQuality.EXCELLENT,
        FeedbackQuality.GOOD,
    )
```

---

## 5. Fallback 실행 로직

### 5.1 FallbackOrchestrator

```python
class FallbackOrchestrator:
    """Fallback 체인 오케스트레이터."""

    def __init__(self, max_retries: int = 2):
        self._max_retries = max_retries

    async def execute_fallback(
        self,
        reason: FallbackReason,
        query: str,
        state: dict,
        web_search_client: WebSearchPort | None = None,
    ) -> FallbackResult:
        """Fallback 실행."""
        
        strategy = self._get_next_strategy(reason)

        if strategy == "web_search":
            return await self._execute_web_search_fallback(
                query, reason, web_search_client
            )
        elif strategy == "clarify":
            return self._execute_clarification_fallback(query, state, reason)
        elif strategy == "retry":
            return await self._execute_retry_fallback(state, reason)
        elif strategy == "general_llm":
            return self._execute_general_llm_fallback(query, reason)
        else:
            return FallbackResult.skip_fallback(reason)
```

### 5.2 Web Search Fallback

```python
async def _execute_web_search_fallback(
    self,
    query: str,
    reason: FallbackReason,
    web_search_client: WebSearchPort | None,
) -> FallbackResult:
    """웹 검색 Fallback."""
    
    if not web_search_client:
        return FallbackResult.skip_fallback(reason)

    try:
        # 분리수거 키워드 추가
        search_query = f"{query} 분리수거 방법"
        response = await web_search_client.search(
            query=search_query,
            max_results=3,
            region="kr-kr",
        )

        if response.results:
            return FallbackResult.web_search_fallback(
                {"results": [r.to_dict() for r in response.results]},
                reason,
            )
        else:
            return FallbackResult.skip_fallback(reason)

    except Exception as e:
        logger.error(f"Web search fallback failed: {e}")
        return FallbackResult.skip_fallback(reason)
```

### 5.3 General LLM Fallback (최후의 수단)

```python
def _execute_general_llm_fallback(
    self,
    query: str,
    reason: FallbackReason,
) -> FallbackResult:
    """일반 LLM Fallback.
    
    RAG/웹 검색 모두 실패 시 LLM 지식 기반 답변.
    """
    return FallbackResult(
        success=True,
        strategy_used="general_llm",
        reason=reason,
        next_node="answer",
        message="정확한 분리수거 정보를 찾지 못했지만, "
                "제가 아는 내용으로 도와드릴게요! 📚",
        metadata={"use_llm_knowledge": True},
    )
```

---

## 6. Fallback 트리거 규칙 (전체)

| # | 트리거 | 조건 | 1차 액션 | 2차 액션 |
|---|--------|------|---------|---------|
| 1 | RAG 결과 없음 | `disposal_rules == None` | Web Search | General LLM |
| 2 | RAG 저품질 | `score < 0.4` | Web Search | General LLM |
| 3 | Intent 신뢰도 낮음 | `confidence < 0.3` | **Clarify** | General |
| 4 | 위치 정보 필요 | `intent == location && !location` | **HITL** | - |
| 5 | Subagent 실패 | `subagent_error` | Retry (2회) | Skip |
| 6 | LLM 오류 | `llm_error` | Retry (2회) | Skip |
| 7 | Timeout | `timeout` | Retry (1회) | Skip |
| 8 | Web Search 실패 | `results == []` | General LLM | - |
| 9 | 반복 실패 | `retry_count >= max` | Skip + 안내 | - |

---

## 7. 실제 시나리오

### 7.1 성공 케이스: RAG 품질 충분

```
[사용자] "페트병 어떻게 버려?"

1. RAG 검색 → 재활용폐기물_플라스틱류.json 찾음
2. Rule 평가 → score: 0.85 (GOOD)
3. Fallback 불필요 → 바로 답변 생성

[이코] "페트병은 내용물을 비우고 깨끗이 헹군 후 
        플라스틱 수거함에 배출하시면 돼요! 🌱"
```

### 7.2 Fallback 케이스: Web Search 성공

```
[사용자] "에어프라이어 어떻게 버려?"

1. RAG 검색 → 결과 없음 (규정 DB에 없음)
2. Rule 평가 → score: 0.0 (NONE)
3. Fallback 트리거 → reason: RAG_NO_RESULT
4. Web Search 실행 → "에어프라이어 분리수거 방법" 검색
5. 결과 3개 찾음 → 답변 생성

[이코] "에어프라이어는 소형가전으로 분류돼요! 
        가까운 주민센터나 폐가전 무상수거 서비스를 이용하세요 📱"
```

### 7.3 Clarify 케이스: 질문 불명확

```
[사용자] "이거 버려도 돼?"

1. Intent 분류 → confidence: 0.25 (낮음)
2. Fallback 트리거 → reason: INTENT_LOW_CONFIDENCE
3. Clarify 실행 → 템플릿 메시지

[이코] "어떤 물건의 분리수거 방법이 궁금하신가요? 🤔 
        조금 더 구체적으로 알려주시면 정확히 안내해드릴게요!"
```

---

## 8. 성능 및 비용 최적화

### 8.1 LLM 호출 최소화

| 단계 | LLM 사용 | 조건 |
|------|---------|------|
| Rule 평가 | ❌ | 항상 |
| LLM 정밀 평가 | ⚡ 선택적 | PARTIAL/POOR일 때만 |
| Fallback 판단 | ❌ | 항상 규칙 기반 |
| Clarify 메시지 | ❌ | 템플릿 사용 |

### 8.2 예상 비용 절감

```
기존: 모든 요청에 LLM 평가 → 100% LLM 호출
현재: Rule 기반 + 조건부 LLM → ~30% LLM 호출

비용 절감: ~70%
```

---

## 9. 요약

### 핵심 원칙

1. **규칙 기반 판단**: Fallback 결정에 LLM 추측 금지
2. **다단계 체인**: RAG → Web Search → General LLM
3. **명확화 우선**: 불확실하면 추측보다 질문
4. **비용 최적화**: LLM 호출 최소화

### 변경 파일

| 파일 | 역할 |
|------|------|
| `domain/enums/feedback_quality.py` | 품질 등급 정의 |
| `domain/enums/fallback_reason.py` | Fallback 사유 정의 |
| `application/services/feedback_evaluator.py` | Rule 기반 평가 |
| `application/services/fallback_orchestrator.py` | 체인 오케스트레이션 |
| `application/commands/evaluate_feedback_command.py` | UseCase |
| `infrastructure/nodes/feedback_node.py` | LangGraph 어댑터 |

---

*다음 포스팅: [#15 Eval Agent 고도화](./29-chat-eval-agent-enhancement.md) - Anthropic RAG 평가 패턴 적용*
