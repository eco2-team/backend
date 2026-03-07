# Chat LangGraph Eval Pipeline 설계안 v2.2

| 항목 | 내용 |
|------|------|
| **Author** | Eco² Backend Team |
| **Date** | 2026-02-09 |
| **Version** | v2.2 (Round 4 Expert Review PASSED, avg 98.8/100) |
| **Purpose** | Eco² 채팅 에이전트의 응답 품질을 다층 방어(Swiss Cheese Model)로 평가하는 LangGraph 기반 Eval 파이프라인 설계 |
| **Status** | 설계 완료 — 구현 착수 가능 |
| **Review** | `docs/plans/chat-eval-pipeline-review.md` 참조 |

---

## 1. 목적 및 배경

### 1.1 Why Eval Pipeline?

현재 chat_worker의 feedback_node는 **Rule-Based + LLM Phase 1-4 평가**를 수행하고 있으나, 다음과 같은 한계가 존재합니다:

1. **단일 슬라이스 과신**: LLM Judge 하나에 의존하여 동일 편향의 사각지대가 반복됩니다
2. **Calibration Drift 미탐지**: 모델/프롬프트 변경 시 평가 기준 이동을 감지하지 못합니다
3. **정보 손실 미추적**: 다축 평가를 단일 등급으로 압축하는 과정에서 93.85%의 정보가 소실됩니다
4. **Eval Lifecycle 부재**: Capability → Graduation → Regression → Refresh 순환 체계가 없습니다

### 1.2 설계 원칙 (3개 포스팅 기반)

| 원칙 | 출처 | 적용 |
|------|------|------|
| Swiss Cheese 다층 방어 | Post #273 | Code + LLM + Human 3-Tier Grader |
| BARS 5점 루브릭 | Post #274 | 행동적 앵커 기반 채점 |
| 정보 손실 추적 | Post #274 | 연속 점수 보존 + 비대칭 가중치 |
| 직교 슬라이스 | Post #273 | 각 Grader가 다른 차원 평가 |
| Calibration Drift (CUSUM) | Post #274 | 통계적 공정 관리 |
| Layered Memory | Post #269 | Eval 결과 계층적 저장 |

### 1.3 기존 feedback_node와의 경계

| 구분 | feedback_node (기존) | eval_node (신규) |
|------|---------------------|-----------------|
| **평가 대상** | RAG 검색 품질 (pre-generation) | E2E 응답 품질 (post-generation) |
| **DTO** | `FeedbackResult` (Phase 1-4) | `EvalResult` (BARS 5-Axis) |
| **위치** | `waste_rag → feedback → aggregator` | `answer → eval → END` |
| **Fallback** | RAG 품질 미달 시 web_search 전환 | 응답 품질 미달 시 재생성 (1회) |
| **상호 참조** | - | `FeedbackResult.answer_quality.groundedness` → `EvalResult.faithfulness` 초기값 시딩 |

---

## 2. 아키텍처 개요

### 2.1 Eval Pipeline 위치 및 실행 모드

```
[Chat Pipeline]
intent → vision → router → [nodes] → aggregator → answer
                    │                                │
              feedback_node                    ┌─────┴─────┐
              (RAG 품질)                       │ eval_node  │
                                               └─────┬─────┘
                                                     │
                                          ┌──────────┼──────────┐
                                          ▼          ▼          ▼
                                       [sync]    [async]    [shadow]
                                       L1 only   L1+L2+L3  L1+L2+L3
                                       +regen?   fire-forget log only
```

**3가지 실행 모드 (Feature Flag 제어)**:

| 모드 | 설명 | Critical Path 영향 | 용도 |
|------|------|-------------------|------|
| **`sync`** | L1 Code Grader만 동기 실행. C등급 시 재생성 1회 | < 50ms | Production 기본값 |
| **`async`** | L1 동기 + L2/L3를 Celery Worker로 비동기 | L1만 < 50ms | Production 품질 추적 |
| **`shadow`** | L1+L2+L3 모두 비동기. 응답에 영향 없음. 로그만 | 0ms | A/B 테스트, 새 루브릭 검증 |

```python
# factory.py Feature Flags
@dataclass
class EvalConfig:
    enable_eval_pipeline: bool = False
    eval_mode: Literal["sync", "async", "shadow"] = "async"
    eval_sample_rate: float = 1.0          # 0.0~1.0 (비용 제어)
    eval_llm_grader_enabled: bool = True
    eval_regeneration_enabled: bool = False  # sync 모드 전용
    eval_model: str = "gpt-4o-mini"
    eval_temperature: float = 0.1
    eval_max_tokens: int = 1000
    eval_self_consistency_runs: int = 3
    eval_cusum_check_interval: int = 100   # N번째 요청마다 Calibration
    eval_cost_budget_daily_usd: float = 50.0
```

### 2.2 Eval Subgraph (LangGraph StateGraph)

```python
from langgraph.graph import StateGraph, END
from langgraph.types import Send

def create_eval_subgraph(
    code_grader: CodeGraderService,
    bars_evaluator: BARSEvaluator,
    calibration_monitor: CalibrationMonitorService,
    eval_config: EvalConfig,
) -> CompiledGraph:
    eval_graph = StateGraph(EvalState)

    # Nodes
    eval_graph.add_node("eval_entry", create_eval_entry_node())
    eval_graph.add_node("code_grader", create_code_grader_node(code_grader))
    eval_graph.add_node("llm_grader", create_llm_grader_node(bars_evaluator))
    eval_graph.add_node("calibration_check", create_calibration_node(calibration_monitor))
    eval_graph.add_node("eval_aggregator", create_eval_aggregator_node())
    eval_graph.add_node("eval_decision", create_eval_decision_node())

    # Entry → Parallel fan-out via Send API
    eval_graph.set_entry_point("eval_entry")
    eval_graph.add_conditional_edges(
        "eval_entry",
        route_to_graders,  # Returns list[Send]
    )

    # Fan-in to aggregator
    eval_graph.add_edge("code_grader", "eval_aggregator")
    eval_graph.add_edge("llm_grader", "eval_aggregator")
    eval_graph.add_edge("calibration_check", "eval_aggregator")

    # Aggregator → Decision → END
    eval_graph.add_edge("eval_aggregator", "eval_decision")
    eval_graph.add_edge("eval_decision", END)

    return eval_graph.compile()


def route_to_graders(state: EvalState) -> list[Send]:
    """Send API로 병렬 Grader 디스패치 (기존 dynamic_router.py 패턴 준수)"""
    sends = [Send("code_grader", state)]

    if state.get("llm_grader_enabled", True):
        sends.append(Send("llm_grader", state))

    # Calibration은 N번째 요청마다 (비용 절감)
    if state.get("should_run_calibration", False):
        sends.append(Send("calibration_check", state))

    return sends
```

### 2.3 EvalState TypedDict (독립 서브그래프 상태)

```python
from typing import TypedDict, Annotated
from langgraph.graph import add_messages

class EvalState(TypedDict, total=False):
    # ── Input (ChatState에서 주입) ──
    query: str
    intent: str
    answer: str
    rag_context: dict | None
    conversation_history: list[dict]
    feedback_result: dict | None           # 기존 FeedbackResult 시딩용

    # ── Config ──
    llm_grader_enabled: bool
    should_run_calibration: bool
    eval_retry_count: int                  # 재생성 카운터

    # ── Grader Outputs (각 채널 분리, priority_preemptive_reducer) ──
    code_grader_result: Annotated[dict | None, priority_preemptive_reducer]
    llm_grader_result: Annotated[dict | None, priority_preemptive_reducer]
    calibration_result: Annotated[dict | None, priority_preemptive_reducer]

    # ── Aggregated Output ──
    eval_result: dict | None               # EvalResult.to_dict()
    eval_grade: str | None                 # EvalGrade.value
    eval_continuous_score: float | None    # 0-100
    eval_needs_regeneration: bool
    eval_improvement_hints: list[str]      # 재생성 시 answer_node에 전달할 피드백
```

### 2.4 Main Graph 통합

```python
# factory.py 수정
def create_chat_graph(
    ...,
    eval_config: EvalConfig | None = None,
    eval_dependencies: EvalDependencies | None = None,
) -> CompiledGraph:
    graph = StateGraph(ChatState)
    # ... 기존 노드 등록 ...

    if eval_config and eval_config.enable_eval_pipeline:
        eval_subgraph = create_eval_subgraph(
            code_grader=eval_dependencies.code_grader,
            bars_evaluator=eval_dependencies.bars_evaluator,
            calibration_monitor=eval_dependencies.calibration_monitor,
            eval_config=eval_config,
        )
        graph.add_node("eval", eval_subgraph)

        # 기존 answer → END 엣지 대체
        graph.add_edge("answer", "eval")
        graph.add_conditional_edges(
            "eval",
            route_after_eval,
            {"pass": END, "regenerate": "answer"},
        )
    else:
        graph.add_edge("answer", END)  # 기존 동작 유지

    return graph.compile(checkpointer=checkpointer)


def route_after_eval(state: dict) -> str:
    """eval_mode=sync 시만 재생성 판단. async/shadow는 항상 pass."""
    grade = state.get("eval_grade")
    retry_count = state.get("eval_retry_count", 0)
    regen_enabled = state.get("eval_regeneration_enabled", False)

    if grade == "C" and retry_count < 1 and regen_enabled:
        return "regenerate"
    return "pass"
```

### 2.5 contracts.py 등록

```python
# contracts.py 추가
NODE_OUTPUT_FIELDS["eval"] = frozenset({
    "eval_result",
    "eval_grade",
    "eval_continuous_score",
    "eval_needs_regeneration",
    "eval_improvement_hints",
    "eval_retry_count",
})
```

### 2.6 ChatState 확장

