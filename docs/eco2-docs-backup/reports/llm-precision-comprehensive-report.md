# LLM Precision 종합 리포트

> **작성일**: 2026-02-26
> **Author**: Claude Opus 4.6
> **대상**: Eco² 전체 백엔드 — Chat, Chat Worker, Scan Worker, SSE Gateway
> **목적**: LLM 출력 품질·정확성·신뢰성을 높이기 위해 적용된 모든 기법의 종합 정리

---

## Related

| # | 문서 | 위치 |
|---|------|------|
| Design | Chat Eval Pipeline Plan v2.2 | `docs/plans/chat-eval-pipeline-plan.md` |
| Report | Chat Eval Pipeline 구현 리포트 | `docs/reports/chat-eval-pipeline-implementation-report.md` |
| Report | Eval Pipeline E2E 검증 리포트 | `docs/reports/eval-pipeline-e2e-verification-report.md` |
| Foundation | RAG 평가 전략 | `docs/foundations/27-rag-evaluation-strategy.md` |
| Foundation | Chain-of-Intent (CIKM 2025) | `docs/foundations/26-chain-of-intent-cikm2025.md` |
| Foundation | Multi-Intent ICL (2023) | `docs/foundations/25-multi-intent-icl-2023.md` |
| Blog | Chat Prompt Optimization | `docs/blogs/applied/22-chat-prompt-optimization.md` |
| Blog | Intent Classification | `docs/blogs/applied/24-chat-intent-classification.md` |
| Blog | Multi-Intent Processing | `docs/blogs/applied/25-chat-multi-intent-processing.md` |
| Blog | Feedback Fallback Loop | `docs/blogs/applied/28-chat-feedback-fallback-loop.md` |
| ADR | Swiss Cheese Model | https://rooftopsnow.tistory.com/273 |
| ADR | BARS 루브릭 설계 | https://rooftopsnow.tistory.com/274 |
| ADR | Eval Pipeline Integration | https://rooftopsnow.tistory.com/275 |

---

## 1. Executive Summary

Eco²는 폐기물 분리배출 AI 챗봇으로, LLM 응답의 **정확성(Precision)** 이 사용자 안전과 직결됩니다. 잘못된 분리배출 안내는 환경 오염과 안전 사고로 이어질 수 있기 때문입니다.

이 리포트는 Eco² 백엔드에 적용된 **LLM Precision 기법 40+개**를 11개 카테고리로 분류·정리합니다.

### Precision Layer Map

```
┌──────────────────────────────────────────────────────────┐
│                    USER REQUEST                          │
├──────────────────────────────────────────────────────────┤
│  L1  Input Validation        — 빈 입력 차단, 스키마 검증   │
│  L2  Intent Classification   — 신뢰도 기반 분류 + 캐싱     │
│  L3  Prompt Engineering      — Global/Local 이중 구조       │
│  L4  RAG Retrieval           — 컨텍스트 검색 + 증거 추적     │
│  L5  Feedback Evaluation     — 4-Phase RAG 품질 평가        │
│  L6  Answer Generation       — Structured Output + 스트리밍  │
│  L7  Post-Gen Evaluation     — Swiss Cheese 3-Tier Grader   │
│  L8  Guardrails              — Circuit Breaker + Retry       │
│  L9  Cost Control            — Sampling + Budget + Caching   │
│  L10 Observability           — CUSUM + Metrics + LangSmith   │
├──────────────────────────────────────────────────────────┤
│                    USER RESPONSE                         │
└──────────────────────────────────────────────────────────┘
```

---

## 2. Prompt Engineering

### 2.1 Global + Local 이중 프롬프트 구조

| 계층 | 파일 패턴 | 역할 |
|------|----------|------|
| **Global** | `prompts/global/eco_character.txt` | 페르소나("이코"), 공통 규칙, 톤 |
| **Local** | `prompts/local/{intent}_instruction.txt` | 인텐트별 응답 전략, RAG 활용법, 출력 구조 |

**합성**: `GLOBAL + "\n---\n" + LOCAL[intent]`

Local 프롬프트 5종:

