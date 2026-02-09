# Chat Eval Pipeline 구현 리포트

> **작성일**: 2026-02-10
> **Author**: Claude Opus 4.6
> **대상**: `apps/chat_worker/` — Eval Pipeline Phase 1+2
> **상태**: ✅ 구현 완료 + 전문가 리뷰 통과 (97.1/100)
> **설계안**: `docs/plans/chat-eval-pipeline-plan.md` (v2.2)
> **PR**: https://github.com/eco2-team/backend/pull/545
> **Branch**: `feat/chat-eval-pipeline` → `develop`

---

## Related

| # | 문서 | 링크 |
|---|------|------|
| ADR-1 | Swiss Cheese Model for LLM Evaluation | https://rooftopsnow.tistory.com/273 |
| ADR-2 | LLM-as-Judge 루브릭 설계: 정보이론 관점의 해상도 분석 | https://rooftopsnow.tistory.com/274 |
| ADR-3 | Chat Eval Pipeline Integration Plan — Expert Review Loop | https://rooftopsnow.tistory.com/275 |
| ADR-4 | ADR: Chat LangGraph Eval Pipeline | https://rooftopsnow.tistory.com/276 |
| Design | `docs/plans/chat-eval-pipeline-plan.md` (v2.2) | — |
| Review | `docs/plans/chat-eval-pipeline-review.md` | — |
| PR | feat(eval): Chat Eval Pipeline — Swiss Cheese 3-Tier Grader | [#545](https://github.com/eco2-team/backend/pull/545) |

---

## 1. Executive Summary

Eco² 채팅 에이전트의 응답 품질을 자동 평가하는 **Swiss Cheese 3-Tier Grader** 파이프라인을 구현했습니다.

기존 `feedback_node`는 RAG 검색 품질(pre-generation)만 평가하고, 최종 응답 품질(post-generation)은 측정하지 않았습니다. 단일 LLM Judge에 의존하면 동일 편향이 반복되고, 모델/프롬프트 변경 시 채점 기준 이동(Calibration Drift)을 탐지할 수 없었습니다.

이를 해결하기 위해 **3개 독립 계층**이 서로 다른 차원을 평가하는 Swiss Cheese Model을 적용했습니다.

```
L1 Code Grader ──→ 결정적 규칙 기반 (< 50ms, 무비용)
L2 LLM Grader  ──→ BARS 5축 루브릭 + Self-Consistency (1-5s)
L3 Calibration ──→ CUSUM 통계적 드리프트 감지 (주기적)
       │
       ▼
 Score Aggregator → EvalResult (0-100 연속 점수 + S/A/B/C 등급)
```

### 핵심 수치

| 항목 | 수치 |
|------|------|
| 구현 소스 파일 | 24개 |
| BARS 루브릭 프롬프트 | 6개 |
| 단위 테스트 | 108개 (전수 통과) |
| 총 코드 규모 | ~4,000줄 |
| 설계 리뷰 점수 (R5) | 99.8 / 100 |
| 구현 리뷰 점수 (R2) | 97.1 / 100 |

---

## 2. 아키텍처 개요

### 2.1 Main Graph 내 위치

Eval 서브그래프는 `answer` 노드 이후, `END` 직전에 위치합니다.

```
┌─ Main Chat Graph ──────────────────────────────────────────────────┐
│                                                                     │
│  START → intent → [vision?] → router ─┬→ waste ────┐               │
│                                        ├→ character ┤               │
│                                        ├→ location ─┤──→ answer ──┐ │
│                                        ├→ web_search┤             │ │
│                                        └→ general ──┘             │ │
│                                                                    │ │
│  ┌─ Eval Subgraph (신규) ──────────────────────────────────────┐  │ │
│  │                                                              │  │ │
│  │  eval_entry ──→ ┬─ code_grader ────┐                        │◄─┘ │
│  │     (매핑)      ├─ llm_grader ─────┼→ eval_aggregator       │    │
│  │                 └─ calibration ────┘        │                │    │
│  │                                       eval_decision          │    │
│  │                                         │      │             │    │
│  └─────────────────────────────────────────│──────│─────────────┘    │
│                                            │      │                  │
│                              C등급 + 재생성 │      │ S/A/B등급        │
│                              ◄─────────────┘      └──────→ END       │
└──────────────────────────────────────────────────────────────────────┘
```

### 2.2 Eval Subgraph 내부 구조

LangGraph `Send` API로 L1/L2/L3를 **병렬 팬아웃** 실행합니다.

```
                        eval_entry
                            │
                   route_to_graders()
                    (Send API 분배)
                    ┌───────┼───────┐
                    ▼       ▼       ▼
              code_grader  llm_grader  calibration_check
              (L1, 항상)   (L2, 조건)   (L3, 주기적)
                    │       │       │
                    └───────┼───────┘
                            ▼
               priority_preemptive_reducer
                    (채널 병합)
                            │
                            ▼
                    eval_aggregator
                    (ScoreAggregator)
                            │
                            ▼
                      eval_decision
                  (재생성 판단 + 라우팅)
```

**`route_to_graders()`**는 상태를 보고 실제로 실행할 노드만 `Send` 리스트에 포함합니다:

- `code_grader`: 항상 포함
- `llm_grader`: `llm_grader_enabled == True`일 때만
- `calibration_check`: `should_run_calibration == True`일 때만

---

## 3. Clean Architecture 계층 설계

### 3.1 의존 방향

```
┌──────────────────────────────────────────────────────────────────┐
│                        Dependency Rule                            │
│               의존은 반드시 안쪽(Domain)으로만 향한다               │
├──────────────────────────────────────────────────────────────────┤
│                                                                   │
│  Infrastructure ──▶ Application ──▶ Domain ◀── (순수 Python)     │
│  (Adapters)         (UseCases)      (Entities)                   │
│                                                                   │
│  Infrastructure는 Application Port를 implements                  │
│  Application은 Domain Service를 uses                             │
│                                                                   │
└──────────────────────────────────────────────────────────────────┘
```

### 3.2 계층별 구성 요소

**Domain Layer** — 순수 비즈니스 규칙, 외부 의존 없음

| 컴포넌트 | 파일 | 역할 |
|----------|------|------|
| `EvalGrade` | `domain/enums/eval_grade.py` | S/A/B/C 등급 Enum, 경계 매핑 |
| `AxisScore` | `domain/value_objects/axis_score.py` | BARS 단축 축 VO (frozen) |
| `ContinuousScore` | `domain/value_objects/continuous_score.py` | 0-100 연속 점수 VO |
| `CalibrationSample` | `domain/value_objects/calibration_sample.py` | 보정 샘플 VO |
| `EvalScoringService` | `domain/services/eval_scoring.py` | 비대칭 가중 합산 로직 |
| Domain Exceptions | `domain/exceptions/eval_exceptions.py` | 검증 예외 |

**Application Layer** — UseCase 오케스트레이션, Port 정의

| 컴포넌트 | 파일 | 역할 |
|----------|------|------|
| `EvalConfig` | `application/dto/eval_config.py` | Feature Flag + 실행 설정 |
| `EvalResult` | `application/dto/eval_result.py` | 통합 평가 결과 (frozen) |
| `BARSEvaluator` | `application/ports/eval/bars_evaluator.py` | LLM 평가 Protocol |
| `EvalResultCommandGateway` | `application/ports/eval/...` | 결과 저장 Protocol |
| `EvalResultQueryGateway` | `application/ports/eval/...` | 결과 조회 Protocol |
| `CalibrationDataGateway` | `application/ports/eval/...` | 보정 데이터 Protocol |
| `CodeGraderService` | `application/services/eval/code_grader.py` | L1 결정적 평가 |
| `LLMGraderService` | `application/services/eval/llm_grader.py` | L2 BARS 평가 |
| `ScoreAggregatorService` | `application/services/eval/score_aggregator.py` | 다층 결과 통합 |
| `CalibrationMonitorService` | `application/services/eval/calibration_monitor.py` | L3 CUSUM 드리프트 |
| `EvaluateResponseCommand` | `application/commands/evaluate_response_command.py` | 3-Tier 오케스트레이터 |

**Infrastructure Layer** — 외부 연동 어댑터

| 컴포넌트 | 파일 | 역할 |
|----------|------|------|
| `OpenAIBARSEvaluator` | `infrastructure/llm/evaluators/bars_evaluator.py` | BARSEvaluator 구현체 |
| Pydantic Schemas | `infrastructure/llm/evaluators/schemas.py` | Structured Output 스키마 |
| BARS Prompts (6개) | `infrastructure/assets/prompts/evaluation/` | 루브릭 앵커 텍스트 |
| `eval_node.py` | `infrastructure/orchestration/langgraph/nodes/` | ChatState→EvalState 매핑 |
| `eval_graph_factory.py` | `infrastructure/orchestration/langgraph/` | 서브그래프 빌더 |

---

## 4. 3-Tier Grader 상세

### 4.1 L1: Code Grader — 결정적 규칙 기반

비용 0, 지연 < 50ms. 6개의 직교 슬라이스로 응답의 구조적 품질을 검사합니다.

| 슬라이스 | 가중치 | 검사 대상 | 기준 예시 |
|----------|--------|-----------|-----------|
| `format_compliance` | 0.15 | 마크다운 구조, 괄호 매칭 | 깨진 코드블록 감지 |
| `length_check` | 0.15 | 토큰 수 | 50 ≤ tokens ≤ 2,000 |
| `language_consistency` | 0.15 | 한국어 비율 | ≥ 80% |
| `hallucination_keywords` | 0.25 | 금지 표현 블록리스트 | "100% 안전", "아무렇게나 버려도" 등 14개 |
| `citation_presence` | 0.15 | 출처 표기 패턴 | "환경부", "출처:", "※" 등 |
| `intent_answer_alignment` | 0.15 | Intent별 필수 섹션 | waste: "분리배출", "방법", "주의" |

**출력**: `CodeGraderResult(scores, passed, details, overall_score)`

실패한 슬라이스는 `improvement_hints`로 수집되어 재생성 시 `answer_node`에 전달됩니다:
```
[L1] hallucination_keywords: 금지 표현 2건 감지
[L1] citation_presence: 출처 미포함
```

### 4.2 L2: LLM Grader — BARS 5축 루브릭

BARS(Behaviorally Anchored Rating Scale) 5축을 LLM-as-Judge로 채점합니다.

**5축 및 가중치** (ADR-2 기반):

| 축 | 가중치 | 평가 대상 |
|----|--------|-----------|
| **Faithfulness** | 0.30 | RAG 컨텍스트 대비 사실 충실도 |
| **Relevance** | 0.25 | 질문에 대한 관련성 |
| **Completeness** | 0.20 | 필요 정보의 완결성 |
| **Safety** | 0.15 | 안전성 (위험/오해 소지) |
| **Communication** | 0.10 | 소통 품질 (명확성, 자연스러움) |

> waste/bulk_waste Intent에는 `HAZARDOUS_WEIGHTS`가 적용되어 Safety 가중치가 상향됩니다.

**BARS 앵커**: 각 축별로 1-5점에 대한 행동적 앵커를 한국어로 정의하여 `infrastructure/assets/prompts/evaluation/` 아래 6개 파일로 관리합니다.

**편향 완화 전략** (ADR-2 기반):

| 편향 유형 | 완화 전략 | 구현 |
|-----------|-----------|------|
| Position Bias | 5축 루브릭 블록 순서를 매 호출마다 셔플 | `bars_evaluator.py` |
| Verbosity Bias | RULERS #6: "길이-품질 비상관" 명시 | `bars_system.txt` |
| Score Instability | Self-Consistency (아래 참조) | `llm_grader.py` |

**Self-Consistency 전략**:

BARS 1-5점 중 경계 점수(2, 4)는 등급 변동 리스크가 큽니다. 이 구간에서 추가 N회 독립 평가 후 중앙값을 채택합니다.

```
원본 평가: faithfulness=4 (경계 점수!)
추가 3회:  [3, 4, 3]
전체 집합: [4, 3, 4, 3]  → 중앙값 = 3 채택
```

비경계 점수(1, 3, 5)는 등급 경계에서 멀어 변동해도 같은 등급을 유지하므로 추가 평가를 하지 않습니다.

**Retry-with-Repair**: Structured Output 파싱 실패 시 최대 2회 재시도합니다. (`_MAX_PARSE_RETRIES = 2`)

### 4.3 L3: Calibration Monitor — CUSUM 드리프트 감지

Two-Sided CUSUM(Cumulative Sum) 알고리즘으로 채점 기준 이동을 통계적으로 감지합니다.

```
S⁺(i) = max(0, S⁺(i-1) + (xᵢ − μ₀ − k))    상향 이동
S⁻(i) = max(0, S⁻(i-1) + (μ₀ − xᵢ − k))    하향 이동
```

| 파라미터 | 값 | 의미 |
|----------|-----|------|
| μ₀ | 3.0 | BARS 5점 척도 기대 평균 |
| k (slack) | 0.5 | 허용 변동폭 |
| h (critical) | 4.0 | ~3σ 수준 — CRITICAL 경보 |
| h × 0.6 | 2.4 | ~2σ 수준 — WARNING 경고 |

**심각도 분류**:

| 수준 | 조건 | 의미 |
|------|------|------|
| OK | max(S⁺, S⁻) < 2.4 | 안정적 |
| WARNING | 2.4 ≤ max < 4.0 | 주의 필요 |
| CRITICAL | max ≥ 4.0 | 모델/프롬프트 변경 후 채점 기준 이동 의심 |

5축 각각에 대해 독립적으로 CUSUM을 계산하여, 특정 축만 드리프트가 발생하는 경우도 탐지합니다.

### 4.4 Score Aggregator — 다층 결과 통합

L1(Code) + L2(LLM) 결과를 단일 `EvalResult`로 합산합니다.

```
                    L1 Code Result
                         │
                         ▼
                    ┌─────────┐
L2 LLM Scores ───▶│ Aggregate │──▶ EvalResult
                    └─────────┘       │
                         │            ├── continuous_score: 0-100
                         ▼            ├── grade: S/A/B/C
              EvalScoringService      ├── information_loss: 9.61 bits
              (비대칭 가중 합산)       ├── grade_confidence: 경계까지 거리
                                      ├── code_grader_result
                                      ├── llm_grader_result
                                      └── calibration_status
```

**점수 체계** (ADR-2 기반):

```
BARS 5축 × 5점                비대칭 가중 합산              경계 매핑
(5⁵ = 3,125 상태)  ──────▶  Continuous Score  ──────▶  Grade (S/A/B/C)
 11.61 bits                    0-100 연속                  2.0 bits
                                                    정보 손실: 9.61 bits
```

| 등급 | 범위 | 의미 | 재생성 |
|------|------|------|--------|
| S | 90-100 | 최고 품질 | - |
| A | 75-89 | 양호 | - |
| B | 55-74 | 보통 (FAIL_OPEN 기본값) | - |
| C | 0-54 | 미달 | 재생성 트리거 (1회) |

---

## 5. 비용 제어 및 안전 장치

### 5.1 다단계 비용 가드레일

```
요청 도착
    │
    ▼
eval_sample_rate ── 랜덤 샘플링 (기본 100%)
    │                   └── 제외 시 → B등급 반환 (FAIL_OPEN)
    ▼
L1 Code Grader ──── 무비용, 항상 실행
    │
    ▼
get_daily_cost() ── 일일 비용 체크 (< $50 USD)
    │                   └── 초과 시 → L1-only 모드 (Degraded)
    ▼
L2 LLM Grader ──── BARS 평가 실행
    │
    ▼
request_counter ─── N번째 요청마다 L3 실행 (기본 100회)
    │
    ▼
eval_decision ──── C등급 + 재생성 활성 시 1회만 재생성
                        └── MINIMUM_IMPROVEMENT_THRESHOLD = 5.0점
```

### 5.2 FAIL_OPEN 정책 (ADR-1 기반)

평가 파이프라인의 장애가 서비스에 영향을 주어서는 안 됩니다.

| 실패 지점 | 동작 | 등급 |
|-----------|------|------|
| eval_entry 예외 | `_entry_failed=True` → short-circuit | B |
| L2 LLM 타임아웃/예외 | 빈 dict 반환 → L1-only 모드 | - |
| L3 Calibration 예외 | `calibration_status=None` | - |
| Aggregation 예외 | `EvalResult.failed(reason)` | B |
| 결과 저장 예외 | 로그만 남김 (non-blocking) | - |

B등급(55-74)은 재생성을 트리거하지 않으므로, 평가 실패 시 응답이 그대로 사용자에게 전달됩니다.

### 5.3 실행 모드 3종

| 모드 | L1 | L2 | L3 | 응답 영향 | 용도 |
|------|----|----|-----|-----------|------|
| `sync` | 동기 | 동기 (5s timeout) | — | 재생성 가능 | 실시간 품질 보장 |
| `async` | 동기 | 비동기 (30s) | 비동기 | 없음 | Production 모니터링 |
| `shadow` | 비동기 | 비동기 (60s) | 비동기 | 없음 | A/B 테스트, 로그만 |

---

## 6. EvalConfig Feature Flags

`EvalConfig` DTO가 전체 파이프라인의 동작을 제어합니다.

| 설정 | 기본값 | 역할 |
|------|--------|------|
| `enable_eval_pipeline` | `False` | Eval Pipeline 활성화 여부 |
| `eval_mode` | `"async"` | 실행 모드 (sync/async/shadow) |
| `eval_sample_rate` | `1.0` | 평가 샘플링 비율 (0.0-1.0) |
| `eval_llm_grader_enabled` | `True` | L2 LLM Grader 활성화 |
| `eval_regeneration_enabled` | `False` | C등급 재생성 활성화 |
| `eval_model` | `"gpt-4o-mini"` | 평가용 LLM 모델 |
| `eval_temperature` | `0.1` | 평가 LLM temperature |
| `eval_max_tokens` | `1000` | 평가 LLM max tokens |
| `eval_self_consistency_runs` | `3` | Self-Consistency 추가 평가 횟수 |
| `eval_cusum_check_interval` | `100` | N번째 요청마다 Calibration 실행 |
| `eval_cost_budget_daily_usd` | `50.0` | 일일 평가 비용 상한 (USD) |

---

## 7. 파일 구조

```
apps/chat_worker/
│
├── domain/
│   ├── enums/
│   │   └── eval_grade.py                    # EvalGrade (S/A/B/C)         90줄
│   ├── value_objects/
│   │   ├── axis_score.py                    # AxisScore (frozen VO)        72줄
│   │   ├── continuous_score.py              # ContinuousScore (frozen)     65줄
│   │   └── calibration_sample.py            # CalibrationSample (frozen)   80줄
│   ├── services/
│   │   └── eval_scoring.py                  # EvalScoringService           84줄
│   └── exceptions/
│       └── eval_exceptions.py               # Domain 예외                  47줄
│
├── application/
│   ├── dto/
│   │   ├── eval_config.py                   # EvalConfig                   51줄
│   │   └── eval_result.py                   # EvalResult (frozen)         178줄
│   ├── ports/eval/
│   │   ├── bars_evaluator.py                # BARSEvaluator Protocol       84줄
│   │   ├── eval_result_command_gateway.py   # 결과 저장 Protocol           50줄
│   │   ├── eval_result_query_gateway.py     # 결과 조회 Protocol           66줄
│   │   └── calibration_data_gateway.py      # 보정 데이터 Protocol         70줄
│   ├── services/eval/
│   │   ├── code_grader.py                   # L1 Code Grader             498줄 ★
│   │   ├── llm_grader.py                    # L2 LLM Grader              203줄
│   │   ├── score_aggregator.py              # Score Aggregator            179줄
│   │   └── calibration_monitor.py           # L3 Calibration             274줄
│   └── commands/
│       └── evaluate_response_command.py     # 3-Tier Orchestrator         305줄
│
├── infrastructure/
│   ├── llm/evaluators/
│   │   ├── schemas.py                       # Pydantic Schemas             72줄
│   │   └── bars_evaluator.py                # OpenAIBARSEvaluator         251줄
│   ├── assets/prompts/evaluation/
│   │   ├── bars_system.txt                  # System Prompt                21줄
│   │   ├── bars_faithfulness.txt            # Faithfulness 앵커            28줄
│   │   ├── bars_relevance.txt               # Relevance 앵커              28줄
│   │   ├── bars_completeness.txt            # Completeness 앵커           29줄
│   │   ├── bars_safety.txt                  # Safety 앵커                 30줄
│   │   └── bars_communication.txt           # Communication 앵커          29줄
│   └── orchestration/langgraph/
│       ├── nodes/eval_node.py               # Entry Adapter              135줄
│       └── eval_graph_factory.py            # Subgraph Builder           633줄 ★
│
└── tests/unit/                              # 13개 파일, 108개 테스트
    ├── domain/
    │   ├── enums/test_eval_grade.py                          14 tests
    │   ├── services/test_eval_scoring.py                      9 tests
    │   └── value_objects/
    │       ├── test_axis_score.py                            11 tests
    │       ├── test_calibration_sample.py                     6 tests
    │       └── test_continuous_score.py                      10 tests
    ├── application/
    │   ├── commands/eval/test_evaluate_response.py            8 tests
    │   └── services/eval/
    │       ├── test_code_grader.py                           15 tests
    │       ├── test_llm_grader.py                             6 tests
    │       ├── test_score_aggregator.py                       7 tests
    │       └── test_calibration_monitor.py                    6 tests
    └── infrastructure/
        ├── llm/evaluators/test_bars_evaluator.py              6 tests
        └── orchestration/langgraph/
            ├── nodes/test_eval_node.py                        5 tests
            └── test_eval_subgraph_keys.py                     5 tests
```

---

## 8. 테스트 결과

### 8.1 pytest 실행 결과

```
$ .venv/bin/python -m pytest apps/chat_worker/tests/unit/ -m eval_unit -v

108 passed, 792 deselected, 1 warning in 6.27s
```

### 8.2 테스트 분포

| 계층 | 파일 수 | 테스트 수 | 커버리지 대상 |
|------|---------|-----------|---------------|
| Domain | 5 | 50 | EvalGrade, AxisScore, ContinuousScore, CalibrationSample, EvalScoringService |
| Application | 5 | 42 | CodeGrader, LLMGrader, ScoreAggregator, CalibrationMonitor, EvaluateResponseCommand |
| Infrastructure | 3 | 16 | OpenAIBARSEvaluator, eval_node, EvalState↔ChatState 키 정합성 |
| **합계** | **13** | **108** | — |

### 8.3 주요 테스트 시나리오

**L1 Code Grader** (15 tests):
- 완벽한 답변 / 빈 답변 / 길이 초과·미달
- 환각 키워드 감지 (단일·복수)
- 깨진 마크다운, 괄호 불일치, 미완성 문장
- 한국어 비율 미달, 출처 유무
- Intent별 필수 섹션 검증
- `to_dict` ↔ `from_dict` 라운드트립

**L2 LLM Grader** (6 tests):
- 안전 점수(1,3,5)에서 Self-Consistency 미트리거 확인
- 경계 점수(2)에서 Self-Consistency 트리거 + 재평가 3회 확인
- 타임아웃/예외 시 빈 dict 반환 (graceful degradation)
- `evaluate_all_axes` 인자 전달 검증

**BARS Evaluator Adapter** (6 tests):
- 5축 전체 AxisScore 반환
- 축 순서 셔플 검증 (10회 호출 시 ≥ 2가지 순서)
- 단일 프롬프트 1회 LLM 호출 (비용 절감)
- Retry-with-repair (첫 실패→재시도 성공 / 최대 재시도 후 ValueError)

**EvaluateResponseCommand** (8 tests):
- L1+L2+L3 전체 파이프라인 성공
- L1-only 모드 (llm_grader=None)
- LLM Grader 비활성 시 호출 안 함
- C등급 재생성 트리거 / 비활성 시 미트리거
- 실패 슬라이스 → improvement_hints 수집
- 결과 저장 호출 / 저장 실패 시 non-blocking

**구조적 정합성** (5 tests):
- ChatState에 Layer 8 eval 키 전수 존재
- EvalState에 Aggregated Output 키 전수 존재
- EvalState output 키가 ChatState의 부분집합
- EvalState에 3개 Grader 결과 채널 존재
- EvalState에 Input 키 5개 존재

### 8.4 정적 분석

| 도구 | 결과 |
|------|------|
| **black** (포매팅) | ✅ All clean |
| **ruff** (린트) | ✅ All checks passed |
| **radon** (복잡도) | ✅ All A/B (C/D/F 없음) |

---

## 9. 전문가 리뷰 결과

### 9.1 설계안 리뷰 (5 Round)

| Round | LLM-Eval | Senior-ML | Clean-Arch | LangGraph | Code-Review | 평균 |
|-------|----------|-----------|------------|-----------|-------------|------|
| R1 | 67 | 60 | 75 | 72 | 73 | 69.4 |
| R2 | 90 | 85 | 92 | 88 | 91 | 89.2 |
| R3 | 96 | 93 | 97 | 95 | 96 | 95.4 |
| R4 | 99 | 98 | 99 | 99 | 99 | 98.8 |
| **R5** | **100** | **100** | **100** | **99** | **100** | **99.8** ✅ |

### 9.2 구현체 리뷰 (2 Round)

| Round | LLM-Eval | Senior-ML | Clean-Arch | LangGraph | Code-Review | 평균 |
|-------|----------|-----------|------------|-----------|-------------|------|
| R1 | 82 | 80 | 85 | 87 | 82 | 83.2 |
| **R2** | **97.5** | **94** | **100** | **97** | **97** | **97.1** ✅ |

### 9.3 R1→R2 주요 개선 사항

| # | R1 지적사항 | R2 수정 내용 |
|---|------------|-------------|
| 1 | `route_after_eval` 클로저에서 `EvalConfig` 미참조 | Config 파라미터 바인딩으로 수정 |
| 2 | CUSUM h=5.0은 과도 | h=4.0 (~3σ), warning=2.4 (~2σ)로 조정 |
| 3 | 비용 가드레일 미구현 | `get_daily_cost()` + `eval_cost_budget_daily_usd` 추가 |
| 4 | `eval_sample_rate` 미구현 | `execute()` 최상단에 샘플링 게이트 추가 |
| 5 | Position Bias 미완화 | 5축 루브릭 순서 셔플 + RULERS #6 verbosity 비상관 |
| 6 | `EvalResult` mutable | `frozen=True` 적용, calibration_status를 `aggregate()` 파라미터로 변경 |
| 7 | `EvalResult.failed()` continuous_score=0.0 | 65.0 (B등급 중간값)으로 수정 |
| 8 | eval_node에서 EvalConfig re-export (계층 누수) | `__all__`에서 제거, 직접 import로 변경 |
| 9 | eval_unit 마커 누락 (11개 파일) | 전수 적용 |
| 10 | except 블록 이중 예외 | `state.get("job_id")` 호출 제거 |

---

## 10. 설계 결정 요약

| 결정 | 근거 | ADR 참조 |
|------|------|----------|
| 3-Tier Swiss Cheese Model | 단일 Grader는 동일 편향의 사각지대 반복 | [ADR-1](https://rooftopsnow.tistory.com/273) |
| BARS 5점 척도 (1-5) | 7점은 정보량 +0.36비트 대비 신뢰도 하락, 3점은 해상도 부족 | [ADR-2](https://rooftopsnow.tistory.com/274) |
| 비대칭 가중치 | Faithfulness(0.30)는 환경 도메인에서 안전 직결 | [ADR-2](https://rooftopsnow.tistory.com/274) |
| Self-Consistency (경계 점수만) | 전수 재평가는 비용 3-5배, 경계만 하면 ~1.4배 | [ADR-2](https://rooftopsnow.tistory.com/274) |
| CUSUM (h=4.0, k=0.5) | Shewhart보다 미세 변화 탐지에 유리 | [ADR-4](https://rooftopsnow.tistory.com/276) |
| FAIL_OPEN (실패 시 B등급) | 평가 장애가 서비스에 영향 안 줌 | [ADR-1](https://rooftopsnow.tistory.com/273) |
| Protocol-Based Ports | 구조적 서브타이핑으로 테스트 용이 | Clean Architecture Skill |
| Send API 병렬 팬아웃 | L1/L2/L3 독립 실행으로 지연시간 최소화 | [ADR-4](https://rooftopsnow.tistory.com/276) |
| 5-Round 설계 리뷰 | 69.4→99.8점 점진적 개선으로 설계 품질 보장 | [ADR-3](https://rooftopsnow.tistory.com/275) |

---

## 11. SDK Structured Output 점검

BARS Evaluator의 LLM 호출이 **SDK 레벨 Structured Output**을 사용하는지 점검한 결과입니다.

### 11.1 호출 체인

```
OpenAIBARSEvaluator._call_structured(schema=BARSEvalOutput)
  → LLMClientPort.generate_structured(response_schema=schema)
    → 어댑터별 SDK-level API 호출
```

### 11.2 어댑터별 검증 결과

| 어댑터 | SDK 레벨 | 메커니즘 | 검증 파일:라인 |
|--------|---------|---------|--------------|
| **OpenAI** | **YES** | 1차: Agents SDK `output_type=schema` → 2차: Responses API `{type: "json_schema", strict: True}` | `openai_client.py:205,250` |
| **Gemini** | **YES** | `response_mime_type="application/json"` + `response_schema=schema` | `gemini_client.py:361` |
| **LangChain** | **YES** | `beta.chat.completions.parse(response_format=schema)` | `langchain_runnable_wrapper.py:358` |

### 11.3 핵심 확인 사항

- **Pydantic 스키마가 SDK에 직접 전달됨** — 프롬프트에 JSON 스키마를 문자열로 삽입하는 방식이 아님
- **SDK가 생성 시점에 스키마 준수를 강제** — constrained decoding으로 파싱 오류 최소화
- **`Field(ge=1, le=5)` 범위 제약이 SDK 레벨에서 적용됨**
- **Base Port에 프롬프트 기반 fallback 존재** (`llm_client.py:108-139`) — 3개 어댑터 모두 오버라이드하므로 사용되지 않음
- **retry-with-repair** (`bars_evaluator.py:184-228`) — SDK 레벨에서도 드물게 실패할 수 있으므로 최대 2회 재시도

### 11.4 결론

**갭 없음.** 설계안 §3.2.2의 "SDK-level Structured Output 보장" 요구사항을 정확히 충족합니다.

---

## 12. Commit Log

`feat/chat-eval-pipeline` 브랜치의 7개 논리적 커밋:

| # | Hash | Message | Files | Lines |
|---|------|---------|-------|-------|
| 1 | `f7c50065` | `feat(eval): Domain layer — EvalGrade, Value Objects, EvalScoringService` | 12 | +507 |
| 2 | `55a590d1` | `feat(eval): Application layer — DTOs, Ports, Exceptions` | 11 | +690 |
| 3 | `5dfe9a2d` | `feat(eval): Application Services + Command — 3-Tier Grader 로직` | 8 | +1,520 |
| 4 | `5fc029da` | `feat(eval): Infrastructure — BARS evaluator adapter + rubric prompts` | 9 | +494 |
| 5 | `a3e3e5f4` | `feat(eval): Infrastructure — LangGraph eval subgraph + main graph integration` | 6 | +857 |
| 6 | `a9153458` | `test(eval): Unit tests — 108 tests across all layers + pytest markers` | 18 | +2,082 |
| 7 | `e6de06a2` | `docs(eval): Implementation report — Chat Eval Pipeline Phase 1+2` | 1 | +639 |
| | | **Total** | **65** | **+6,789** |

---

## 13. Known Limitations

| # | 제한사항 | 영향 | 해결 계획 |
|---|---------|------|-----------|
| 1 | Gateway 어댑터 미구현 | 결과 저장/조회 불가 (Port만 정의) | Phase 3에서 PostgreSQL 어댑터 구현 |
| 2 | DI Wiring 미완성 | `setup/dependencies.py`에 eval 주입 코드 없음 | Phase 3 |
| 3 | Main Graph 통합 미완성 | `factory.py`에 eval subgraph 조건부 삽입 코드 없음 | Phase 3 |
| 4 | Calibration 트리거가 stopgap | `eval_retry_count` 기반 (Global request counter 미구현) | Redis INCR 기반으로 전환 예정 |
| 5 | Integration Test 미작성 | 단위 테스트만 존재 | Phase 3에서 서브그래프 E2E 테스트 추가 |

---

## 14. Next Steps (Phase 3)

1. **Gateway 어댑터 구현**: `EvalResultCommandGateway`, `EvalResultQueryGateway`, `CalibrationDataGateway`의 PostgreSQL 구현체
2. **DI Wiring**: `setup/dependencies.py`에서 eval 서비스 조립 및 주입
3. **Main Graph 통합**: `factory.py`에서 `eval_config.enable_eval_pipeline == True` 시 서브그래프 삽입
4. **Integration Tests**: 서브그래프 컴파일→실행 E2E, Gateway 어댑터 검증
5. **pyproject.toml 마커 등록**: `eval_unit`, `eval_regression`, `eval_capability`

---

## Appendix A: EvalState TypedDict

```python
class EvalState(TypedDict):
    # ── Input (eval_entry에서 매핑) ──
    query: str
    intent: str
    answer: str
    rag_context: str | list[str] | None
    conversation_history: list[dict]
    feedback_result: dict | None

    # ── Config (eval_entry에서 주입) ──
    llm_grader_enabled: bool
    should_run_calibration: bool
    eval_retry_count: int

    # ── Grader 결과 채널 (Annotated + reducer) ──
    code_grader_result: Annotated[dict | None, priority_preemptive_reducer]
    llm_grader_result: Annotated[dict | None, priority_preemptive_reducer]
    calibration_result: Annotated[dict | None, priority_preemptive_reducer]

    # ── Aggregated Output (ChatState로 전파) ──
    eval_result: dict | None
    eval_grade: str | None
    eval_continuous_score: float | None
    eval_needs_regeneration: bool
    eval_improvement_hints: list[str]

    # ── Internal ──
    _entry_failed: bool
    _prev_eval_score: float | None
```

## Appendix B: ChatState Eval Keys (Layer 8)

```python
# infrastructure/orchestration/langgraph/state.py
class ChatState(TypedDict):
    # ... (기존 Layer 1-7 필드) ...

    # ── Layer 8: Eval Pipeline ──
    eval_result: dict[str, Any] | None
    eval_grade: str | None
    eval_continuous_score: float | None
    eval_needs_regeneration: bool
    eval_retry_count: int
    eval_improvement_hints: list[str]
    _prev_eval_score: float | None
```