```python
# state.py Layer 8: Evaluation (신규)
eval_result: dict | None = None                    # 단순 필드 (reducer 불필요, eval 후 1회 기록)
eval_grade: str | None = None                      # EvalGrade.value
eval_continuous_score: float | None = None
eval_needs_regeneration: bool = False
eval_retry_count: int = 0                          # 재생성 카운터 (무한루프 방지)
eval_improvement_hints: list[str] = field(default_factory=list)  # 재생성 가이드
```

### 2.7 NodePolicy 적용

```python
# policies/node_policy.py 추가
NODE_POLICIES["eval"] = NodePolicy(
    name="eval",
    timeout_ms=15000,          # Full eval 15s (async 모드)
    max_retries=0,             # Eval 실패 시 재시도 없음
    fail_mode=FailMode.FAIL_OPEN,  # Eval 실패해도 응답 전달
    cb_threshold=10,           # Circuit breaker: 10회 연속 실패 시 열림
    rationale="Eval failure must not block response delivery",
)
# CircuitBreaker 레벨에서 recovery_timeout 설정 (see A.2, B.1)
# eval_cb = CircuitBreaker(name="eval", threshold=10, recovery_timeout=60.0)

# sync 모드: EvalConfig.eval_mode에 따라 timeout_ms를 동적 결정 (see B.8)
# eval_mode == "sync" → timeout_ms=500, eval_mode == "async" → timeout_ms=15000
```

---

## 3. Swiss Cheese 3-Tier Grader 설계

### 3.1 Layer 1: Code-Based Grader (결정적)

**역할**: 정량적 임계치 기반의 빠르고 재현 가능한 평가. < 50ms.

| Slice | 측정 대상 | 방법 | 임계치 |
|-------|----------|------|--------|
| `format_compliance` | 응답 형식 준수 | Regex + 구조 검증 | 필수 필드 존재 여부 |
| `length_check` | 응답 길이 적정성 | Token count | 50 < tokens < 2000 |
| `language_consistency` | 한국어 자연어 문장 비율 | Unicode range (기술 용어/URL/이모지 제외) | >= 80% |
| `hallucination_keywords` | 금지 표현 탐지 | Keyword blocklist + 주기적 갱신 | 0 matches |
| `citation_presence` | 출처 정보 포함 | Pattern matching | waste intent 시 필수 |
| `intent_answer_alignment` | 의도-응답 정합성 | Intent별 구조 템플릿 매칭 | intent별 필수 섹션 존재 |

**구현 위치**: `application/services/eval/code_grader.py` (순수 비즈니스 로직, 외부 의존성 없음)

```python
@dataclass(frozen=True, slots=True)
class CodeGraderResult:
    scores: dict[str, float]         # slice_name → 0.0~1.0
    passed: dict[str, bool]          # slice_name → pass/fail
    details: dict[str, str]          # slice_name → 상세 사유
    overall_score: float             # 가중 합산

    def to_dict(self) -> dict: ...

    @classmethod
    def from_dict(cls, data: dict) -> CodeGraderResult: ...
```

### 3.2 Layer 2: LLM-Based Grader (확률적)

**역할**: 뉘앙스, 공감, 정확성 등 정성적 품질 평가

#### 3.2.1 평가 축 (5-Axis BARS Rubric)

각 축은 **5점 BARS(Behaviorally Anchored Rating Scale)**로 채점합니다.

**Axis 1: Faithfulness (사실 충실도)** — 가중치 0.30
```
1점: 컨텍스트에 없는 정보를 생성. 검증 불가능한 주장 포함
2점: 부분적으로 컨텍스트 기반이나 추론 비약 존재 (1개 이상 미지원 주장)
3점: 대부분 컨텍스트 기반. 경미한 해석 차이 1건 이하
4점: 모든 주장이 컨텍스트에서 직접 도출. 미지원 주장 0건
5점: 모든 주장에 명시적 근거 인용. 불확실한 정보에 "확인 필요" 표기
```

**Axis 2: Relevance (질문 관련성)** — 가중치 0.25
```
1점: 질문과 무관한 응답. 의도 파악 실패
2점: 질문의 일부만 다루며, 핵심 요구사항 누락
3점: 질문의 핵심을 다루나 부가 정보가 과도하거나 부족
4점: 질문에 정확히 대응. 필요 정보 모두 포함
5점: 질문에 정확히 대응 + 사용자가 암묵적으로 필요로 할 후속 정보 제공
```

**Axis 3: Completeness (정보 완결성)** — 가중치 0.20
```
1점: 필수 정보 중 20% 미만 포함 (TREC Nugget 기준)
2점: 필수 정보 20-50% 포함. 핵심 절차 누락
3점: 필수 정보 50-75% 포함. 보조 정보 일부 누락
4점: 필수 정보 75-95% 포함. 경미한 보조 정보만 누락
5점: 필수 정보 95% 이상 포함. 분리배출 절차 완전 안내
```

**Axis 4: Safety (안전성)** — 가중치 0.15 (위험물 intent 시 동적 0.25로 부스트)
```
1점: 유해 정보 포함 (잘못된 폐기 방법으로 환경/안전 위험)
2점: 불완전한 안전 정보 (주의사항 누락으로 잠재 위험)
3점: 안전 정보 포함하나 강조 부족
4점: 적절한 안전 정보 + 주의사항 명시
5점: 안전 정보 + 주의사항 + 대안 제시 (위험물 신고 안내 등)
```

**Axis 5: Communication (소통 품질)** — 가중치 0.10 (위험물 intent 시 0.05로 축소)
```
1점: 전문 용어 과다. 구조 없이 나열. 이해 불가
2점: 일부 구조화되나 순서/논리 혼란
3점: 기본 구조 갖춤. 단계별 안내 시도
4점: 명확한 단계별 안내. 이모지/마크다운 적절 활용
5점: 사용자 수준 맞춤 표현 + 단계별 안내 + 시각적 구분 + 친근한 톤
```

#### 3.2.2 Structured Output (Pydantic 스키마)

```python
# infrastructure/llm/evaluators/schemas.py
from pydantic import BaseModel, Field

class AxisEvaluation(BaseModel):
    score: int = Field(ge=1, le=5, description="BARS 1-5점")
    evidence: str = Field(description="근거 인용 (RULERS: 반드시 Retrieved Context에서 인용)")
    reasoning: str = Field(description="채점 근거")

class BARSEvalOutput(BaseModel):
    faithfulness: AxisEvaluation
    relevance: AxisEvaluation
    completeness: AxisEvaluation
    safety: AxisEvaluation
    communication: AxisEvaluation
```

LLM 호출 시 `generate_structured(schema=BARSEvalOutput)` 사용하여 **regex 파싱 제거**.
파싱 실패 시 retry-with-repair 루프 (최대 2회):
1. 첫 시도: `generate_structured()` (Structured Output)
2. 실패 시: 에러 메시지 + 원본 프롬프트로 재호출
3. 재실패 시: L1 Code Grader 결과만 사용 (graceful degradation)

`parse_success_rate` 메트릭을 Calibration Monitor에서 추적.

#### 3.2.3 LLM Judge 프롬프트 구조

```
infrastructure/assets/prompts/evaluation/
├── base_evaluation_system.txt     # 공통 System prompt (역할, RULERS 제약)
├── faithfulness_rubric.txt        # Axis별 BARS 앵커만
├── relevance_rubric.txt
├── completeness_rubric.txt
├── safety_rubric.txt
└── communication_rubric.txt
```

각 축은 **독립 프롬프트**로 호출 (Sycophancy 방지, context bleed 차단):
- 기본: 5개 축을 **단일 프롬프트**로 묶어 1회 호출 (비용 절감)
- Self-Consistency 트리거 시: 해당 축만 **개별 프롬프트**로 3회 독립 호출

#### 3.2.4 편향 대응 전략 (7종)

| # | 편향 | 대응 | 구현 |
|---|------|------|------|
| 1 | 중심 편향 (3점 쏠림) | Logprob 정규화 + 극단값 앵커 강화 | temperature=0.1 |
| 2 | 관대화 편향 | 부정 앵커(1-2점) 구체적 실패 행동 명시 | 루브릭 설계 |
| 3 | Sycophancy | 차원 독립 평가 | 각 축 독립 system prompt |
| 4 | 위치 편향 | 루브릭 순서 셔플링 | 평가 시 축 순서 무작위화 |
| 5 | Self-Consistency | 3회 독립 채점, CV < 0.2 | 고위험 구간(score ∈ [2.5, 3.5]) 선별 적용 |
| 6 | **Verbosity Bias** | 응답 길이 ↔ 점수 상관 모니터링 | `token_count_decorrelation`: Pearson r > 0.3 시 경고 |
| 7 | **Self-Enhancement Bias** | Judge 모델 ≠ 생성 모델 패밀리 | Cross-model validation: 10% 샘플에 다른 모델 패밀리 Judge 병행 |

**구현 위치**: `application/services/eval/llm_grader.py` (오케스트레이터, Port를 통해 LLM 호출)

```python
@dataclass(frozen=True, slots=True)
class LLMGraderResult:
    axis_scores: dict[str, AxisScore]   # axis_name → AxisScore (domain VO)
    raw_scores: list[dict]              # Self-Consistency 다회차 결과
    consistency_cv: float               # 변동계수
    overall_score: float                # 비대칭 가중 합산
    continuous_score: float             # 0-100 연속 점수
    model_version: str                  # 사용된 모델 ID
    prompt_version: str                 # 루브릭 git SHA

    def to_dict(self) -> dict: ...

    @classmethod
    def from_dict(cls, data: dict) -> LLMGraderResult: ...
```

### 3.3 Layer 3: Calibration & Drift Detection

**역할**: 평가 시스템 자체의 신뢰성 모니터링. 매 N번째 요청마다 실행 (기본 N=100).

#### 3.3.1 Calibration Set + Annotation Protocol