| 파일 | 인텐트 | 핵심 지침 |
|------|--------|----------|
| `waste_instruction.txt` | WASTE | RAG 결과 기반 분리배출 방법 안내, 인용 필수 |
| `character_instruction.txt` | CHARACTER | 캐릭터 소개, 인격적 대화 |
| `location_instruction.txt` | LOCATION | 위치 기반 센터 안내, 지도 연동 |
| `web_instruction.txt` | WEB_SEARCH | 출처 명시, 검색 결과 요약 |
| `general_instruction.txt` | GENERAL | 환경 연결 대화, 자연스러운 전환 |

### 2.2 프롬프트 에셋 전체 현황

| 카테고리 | 파일 수 | 용도 |
|----------|--------|------|
| Classification | 5 | `intent.txt`, `multi_intent_detect.txt`, `decompose.txt` 등 |
| Evaluation (BARS) | 6 | `bars_faithfulness.txt` ~ `bars_communication.txt` + system |
| Image Generation | 4 | `system.txt`, `basic.txt`, `character_reference.txt` 등 |
| Summarization | 1 | `context_compress.txt` (컨텍스트 압축) |
| Local Instruction | 5 | 인텐트별 응답 지침 |
| Extraction | 2 | `category.txt`, `category_system.txt` (카테고리 추출) |
| **합계** | **~23개, 1,500+ lines** | |

**캐싱**: `@lru_cache(maxsize=32)` — 프롬프트 로딩 시 LRU 캐시 적용 (`prompt_loader.py`)

### 2.3 Structured Output 강제

| 컴포넌트 | 스키마 | 강제 방식 |
|----------|--------|----------|
| Intent 분류 | `IntentClassificationSchema` | Pydantic `BaseModel` |
| Multi-Intent | `MultiIntentDetectionSchema` | Pydantic `BaseModel` |
| BARS 평가 | `BARSEvalOutput` (5-axis) | `json_schema` + `strict: True` |
| Vision 분류 | `VisionResult` | Structured Output API |

**Repair 전략** (`bars_evaluator.py`):
- 파싱 실패 시 최대 2회 재시도
- 에러 컨텍스트를 repair prompt에 포함: `"[파싱 오류: {e}]\n올바른 JSON 형식으로 재응답하세요."`

---

## 3. Intent Classification

### 3.1 신뢰도 기반 분류

**소스**: `apps/chat_worker/application/services/intent_classifier_service.py`

| 파라미터 | 값 | 설명 |
|---------|---|------|
| Temperature | `0.1` | 결정적 분류 보장 |
| Confidence Threshold | `0.6` | 미만 시 `GENERAL` fallback |
| Cache TTL | `3,600초` (1시간) | Redis, 30% LLM 호출 절감 |
| Cache Key | `MD5(message)` | 메시지 해시 기반 |

**신뢰도 조정 공식**:
```
Base: 1.0
- Invalid response:     -0.3
- Short message (<5자):  -0.2
- Keyword match:         +0.1 per match
- Fallback: < 0.6 → Intent.GENERAL
```

### 3.2 Multi-Intent 검출

3단계 파이프라인:

| 단계 | 방식 | 목적 |
|------|------|------|
| Stage 1 | 키워드 프리필터링 | 빠른 rejection (불필요한 LLM 호출 방지) |
| Stage 2 | LLM 분류 | 의미론적 멀티인텐트 탐지 |
| Stage 3 | 쿼리 분해 | 확인된 멀티인텐트를 개별 쿼리로 분리 |

**Few-shot 구성** (ICL 2023 논문 기반):
- Single-intent 예시 2~3개
- Multi-intent 예시 2~3개
- 트리키 케이스 2~3개
- 신뢰도 < 0.7 → single intent fallback

### 3.3 Chain-of-Intent (CIKM 2025)

**소스**: `docs/foundations/26-chain-of-intent-cikm2025.md`

HMM 전이 행렬 기반 인텐트 연쇄 부스팅:

```python
INTENT_TRANSITION_BOOST = {
    Intent.WASTE: {
        Intent.LOCATION: 0.15,           # "버리는데 센터 어디?"
        Intent.COLLECTION_POINT: 0.10,
    },
    ...
}
MAX_TRANSITION_BOOST = 0.15              # 부스트 상한
MIN_CONFIDENCE_FOR_BOOST = 0.7           # 최소 신뢰도 (부스트 적용 조건)
```

**효과**: 다턴 대화에서 문맥 기반 인텐트 예측 정확도 향상

### 3.4 Multi-Intent 응답 합성

