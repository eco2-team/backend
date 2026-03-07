# 이코에코(Eco²) Agent #15: Eval Agent 고도화

> Anthropic RAG 평가 패턴 적용 - Citation, Nugget, Groundedness, Just-in-Time Context

| 항목 | 값 |
|-----|-----|
| **작성일** | 2026-01-15 |
| **버전** | v3.0 |
| **시리즈** | Eco² Agent 시리즈 |
| **이전 포스팅** | [#14 Feedback Loop & Fallback Chain](./28-chat-feedback-fallback-loop.md) |
| **참조** | docs/foundations/27-rag-evaluation-strategy.md |

---

## 1. 배경: 기존 평가의 한계

### 1.1 기존 프롬프트 문제점

```json
// 기존 feedback_evaluation.txt 출력
{
    "relevance": 0.8,
    "completeness": 0.7,
    "accuracy": 0.9,
    "overall_score": 0.8,
    "suggestions": ["추가 검색 필요", "..."],
    "explanation": "평가 이유"
}
```

| 문제 | 설명 |
|------|------|
| **모호성** | "0.7점"이 무엇을 의미하는지 불명확 |
| **비재현성** | 같은 입력에 다른 점수 |
| **디버깅 불가** | 왜 그 점수인지 추적 불가 |
| **액션 연결 부재** | "추가 검색 필요"가 구체적이지 않음 |

### 1.2 Anthropic 연구 기반 개선 방향

| 출처 | 핵심 인사이트 | 적용 |
|------|-------------|------|
| **CitationAgent** | 모든 판단에 근거(Evidence) 명시 | Phase 1 |
| **TREC RAG Track** | Nugget 기반 완전성 측정 | Phase 2 |
| **RAGAS Framework** | Groundedness/Faithfulness 분리 | Phase 3 |
| **Context Engineering** | Just-in-Time 구체적 행동 | Phase 4 |

---

## 2. Phase 1-4 통합 구현

### 2.1 개선된 프롬프트 (feedback_evaluation.txt)

```
당신은 RAG 시스템의 품질을 다차원으로 평가하는 전문가입니다.

## 평가 원칙
1. 모든 판단에 근거(Citation)를 명시합니다
2. Retrieval 품질과 Generation 품질을 분리하여 평가합니다
3. 불확실한 판단은 confidence를 낮추고 이유를 명시합니다

## 평가 절차

### Step 1: 질문 분해 (Nugget 추출)
질문에 답하기 위해 필요한 핵심 정보 단위(Nugget)를 식별하세요.

### Step 2: Retrieval 평가
각 검색 결과가 어떤 Nugget을 커버하는지 매핑하세요.

### Step 3: Groundedness 평가
검색 결과가 질문의 핵심 요소를 얼마나 뒷받침하는지 평가하세요.

### Step 4: 다음 단계 제안
부족한 정보를 채우기 위한 구체적인 행동을 제안하세요.
```

### 2.2 개선된 JSON 스키마

```json
{
  "meta": {
    "eval_version": "v1.0.0"
  },

  "retrieval_quality": {
    "context_relevance": 0.85,
    "evidence": [{
      "chunk_id": "재활용폐기물_플라스틱류",
      "relevance": "high",
      "quoted_text": "내용물과 이물질, 부속품을 제거하고 물로 헹군 후 배출",
      "covers_nuggets": ["배출_방법", "세척_필요"]
    }]
  },

  "completeness": {
    "required_nuggets": [
      {"id": "nugget_1", "description": "배출 방법", "covered": true},
      {"id": "nugget_2", "description": "라벨 제거 여부", "covered": false}
    ],
    "coverage_ratio": 0.5,
    "missing_nuggets": ["nugget_2"]
  },

  "answer_quality": {
    "groundedness": 0.9,
    "groundedness_evidence": [{
      "claim": "페트병은 세척 후 배출",
      "source_chunk_id": "재활용폐기물_플라스틱류",
      "supported": true
    }],
    "hallucination_risk": "none"
  },

  "next_steps": {
    "action_required": true,
    "suggestions": [{
      "type": "additional_retrieval",
      "urgency": "immediate",
      "query": "페트병 라벨 제거 방법",
      "reason": "라벨 관련 정보 부족"
    }]
  },

  "confidence": {
    "overall": 0.8,
    "low_confidence_areas": []
  },

  "overall_score": 0.78
}
```

---

## 3. FeedbackResult DTO 확장

### 3.1 Phase 1-4 데이터 구조

```python
# application/dto/feedback_result.py

@dataclass
class EvidenceItem:
    """Phase 1: Citation 근거."""
    chunk_id: str
    relevance: Literal["high", "medium", "low"]
    quoted_text: str = ""
    covers_nuggets: list[str] = field(default_factory=list)


@dataclass
class NuggetItem:
    """Phase 2: 필수 정보 단위."""
    id: str
    description: str
    covered: bool = False


@dataclass
class GroundednessEvidence:
    """Phase 3: Groundedness 근거."""
    claim: str
    source_chunk_id: str
    supported: bool = True


@dataclass
class NextStepSuggestion:
    """Phase 4: Just-in-Time 행동."""
    type: Literal["additional_retrieval", "clarification", "none"]
    urgency: Literal["immediate", "deferred", "optional"]
    query: str = ""
    reason: str = ""
```

### 3.2 FeedbackResult 확장

```python
@dataclass
class FeedbackResult:
    """RAG 품질 평가 결과 (Phase 1-4 통합)."""
    
    # 기존 필드 (레거시 호환)
    quality: FeedbackQuality
    score: float
    needs_fallback: bool = False
    fallback_reason: FallbackReason | None = None
    suggestions: list[str] = field(default_factory=list)

    # Phase 1-4 확장 필드
    retrieval_quality: RetrievalQuality | None = None
    completeness: CompletenessResult | None = None
    answer_quality: AnswerQuality | None = None
    next_steps: NextSteps | None = None
    confidence: Confidence | None = None

    def get_next_query(self) -> str | None:
        """Phase 4: 다음 검색 쿼리 추출."""
        if not self.next_steps:
            return None
        for sugg in self.next_steps.suggestions:
            if sugg.type == "additional_retrieval" and sugg.urgency == "immediate":
                return sugg.query
        return None

    def get_missing_info(self) -> list[str]:
        """Phase 2: 누락된 정보 목록."""
        if not self.completeness:
            return []
        return [n.description for n in self.completeness.required_nuggets if not n.covered]
```

---

## 4. LLMFeedbackEvaluator 파싱 개선

### 4.1 Phase 1-4 파싱 로직

```python
# infrastructure/llm/evaluators/feedback_evaluator.py

class LLMFeedbackEvaluator(LLMFeedbackEvaluatorPort):
    """LLM 기반 RAG 품질 평가기 (Phase 1-4 적용)."""

    def _parse_phase4_response(self, response: str) -> FeedbackResult:
        """Phase 1-4 평가 응답 파싱."""
        data = json.loads(response)

        # Phase 1: Retrieval Quality (Evidence)
        retrieval_quality = self._parse_retrieval_quality(data.get("retrieval_quality"))

        # Phase 2: Completeness (Nuggets)
        completeness = self._parse_completeness(data.get("completeness"))

        # Phase 3: Answer Quality (Groundedness)
        answer_quality = self._parse_answer_quality(data.get("answer_quality"))

        # Phase 4: Next Steps
        next_steps = self._parse_next_steps(data.get("next_steps"))

        return FeedbackResult.from_evaluation(
            overall_score=data.get("overall_score", 0.5),
            retrieval_quality=retrieval_quality,
            completeness=completeness,
            answer_quality=answer_quality,
            next_steps=next_steps,
            confidence=self._parse_confidence(data.get("confidence")),
        )
```

### 4.2 레거시 호환성

```python
def _parse_phase4_response(self, response: str) -> FeedbackResult:
    try:
        # Phase 1-4 파싱 시도
        return self._parse_new_format(response)
    except (json.JSONDecodeError, ValueError):
        # 레거시 포맷으로 폴백
        return self._parse_legacy_response(response)
```

---

## 5. TagBasedRetriever: 컨텍스트 검색

### 5.1 Anthropic Contextual Retrieval 패턴

```
[질문] → [품목 추출] → [상황 태그 추출] → [관련 규정 섹션만 검색]
                             ↓
        item_class_list.yaml + situation_tags.yaml
```

### 5.2 데이터 구조

```yaml
# item_class_list.yaml (~200개 품목)
item_class_list:
  재활용폐기물:
    플라스틱류:
    - PET용기
    - PP용기
    - PE용기
    무색페트병:
    - 먹는샘물PET병
    - 음료PET병

# situation_tags.yaml (~100개 상황)
situation_tags:
  - 오염_심함
  - 세척_필요
  - 라벨_부착
  - 뚜껑_분리_필요
```

### 5.3 TagBasedRetriever 구현

```python
# infrastructure/retrieval/tag_based_retriever.py

class TagBasedRetriever(RetrieverPort):
    """태그 기반 컨텍스트 Retriever."""

    def extract_context(self, message: str) -> RetrievalContext:
        """메시지에서 컨텍스트 추출."""
        # 1. 품목 태그 추출 (item_class_list)
        matched_items = self._match_items(message)
        
        # 2. 상황 태그 추출 (situation_tags)
        matched_situations = self._match_situations(message)
        
        return RetrievalContext(
            matched_items=matched_items,
            matched_situations=matched_situations,
        )

    def search_with_context(self, message: str) -> list[ContextualSearchResult]:
        """컨텍스트 기반 검색."""
        context = self.extract_context(message)
        
        results = []
        for key, data in self._data.items():
            # 태그 매칭
            matched_tags = self._match_tags(data, context)
            if matched_tags:
                results.append(ContextualSearchResult(
                    chunk_id=key,
                    data=data,
                    quoted_text=self._extract_relevant_quote(data, matched_tags),
                    relevance="high" if len(matched_tags) > 2 else "medium",
                    matched_tags=matched_tags,
                ))
        
        return sorted(results, key=lambda x: x.relevance)
```

### 5.4 Evidence 형식 반환

```python
# SearchRAGOutput에 Evidence 추가
@dataclass
class SearchRAGOutput:
    found: bool
    disposal_rules: dict[str, Any] | None = None
    search_method: str = "none"  # "classification" | "contextual" | "keyword"
    evidence: list[dict[str, Any]] = field(default_factory=list)  # Phase 1 연동
```

---

## 6. 검색 전략 우선순위

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    검색 전략 Cascade                                     │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  1. 분류 기반 검색 (Vision 결과 있는 경우)                              │
│     └── classification_result → category/subcategory                    │
│                                                                         │
│  2. 태그 기반 컨텍스트 검색 (Anthropic Contextual Retrieval)            │
│     └── message → item_class + situation_tags → 관련 규정               │
│                                                                         │
│  3. 키워드 기반 Fallback 검색                                           │
│     └── message → WASTE_KEYWORDS → 전체 검색                            │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 7. 전체 파이프라인

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    Eval Agent Enhanced Pipeline                          │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  [질문] "오염된 페트병 어떻게 버려?"                                    │
│     │                                                                   │
│     ▼                                                                   │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │  TagBasedRetriever.extract_context()                             │   │
│  │  ├── matched_items: ["페트병", "PET용기"]                        │   │
│  │  └── matched_situations: ["오염_심함"]                           │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│     │                                                                   │
│     ▼                                                                   │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │  TagBasedRetriever.search_with_context()                         │   │
│  │  └── ContextualSearchResult                                      │   │
│  │      ├── chunk_id: "재활용폐기물_플라스틱류"                     │   │
│  │      ├── quoted_text: "오염된 배달용기: 일반종량제폐기물로 배출" │   │
│  │      └── matched_tags: ["페트병", "오염_심함"]                   │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│     │                                                                   │
│     ▼                                                                   │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │  LLMFeedbackEvaluator.evaluate()                                 │   │
│  │  ├── Phase 1: Evidence 추출                                      │   │
│  │  ├── Phase 2: Nugget 커버리지 계산                               │   │
│  │  ├── Phase 3: Groundedness 평가                                  │   │
│  │  └── Phase 4: next_query 생성                                    │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│     │                                                                   │
│     ▼                                                                   │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │  FallbackOrchestrator (필요시)                                   │   │
│  │  └── next_query로 추가 검색 또는 Web Search                      │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 8. 변경 파일 목록

| 파일 | 변경 내용 |
|------|----------|
| `infrastructure/assets/prompts/evaluation/feedback_evaluation.txt` | Phase 1-4 프롬프트 |
| `application/dto/feedback_result.py` | Evidence, Nugget, Groundedness DTO |
| `infrastructure/llm/evaluators/feedback_evaluator.py` | Phase 1-4 파싱 |
| `application/ports/retrieval/retriever.py` | RetrievalContext, ContextualSearchResult |
| `infrastructure/retrieval/tag_based_retriever.py` | 태그 기반 검색 (신규) |
| `application/commands/search_rag_command.py` | 컨텍스트 검색 통합 |
| `setup/dependencies.py` | TagBasedRetriever 주입 |

---

## 9. 참고 문헌

### Anthropic 기술 문서
- [How we built our multi-agent research system](https://www.anthropic.com/engineering/built-multi-agent-research-system) (2025)
- [Introducing Contextual Retrieval](https://www.anthropic.com/news/contextual-retrieval) (2024)
- [Effective context engineering for AI agents](https://www.anthropic.com/engineering/effective-context-engineering) (2025)

### 학술 자료
- [RAGAS: Automated Evaluation of RAG](https://arxiv.org/abs/2309.15217) (2023)
- [TREC 2024 RAG Track - AutoNuggetizer](https://trec-rag.github.io/)
- [TruLens RAG Triad](https://www.trulens.org/trulens_eval/core_concepts_rag_triad/)

---

*문서 버전: v3.0*
*최종 수정: 2026-01-15*