```python
@dataclass(frozen=True, slots=True)
class CalibrationSample:
    id: str
    query: str
    intent: str
    context: str
    answer: str
    ground_truth_scores: dict[str, int]  # axis → expert score (1-5)
    annotator_ids: list[str]             # 최소 2명
    inter_annotator_kappa: float         # Cohen's kappa (≥ 0.6 합격)
    created_at: datetime
    version: str                         # calibration set version
```

**Annotation Protocol**:
1. **최소 2명** 독립 어노테이터가 각 축을 **개별** 채점
2. **Cohen's kappa ≥ 0.6** 이상이어야 calibration set에 포함
3. kappa < 0.6인 샘플: **제3 어노테이터** adjudication
4. 강제 justification: 점수와 함께 근거 문장 기록 필수
5. **Intent별 층화 샘플링**: 10개 intent x 5-10개 = 50-100개
6. **갱신 주기**: 2주 또는 모델/프롬프트 변경 시

#### 3.3.2 Proper Two-Sided CUSUM

```python
def cusum_check(
    recent_scores: list[float],
    baseline_mean: float,
    baseline_std: float,
    k: float = 0.5,   # slack parameter
    h: float = 4.0,   # decision interval
) -> tuple[str, float, float]:
    """Proper tabular CUSUM (two-sided)."""
    s_pos, s_neg = 0.0, 0.0
    for s in recent_scores:
        z = (s - baseline_mean) / max(baseline_std, 1e-6)
        s_pos = max(0.0, s_pos + z - k)
        s_neg = max(0.0, s_neg - z - k)
        if s_pos > h or s_neg > h:
            return "CRITICAL", s_pos, s_neg
    if s_pos > h * 0.6 or s_neg > h * 0.6:
        return "WARNING", s_pos, s_neg
    return "OK", s_pos, s_neg
```

- **모니터링 대상**: 축별 평균 점수, Krippendorff's α (축별 개별), Pearson r
- **트리거**: α < 0.75 또는 r < 0.85 시 자동 재보정 알림 (Slack webhook)
- **추가 검증**: `parse_success_rate` (Structured Output 성공률) 모니터링
- **구현 위치**: `application/services/eval/calibration_monitor.py`

#### 3.3.3 축 판별 타당도 (Discriminant Validity)

Phase 1 (Capability Eval) 중 50+ 평가 결과 축적 후:
- 축 간 상관 행렬 계산
- **r > 0.85** 인 축 쌍 발견 시: 루브릭 앵커 세분화 또는 축 통합 검토
- 결과를 `calibration_drift_log`에 기록

### 3.4 Layer 4: Human-in-the-Loop (HITL) 샘플링

**역할**: Gold standard 품질 검증 + Calibration Set 신선도 유지

**자동 HITL 큐잉 조건**:
1. 등급 경계 근접: `continuous_score ∈ [53, 57] ∪ [73, 77]` (5% 자동 큐잉)
2. Self-Consistency CV > 0.2 (LLM Judge 불일치)
3. C등급 + 재생성 후에도 C등급 (최종 에스컬레이션)

**프로세스**:
- HITL 큐: RabbitMQ `eval.human_review` 큐로 발행
- Human 어노테이션 결과 → Calibration Set 갱신 (신선도 유지)
- LangGraph `interrupt_before=["eval_decision"]`으로 선택적 수동 개입 지원

---

## 4. Domain Layer 설계

### 4.1 Value Objects

```python
# domain/value_objects/axis_score.py
@dataclass(frozen=True, slots=True)
class AxisScore:
    """단일 평가축의 BARS 채점 결과. Immutable Value Object."""
    axis: str
    score: int              # 1-5 BARS
    evidence: str
    reasoning: str

    def __post_init__(self) -> None:
        if not 1 <= self.score <= 5:
            raise InvalidBARSScoreError(f"BARS score must be 1-5, got {self.score}")
        if not self.evidence.strip():
            raise InvalidBARSScoreError("Evidence must not be empty (RULERS)")

    @property
    def normalized(self) -> float:
        """0-100 정규화."""
        return (self.score - 1) / 4.0 * 100


# domain/value_objects/continuous_score.py
@dataclass(frozen=True, slots=True)
class ContinuousScore:
    """0-100 연속 점수. 정보 손실 추적 포함."""
    value: float            # 0-100
    information_loss: float # bits lost (32.51 - output bits)
    grade_confidence: float # 등급 경계까지 거리

    def __post_init__(self) -> None:
        if not 0.0 <= self.value <= 100.0:
            raise ValueError(f"Score must be 0-100, got {self.value}")
```

### 4.2 Enums

```python
# domain/enums/eval_grade.py
class EvalGrade(str, Enum):
    S = "S"  # >= 90
    A = "A"  # 75-89
    B = "B"  # 55-74
    C = "C"  # < 55

    @classmethod
    def from_continuous_score(cls, score: float) -> EvalGrade:
        if score >= 90:
            return cls.S
        elif score >= 75:
            return cls.A
        elif score >= 55:
            return cls.B
        return cls.C

    @property
    def needs_regeneration(self) -> bool:
        return self == EvalGrade.C

    @property
    def grade_boundary_distance(self) -> tuple[float, float]:
        """(하한까지 거리, 상한까지 거리) 반환."""
        boundaries = {"S": (90, 100), "A": (75, 89), "B": (55, 74), "C": (0, 54)}
        return boundaries[self.value]
```

### 4.3 Domain Service (Scoring Rules)

```python
# domain/services/eval_scoring.py
class EvalScoringService:
    """순수 비즈니스 로직: 점수 산출 규칙. 외부 의존성 없음."""

    # 비대칭 가중치 (순열 충돌 방지)
    DEFAULT_WEIGHTS: ClassVar[dict[str, float]] = {
        "faithfulness": 0.30,
        "relevance": 0.25,
        "completeness": 0.20,
        "safety": 0.15,
        "communication": 0.10,
    }

    # 위험물 intent 시 Safety 가중치 동적 부스트
    HAZARDOUS_WEIGHTS: ClassVar[dict[str, float]] = {
        "faithfulness": 0.30,
        "relevance": 0.25,
        "completeness": 0.15,
        "safety": 0.25,
        "communication": 0.05,
    }

    @staticmethod
    def compute_continuous_score(
        axis_scores: dict[str, AxisScore],
        weights: dict[str, float] | None = None,
    ) -> ContinuousScore:
        w = weights or EvalScoringService.DEFAULT_WEIGHTS
        weighted_sum = sum(
            w[axis] * score.normalized
            for axis, score in axis_scores.items()
            if axis in w
        )
        grade = EvalGrade.from_continuous_score(weighted_sum)
        # 정보 손실: 5^5 = 3125 combinations → 4 grades
        input_bits = 5 * math.log2(5)    # 11.61 bits
        output_bits = math.log2(4)        # 2.0 bits
        info_loss = input_bits - output_bits  # 9.61 bits

        lower, upper = grade.grade_boundary_distance
        boundary_dist = min(abs(weighted_sum - lower), abs(weighted_sum - upper))

        return ContinuousScore(
            value=round(weighted_sum, 2),
            information_loss=round(info_loss, 2),
            grade_confidence=round(boundary_dist, 2),
        )
```

### 4.4 Domain Exceptions

```python
# domain/exceptions/eval_exceptions.py
class InvalidBARSScoreError(DomainError):
    """BARS 1-5 범위 위반."""

class InvalidGradeError(DomainError):
    """유효하지 않은 등급."""

# application/exceptions/eval_exceptions.py
class EvalTimeoutError(ApplicationError):
    """Eval 처리 시간 초과."""

class MaxRegenerationReachedError(ApplicationError):
    """최대 재생성 횟수 도달."""

class CalibrationDriftError(ApplicationError):
    """Calibration drift CRITICAL 감지."""
```

---

## 5. Application Layer 설계

### 5.1 Ports (Protocol 기반)

```python
# application/ports/eval/bars_evaluator.py
class BARSEvaluator(Protocol):
    """LLM 기반 BARS 평가 Port. Infrastructure에서 구현.

    NOTE: rubric 로딩은 인프라 관심사이므로 어댑터가 내부 처리.
    Port 시그니처에서 rubric 파라미터 제거 (see B.6).
    """
    async def evaluate_axis(
        self, axis: str, query: str, context: str, answer: str
    ) -> AxisScore: ...

    async def evaluate_all_axes(
        self, query: str, context: str, answer: str
    ) -> dict[str, AxisScore]: ...


# application/ports/eval/eval_result_command_gateway.py
class EvalResultCommandGateway(Protocol):
    """Eval 결과 저장 (CQS: Command)."""
    async def save_result(self, eval_result: EvalResult) -> None: ...
    async def save_drift_log(self, drift_entry: dict) -> None: ...


# application/ports/eval/eval_result_query_gateway.py
class EvalResultQueryGateway(Protocol):
    """Eval 결과 조회 (CQS: Query)."""
    async def get_recent_scores(self, axis: str, n: int = 10) -> list[float]: ...
    async def get_daily_cost(self) -> float: ...
    async def get_intent_distribution(self, days: int = 7) -> dict[str, float]:
        """최근 N일간 intent별 트래픽 비율 반환. B.10 calibration coverage 검증에 사용."""
        ...


# application/ports/eval/calibration_data_gateway.py
class CalibrationDataGateway(Protocol):
    """Calibration Set 접근."""
    async def get_calibration_set(self) -> list[CalibrationSample]: ...
    async def get_calibration_version(self) -> str: ...
    async def get_calibration_intent_set(self) -> set[str]:
        """현재 calibration set에 포함된 intent 집합 반환. B.10 coverage 검증에 사용."""
        ...
```

### 5.2 DTOs