**소스**: `docs/blogs/applied/25-chat-multi-intent-processing.md`

Policy Composition 패턴:
```
입력: "페트병 버리고 캐릭터 알려줘"
인텐트: [waste, character]
시스템 프롬프트: [GLOBAL] + "---" + [WASTE_INSTRUCT] + [CHARACTER_INSTRUCT]
```

---

## 4. RAG & Retrieval Quality

### 4.1 Contextual Retrieval

**소스**: `apps/chat_worker/application/ports/retrieval/retriever.py`

```python
@dataclass
class ContextualSearchResult:
    chunk_id: str              # 인용 추적용
    relevance: str             # high | medium | low
    matched_tags: list[str]    # 태그 기반 매칭
```

| 기법 | 효과 |
|------|------|
| Context Preservation | 27% baseline 실패 방지 |
| Lexical Mismatch Handling | 동의어/별칭 처리 |
| Specificity Gap Bridging | 구체성 격차 해소 |
| Chunk-level Metadata | `file_path`, `line_range` 추적 |

### 4.2 Fallback Chain

```
Primary: Local RAG (마크다운 문서)
  → Fallback 1: Web Search (DuckDuckGo/Tavily)
    → Fallback 2: Clarification Request (질의 명확화)
      → Fallback 3: General LLM Response (범용 응답)
```

### 4.3 Feedback Evaluation (Pre-Generation RAG 품질 평가)

**소스**: `apps/chat_worker/infrastructure/llm/evaluators/feedback_evaluator.py`

#### Rule-Based 점수 (L1)

```python
score = 0.3 * has_data
      + 0.2 * has_category
      + 0.2 * disposal_info_richness
      + 0.3 * keyword_match_ratio
```

- `score < 0.4` → Web Search fallback 권고
- Temperature: `0.1` (일관된 평가)

#### LLM-Based 4-Phase 평가

| Phase | 평가 대상 | 핵심 지표 |
|-------|----------|----------|
| Phase 1 | Citation Tracking | `chunk_id` → `relevance` → `quoted_text` |
| Phase 2 | Nugget Completeness | `coverage_ratio = covered / total_required` |
| Phase 3 | Groundedness | `claim` → `source_chunk_id` → `supported: bool` |
| Phase 4 | JIT Next Queries | `type: additional_retrieval` → `urgency` → `query` |

---

## 5. Evaluation Pipeline (Post-Generation)

### 5.1 Swiss Cheese 3-Tier Grader

```
L1 Code Grader ──→ 결정적 규칙 (< 50ms, 무비용)
L2 LLM Grader  ──→ BARS 5축 + Self-Consistency (1~5s)
L3 Calibration ──→ CUSUM 통계적 드리프트 감지 (주기적)
       │
       ▼
 Score Aggregator → EvalResult (0-100 연속 점수 + S/A/B/C 등급)
```

### 5.2 L1: Code Grader

| 규칙 | 기준 | 결과 |
|------|------|------|
| Format Compliance | regex + structure validation | pass/fail |
| Length Check | 50 < tokens < 2000 | pass/fail |
| Language Consistency | ≥ 80% 자연 한국어 | pass/fail |
| Hallucination Blocklist | 키워드 매칭 | pass/fail |
| Citation Presence | waste 인텐트에서 인용 존재 여부 | pass/fail |
| Intent-Answer Alignment | 템플릿 매칭 | pass/fail |

### 5.3 L2: LLM Grader (BARS 5-Axis Rubric)

**소스**: `apps/chat_worker/infrastructure/llm/evaluators/bars_evaluator.py`

| 설정 | 값 |
|------|---|
| Model | `gpt-5.2` |
| Temperature | `0.1` |
| Max Tokens | `1,000` |
| Self-Consistency | 3회 실행 → median 집계 |
| 출력 | Structured JSON (strict mode) |
| Retry | 최대 2회 (repair prompt 포함) |

**5-Axis 가중치** (`eval_scoring.py`):

| 축 | Default Weight | Hazardous Weight | 설명 |
|----|---------------|-----------------|------|
| Faithfulness | **0.30** | 0.30 | 근거 기반 정확성 (최우선) |
| Relevance | 0.25 | 0.25 | 질문-답변 정합성 |
| Completeness | 0.20 | 0.15 | 정보 커버리지 |
| Safety | 0.15 | **0.25** | 유해 정보 탐지 (위험물 +0.10) |
| Communication | 0.10 | 0.05 | 명확성·가독성 |

