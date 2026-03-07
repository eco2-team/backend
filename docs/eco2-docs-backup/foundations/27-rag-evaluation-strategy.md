# RAG 품질 평가 전략: LLM-as-a-Judge 설계 원칙

> **목적**: RAG(Retrieval-Augmented Generation) 시스템의 품질을 LLM Judge로 평가할 때, 단순 점수 매기기를 넘어 **디버깅 가능하고(Debuggable)**, **일관성 있으며(Consistent)**, **에이전트 피드백 루프에 활용 가능한(Actionable)** 평가 체계를 구축하기 위한 이론적 토대와 실전 설계 원칙을 정리한다.

---

## 목차

1. [개요: 왜 평가가 어려운가](#1-개요-왜-평가가-어려운가)
2. [Pillar A: 평가 지표의 정량화](#2-pillar-a-평가-지표의-정량화-quantification)
3. [Pillar B: 근거 기반 평가](#3-pillar-b-근거-기반-평가-citation--evidence)
4. [Pillar C: 에이전트 관점의 맥락](#4-pillar-c-에이전트-관점의-맥락-context--flow)
5. [Pillar D: Judge 신뢰성 확보](#5-pillar-d-judge-신뢰성-확보-reliability)
6. [실전 적용: JSON 스키마 설계](#6-실전-적용-json-스키마-설계)
7. [참고 문헌](#7-참고-문헌)

---

## 1. 개요: 왜 평가가 어려운가

### 1.1 RAG 평가의 본질적 어려움

RAG 시스템은 두 가지 독립적인 컴포넌트로 구성된다:

```
[Query] → [Retriever] → [Context] → [Generator] → [Answer]
```

평가의 어려움은 **실패 지점이 분산**되어 있다는 점에서 기인한다:

| 실패 유형 | 원인 | 증상 |
|-----------|------|------|
| Retrieval 실패 | 관련 문서를 찾지 못함 | 답변이 피상적이거나 "모르겠다" |
| Context 과잉 | 너무 많은 문서가 노이즈로 작용 | 답변이 산만하거나 중요 정보 누락 |
| Generation 환각 | Context에 없는 내용을 생성 | 그럴듯하지만 틀린 답변 |
| Attribution 실패 | 답변의 근거가 불명확 | 검증 불가능한 답변 |

### 1.2 기존 평가 방식의 한계

단순 3점 척도(Relevance, Completeness, Accuracy)는 다음 문제를 가진다:

1. **모호성**: "0.7점"이 무엇을 의미하는지 불명확
2. **비재현성**: 같은 입력에 다른 점수가 나옴
3. **디버깅 불가**: 왜 그 점수인지 추적 불가
4. **액션 연결 부재**: 점수가 낮으면 뭘 해야 하는지 불분명

---

## 2. Pillar A: 평가 지표의 정량화 (Quantification)

### 2.1 RAGAS Framework: RAG 평가의 표준

**출처**: [RAGAS: Automated Evaluation of Retrieval Augmented Generation (2023)](https://arxiv.org/abs/2309.15217)

RAGAS는 Reference Answer 없이도 RAG 품질을 측정할 수 있는 프레임워크로, 다음 지표들을 제안한다:

#### 핵심 지표

| 지표 | 정의 | 측정 대상 |
|------|------|----------|
| **Faithfulness** | 답변이 Context에 기반하는가? | Generator |
| **Answer Relevance** | 답변이 질문에 적절한가? | Generator |
| **Context Precision** | 검색된 문서 중 관련 있는 비율 | Retriever |
| **Context Recall** | 필요한 정보가 검색되었는가? | Retriever |

#### Faithfulness 측정 방법

```
Faithfulness = (Context에서 지지되는 문장 수) / (답변의 총 문장 수)
```

**구현 전략**:
1. 답변을 개별 문장(Statement)으로 분해
2. 각 문장이 Context에서 추론 가능한지 판단
3. 비율 계산

```python
# 예시: Faithfulness 평가 프롬프트 구조
"""
다음 문장이 주어진 Context에서 추론 가능한지 판단하세요.

Context: {context}
Statement: {statement}

판단: [Yes/No]
근거: [Context에서 해당 부분 인용]
"""
```

### 2.2 TruLens RAG Triad: 실무 표준

**출처**: [TruLens Documentation](https://www.trulens.org/trulens_eval/core_concepts_rag_triad/)

TruLens는 RAGAS 개념을 3축으로 단순화하여 실무에서 널리 사용된다:

```
                    ┌─────────────────┐
                    │  Answer Quality │
                    └────────┬────────┘
                             │
              ┌──────────────┼──────────────┐
              │              │              │
              ▼              ▼              ▼
     ┌────────────┐  ┌────────────┐  ┌────────────┐
     │  Context   │  │Groundedness│  │  Answer    │
     │ Relevance  │  │            │  │ Relevance  │
     └────────────┘  └────────────┘  └────────────┘
          │              │              │
          ▼              ▼              ▼
     [Retriever]    [Generator]    [End-to-End]
```

#### 기존 프롬프트와의 매핑

| 기존 지표 | TruLens 매핑 | 개선 방향 |
|-----------|-------------|----------|
| `relevance` | Context Relevance | 검색 결과 ↔ 질문 관계 |
| `completeness` | (부분적) Answer Relevance | Nugget 커버리지로 세분화 |
| `accuracy` | Groundedness + Faithfulness | 두 개념 분리 필요 |

### 2.3 TREC RAG Track: Nugget 기반 완전성 평가

**출처**: [TREC 2024 RAG Track - AutoNuggetizer](https://trec-rag.github.io/)

**핵심 인사이트**: "완전성(Completeness)"을 주관적 판단이 아닌, **필수 정보 단위(Nugget)의 커버리지**로 객관화한다.

#### Nugget이란?

> 질문에 답하기 위해 반드시 포함되어야 하는 최소 정보 단위

**예시**:

```
질문: "파리 기후 협정의 주요 내용은?"

Nuggets:
1. 지구 평균 기온 상승을 2°C 이하로 제한
2. 1.5°C 제한 노력 목표
3. 선진국 기후 재정 지원 의무
4. 5년 주기 국가 감축 목표(NDC) 제출
5. 탄소 시장 메커니즘 도입
```

#### Completeness 정량화

```
Completeness = (답변에 포함된 Nugget 수) / (총 필수 Nugget 수)
```

#### 프롬프트 적용

```python
# 1단계: 질문에서 Nugget 추출
"""
다음 질문에 완전히 답하기 위해 필요한 핵심 정보 단위(Nugget)를 나열하세요.

질문: {query}

Nuggets (JSON 배열):
"""

# 2단계: Nugget 커버리지 평가
"""
다음 검색 결과가 각 Nugget을 포함하는지 판단하세요.

Nuggets: {nuggets}
검색 결과: {rag_results}

커버리지 (JSON):
{
  "covered_nuggets": [...],
  "missing_nuggets": [...],
  "coverage_ratio": 0.0-1.0
}
"""
```

---

## 3. Pillar B: 근거 기반 평가 (Citation & Evidence)

### 3.1 Anthropic CitationAgent: 검증 가능한 평가

**출처**: [How we built our multi-agent research system (Anthropic, 2025)](https://www.anthropic.com/engineering/built-multi-agent-research-system)

**핵심 원칙**: Judge가 점수를 줄 때 반드시 **근거의 위치(Citation)**를 명시하도록 강제한다.

#### 왜 Citation이 중요한가?

1. **디버깅 가능성**: 평가가 잘못되었을 때 어디서 틀렸는지 추적 가능
2. **환각 방지**: Judge도 환각할 수 있으므로, 근거 명시로 검증 가능
3. **피드백 루프**: 어떤 청크가 유용했는지 데이터 축적 가능

#### 구현 패턴

```python
# Citation 강제 스키마
{
  "relevance_score": 0.85,
  "relevance_evidence": [
    {
      "snippet_id": "chunk_042",
      "quoted_text": "파리 협정은 2015년 채택되어...",
      "relevance_reason": "질문의 '파리 협정' 키워드와 직접 관련"
    }
  ],
  "groundedness_score": 0.9,
  "groundedness_evidence": [
    {
      "claim": "2°C 목표가 설정되었다",
      "source_snippet_id": "chunk_042",
      "source_quote": "지구 평균 기온 상승을 2°C 이하로 제한"
    }
  ]
}
```

### 3.2 Cursor Codebase Indexing: 청크 단위 추적

**출처**: [Cursor Docs - Codebase Indexing](https://docs.cursor.com/context/codebase-indexing)

**핵심 인사이트**: 로컬 RAG 시스템에서 검색 결과의 **물리적 위치(파일/청크)**를 추적하면 평가와 디버깅이 용이해진다.

#### 평가에 적용할 포인트

1. **검색 단위 명시**: 파일명, 라인 번호, 청크 ID
2. **중복 감지**: 같은 청크가 반복 검색되었는지 확인
3. **캐시 영향 분리**: 캐시된 결과 vs 신규 검색 구분

```python
# 검색 결과 메타데이터 예시
{
  "results": [
    {
      "chunk_id": "file_auth_py_chunk_003",
      "file_path": "apps/auth/domain/user.py",
      "line_range": [45, 67],
      "relevance_score": 0.92,
      "from_cache": false
    }
  ]
}
```

### 3.3 Anthropic Contextual Retrieval: 컨텍스트 품질 평가

**출처**: [Introducing Contextual Retrieval (Anthropic, 2024)](https://www.anthropic.com/news/contextual-retrieval)

**핵심 발견**: 전통적인 임베딩 검색은 **평균 27%의 실패율**을 보이며, 이는 청크가 원본 문서의 맥락을 잃기 때문이다.

#### Retrieval 실패 유형

| 실패 유형 | 설명 | 예시 |
|-----------|------|------|
| **Lexical Mismatch** | 동의어/유의어 불일치 | "AI" vs "인공지능" |
| **Context Loss** | 청크가 문서 맥락을 잃음 | "이 방법은..." (어떤 방법?) |
| **Specificity Gap** | 질문이 너무 구체적 | 특정 함수명 검색 실패 |

#### 평가에 적용할 질문

```python
# Context 품질 평가 프롬프트
"""
다음 검색 결과가 질문에 답하기에 충분한지 평가하세요.

## 평가 관점
1. **커버리지**: 질문의 모든 측면이 다뤄지는가?
2. **구체성**: 충분히 구체적인 정보가 있는가?
3. **맥락 완전성**: 청크가 독립적으로 이해 가능한가?

질문: {query}
검색 결과: {rag_results}
"""
```

---

## 4. Pillar C: 에이전트 관점의 맥락 (Context & Flow)

### 4.1 Just-in-Time Context: 적시 정보 판단

**출처**: [Effective Context Engineering for AI Agents (Anthropic, 2025)](https://www.anthropic.com/engineering/effective-context-engineering)

**핵심 개념**: 모든 정보를 미리 검색하는 것이 아니라, **필요한 시점에 필요한 정보**를 가져오는 전략.

#### 평가에의 시사점

"추가 검색 필요"라는 피드백은 너무 모호하다. 대신:

1. **지금 당장 필요한 정보**인지 vs **나중에 필요할 수 있는 정보**인지 구분
2. **어떤 질문**으로 검색해야 하는지 명시
3. **우선순위** 부여

```python
# 개선된 "next_step" 스키마
{
  "missing_info": [
    {
      "description": "파리 협정의 실제 이행 현황",
      "urgency": "immediate",  # immediate | deferred | optional
      "suggested_query": "파리 협정 2024년 각국 NDC 이행률",
      "reason": "질문이 '현재 상황'을 물었으나 검색 결과는 협정 체결 시점 정보만 포함"
    }
  ]
}
```

### 4.2 멀티턴 평가에서의 맥락 관리

에이전트가 여러 턴에 걸쳐 정보를 수집할 때, 각 턴의 평가는 **누적 맥락**을 고려해야 한다.

#### 고려사항

| 관점 | 단일 턴 평가 | 멀티턴 평가 |
|------|-------------|------------|
| 완전성 | 이번 검색으로 충분? | 지금까지 모은 정보로 충분? |
| 중복 | N/A | 이미 있는 정보를 또 가져왔나? |
| 진전 | N/A | 이전 턴 대비 얼마나 진전? |

```python
# 멀티턴 평가 스키마 확장
{
  "turn_number": 3,
  "cumulative_coverage": 0.75,  # 전체 Nugget 대비
  "turn_contribution": 0.15,    # 이번 턴의 기여도
  "redundant_chunks": ["chunk_012"],  # 이전 턴과 중복
  "novel_info": ["새로운 통계 데이터 추가"]
}
```

---

## 5. Pillar D: Judge 신뢰성 확보 (Reliability)

### 5.1 ConsJudge: Judge 일관성 문제

**출처**: [ConsJudge: Judge as a Judge (2025)](https://arxiv.org/abs/2501.xxxxx)

**핵심 문제**: LLM Judge는 프롬프트의 미세한 변화에도 점수가 크게 달라질 수 있다.

#### 일관성 저하 원인

1. **순서 편향**: 선택지/예시의 순서에 따라 점수 변화
2. **표현 편향**: 같은 의미의 다른 표현에 다른 점수
3. **길이 편향**: 긴 답변에 높은 점수를 주는 경향

#### 해결 전략

| 전략 | 설명 | 구현 |
|------|------|------|
| **다중 샘플링** | 같은 평가를 여러 번 수행 | temperature > 0으로 3회 평가 후 중앙값 |
| **다중 루브릭** | 다른 관점의 루브릭으로 교차 검증 | 긍정/부정 프레이밍 비교 |
| **불확실성 명시** | Judge가 확신 없을 때 표시 | `confidence` 필드 추가 |

```python
# 불확실성 명시 스키마
{
  "relevance_score": 0.7,
  "confidence": 0.6,  # 0.0-1.0, 낮으면 재평가 필요
  "conflicting_signals": [
    "일부 키워드 매칭되나 맥락이 다름"
  ]
}
```

### 5.2 Snowflake: Judge 최적화 관점

**출처**: [Eval-guided optimization of LLM judges (Snowflake, 2025)](https://www.snowflake.com/engineering-blog/)

**핵심 인사이트**: Judge 프롬프트도 **최적화 대상**이며, 벤치마크 대비 성능을 측정해야 한다.

#### 운영 원칙

1. **버전 관리**: 평가 프롬프트에 버전 번호 부여
2. **회귀 테스트**: Golden Set에 대해 새 프롬프트 성능 비교
3. **A/B 테스트**: 프로덕션에서 두 버전 병행 운영

```python
# 프롬프트 버전 메타데이터
EVAL_PROMPT_VERSION = "v2.3.1"
EVAL_PROMPT_DATE = "2025-01-15"
BENCHMARK_SCORE = 0.87  # Golden Set 기준
```

### 5.3 OpenAI Evals: 평가 시스템 설계

**출처**: [OpenAI - Working with Evals](https://platform.openai.com/docs/guides/evals)

**핵심 원칙**: 평가는 일회성 작업이 아니라 **지속적인 품질 관리 시스템**이다.

#### 시스템 구성 요소

```
┌─────────────────────────────────────────────────────┐
│                    Eval System                       │
├──────────────┬──────────────┬───────────────────────┤
│  Test Cases  │  Evaluators  │  Metrics Dashboard    │
│  (Golden Set)│  (Prompts)   │  (Tracking)           │
├──────────────┼──────────────┼───────────────────────┤
│ - 다양한 쿼리│ - 버전 관리  │ - 시계열 추적         │
│ - 엣지 케이스│ - 다중 판단자│ - 회귀 감지           │
│ - 정답 라벨  │ - 신뢰 구간  │ - 알림                │
└──────────────┴──────────────┴───────────────────────┘
```

---

## 6. 실전 적용: JSON 스키마 설계

### 6.1 기존 프롬프트 분석

현재 `feedback_evaluation.txt`의 출력 스키마:

```json
{
    "relevance": 0.8,
    "completeness": 0.7,
    "accuracy": 0.9,
    "overall_score": 0.8,
    "suggestions": ["추가 검색 필요", "..."],
    "explanation": "평가 이유"
}
```

**문제점**:
- `accuracy`가 Groundedness와 Faithfulness를 혼합
- `completeness`가 주관적 판단에 의존
- `suggestions`가 구체적 행동으로 연결되지 않음
- Citation/Evidence 부재로 디버깅 불가

### 6.2 개선된 스키마 (Recommended)

```json
{
  "meta": {
    "eval_version": "v1.0.0",
    "model": "claude-3-5-sonnet",
    "timestamp": "2025-01-15T10:30:00Z"
  },
  
  "retrieval_quality": {
    "context_relevance": 0.85,
    "context_coverage": 0.7,
    "evidence": [
      {
        "chunk_id": "chunk_042",
        "relevance": "high",
        "covers_nuggets": ["nugget_1", "nugget_3"]
      }
    ]
  },
  
  "answer_quality": {
    "groundedness": 0.9,
    "groundedness_evidence": [
      {
        "claim": "답변에서 추출된 주장",
        "source_chunk_id": "chunk_042",
        "source_quote": "해당 청크에서 인용",
        "supported": true
      }
    ],
    "answer_relevance": 0.85,
    "hallucination_detected": false
  },
  
  "completeness": {
    "required_nuggets": [
      {"id": "nugget_1", "description": "필수 정보 1", "covered": true},
      {"id": "nugget_2", "description": "필수 정보 2", "covered": false}
    ],
    "coverage_ratio": 0.5,
    "missing_nuggets": ["nugget_2"]
  },
  
  "next_steps": {
    "action_required": true,
    "suggestions": [
      {
        "type": "additional_retrieval",
        "urgency": "immediate",
        "query": "구체적인 추가 검색 쿼리",
        "reason": "nugget_2를 커버하기 위해 필요"
      }
    ]
  },
  
  "confidence": {
    "overall": 0.8,
    "low_confidence_areas": ["groundedness 판단에 모호한 부분 있음"],
    "conflicting_signals": []
  },
  
  "overall_score": 0.78
}
```

### 6.3 스키마 필드 상세 설명

| 필드 | 이론적 근거 | 목적 |
|------|------------|------|
| `retrieval_quality.evidence` | Anthropic CitationAgent | 디버깅 가능한 평가 |
| `completeness.required_nuggets` | TREC AutoNuggetizer | 객관적 완전성 측정 |
| `answer_quality.groundedness_evidence` | RAGAS Faithfulness | 환각 감지 |
| `next_steps.suggestions` | Just-in-Time Context | 에이전트 행동 유도 |
| `confidence` | ConsJudge | Judge 불확실성 명시 |

### 6.4 단계적 적용 전략

복잡한 스키마를 한 번에 적용하기보다, 단계적으로 확장한다:

**Phase 1 (MVP)**: Citation 추가
```json
{
  "relevance": 0.8,
  "evidence_snippets": ["chunk_042", "chunk_043"],
  "completeness": 0.7,
  "accuracy": 0.9,
  "overall_score": 0.8,
  "explanation": "..."
}
```

**Phase 2**: Nugget 기반 완전성
```json
{
  // Phase 1 +
  "missing_nuggets": ["필수 정보 2"],
  "coverage_ratio": 0.5
}
```

**Phase 3**: Groundedness 분리
```json
{
  // Phase 2 +
  "groundedness": 0.9,
  "faithfulness": 0.85,
  "hallucination_claims": []
}
```

**Phase 4**: 불확실성 & 행동
```json
{
  // Phase 3 +
  "confidence": 0.8,
  "next_queries": ["추가 검색 쿼리"]
}
```

---

## 7. 참고 문헌

### 논문

1. **RAGAS** - Es, S., et al. (2023). "RAGAS: Automated Evaluation of Retrieval Augmented Generation." arXiv:2309.15217
2. **TREC RAG Track** - Pradeep, R., et al. (2024). "AutoNuggetizer for RAG Evaluation." TREC 2024
3. **ConsJudge** - (2025). "Judge as a Judge: Improving Consistency of LLM Evaluators."
4. **Survey: RAG Evaluation** - (2024). "A Survey on Evaluation of Retrieval-Augmented Generation."
5. **Survey: LLM-as-a-Judge** - (2024). "A Survey on LLM-as-a-Judge."

### 기업 기술 문서

6. **Anthropic** - "Contextual Retrieval" (2024)
7. **Anthropic** - "How we built our multi-agent research system" (2025)
8. **Anthropic** - "Effective context engineering for AI agents" (2025)
9. **Anthropic** - "Prompt caching" (Claude Docs)
10. **Cursor** - "Codebase Indexing" (Docs)
11. **OpenAI** - "Working with evals" (Docs)

### 실무 도구 문서

12. **TruLens** - RAG Triad Documentation
13. **Snowflake** - "Eval-guided optimization of LLM judges" (2025)
14. **LangSmith** - "Evaluate a RAG application"
15. **LangChain** - openevals GitHub
16. **DeepEval** - RAG 평가 가이드 (2026)

---

## 부록: 프롬프트 템플릿

### A. 기본 평가 프롬프트 (Phase 1)

```
당신은 RAG 검색 결과의 품질을 평가하는 전문가입니다.

## 평가 원칙
1. 모든 점수에는 반드시 근거(evidence)를 제시하세요
2. 근거는 검색 결과의 구체적인 청크 ID와 인용문을 포함해야 합니다
3. 확신이 없는 부분은 명시적으로 표시하세요

## 평가 기준
- **관련성 (0.0-1.0)**: 검색 결과가 질문의 핵심 요소를 다루는가?
- **완전성 (0.0-1.0)**: 질문에 답하기 위한 필수 정보가 모두 포함되었는가?
- **정확성 (0.0-1.0)**: 정보가 정확하고 신뢰할 수 있는가?

## 사용자 질문
{query}

## 검색 결과
{rag_results}

## 출력 형식 (JSON)
{
    "relevance": 0.0-1.0,
    "completeness": 0.0-1.0,
    "accuracy": 0.0-1.0,
    "overall_score": 0.0-1.0,
    "evidence_snippets": ["관련 청크 ID 목록"],
    "missing_info": ["부족한 정보 목록"],
    "explanation": "평가 이유 (구체적 인용 포함)"
}

JSON 형식으로만 응답하세요.
```

### B. 고급 평가 프롬프트 (Phase 4)

```
당신은 RAG 시스템의 품질을 다차원으로 평가하는 전문가입니다.

## 평가 원칙
1. 모든 판단에 근거(Citation)를 명시합니다
2. Retrieval 품질과 Generation 품질을 분리하여 평가합니다
3. 불확실한 판단은 confidence를 낮추고 이유를 명시합니다

## 평가 절차

### Step 1: 질문 분해
질문에 답하기 위해 필요한 핵심 정보 단위(Nugget)를 식별하세요.

### Step 2: Retrieval 평가
각 검색 결과가 어떤 Nugget을 커버하는지 매핑하세요.

### Step 3: Groundedness 평가
답변의 각 주장이 검색 결과에서 지지되는지 확인하세요.

### Step 4: 다음 단계 제안
부족한 정보를 채우기 위한 구체적인 행동을 제안하세요.

## 입력
- 질문: {query}
- 검색 결과: {rag_results}
- 이전 맥락 (있는 경우): {previous_context}

## 출력 스키마
{출력 스키마 JSON - 6.2절 참조}

JSON 형식으로만 응답하세요.
```

---

*문서 버전: v1.0.0*
*최종 수정: 2025-01-15*
*작성 근거: Anthropic, RAGAS, TREC, TruLens, ConsJudge 등 주요 연구 및 실무 문서*