```python
# application/dto/eval_result.py
@dataclass
class EvalResult:
    continuous_score: float
    axis_scores: dict[str, dict]     # axis → {score, evidence, reasoning}
    grade: str                       # EvalGrade.value
    information_loss: float
    grade_confidence: float
    code_grader_result: dict | None
    llm_grader_result: dict | None
    calibration_status: str | None   # "OK" | "WARNING" | "CRITICAL"
    model_version: str
    prompt_version: str
    eval_duration_ms: int
    eval_cost_usd: float | None
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict: ...

    @classmethod
    def from_dict(cls, data: dict) -> EvalResult: ...

    @classmethod
    def code_only(cls, code_result: CodeGraderResult) -> EvalResult:
        """L1 Code Grader 결과만으로 생성 (degraded mode)."""
        ...

    @classmethod
    def failed(cls, reason: str) -> EvalResult:
        """평가 실패 시 기본값 생성."""
        ...
```

### 5.3 Command (UseCase)

```python
# application/commands/evaluate_response_command.py
class EvaluateResponseCommand:
    """응답 평가 오케스트레이션 UseCase.

    L1 Code Grader (순수 로직) → L2 LLM Grader (BARSEvaluator Port) →
    L3 Calibration (CalibrationDataGateway Port) → Score Aggregation (Domain Service)
    """
    def __init__(
        self,
        code_grader: CodeGraderService,
        bars_evaluator: BARSEvaluator,          # Port
        calibration_gateway: CalibrationDataGateway,  # Port
        eval_result_command: EvalResultCommandGateway, # Port
        eval_result_query: EvalResultQueryGateway,     # Port
        scoring_service: EvalScoringService,     # Domain Service
        eval_config: EvalConfig,
    ): ...

    async def execute(self, input: EvaluateResponseInput) -> EvaluateResponseOutput: ...
```

---

## 6. 점수 산출 체계

### 6.1 비대칭 가중치 + 동적 Safety 부스트

Domain Service `EvalScoringService.compute_continuous_score()` 참조 (Section 4.3).

위험물 카테고리 (`batteries`, `chemicals`, `electronics`, `medical_waste`) 감지 시:
- Safety 가중치: 0.15 → **0.25**
- Communication 가중치: 0.10 → **0.05**
- 연속 점수 산출: `((weighted_sum - 1.0) / 4.0) * 100`

### 6.2 등급 기준

| 등급 | 연속 점수 | 의미 | Regeneration |
|------|----------|------|-------------|
| S | >= 90 | 탁월 | No |
| A | 75-89 | 우수 | No |
| B | 55-74 | 보통 | No (로그만) |
| C | < 55 | 미흡 | Yes (sync 모드, 1회) |

### 6.3 재생성 시 UX 처리

**문제**: 재생성 시 SSE로 첫 번째(실패) 응답이 이미 스트리밍됨.

**해결**: sync 모드에서는 **L1 Code Grader만** 사용 (< 50ms).
- L1은 answer_node의 스트리밍 **완료 전** 빠르게 판단 가능
- C등급 판정 시: SSE `eval_regeneration_started` 이벤트 발행 → 프론트엔드에서 "더 나은 답변을 준비하고 있어요" 표시
- 재생성된 응답은 새 SSE 스트림으로 전달
- `eval_improvement_hints`를 answer_node에 전달하여 개선된 프롬프트로 재생성

---

## 7. Eval Lifecycle 관리

### 7.1 Phase 1: Capability Eval

```
목적: 에이전트가 무엇을 잘하는가 파악
기대 통과율: 30-50%
데이터: EvalTestCase (아래 스키마)
출력: Intent별 강점/약점 히트맵, 축 판별 타당도 행렬
```

### 7.2 Phase 2: Graduation

```
조건: Pass rate >= 90% 안정화 (연속 3회 배치)
결과: Capability Eval → Regression Eval 전환
기록: graduation_timestamp, baseline_scores, baseline_cusum
```

### 7.3 Phase 3: Regression Eval

```
목적: 기존 기능 유지 확인
기대 통과율: ~100%
트리거: 모델 변경, 프롬프트 수정, RAG 데이터 갱신
pre-merge gate: pass^5 >= 0.59
출력: 퇴행 감지 알림
```

### 7.4 Phase 4: Eval Refresh

```
증상: 100% 통과 지속 (포화)
대응:
  - 어려운 테스트 케이스 추가
  - Edge case 발굴
  - Adversarial 테스트 도입
```

### 7.5 Test Case 스키마

```python
@dataclass
class EvalTestCase:
    id: str
    query: str
    intent: str
    context: str
    expected_grade: EvalGrade
    expected_axis_ranges: dict[str, tuple[int, int]]  # axis → (min, max)
    phase: Literal["capability", "regression"]
    difficulty: Literal["easy", "medium", "hard", "adversarial"]
    direction: Literal["should_pass", "should_fail"]  # 양방향 균형
    created_at: datetime
    graduated_at: datetime | None = None
```

---

## 8. 평가 메트릭

### 8.1 pass@k vs pass^k

```python
# Eco² = Conversational Agent → pass^k 적용
pass_at_k = 1 - (1 - p) ** k    # 한번이라도 성공
pass_pow_k = p ** k               # 항상 성공

# 기본 설정: k=5, p=target 0.90 → pass^5 = 0.59
```

**적용 위치**: CI/CD Regression Eval (`pytest -m eval_regression`)에서 pass^5 계산.
Grafana 대시보드에 Rolling pass^5 per intent 패널.

### 8.2 양방향 균형 테스트 & Partial Credit

`test_cases.json`에 `direction: "should_pass" | "should_fail"` 필드로 구분.
Partial Credit은 축별 점수로 자연스럽게 지원 (binary pass/fail 아님).

---

## 9. 운영 인프라

### 9.1 Prometheus 메트릭

```python
# Counters
eval_total{grade, intent, mode}              # 평가 횟수
eval_regeneration_total{reason}              # 재생성 횟수
eval_drift_alert_total{severity, axis}       # 드리프트 알림
eval_parse_failure_total                     # Structured Output 파싱 실패

# Histograms
eval_duration_seconds{layer}                 # code|llm|calibration|total
eval_axis_score{axis}                        # 축별 점수 분포
eval_consistency_cv                          # Self-Consistency CV 분포

# Gauges
eval_cusum_value{axis}                       # 현재 CUSUM 값
eval_calibration_alpha{axis}                 # Krippendorff's α
eval_daily_cost_usd                          # 일일 누적 비용
eval_verbosity_correlation                   # 길이-점수 상관계수
```

### 9.2 CI/CD 통합

```yaml
# .github/workflows/eval.yml
name: Eval Pipeline CI
on:
  push:
    paths: ['apps/chat_worker/**']
  schedule:
    - cron: '0 3 * * *'  # Nightly Capability Eval

jobs:
  eval-regression:
    steps:
      - run: pytest -m eval_regression --tb=short
      - run: pytest -m eval_unit --tb=short

  eval-capability:
    if: github.event_name == 'schedule'
    steps:
      - run: pytest -m eval_capability --tb=short
      - uses: actions/upload-artifact@v4
        with:
          name: eval-results
          path: reports/eval/
```

**Pre-merge gate**: `eval-regression` 통과 필수.

### 9.3 모델/프롬프트 버전닝

```python
# EvalResult에 포함
model_version: str   # e.g., "gpt-4o-mini-2024-07-18"
prompt_version: str  # rubric 파일들의 git SHA (hashlib.sha256)

# 버전 비교 API
async def compare_eval_results(
    baseline_version: str,
    current_version: str,
) -> EvalComparisonReport: ...
```

### 9.4 비용 모델링 + 가드레일

| 모드 | 호출 수/평가 | 토큰/호출 | 비용/평가 (gpt-4o-mini) |
|------|------------|----------|----------------------|
| L1 Code only | 0 | 0 | $0.000 |
| L2 Basic (단일 프롬프트) | 1 | ~800 | $0.0001 |
| L2 + Self-Consistency | 3 | ~2,400 | $0.0004 |
| Full (L2 SC + 축별 분리) | 15 | ~7,500 | $0.001 |
| **월 예상** (10K req/day, async) | | | **$90-$300** |

**가드레일**: `eval_cost_budget_daily_usd` 초과 시 → L2 비활성화, L1만 운영.
일일 비용은 Redis counter로 추적 (`eval:daily_cost:{date}`).

---

## 10. 데이터 저장

### 10.1 Layered Memory

```
L1: Working Memory (EvalState / ChatState)
    → eval_result, eval_grade (현재 턴)

L2: Hot Storage (Redis)
    → eval:recent:{axis}  (최근 100개, CUSUM 입력, TTL=7d)
    → eval:daily_cost:{date} (일일 비용, TTL=30d)

L3: Cold Storage (PostgreSQL)
    → eval_results (전체 이력)
    → calibration_drift_log (드리프트 기록)
```

### 10.2 PostgreSQL 스키마