**설계 근거**:
- Faithfulness 최우선: 할루시네이션 방지가 분리배출 안내에서 가장 중요
- Safety 가변 가중치: 위험 폐기물(농약, 배터리 등) 관련 질의 시 Safety 비중 +0.10

### 5.4 L3: Calibration Monitor (CUSUM)

| 파라미터 | 값 |
|---------|---|
| 알고리즘 | Two-Sided CUSUM |
| Drift Threshold (h) | `4.0` |
| Check Interval | 매 100번째 요청 |
| Sample Rate | 설정 가능 (기본 5%) |

### 5.5 등급 체계 & 연속 점수

| 등급 | 점수 범위 | 액션 |
|------|----------|------|
| **S** | 90–100 | 통과 |
| **A** | 75–89 | 통과 |
| **B** | 55–74 | 로그 기록 |
| **C** | < 55 | 재생성 (sync 모드, 1회 시도) |

**FAIL_OPEN**: 평가 실패 시 → `grade: B`, `score: 65.0`, 재생성 없음

### 5.6 Async Fire-and-Forget 아키텍처

```
Main Graph: answer → done(즉시 반환) → END
                 └→ eval(asyncio.create_task) → background
```

| 항목 | 값 |
|------|---|
| 사용자 체감 지연 | **0ms** |
| 평가 목적 | 모니터링 전용 (재생성 없음) |
| 실패 모드 | FAIL_OPEN (B등급 fallback) |
| 업계 벤치마크 | LangSmith/Langfuse와 동일 패턴 |

---

## 6. Model Configuration

### 6.1 모델 선택 전략

| 컴포넌트 | 모델 | 용도 |
|----------|------|------|
| Chat 기본 | `gpt-5.2-turbo` | 응답 생성 |
| Chat Worker | `gpt-5.2` | 인텐트 분류 + 응답 |
| Eval Pipeline | `gpt-5.2` | BARS 5축 평가 |
| Scan Worker (Vision) | `gpt-5.1` | 이미지 기반 폐기물 분류 |
| Image Generation | `gpt-5.2` | 캐릭터 이미지 |

### 6.2 Model Tier 시스템

```python
class ModelTier(str, Enum):
    FAST = "fast"           # gpt-4o-mini, gemini-flash
    STANDARD = "standard"   # gpt-4o, gemini-pro
    PREMIUM = "premium"     # gpt-4-turbo, claude-opus
```

**선택 지점**: Scan API (유연한 모델 전환)

### 6.3 Temperature 맵

| 태스크 | Temperature | 근거 |
|--------|------------|------|
| Intent Classification | `0.1` | 재현 가능한 분류 |
| Answer Generation | 기본값 | 다양성과 일관성 균형 |
| Eval (BARS) | `0.1` | 일관된 채점 |
| Feedback Evaluation | `0.1` | 일관된 품질 평가 |

### 6.4 Token Budget

| 컨텍스트 | Max Tokens | 비고 |
|----------|-----------|------|
| 응답 생성 | 2,000 (기본) | 인텐트별 조정 가능 |
| Eval 출력 | 1,000 | BARS JSON 스키마 |
| 컨텍스트 압축 트리거 | `context_window - max_output` | 동적 계산 (예: 400K - 128K = 272K) |
| 압축 출력 | context_window × 15% | 약 60K tokens |

---

## 7. Guardrails & Resilience

### 7.1 입력 검증

| 계층 | 검증 | 소스 |
|------|------|------|
| API | 빈 메시지 차단 (`message.strip()`) | `chat/controllers/chat.py:420` |
| API | HttpUrl 검증 (이미지 URL) | `SendMessageRequest` 스키마 |
| API | UserLocation 스키마 (lat/lon) | Pydantic validation |

### 7.2 Circuit Breaker

**소스**: `apps/chat_worker/application/ports/circuit_breaker.py`

| 상태 | 동작 |
|------|------|
| CLOSED | 정상 운영 |
| OPEN | 즉시 실패 (cascading failure 방지) |
| HALF_OPEN | 복구 시도 |