```sql
-- TEXT 기본 원칙: RFC/표준 근거 없는 컬럼은 TEXT 사용
-- CHECK 제약조건: 고정 값 집합은 CHECK IN 패턴 적용
-- TIMESTAMPTZ: 모든 시간 컬럼 타임존 포함

CREATE TABLE eval_results (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    job_id TEXT NOT NULL,
    thread_id TEXT,
    intent TEXT NOT NULL,
    grade CHAR(1) NOT NULL
        CHECK (grade IN ('S', 'A', 'B', 'C')),
    continuous_score FLOAT NOT NULL
        CHECK (continuous_score BETWEEN 0 AND 100),
    axis_scores JSONB NOT NULL,
    code_grader_result JSONB,
    llm_grader_result JSONB,
    calibration_status TEXT
        CHECK (calibration_status IN
            ('STABLE', 'DRIFTING', 'RECALIBRATING')),
    information_loss FLOAT,
    grade_confidence FLOAT,
    model_version TEXT,
    prompt_version TEXT,
    eval_mode TEXT NOT NULL
        CHECK (eval_mode IN ('full', 'code_only', 'llm_only')),
    eval_duration_ms INT,
    eval_cost_usd FLOAT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_eval_results_intent_created
    ON eval_results(intent, created_at DESC);
CREATE INDEX idx_eval_results_grade
    ON eval_results(grade);
CREATE INDEX idx_eval_results_job
    ON eval_results(job_id);

CREATE TABLE calibration_drift_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    axis TEXT NOT NULL,
    cusum_pos FLOAT NOT NULL,
    cusum_neg FLOAT NOT NULL,
    severity TEXT NOT NULL
        CHECK (severity IN ('OK', 'WARNING', 'CRITICAL')),
    baseline_mean FLOAT,
    baseline_std FLOAT,
    recent_scores JSONB,
    action_taken TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

---

## 11. Clean Architecture 디렉토리 구조

```
apps/chat_worker/
├── domain/
│   ├── value_objects/
│   │   ├── axis_score.py              # AxisScore VO (frozen, validated)
│   │   └── continuous_score.py        # ContinuousScore VO
│   ├── enums/
│   │   └── eval_grade.py              # EvalGrade Enum (S/A/B/C)
│   ├── services/
│   │   └── eval_scoring.py            # 순수 점수 산출 규칙
│   └── exceptions/
│       └── eval_exceptions.py         # InvalidBARSScoreError 등
│
├── application/
│   ├── commands/
│   │   └── evaluate_response_command.py  # UseCase 오케스트레이터
│   ├── services/
│   │   └── eval/
│   │       ├── code_grader.py            # L1 Code Grader (순수 로직)
│   │       ├── llm_grader.py             # L2 오케스트레이터 (Port 호출)
│   │       ├── calibration_monitor.py    # L3 모니터 (Port 통해 데이터 접근)
│   │       ├── score_aggregator.py       # Domain Service 위임
│   │       └── eval_lifecycle.py         # Phase 관리 (Port 통해 상태 저장)
│   ├── ports/
│   │   └── eval/
│   │       ├── bars_evaluator.py         # Protocol: LLM BARS 평가
│   │       ├── eval_result_command_gateway.py  # Protocol: 결과 저장
│   │       ├── eval_result_query_gateway.py    # Protocol: 결과 조회
│   │       └── calibration_data_gateway.py     # Protocol: Calibration 접근
│   ├── dto/
│   │   ├── eval_result.py                # EvalResult DTO (to_dict, from_dict, factories)
│   │   └── eval_test_case.py             # EvalTestCase 스키마
│   └── exceptions/
│       └── eval_exceptions.py            # EvalTimeoutError 등
│
├── infrastructure/
│   ├── orchestration/langgraph/
│   │   ├── nodes/
│   │   │   └── eval_node.py              # Thin adapter (state ↔ command)
│   │   ├── eval_graph_factory.py         # Eval subgraph 빌더
│   │   └── routing/
│   │       └── eval_router.py            # route_to_graders, route_after_eval
│   ├── llm/evaluators/
│   │   ├── bars_evaluator.py             # BARSEvaluator 어댑터 (Structured Output)
│   │   └── schemas.py                    # Pydantic: BARSEvalOutput
│   ├── eval/
│   │   ├── redis_eval_store.py           # EvalResultCommandGateway 구현 (Redis L2)
│   │   ├── postgres_eval_store.py        # EvalResultCommandGateway 구현 (PG L3)
│   │   └── json_calibration_store.py     # CalibrationDataGateway 구현
│   └── assets/
│       ├── prompts/evaluation/
│       │   ├── base_evaluation_system.txt
│       │   ├── faithfulness_rubric.txt
│       │   ├── relevance_rubric.txt
│       │   ├── completeness_rubric.txt
│       │   ├── safety_rubric.txt
│       │   └── communication_rubric.txt
│       └── eval/
│           ├── calibration_set_v1.json
│           └── test_cases.json
│
└── tests/
    ├── unit/
    │   ├── domain/
    │   │   ├── test_axis_score.py         # VO validation, normalization
    │   │   ├── test_continuous_score.py   # Range, info loss
    │   │   ├── test_eval_grade.py         # from_continuous_score, boundaries
    │   │   └── test_eval_scoring.py       # Weights, dynamic boost, edge cases
    │   ├── application/
    │   │   ├── services/eval/
    │   │   │   ├── test_code_grader.py    # 6 slices + boundary tests
    │   │   │   ├── test_llm_grader.py     # Mock BARSEvaluator, SC logic
    │   │   │   ├── test_score_aggregator.py # All zeros/fives, NaN
    │   │   │   └── test_calibration_monitor.py # CUSUM boundaries
    │   │   └── commands/
    │   │       └── test_evaluate_response.py # Policy/flow with AsyncMock
    │   └── infrastructure/
    │       └── test_eval_node.py           # State transform
    ├── integration/
    │   └── test_eval_pipeline.py           # Full subgraph execution
    └── e2e/
        └── test_eval_e2e.py                # RabbitMQ → eval → PG 저장
```

---

## 12. 테스트 전략

### 12.1 Unit 테스트

**Domain Layer**: `test_axis_score.py`
```python
# 경계값 테스트
def test_axis_score_valid_range(): ...
def test_axis_score_below_min_raises(): ...
def test_axis_score_above_max_raises(): ...
def test_axis_score_empty_evidence_raises(): ...
def test_axis_score_normalized(): ...
```

**Application Layer**: `test_llm_grader.py` (Mock 전략)
```python
@pytest.fixture
def mock_bars_evaluator() -> AsyncMock:
    evaluator = AsyncMock(spec=BARSEvaluator)
    evaluator.evaluate_all_axes.return_value = {
        "faithfulness": AxisScore(axis="faithfulness", score=4, evidence="...", reasoning="..."),
        # ... 5 axes
    }
    return evaluator

async def test_llm_grader_basic(mock_bars_evaluator): ...
async def test_llm_grader_self_consistency_triggered(mock_bars_evaluator): ...
async def test_llm_grader_parse_failure_degrades(mock_bars_evaluator): ...
async def test_llm_grader_timeout_degrades(mock_bars_evaluator): ...
```

**Golden Dataset**: 5-10개 `conftest.py` fixture로 CI에서 항상 실행.

### 12.2 Integration 테스트

```python
@pytest.mark.eval_regression
async def test_eval_subgraph_waste_query():
    """waste intent에 대한 full subgraph 실행."""
    ...

@pytest.mark.eval_regression
async def test_eval_subgraph_regeneration_loop():
    """C등급 → 재생성 → 최대 1회 검증."""
    ...

@pytest.mark.eval_regression
async def test_eval_subgraph_entry_failure_degrades_gracefully():
    """eval_entry 에러 시 EvalResult.failed() → eval_decision → END short-circuit 검증."""
    ...
```

### 12.3 pytest markers

```ini
# pyproject.toml
[tool.pytest.ini_options]
markers = [
    "eval_unit: Eval unit tests",
    "eval_regression: Eval regression tests (CI gate)",
    "eval_capability: Eval capability tests (nightly)",
]
```

---

## 13. 위험 요소 및 대응

| 위험 | 영향 | 대응 |
|------|------|------|
| LLM Eval 지연 | 응답 시간 증가 | async 기본 모드 + sync는 L1만 (< 50ms) |
| Structured Output 파싱 실패 | 평가 실패 | retry-with-repair 2회 → L1 fallback |
| 비용 초과 | 운영비 상승 | daily budget 가드레일 + sample_rate 조절 |
| 과도한 재생성 루프 | 무한 루프 | eval_retry_count in state + max 1회 |
| Calibration Set 편향 | 평가 왜곡 | Intent별 층화 샘플링 + kappa >= 0.6 |
| 축 간 과도한 상관 | 평가 중복 | Phase 1에서 r > 0.85 쌍 감지 → 루브릭 수정 |
| Self-Enhancement Bias | 자기 평가 과대 | Cross-model validation (10% 샘플) |
| SSE 재생성 UX | 사용자 혼란 | eval_regeneration_started 이벤트 + 프론트 대응 |
| Circuit Breaker 열림 | 평가 중단 | FAIL_OPEN 정책 → 응답은 항상 전달 |

---

## 14. 구현 로드맵

### Phase 1: Foundation (1주)
- [ ] Domain: AxisScore VO, ContinuousScore VO, EvalGrade Enum, EvalScoringService
- [ ] Application: 4개 Port (Protocol), EvalResult DTO, EvalConfig
- [ ] Application: CodeGraderService (6 slices)
- [ ] Infrastructure: eval_node, eval_graph_factory, contracts.py 등록
- [ ] Infrastructure: EvalConfig → factory.py Feature Flag 통합
- [ ] Tests: Domain unit + Code Grader unit + eval_node state transform

### Phase 2: LLM Judge (1주)
- [ ] Infrastructure: BARSEvalOutput Pydantic schema, bars_evaluator adapter
- [ ] Application: LLMGraderService (오케스트레이터)
- [ ] Application: ScoreAggregator (Domain Service 위임)
- [ ] Application: EvaluateResponseCommand (3-tier 오케스트레이션)
- [ ] 5-Axis BARS 프롬프트 작성 (base + 5 rubric files)
- [ ] Tests: LLM Grader unit (AsyncMock) + Integration (subgraph)
- [ ] NodePolicy + CircuitBreaker 적용

### Phase 3: Calibration & Ops (3일)
- [ ] Application: CalibrationMonitorService (proper CUSUM)
- [ ] Infrastructure: Redis eval store, Postgres eval store
- [ ] Calibration Set v1 수집 (50개, 2-annotator, kappa >= 0.6)
- [ ] Prometheus 메트릭 계기판 + Grafana 대시보드
- [ ] CI/CD: pytest markers + GitHub Actions workflow
- [ ] Runbook 작성: `docs/runbooks/eval-pipeline.md` (B.12 기반 alert/SLA/routing)

### Phase 4: Lifecycle & Polish (3일)
- [ ] Eval Lifecycle Manager (Phase transition logic)
- [ ] HITL queue (RabbitMQ eval.human_review)
- [ ] Shadow mode 검증 + A/B 비교 API
- [ ] E2E 테스트 + k6 부하 테스트 시나리오
- [ ] 모델/프롬프트 버전닝 + 비용 가드레일

---

## Appendix A: Round 2 잔여 갭 해결

> Round 2 리뷰(avg 89.2)에서 96+ 도달을 위해 식별된 교차 이슈 + 전문가별 세부 갭 해결

### A.1 ChatState ↔ EvalState 상태 브릿징 (LangGraph, Code)

EvalState는 독립 TypedDict이므로, 서브그래프 진입 시 ChatState → EvalState 매핑이 필요하다.

```python
# infrastructure/orchestration/langgraph/nodes/eval_node.py
def create_eval_wrapper_node(eval_config: EvalConfig):
    """ChatState → EvalState 변환 래퍼. 서브그래프 외부에서 실행."""
    def eval_wrapper(state: dict) -> dict:
        return {
            # ChatState → EvalState 필드 매핑
            "query": state.get("message", ""),
            "intent": state.get("intent", ""),
            "answer": state.get("answer", ""),
            "rag_context": state.get("disposal_rules"),
            "conversation_history": state.get("messages", []),
            "feedback_result": state.get("rag_feedback"),
            # Config injection
            "llm_grader_enabled": eval_config.eval_llm_grader_enabled,
            "should_run_calibration": _should_calibrate(state, eval_config),
            "eval_retry_count": state.get("eval_retry_count", 0),
        }
    return eval_wrapper

# factory.py에서:
graph.add_node("eval_bridge", create_eval_wrapper_node(eval_config))
graph.add_node("eval", eval_subgraph)
graph.add_edge("answer", "eval_bridge")
graph.add_edge("eval_bridge", "eval")
```

**서브그래프 출력 → ChatState 전파**: EvalState와 ChatState 간 동일 키 이름 (`eval_grade`, `eval_retry_count`, `eval_continuous_score`, `eval_needs_regeneration`, `eval_improvement_hints`, `eval_result`)으로 LangGraph의 자동 키 오버랩 매핑에 의해 전파됩니다.

### A.2 NodePolicy 스키마 확장 (LangGraph, Code)

기존 `NodePolicy` dataclass에 `cb_reset_timeout_ms` 필드가 없습니다. 두 가지 옵션이 있습니다:

**선택: Option B** — CircuitBreaker 레벨에서 설정하고 NodePolicy는 기존 스키마 유지.

```python
# eval NodePolicy (기존 스키마 호환)
NODE_POLICIES["eval"] = NodePolicy(
    name="eval",
    timeout_ms=15000,
    max_retries=0,
    fail_mode=FailMode.FAIL_OPEN,
    cb_threshold=10,
    rationale="Eval failure must not block response delivery",
)

# CircuitBreaker 초기화 시 별도 설정
eval_cb = CircuitBreaker(threshold=10, reset_timeout=60.0)  # 60s half-open
```

### A.3 Aggregator Nullable 처리 + priority_preemptive_reducer 계약 (LangGraph, CleanArch, Code)

`eval_aggregator_node`는 선택적 Grader 결과의 `None` 상태를 명시적으로 처리합니다.

```python
def create_eval_aggregator_node():
    def eval_aggregator(state: dict) -> dict:
        code_result = state.get("code_grader_result")   # 항상 존재
        llm_result = state.get("llm_grader_result")      # nullable (disabled 시)
        cal_result = state.get("calibration_result")     # nullable (interval 미도달 시)

        # L1은 필수, L2/L3는 선택적 병합
        if code_result and not llm_result:
            return EvalResult.code_only(CodeGraderResult.from_dict(code_result)).to_dict()
        # ... full aggregation when all present
    return eval_aggregator
```

**priority_preemptive_reducer 계약**: 기존 `state.py`의 `priority_preemptive_reducer`를 재사용합니다. 이 reducer는 `_priority`, `_sequence`, `success` 메타데이터 키를 사용하여 충돌을 해결합니다. 각 Grader 노드는 출력 시 이 메타데이터를 포함해야 합니다:

```python
# 각 grader 노드 출력 예시
return {"code_grader_result": {
    "scores": {...}, "overall_score": 0.85,
    "success": True, "_priority": 1, "_sequence": lamport_clock()
}}
```

### A.4 Protocol vs ABC 컨벤션 결정 (CleanArch)

**결정**: 신규 코드는 **Protocol** 사용. 기존 ABC 포트는 별도 마이그레이션 PR에서 전환.

```python
# Convention Decision Record
# - 신규 포트: Protocol (structural subtyping, 테스트 용이)
# - 기존 포트: ABC 유지 (호환성), 향후 `refactor/protocol-migration` 브랜치에서 일괄 전환
# - 마이그레이션 우선순위: eval ports > 기존 ports
```

이 결정을 `docs/plans/` 또는 ADR로 기록합니다.

### A.5 Base Exception 클래스 정의 (CleanArch)

```python
# domain/exceptions/base.py
class DomainError(Exception):
    """도메인 레이어 비즈니스 규칙 위반."""

# application/exceptions/base.py
class ApplicationError(Exception):
    """애플리케이션 레이어 UseCase 실행 오류."""
```

기존 코드베이스에 해당 클래스가 없으므로 eval 구현 Phase 1에서 함께 도입합니다.

### A.6 domain/services/ 패턴 도입 노트 (CleanArch)

`domain/services/`는 DDD의 표준 개념(Stateless Domain Service)이며, 기존 `domain/` 레이어의 의도적 확장입니다. `__init__.py`에서 export하며, 향후 다른 도메인 서비스(예: `IntentScoringService`)도 이 패턴을 따릅니다.

### A.7 Self-Consistency 집계 방법 (LLM Eval)

Self-Consistency 3회 독립 채점 시:
- **집계 방법**: **Median** (서수 BARS 점수에 대해 Mean보다 robust)
- **CV 계산**: 3회 점수의 표준편차 / 평균 (CV < 0.2 자동 승인)
- **트리거 조건**: 단일 프롬프트 결과 score ∈ [2.5, 3.5] 구간
- **3회 실행 시**: 각 run은 다른 축 순서 셔플링 적용 (편향 대응 #4와 복합)

### A.8 Cross-Model Validation 임계치 (LLM Eval)

```python
CROSS_MODEL_DIVERGENCE_THRESHOLD = 1.0  # BARS 점수 차이

# 10% 샘플에 대해 alternative judge (e.g., Claude) 병행
# 임의의 축에서 |primary_score - alternative_score| > 1.0 시:
#   → HITL 큐잉 (eval.human_review)
#   → eval_cross_model_divergence Prometheus counter 증가
```

### A.9 재생성 품질 게이트 (LLM Eval)

```python
MINIMUM_IMPROVEMENT_THRESHOLD = 5.0  # 연속 점수 최소 개선폭

def route_after_eval(state: dict) -> str:
    grade = state.get("eval_grade")
    retry_count = state.get("eval_retry_count", 0)
    regen_enabled = state.get("eval_regeneration_enabled", False)
    prev_score = state.get("_prev_eval_score")  # 이전 평가 점수
    curr_score = state.get("eval_continuous_score", 0)

    if grade == "C" and retry_count < 1 and regen_enabled:
        return "regenerate"

    # 재생성 후: 최소 개선폭 미달 시 그냥 전달
    if retry_count >= 1 and prev_score and (curr_score - prev_score) < MINIMUM_IMPROVEMENT_THRESHOLD:
        return "pass"  # 의미 없는 재생성 방지

    return "pass"
```

### A.10 Eval Lifecycle Phase 전환 자동화 (LLM Eval)

| 전환 | 조건 | "배치" 정의 |
|------|------|-----------|
| Phase 1 → 2 | pass rate >= 90%, **3회 연속 주간 배치** | 주간 배치 = 해당 주 전체 eval 결과 (최소 100건) |
| Phase 2 → 3 | Graduation 승인 | 수동 승인 + baseline 스냅샷 자동 저장 |
| Phase 3 → 4 | pass rate = 100%, **4주 연속** | 주간 배치 (최소 100건/주) |

`eval_lifecycle.py`에서 Redis 카운터로 주간 배치 집계, 전환 조건 자동 판단.

### A.11 Alerting Rules (ML Engineer)

| 메트릭 | 조건 | 심각도 | 라우팅 |
|--------|------|--------|--------|
| `eval_daily_cost_usd` | > budget * 0.8 | WARNING | Slack #eval-alerts |
| `eval_daily_cost_usd` | > budget | CRITICAL | Slack + L2 자동 비활성화 |
| `eval_cusum_value{axis}` | > h (4.0) | CRITICAL | Slack + Calibration 큐잉 |
| `eval_parse_failure_total` rate | > 10% / 5min | WARNING | Slack #eval-alerts |
| `eval_duration_seconds{layer="total"}` p99 | > 10s | WARNING | Slack #eval-alerts |
| `eval_calibration_alpha{axis}` | < 0.75 | CRITICAL | Slack + HITL 에스컬레이션 |

### A.12 EvalResult.failed() 기본값 (Code)

```python
@classmethod
def failed(cls, reason: str) -> EvalResult:
    return cls(
        continuous_score=0.0,
        axis_scores={},
        grade=EvalGrade.C.value,
        information_loss=0.0,
        grade_confidence=0.0,
        code_grader_result=None,
        llm_grader_result=None,
        calibration_status=None,
        model_version="",
        prompt_version="",
        eval_duration_ms=0,
        eval_cost_usd=0.0,
        metadata={"error": reason, "degraded": True},
    )
```

### A.13 EvalGrade.grade_boundary_distance 네이밍 수정 (Code)

```python
# 기존 (혼동 유발)
@property
def grade_boundary_distance(self) -> tuple[float, float]: ...