**Eval 연동**: Circuit Breaker OPEN → `EvalResult.failed()` → `grade: B, score: 65.0`, 재생성 없음

### 7.3 Retry with Exponential Backoff

**소스**: `apps/chat_worker/infrastructure/error_handling/retry_policy.py`

```python
@dataclass
class RetryPolicy:
    max_retries: int = 3
    base_delay: float = 1.0        # 초기 지연 (초)
    max_delay: float = 30.0        # 지연 상한
    exponential_base: float = 2.0  # 2^attempt
    jitter: bool = True            # ±25% 랜덤 편차
```

**Transient 예외만 재시도**: `TimeoutError`, `ConnectionError`, `asyncio.TimeoutError`

### 7.4 HTTP 클라이언트 설정 (Scan Worker)

```python
OPENAI_TIMEOUT = httpx.Timeout(
    connect=5.0, read=30.0, write=10.0, pool=5.0
)
OPENAI_LIMITS = httpx.Limits(
    max_connections=100, max_keepalive_connections=20, keepalive_expiry=30.0
)
MAX_RETRIES = 2
```

---

## 8. Caching Strategy

| 대상 | 저장소 | TTL | Key 패턴 | 절감 효과 |
|------|--------|-----|---------|----------|
| Intent 분류 | Redis | 3,600초 | `intent:MD5(msg)` | ~30% LLM 호출 |
| 프롬프트 파일 | In-memory LRU | 프로세스 수명 | `(category, name)` | I/O 제거 |
| 응답 캐시 | Redis | 86,400초 | `hash(intent+query+ctx)` | 동일 질의 즉시 응답 |

**장애 허용**: Redis 캐시 실패 시 graceful degradation → LLM 직접 호출

---

## 9. Cost Optimization

### 9.1 Eval Sampling

```python
eval_sample_rate: float = 1.0  # 0.0~1.0 범위
```

- Production: `0.05~0.10` (5~10% 샘플링) → 90~95% 비용 절감
- Shadow 모드: `1.0` (A/B 테스트 시 전수 평가)

### 9.2 Daily Budget Guardrail

```python
eval_cost_budget_daily_usd: float = 50.0
```

예산 소진 시 → 당일 잔여 요청에 대해 Eval sampling 비활성화

### 9.3 비용 추적

모든 `EvalResult`에 포함:
- `eval_cost_usd: float | None` — 실제 비용 (Code-only 시 None)
- `eval_duration_ms: int` — 지연 시간

### 9.4 비용 절감 종합

| 기법 | 절감율 |
|------|--------|
| Intent Cache (Redis) | ~30% |
| Model Tier (FAST vs PREMIUM) | ~50% |
| Eval Sampling (5%) | ~95% |
| Self-Consistency 3회 (vs 5회) | ~40% |

---

## 10. Streaming & Real-Time Quality

### 10.1 SSE Token 스트리밍

**소스**: `apps/sse_gateway/core/broadcast_manager.py`

| 기법 | 구현 |
|------|------|
| Token 중복 제거 | `last_token_seq` 시퀀스 기반 |
| Stage 이벤트 중복 제거 | Redis Stream ID (단조 증가) |
| Queue Overflow | 가장 오래된 비-terminal 이벤트 드롭 |
| 재연결 복구 | `TOKEN_STATE_PREFIX` 주기적 스냅샷 |

### 10.2 SSE Metrics

- `SSE_TTFB` — Time To First Byte
- `SSE_ACTIVE_JOBS` — 활성 작업 수
- `SSE_QUEUE_DROPPED` — 드롭된 이벤트 수
- `SSE_PUBSUB_SUBSCRIBE_LATENCY` — 구독 지연

---

## 11. Observability & Monitoring

### 11.1 Eval Pipeline Metrics

| 메트릭 | 타입 | 용도 |
|--------|------|------|
| `eval_continuous_score` | Gauge | 연속 점수 분포 추적 |
| `eval_grade` | Counter | 등급별 분포 (S/A/B/C) |
| `eval_needs_regeneration` | Counter | 재생성 트리거 빈도 |
| `eval_retry_count` | Histogram | 재생성 시도 횟수 |
| `eval_cost_usd` | Counter | 누적 비용 |
| `eval_duration_ms` | Histogram | 평가 지연 시간 |

### 11.2 CUSUM Drift Detection

- Two-Sided CUSUM: 상향/하향 드리프트 동시 감지
- `h = 4.0`: 감지 임계값
- 매 100번째 요청마다 체크
- 드리프트 탐지 시 → Alert (프롬프트/모델 변경 필요 신호)

### 11.3 LangSmith Integration

**소스**: `docs/reports/langsmith-telemetry-integration-report.md`

- Trace-level 디버깅
- Feedback annotation (품질 라벨링)
- Dataset 생성 (eval 학습용)
- Structured logging

---

## 12. Vision (Scan Worker)

### 12.1 이미지 기반 폐기물 분류

**소스**: `apps/scan_worker/infrastructure/llm/gpt/vision.py`

| 설정 | 값 |
|------|---|
| Model | `gpt-5.1` |
| Output Schema | `VisionResult` (Structured Output) |
| 분류 체계 | 대분류 → 중분류 → 소분류 |
| 상황 태그 | `situation_tags: List[str]` (컨텍스트 인식) |

### 12.2 LLM Provider 선택

```python
class LLMProvider(str, Enum):
    OPENAI = "openai"
    GEMINI = "gemini"
```

Scan API에서 클라이언트가 Provider 선택 가능 → A/B 테스트 지원

---

## 13. Testing & Quality Assurance

| 항목 | 수치 |
|------|------|
| Eval Pipeline 테스트 | 165+ (ALL PASS) |
| 커버리지 | 50% (1,475/2,975 lines) |
| 평균 복잡도 | A (2.29) |
| 유지보수성 | A (대부분 파일) |
| 추정 버그 | 0.26 (안정) |

테스트 범위:
- Unit: Code Grader, LLM Grader, Calibration, Scoring
- Integration: Subgraph 실행, 노드 연결
- E2E: 전체 파이프라인 흐름

---

## 14. Summary: LLM Precision 기법 전체 맵