# 수정
@property
def grade_boundaries(self) -> tuple[float, float]:
    """해당 등급의 (하한, 상한) 반환."""
    boundaries = {"S": (90, 100), "A": (75, 89), "B": (55, 74), "C": (0, 54)}
    return boundaries[self.value]
```

`compute_continuous_score`에서 호출부도 `grade.grade_boundaries`로 변경.

### A.14 Cost Guardrail 테스트 (Code)

```python
# tests/unit/application/services/eval/test_cost_guardrail.py
@pytest.mark.eval_unit
async def test_cost_budget_exceeded_disables_llm_grader(mock_eval_query_gateway):
    mock_eval_query_gateway.get_daily_cost.return_value = 51.0  # > budget 50.0
    config = EvalConfig(eval_cost_budget_daily_usd=50.0)
    command = EvaluateResponseCommand(..., eval_config=config)
    result = await command.execute(input)
    assert result.llm_grader_result is None  # L2 비활성화 확인
    assert result.metadata.get("cost_budget_exceeded") is True
```

### A.15 Calibration Set 크기 통계적 근거 (LLM Eval)

50개 샘플 (SD=1.0 가정):
- **Standard Error**: SE = 1.0 / sqrt(50) ≈ 0.14
- **최소 탐지 효과 크기**: Cohen's d = 0.5 (medium effect), power 0.80, α = 0.05
- **50 샘플로 탐지 가능**: 0.5-point drift (5점 척도에서 10% 이동) at 80% power
- 이는 실무적으로 "B등급이 C등급으로 떨어지는 수준"의 드리프트 탐지에 충분

### A.16 Data Retention + Partitioning (ML Engineer)

```sql
-- 월별 파티셔닝 (PostgreSQL 12+)
CREATE TABLE eval_results (
    -- ... 기존 컬럼 ...
) PARTITION BY RANGE (created_at);

-- 월별 파티션 자동 생성 (pg_partman 또는 cron)
CREATE TABLE eval_results_2026_02 PARTITION OF eval_results
    FOR VALUES FROM ('2026-02-01') TO ('2026-03-01');

-- 보존 정책: 6개월 핫 → 아카이브 → 12개월 후 삭제
```

---

## Appendix B: Round 3 잔여 갭 해결

> Round 3 리뷰(avg 95.4)에서 96+ 도달을 위해 식별된 교차 이슈 해결

### B.1 CircuitBreaker 파라미터명 수정 (LangGraph)

A.2의 예시에서 `reset_timeout=60.0` → 실제 `CircuitBreaker.__init__` 시그니처는 `recovery_timeout`:

```python
# 올바른 호출
eval_cb = CircuitBreaker(name="eval", threshold=10, recovery_timeout=60.0)
```

Section 2.7도 `cb_reset_timeout_ms` 제거하고 `rationale` 필드 추가로 수정 완료 (본문 반영).

### B.2 `_prev_eval_score` 필드 선언 + 데이터 흐름 (LangGraph)

A.9의 `route_after_eval`이 참조하는 `_prev_eval_score`를 EvalState에 추가:

```python
# EvalState TypedDict 확장
class EvalState(TypedDict, total=False):
    # ... 기존 필드 ...
    _prev_eval_score: float | None  # 재생성 전 점수 (quality gate용)

# eval_aggregator_node에서 재생성 시 저장:
def eval_aggregator(state: dict) -> dict:
    result = aggregate(...)
    return {
        "eval_continuous_score": result.continuous_score,
        "_prev_eval_score": state.get("eval_continuous_score"),  # 이전 점수 보존
        # ...
    }
```

ChatState 확장에도 `_prev_eval_score: float | None = None` 추가.

### B.3 eval_bridge 아키텍처 재설계 (LangGraph, Code, CleanArch)

Round 3에서 가장 많은 전문가가 지적한 교차 이슈. eval_bridge를 **서브그래프 내부 entry 노드**로 이동하여 상위 그래프 state schema 충돌 해결:

```python
# eval_graph_factory.py
def create_eval_subgraph(eval_config: EvalConfig) -> CompiledGraph:
    eval_graph = StateGraph(EvalState)

    # Entry: ChatState 키 → EvalState 키 변환 (서브그래프 내부)
    def eval_entry(state: dict) -> dict:
        """서브그래프 entry 노드. 부모 ChatState에서 필요한 필드 추출."""
        return {
            "query": state.get("message", ""),
            "intent": state.get("intent", ""),
            "answer": state.get("answer", ""),
            "rag_context": state.get("disposal_rules"),
            "conversation_history": state.get("messages", []),
            "feedback_result": state.get("rag_feedback"),
            "llm_grader_enabled": eval_config.eval_llm_grader_enabled,
            "should_run_calibration": _should_calibrate(state, eval_config),
            "eval_retry_count": state.get("eval_retry_count", 0),
            "_prev_eval_score": state.get("eval_continuous_score"),
        }

    eval_graph.add_node("eval_entry", eval_entry)
    # ... grader nodes, aggregator ...
    eval_graph.set_entry_point("eval_entry")
    eval_graph.add_conditional_edges(
        "eval_entry",
        route_to_graders,  # Returns list[Send] — Section 2.2와 동일 패턴
    )
    return eval_graph.compile()

# factory.py (부모 그래프)에서:
eval_subgraph = create_eval_subgraph(eval_config)
graph.add_node("eval", eval_subgraph)  # 서브그래프를 직접 노드로 등록
graph.add_edge("answer", "eval")       # eval_bridge 불필요
graph.add_conditional_edges("eval", route_after_eval, {...})
```

**변경 사항**: A.1의 `eval_bridge` 외부 래퍼 → `eval_entry` 서브그래프 내부 entry 노드로 변경. LangGraph는 서브그래프 호출 시 부모 state를 그대로 전달하므로, entry 노드에서 필드 매핑이 자연스럽게 수행됨. 출력도 EvalState의 `eval_grade`, `eval_continuous_score` 등이 부모 ChatState의 동명 필드에 자동 병합.

**에러 처리**: eval_entry는 try/except로 감싸고, 실패 시 `EvalResult.failed()` 반환합니다. `route_to_graders`는 에러 상태를 감지하여 grader를 건너뛰고 `eval_decision` → `END`로 short-circuit합니다:

```python
def eval_entry(state: dict) -> dict:
    try:
        return { ... }  # 정상 매핑
    except Exception as e:
        logger.warning(f"eval_entry failed: {e}")
        failed = EvalResult.failed(f"eval_entry: {e}").to_dict()
        failed["_entry_failed"] = True  # short-circuit 시그널
        return failed

def route_to_graders(state: EvalState) -> list[Send]:
    # 에러 short-circuit: entry 실패 시 grader 건너뛰고 aggregator로 직행
    if state.get("_entry_failed"):
        return [Send("eval_aggregator", state)]
    sends = [Send("code_grader", state)]
    # ... 정상 경로 ...
    return sends
```

### B.4 서브그래프 출력 키 매핑 검증 테스트 (LangGraph, Code, CleanArch)

```python
# tests/unit/infrastructure/test_eval_subgraph_keys.py
@pytest.mark.eval_unit
def test_eval_output_keys_match_chat_state():
    """EvalState 출력 키가 ChatState에 존재하는지 검증."""
    from chat_worker.infrastructure.orchestration.langgraph.state import ChatState

    REQUIRED_EVAL_OUTPUT_KEYS = {
        "eval_result", "eval_grade", "eval_continuous_score",
        "eval_needs_regeneration", "eval_retry_count",
        "eval_improvement_hints", "_prev_eval_score",
    }
    chat_state_fields = set(ChatState.__annotations__.keys())
    missing = REQUIRED_EVAL_OUTPUT_KEYS - chat_state_fields
    assert not missing, f"ChatState에 누락된 eval 키: {missing}"
```

### B.5 conftest.py Eval 픽스처 + pyproject.toml 마커 등록 (Code)

```python
# tests/conftest.py (기존 파일에 추가)
@pytest.fixture
def eval_config() -> EvalConfig:
    """테스트용 EvalConfig (모든 기능 활성화)."""
    return EvalConfig(
        eval_enabled=True,
        eval_mode="async",
        eval_llm_grader_enabled=True,
        eval_self_consistency_enabled=True,
        eval_regeneration_enabled=True,
        eval_cost_budget_daily_usd=50.0,
    )

@pytest.fixture
def sample_eval_state() -> dict:
    """최소 EvalState 샘플."""
    return {
        "query": "플라스틱 병 분리배출 방법",
        "intent": "waste_query",
        "answer": "플라스틱 병은 내용물을 비우고 라벨을 제거한 후...",
        "rag_context": {"disposal_rules": [...]},
        "conversation_history": [],
        "feedback_result": {"overall_quality": "good"},
    }
```

```toml
# pyproject.toml (기존 markers 리스트에 추가)
[tool.pytest.ini_options]
markers = [
    "integration: marks tests as integration tests",
    "eval_unit: Eval unit tests (fast, no external deps)",
    "eval_regression: Eval regression tests (CI gate)",
    "eval_capability: Eval capability tests (nightly schedule)",
]
```

**asyncio_mode 호환성 노트**: 기존 `asyncio_mode = "auto"` 설정에 의해 `async def test_*` 함수는 `@pytest.mark.asyncio` 데코레이터 없이 자동 실행됨. Eval 테스트도 동일 패턴 적용.

### B.6 BARSEvaluator Port rubric 파라미터 제거 (CleanArch)

`evaluate_axis` 시그니처에서 `rubric: str` 제거 (본문 반영 완료). 루브릭 로딩은 인프라 어댑터 내부에서 처리:

```python
# infrastructure/llm/evaluators/bars_evaluator.py (어댑터)
class OpenAIBARSEvaluator:
    def __init__(self, rubric_dir: Path):
        self._rubrics = {
            axis: (rubric_dir / f"{axis}_rubric.txt").read_text()
            for axis in EVAL_AXES
        }

    async def evaluate_axis(self, axis: str, query: str, context: str, answer: str) -> AxisScore:
        rubric = self._rubrics[axis]  # 내부에서 로드
        # ... LLM 호출 ...
```

### B.7 Domain 레이어 배치 원칙 명문화 (CleanArch)

```
배치 원칙 (DDD Placement Criterion):
├── domain/services/     : 바운디드 컨텍스트의 불변 규칙 (invariant)
│   └── EvalScoringService — 가중치 산출, 등급 경계는 도메인 불변
│
├── application/services/ : 배포/운영 정책 (policy)에 따라 변할 수 있는 로직
│   ├── CodeGraderService — 체크 항목은 운영 정책 (새 format 추가 가능)
│   ├── LLMGraderService  — 외부 Port 호출 오케스트레이션
│   └── CalibrationMonitor — CUSUM 파라미터는 운영 설정
```

**결정 기준**: "이 로직이 모든 배포 환경에서 동일한가?" → Yes: domain/services, No: application/services.

`DomainError`는 `chat_worker/domain/exceptions/base.py`에 신규 생성 (apps/chat/ 에서 import하지 않음 — 마이크로서비스 경계 보호).

### B.8 eval NodePolicy 동적 타임아웃 (CleanArch, Code)

`eval_sync` 별도 정책 대신 단일 `eval` 정책 + `EvalConfig.eval_mode` 기반 동적 타임아웃:

```python
# factory.py에서 NodePolicy 등록 시:
eval_timeout = 500 if eval_config.eval_mode == "sync" else 15000
NODE_POLICIES["eval"] = NodePolicy(
    name="eval",
    timeout_ms=eval_timeout,
    max_retries=0,
    fail_mode=FailMode.FAIL_OPEN,
    cb_threshold=10,
    rationale=f"Eval {eval_config.eval_mode} mode: {eval_timeout}ms",
)
```

이로써 `eval_sync` 별도 키 불필요. 기존 `get_node_policy("eval")` 패턴 유지.

### B.9 Shadow Mode Observability 구체 스펙 (LLM Eval)

```python
# Shadow 모드 전용 Prometheus 메트릭
SHADOW_METRICS = {
    "eval_shadow_grade_distribution": Histogram(
        "eval_shadow_grade_distribution",
        "Grade distribution in shadow mode",
        labelnames=["grade", "intent"],
    ),
    "eval_shadow_duration_seconds": Histogram(
        "eval_shadow_duration_seconds",
        "Eval latency in shadow mode",
        buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0],
    ),
    "eval_shadow_vs_production_divergence": Gauge(
        "eval_shadow_vs_production_divergence",
        "Avg score diff between shadow and production evals",
        labelnames=["axis"],
    ),
}
```

**Grafana 대시보드 패널 (Shadow Analysis)**:
1. Shadow Grade Distribution (stacked bar, by intent)
2. Shadow vs Production Score Divergence (time series, per axis)
3. Shadow Eval Latency p50/p95/p99 (histogram)
4. Shadow Cost (daily rolling sum)

**A/B 비교 로직**: Shadow + Production 동시 실행 시, `eval_shadow_vs_production_divergence` 게이지를 axis별로 업데이트. 주간 리포트에 divergence > 10% axis 자동 하이라이트.

### B.10 Calibration Set 도메인 진화 대응 (LLM Eval, ML)

```python
# application/services/eval/calibration_monitor.py
async def check_calibration_coverage(
    self, eval_query_gw: EvalResultQueryGateway, calibration_gw: CalibrationDataGateway
):
    """활성 트래픽의 intent 분포와 calibration set 커버리지 비교."""
    active_intents = await eval_query_gw.get_intent_distribution(days=7)
    calibration_intents = await calibration_gw.get_calibration_intent_set()

    for intent, traffic_pct in active_intents.items():
        if intent not in calibration_intents and traffic_pct > 0.05:  # 5% 이상
            logger.warning(f"Calibration coverage gap: {intent} ({traffic_pct:.1%})")
            # → Slack alert + HITL 큐잉 (새 calibration 샘플 수집 트리거)
```

**Calibration Set 버전 마이그레이션 절차**:
1. 새 calibration set v(N+1) 준비 (신규 intent 포함, 최소 50샘플)
2. v(N)과 v(N+1) 병행 스코어링 (2주간)
3. 병행 결과에서 상관계수 r > 0.85 확인
4. v(N+1) baseline 스냅샷 저장 + CUSUM 리셋
5. v(N) 아카이브, v(N+1) 활성화

**마이그레이션 실패 경로 (r ≤ 0.85)**:
1. 마이그레이션을 자동 차단하고 v(N)을 유지합니다
2. Slack `#eval-alerts`에 `calibration_migration_blocked` 알림을 전송합니다 (severity: WARNING, SLA: 4h)
3. 불일치 원인 진단을 위해 축별 상관계수 분해 리포트를 생성합니다
4. HITL 큐에 해당 calibration set 샘플을 에스컬레이션하여 어노테이션 품질을 재검증합니다
5. 재검증 후 수정된 v(N+1)'로 마이그레이션 절차를 처음부터 재시작합니다

### B.11 Power Analysis SD 가정 검증 노트 (LLM Eval)

A.15의 SD=1.0 가정에 대한 보강:

> **Phase 1 검증 항목**: 실제 BARS 점수의 경험적 SD를 측정합니다. 만약 observed SD > 1.2이면, 최소 탐지 효과 크기 d=0.5를 80% power로 유지하기 위해 calibration set 크기를 확장합니다.
>
> 필요 샘플 수 공식: `n = (Z_alpha + Z_beta)^2 * SD^2 / delta^2`
> - SD=1.2: n = (1.96 + 0.84)^2 * 1.44 / 0.25 ≈ 45 → 50 유지 가능
> - SD=1.5: n = 7.84 * 2.25 / 0.25 ≈ 71 → 75로 확장 필요
> - SD=2.0: n = 7.84 * 4.0 / 0.25 ≈ 126 → 130으로 확장 필요

### B.12 Runbook + On-Call 에스컬레이션 (ML)

```yaml
# Eval Runbook Reference (docs/runbooks/eval-pipeline.md)
alerts:
  eval_cost_budget_warning:
    severity: WARNING
    action: "확인 후 sample_rate 조정"
    sla: 4h
    routing: Slack #eval-alerts

  eval_cost_budget_critical:
    severity: CRITICAL
    action: "L2 자동 비활성화됨. 원인 분석 후 재활성화"
    sla: 1h
    routing: Slack #eval-alerts + PagerDuty

  eval_cusum_drift:
    severity: CRITICAL
    action: "Calibration 재검증 + HITL 큐 확인"
    sla: 2h
    routing: Slack #eval-alerts + PagerDuty

  eval_parse_failure_rate:
    severity: WARNING
    action: "Structured Output 스키마 및 LLM 응답 확인"
    sla: 4h
    routing: Slack #eval-alerts
```

### B.13 버전 비교 통계 방법 (ML)

Section 9.3의 `compare_eval_results` API에 사용하는 통계 방법:

```python
async def compare_eval_results(
    baseline_version: str, current_version: str
) -> EvalComparisonReport:
    """Paired Wilcoxon signed-rank test (ordinal BARS 점수에 적합)."""
    from scipy.stats import wilcoxon

    baseline_scores = await get_calibration_scores(baseline_version)
    current_scores = await get_calibration_scores(current_version)

    stat, p_value = wilcoxon(baseline_scores, current_scores)

    # Bootstrap 95% CI for mean difference
    diffs = np.array(current_scores) - np.array(baseline_scores)
    ci_low, ci_high = bootstrap_ci(diffs, n_boot=10000, alpha=0.05)

    return EvalComparisonReport(
        p_value=p_value,
        mean_diff=np.mean(diffs),
        ci_95=(ci_low, ci_high),
        significant=p_value < 0.05,
    )
```

### B.14 Celery Eval Worker 오토스케일링 (ML)

```yaml
# workloads/scaling/eval-worker-keda.yaml
apiVersion: keda.sh/v1alpha1
kind: ScaledObject
metadata:
  name: eval-worker-scaledobject
spec:
  scaleTargetRef:
    name: chat-worker  # Celery worker deployment
  minReplicaCount: 1
  maxReplicaCount: 5
  triggers:
    - type: rabbitmq
      metadata:
        queueName: eval.run_evaluation
        queueLength: "10"  # 큐에 10개 이상 → 스케일아웃
        host: amqp://rabbitmq.messaging.svc.cluster.local
```

기존 `workloads/scaling/` 디렉토리의 HPA 패턴과 일관. eval 전용 큐 `eval.run_evaluation`의 depth 기반 자동 확장.

### B.15 contracts.py eval 노드 의미 구분 노트 (LangGraph)

```python
# contracts.py 추가
NODE_OUTPUT_FIELDS["eval"] = frozenset({
    "eval_result", "eval_grade", "eval_continuous_score",
    "eval_needs_regeneration", "eval_retry_count",
    "eval_improvement_hints", "_prev_eval_score",
})

# NOTE: eval 노드는 intent 응답 생성에 관여하지 않음 (품질 메타데이터 전용).
# is_node_required_for_intent("eval", any_intent) → always False.
# INTENT_REQUIRED_FIELDS에 eval 키를 추가하지 않음.
```

---

## 참고 문헌

1. [LLM-as-Judge 루브릭 설계](https://rooftopsnow.tistory.com/274) — BARS, 정보 손실, Calibration Drift
2. [Swiss Cheese Model for LLM Agent Evaluation](https://rooftopsnow.tistory.com/273) — 다층 방어, 직교 슬라이스, Eval Lifecycle
3. [Agent Memory Architecture](https://rooftopsnow.tistory.com/269) — Layered Memory, Eval 결과 저장 전략
4. Kim et al., "Prometheus" (ICLR 2024) — 5점 루브릭 기반 LLM-Human 상관도 0.897
5. TREC RAG Track — Nugget-based completeness evaluation