| # | 카테고리 | 기법 | 핵심 값/설정 | 영향 |
|---|---------|------|------------|------|
| 1 | Prompt | Global + Local 이중 구조 | 23개 프롬프트, 1,500+ lines | 인텐트별 최적 지침 |
| 2 | Prompt | Structured Output 강제 | Pydantic + `strict: True` | 스키마 위반 제거 |
| 3 | Prompt | Repair Retry (파싱 실패) | max 2회, 에러 컨텍스트 포함 | 파싱 성공률 향상 |
| 4 | Intent | 신뢰도 기반 분류 | threshold: 0.6, temp: 0.1 | 잘못된 라우팅 방지 |
| 5 | Intent | Multi-Intent 3단계 검출 | 키워드 → LLM → 쿼리 분해 | 복합 질의 정밀 처리 |
| 6 | Intent | Chain-of-Intent 부스팅 | max boost: 0.15, min conf: 0.7 | 문맥 기반 예측 향상 |
| 7 | Intent | Policy Composition | Global + Local[A] + Local[B] | 멀티인텐트 응답 합성 |
| 8 | Intent | Redis Cache | TTL: 3,600초 | ~30% LLM 호출 절감 |
| 9 | RAG | Contextual Retrieval | chunk_id + relevance + tags | 27% 실패율 감소 |
| 10 | RAG | 4-Phase Feedback | Citation → Nugget → Ground → JIT | 다차원 품질 평가 |
| 11 | RAG | Fallback Chain | RAG → Web → Clarify → General | 응답 생성 보장 |
| 12 | RAG | Rule-Based Score | 4-factor weighted (threshold: 0.4) | 저비용 사전 필터 |
| 13 | Eval | Swiss Cheese 3-Tier | Code + LLM + Calibration | 단일 장애점 제거 |
| 14 | Eval | BARS 5-Axis Rubric | 5축 가중 평가 (faith: 0.30) | 다차원 품질 측정 |
| 15 | Eval | Self-Consistency | 3회 실행 → median | 평가 분산 감소 |
| 16 | Eval | Hazardous 가변 가중치 | safety: 0.15 → 0.25 | 위험물 안전 강화 |
| 17 | Eval | 연속 점수 (0-100) | S/A/B/C 등급 매핑 | 정보 손실 최소화 |
| 18 | Eval | Async Fire-and-Forget | 0ms 지연, 모니터링 전용 | 사용자 경험 무영향 |
| 19 | Eval | FAIL_OPEN | B등급(65.0) fallback | 평가 실패 → 응답 차단 없음 |
| 20 | Eval | CUSUM Drift Detection | h: 4.0, interval: 100 | 모델 드리프트 조기 경보 |
| 21 | Model | Multi-Model Tier | fast/standard/premium | 비용-품질 트레이드오프 |
| 22 | Model | Temperature 분리 | 0.1 (분류/평가), default (생성) | 태스크별 최적화 |
| 23 | Model | Token Budget 관리 | 동적 컨텍스트 압축 | 컨텍스트 윈도우 활용 극대화 |
| 24 | Guard | Input Validation | 빈 입력 차단, URL/위치 검증 | 노이즈 입력 제거 |
| 25 | Guard | Circuit Breaker | CLOSED/OPEN/HALF_OPEN | cascading failure 방지 |
| 26 | Guard | Exponential Backoff | 3회, 1~30초, ±25% jitter | transient 오류 복구 |
| 27 | Guard | Hallucination Blocklist | 키워드 매칭 | 위험 표현 차단 |
| 28 | Guard | Language Consistency | ≥ 80% 한국어 | 언어 혼합 방지 |
| 29 | Guard | Citation Enforcement | waste 인텐트 필수 | 근거 없는 답변 차단 |
| 30 | Cost | Eval Sampling | rate: 0.05~1.0 | 최대 95% 비용 절감 |
| 31 | Cost | Daily Budget | $50/일 | 비용 폭주 방지 |
| 32 | Cost | 비용 추적 | EvalResult.eval_cost_usd | 비용 가시화 |
| 33 | Cost | Prompt LRU Cache | maxsize=32 | I/O 제거 |
| 34 | Stream | Token Dedup | 시퀀스 기반 | 중복 토큰 제거 |
| 35 | Stream | Stage Dedup | Redis Stream ID 기반 | 중복 이벤트 제거 |
| 36 | Stream | Reconnection Recovery | 주기적 스냅샷 | 끊김 복구 |
| 37 | Observe | Eval Metrics | score, grade, cost, duration | 실시간 품질 모니터링 |
| 38 | Observe | LangSmith Tracing | Trace + Feedback + Dataset | 디버깅 + 학습 데이터 |
| 39 | Vision | Structured Classification | VisionResult 스키마 | 이미지 분류 정확성 |
| 40 | Vision | Multi-Provider | OpenAI / Gemini 선택 | A/B 테스트 가능 |
| 41 | Test | 165+ Eval Tests | Unit + Integration + E2E | 회귀 방지 |

---

## 15. Architectural Insight

### 왜 이 구조인가?

1. **Multi-Layer Defense**: 단일 기법에 의존하지 않고 10개 레이어를 중첩 → Swiss Cheese Model 원리
2. **Faithfulness 최우선**: 분리배출 도메인에서 할루시네이션은 안전 사고로 직결 → 가중치 0.30으로 최우선
3. **Async-First**: 평가가 응답 지연에 영향을 주지 않음 → 업계 표준(LangSmith, Langfuse)과 동일
4. **Evidence-Driven**: 모든 품질 판단(eval, RAG, intent)에 인용 증거 포함 → 디버깅 가능
5. **Cost-Aware**: Sampling + Caching + Tier로 30~95% 비용 절감 → 지속 운영 가능
6. **Graceful Degradation**: 모든 실패 경로에 fallback 존재 → 응답 생성 중단 없음

### Precision vs Latency 트레이드오프

```
                    Precision ──→
              Low          Med          High
         ┌──────────┬──────────┬──────────┐
  Fast   │ General  │ Cached   │ Code     │  ← < 50ms
         │ LLM      │ Intent   │ Grader   │
         ├──────────┼──────────┼──────────┤
  Med    │          │ RAG +    │ BARS     │  ← 1~5s
         │          │ Feedback │ (3-run)  │
         ├──────────┼──────────┼──────────┤
  Slow   │          │          │ CUSUM    │  ← 주기적
         │          │          │ Calibr.  │
         └──────────┴──────────┴──────────┘
                 Latency ──→
```

---

> **Total: 41 LLM Precision 기법** across 11 categories
> (Prompt Engineering, Intent Classification, RAG, Evaluation, Model Config, Guardrails, Cost, Streaming, Observability, Vision, Testing)
