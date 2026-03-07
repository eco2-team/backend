# Chat Eval Pipeline 구현 리포트

> **작성일**: 2026-02-10
> **Author**: Claude Opus 4.6
> **대상**: `apps/chat_worker/` — Eval Pipeline Phase 1+2+3+4
> **상태**: ✅ Phase 4 완료 (Async Fire-and-Forget + 165 tests ALL PASS)
> **설계안**: `docs/plans/chat-eval-pipeline-plan.md` (v2.2)
> **PRs**: [#548](https://github.com/eco2-team/backend/pull/548), [#549](https://github.com/eco2-team/backend/pull/549) (`feat/chat-eval-pipeline` → `develop`)
> **E2E 검증 리포트**: `docs/reports/eval-pipeline-e2e-verification-report.md`

---

## Related

| # | 문서 | 링크 |
|---|------|------|
| ADR-1 | Swiss Cheese Model for LLM Evaluation | https://rooftopsnow.tistory.com/273 |
| ADR-2 | LLM-as-a-Judge 루브릭 설계: 정보이론 관점의 해상도 분석 | https://rooftopsnow.tistory.com/274 |
| ADR-3 | Chat Eval Pipeline Integration Plan — Expert Review Loop | https://rooftopsnow.tistory.com/275 |
| ADR-4 | ADR: Chat LangGraph Eval Pipeline | https://rooftopsnow.tistory.com/276 |
| Design | `docs/plans/chat-eval-pipeline-plan.md` (v2.2) | — |
| Review | `docs/plans/chat-eval-pipeline-review.md` | — |
| E2E Report | `docs/reports/eval-pipeline-e2e-verification-report.md` | — |
| PRs | feat(eval): Chat Eval Pipeline | [#548](https://github.com/eco2-team/backend/pull/548), [#549](https://github.com/eco2-team/backend/pull/549) |

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
| 구현 소스 파일 | 36개 (Phase 1+2: 24 + Phase 3: 11 + Phase 4: 1) |
| BARS 루브릭 프롬프트 | 6개 |
| 테스트 | 165개 (단위 148 + 통합 17, 전수 통과) |
| 총 코드 규모 | ~6,000줄 |
| 설계 리뷰 점수 (R5) | 99.8 / 100 |
| 구현 리뷰 점수 (R2) | 97.1 / 100 |
| 사용자 체감 지연 | **0ms** (async fire-and-forget) |
| 평가 모델 | GPT-5.2 |

---

## 2. 아키텍처 개요

### 2.1 Async Fire-and-Forget 아키텍처

> **변경 이유**: 초기 구현에서 eval 서브그래프가 메인 그래프 내 `answer → eval(블로킹) → END`으로 동작하여, 스트리밍 완료 후 eval 실행 시간(~75ms+)만큼 딜레이가 발생했습니다. 업계 조사 결과 LangSmith/Langfuse 등 프로덕션 eval 도구들이 fire-and-forget 패턴을 채택하고 있어, eval 서브그래프를 메인 그래프에서 분리하고 `asyncio.create_task`로 비동기 실행하도록 전환했습니다.

```
┌─────────────────────────────────────────────────────────────────────────┐
│              Chat Eval Pipeline — Async Fire-and-Forget                  │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  ┌─ Main Chat Graph ─────────────────────────────────────────────────┐  │
│  │                                                                    │  │
│  │  START → intent → [vision?] → router ─┬→ waste ────┐              │  │
│  │                                        ├→ character ┤              │  │
│  │                                        ├→ location ─┤──→ answer ──┤  │
│  │                                        ├→ web_search┤          │  │  │
│  │                                        └→ general ──┘          │  │  │
│  │                                                                │  │  │
│  │                                                          END ◄─┘  │  │
│  └───────────────────────────────────────────────────────────────────┘  │
│                                                                         │
│  answer_node → done(즉시) → eval(asyncio.create_task)                  │
│                                     │                                   │
│                                eval_entry                               │
│                                     │                                   │
│                                ┌────┴────┐                              │
│                                ▼         ▼                              │
│                          code_grader  llm_grader                        │
│                            (L1)        (L2)                             │
│                                └────┬────┘                              │
│                                     ▼                                   │
│                              eval_aggregator                            │
│                                     │                                   │
│                                eval_decision                            │
│                                     │                                   │
│                                calibration (L3)                         │
│                                  CUSUM drift                            │
│                                     │                                   │
│                                로그 + 저장 (모니터링 전용)               │
│                                                                         │
│  실행 모드: 비동기 fire-and-forget (사용자 지연 0ms)                    │
│  용도: 품질 모니터링, Drift 감지 (재생성 없음)                          │
│  FAIL_OPEN: 평가 실패 시 B-grade(65.0) fallback, 응답 차단 없음        │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

**변경 전 vs 후**:

```
변경 전: answer → eval(블로킹) → END         ← 스트리밍 후 딜레이 발생
변경 후: answer → END(즉시) → eval(fire-and-forget)  ← 사용자 지연 0ms
```

**변경된 파일** (Phase 4+ 아키텍처 전환):

| 파일 | 변경 이유 |
|------|-----------|
| `factory.py` | Eval 서브그래프를 메인 그래프에서 제거, `answer → END` 복원. 메인 그래프에서 eval 서비스 의존 제거 (코드 그래프는 eval을 모른다) |
| `dependencies.py` | `get_eval_subgraph()` 신규 — eval 서비스 조립을 독립 캐시로 분리. ProcessChatCommand에 eval_subgraph 주입 |
| `process_chat.py` | `_run_eval_async()` 추가 — done 이벤트 발행 후 `asyncio.create_task`로 비동기 실행. 실패해도 응답에 영향 없음 (FAIL_OPEN) |

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
                    (로깅 + 저장)
```

**`route_to_graders()`**는 상태를 보고 실제로 실행할 노드만 `Send` 리스트에 포함합니다:

- `code_grader`: 항상 포함
- `llm_grader`: `llm_grader_enabled == True`일 때만
- `calibration_check`: `should_run_calibration == True`일 때만

---

## 3. 아키텍처 의사결정: Async Fire-and-Forget 전환

### 3.1 문제

초기 구현에서 eval 서브그래프가 메인 그래프에 동기적으로 포함되어 `answer → eval(블로킹) → END` 흐름으로 인해 스트리밍 후 딜레이가 발생했습니다.

### 3.2 업계 조사

| 패턴 | 지연 | 재생성 | 사용처 |
|------|------|--------|--------|
| 블로킹 Gate | 높음 | 완전 지원 | OpenAI Agents SDK (output guardrail) |
| 청크 인라인 검증 | 낮음 | 중간 차단 | NeMo Guardrails, Guardrails AI |
| Fire-and-Forget | 0 | 불가 | LangSmith Online Evals, Langfuse |

주요 발견:

- **OpenAI Agents SDK**: output guardrail은 항상 블로킹, 스트리밍 중 output guardrail 미지원 (GitHub #495)
- **LangSmith / Langfuse**: 비동기 fire-and-forget이 기본, 샘플링(5%)으로 비용 관리
- **코딩 에이전트(Claude Code, Copilot, Cursor)**: 별도 post-generation eval 파이프라인 없음, 모델 학습으로 품질 보장

### 3.3 결정

**Async fire-and-forget 채택 (재생성 없음, 모니터링 전용)**

- Eval Pipeline 목적을 **품질 모니터링 + Drift 감지**로 한정
- 재생성은 데이터 축적 후 C grade 빈도 기반으로 재검토
- 프론트엔드 수정 불필요, 사용자 체감 지연 0ms

### 3.4 재생성(Regeneration) 미채택 이유

1. **UX 문제**: 텍스트 스트리밍이 이미 사용자에게 표시된 상태에서 "이 응답은 품질 미달입니다, 재생성합니다"는 불쾌한 경험
2. **업계 사례**: LangSmith/Langfuse는 fire-and-forget, Claude Code/Copilot은 post-gen eval 자체가 없음
3. **비용**: 재생성은 LLM 호출을 2배로 증가시키며, C등급 빈도가 낮으면 ROI가 맞지 않음
4. **모니터링 우선**: 데이터 축적 후 C등급 빈도가 높으면 모델/프롬프트 개선으로 근본 해결

---

## 4. Clean Architecture 계층 설계

### 4.1 의존 방향

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

### 4.2 계층별 구성 요소

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
| `RedisEvalCounter` | `infrastructure/persistence/eval/redis_eval_counter.py` | Redis INCR 글로벌 요청 카운터 |
| `RedisEvalResultAdapter` | `infrastructure/persistence/eval/redis_eval_result_adapter.py` | Redis L2 Hot Storage |
| `PostgresEvalResultAdapter` | `infrastructure/persistence/eval/postgres_eval_result_adapter.py` | PostgreSQL L3 Cold Storage |
| `CompositeEvalCommandGateway` | `infrastructure/persistence/eval/composite_eval_gateway.py` | Redis+PG 동시 저장, PG non-blocking |
| `CompositeEvalQueryGateway` | `infrastructure/persistence/eval/composite_eval_gateway.py` | Redis-first, PG fallback |
| `JsonCalibrationDataAdapter` | `infrastructure/persistence/eval/json_calibration_adapter.py` | JSON Calibration Set 로더 + 메모리 캐시 |
| Calibration Fixture | `infrastructure/assets/data/calibration_set.json` | 8 샘플 × 6 Intent, v1.0 |
| V005 Migration | `migrations/V005__create_eval_schema.sql` | chat.eval_results + chat.calibration_drift_log |

---

## 5. 3-Tier Grader 상세

### 5.1 L1: Code Grader — 결정적 규칙 기반

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

### 5.2 L2: LLM Grader — BARS 5축 루브릭

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

**평가 모델**: GPT-5.2 (`eval_model: str = "gpt-5.2"`)

> **변경 이유**: gpt-4o-mini에서 GPT-5.2로 변경. 5축 BARS 루브릭 채점의 정확도와 일관성이 더 높은 최신 모델을 사용하여 평가 품질을 향상시킴.

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

### 5.3 L3: Calibration Monitor — CUSUM 드리프트 감지

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

### 5.4 Score Aggregator — 다층 결과 통합

L1(Code) + L2(LLM) 결과를 단일 `EvalResult`로 합산합니다.

| 등급 | 범위 | 의미 |
|------|------|------|
| S | 90-100 | 최고 품질 |
| A | 75-89 | 양호 |
| B | 55-74 | 보통 (FAIL_OPEN 기본값) |
| C | 0-54 | 미달 (로깅, 재생성 없음) |

---

## 6. 비용 제어 및 안전 장치

### 6.1 다단계 비용 가드레일

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
eval_decision ──── 로깅 + 저장 (모니터링 전용, 재생성 없음)
```

### 6.2 FAIL_OPEN 정책 (ADR-1 기반)

평가 파이프라인의 장애가 서비스에 영향을 주어서는 안 됩니다.

| 실패 지점 | 동작 | 등급 |
|-----------|------|------|
| eval_entry 예외 | `_entry_failed=True` → short-circuit | B |
| L2 LLM 타임아웃/예외 | 빈 dict 반환 → L1-only 모드 | - |
| L3 Calibration 예외 | `calibration_status=None` | - |
| Aggregation 예외 | `EvalResult.failed(reason)` | B |
| 결과 저장 예외 | 로그만 남김 (non-blocking) | - |
| **전체 eval task 예외** | `_run_eval_async` catch → 경고 로그만 | - |

> fire-and-forget이므로 eval 전체가 실패해도 사용자 응답은 이미 전달 완료된 상태입니다.

### 6.3 실행 모드 3종

| 모드 | L1 | L2 | L3 | 응답 영향 | 용도 |
|------|----|----|-----|-----------|------|
| `sync` | 동기 | 동기 (5s timeout) | — | 없음 (fire-and-forget) | 실시간 품질 추적 |
| `async` | 동기 | 비동기 (30s) | 비동기 | 없음 | Production 모니터링 |
| `shadow` | 비동기 | 비동기 (60s) | 비동기 | 없음 | A/B 테스트, 로그만 |

> **변경 이유**: 모든 모드에서 "응답 영향: 없음"으로 통일. fire-and-forget 아키텍처 전환으로 sync 모드에서도 재생성이 발생하지 않습니다.

---

## 7. EvalConfig Feature Flags

`EvalConfig` DTO가 전체 파이프라인의 동작을 제어합니다.

| 설정 | 기본값 | 역할 |
|------|--------|------|
| `enable_eval_pipeline` | `True` | Eval Pipeline 활성화 여부 |
| `eval_mode` | `"async"` | 실행 모드 (sync/async/shadow) |
| `eval_sample_rate` | `1.0` | 평가 샘플링 비율 (0.0-1.0) |
| `eval_llm_grader_enabled` | `True` | L2 LLM Grader 활성화 |
| `eval_regeneration_enabled` | `False` | C등급 재생성 (비활성, 미사용) |
| `eval_model` | `"gpt-5.2"` | 평가용 LLM 모델 |
| `eval_temperature` | `0.1` | 평가 LLM temperature |
| `eval_max_tokens` | `1000` | 평가 LLM max tokens |
| `eval_self_consistency_runs` | `3` | Self-Consistency 추가 평가 횟수 |
| `eval_cusum_check_interval` | `100` | N번째 요청마다 Calibration 실행 |
| `eval_cost_budget_daily_usd` | `50.0` | 일일 평가 비용 상한 (USD) |

> **변경 이유**: `eval_model`을 `gpt-4o-mini`에서 `gpt-5.2`로 변경. `eval_regeneration_enabled`는 `False`가 기본이며, fire-and-forget 아키텍처에서는 참조되지 않습니다.

---

## 8. 파일 구조

```
migrations/
└── V005__create_eval_schema.sql             # ★ Phase 3 신규

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
│   │   └── calibration_monitor.py           # L3 Calibration             291줄
│   └── commands/
│       ├── evaluate_response_command.py     # 3-Tier Orchestrator         305줄
│       └── process_chat.py                  # ★ Phase 4+: eval_subgraph 주입 + _run_eval_async()
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
│   ├── persistence/                         # ★ Phase 3 신규
│   │   └── eval/
│   │       ├── __init__.py                    # 패키지 exports
│   │       ├── redis_eval_counter.py          # Global Request Counter     79줄
│   │       ├── redis_eval_result_adapter.py   # Redis L2 Hot Storage      115줄
│   │       ├── postgres_eval_result_adapter.py # PostgreSQL L3 Cold       119줄
│   │       ├── composite_eval_gateway.py      # Composite Gateway         140줄
│   │       └── json_calibration_adapter.py    # JSON Calibration Loader   114줄
│   ├── assets/data/
│   │   └── calibration_set.json             # Calibration Fixture (8샘플) 325줄
│   └── orchestration/langgraph/
│       ├── factory.py                       # ★ Phase 4+: eval 서브그래프 제거, answer → END 복원
│       ├── nodes/eval_node.py               # Entry Adapter + 구조화 로깅  135줄
│       └── eval_graph_factory.py            # Subgraph Builder + 노드별 로깅 633줄 ★
│
├── setup/                                   # ★ Phase 3+4 수정
│   ├── config.py                            # +14 eval 환경변수 필드 (PG DSN 추가)
│   └── dependencies.py                      # ★ Phase 4+: get_eval_subgraph() 독립 캐시 + ProcessChatCommand 주입
│
├── tests/unit/                              # 17개 파일, 148개 테스트
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
        ├── orchestration/langgraph/
        │   ├── nodes/test_eval_node.py                        5 tests
        │   └── test_eval_subgraph_keys.py                     5 tests
        └── persistence/eval/
            ├── test_redis_eval_counter.py                     9 tests
            ├── test_redis_eval_result_adapter.py              8 tests
            ├── test_composite_eval_gateway.py                15 tests
            └── test_json_calibration_adapter.py               8 tests
│
└── tests/integration/eval/                  # 12개 테스트
    └── test_eval_wiring.py                    # DI wiring + counter + recalibrate stub
```

---

## 9. 테스트 결과

### 9.1 pytest 실행 결과

```
$ .venv/bin/python -m pytest apps/chat_worker/tests/ -m eval_unit -v
165 passed in 4.32s ✅
```

### 9.2 테스트 분포

| 계층 | 파일 수 | 테스트 수 | 커버리지 대상 |
|------|---------|-----------|---------------|
| Domain | 5 | 50 | EvalGrade, AxisScore, ContinuousScore, CalibrationSample, EvalScoringService |
| Application | 5 | 42 | CodeGrader, LLMGrader, ScoreAggregator, CalibrationMonitor, EvaluateResponseCommand |
| Infrastructure (Phase 1+2) | 3 | 16 | OpenAIBARSEvaluator, eval_node, EvalState↔ChatState 키 정합성 |
| Infrastructure (Phase 3) | 4 | 40 | RedisEvalCounter, RedisEvalResultAdapter, CompositeEvalGateway, JsonCalibrationAdapter |
| Integration (Phase 3+4) | 1 | 17 | DI wiring, counter injection, recalibrate stub, gateway assembly, PG pool wiring |
| **합계** | **18** | **165** | — |

### 9.3 정적 분석

| 도구 | 결과 |
|------|------|
| **black** (포매팅) | ✅ All clean |
| **ruff** (린트) | ✅ All checks passed |

---

## 10. 전문가 리뷰 결과

### 10.1 설계안 리뷰 (5 Round)

| Round | LLM-Eval | Senior-ML | Clean-Arch | LangGraph | Code-Review | 평균 |
|-------|----------|-----------|------------|-----------|-------------|------|
| R1 | 67 | 60 | 75 | 72 | 73 | 69.4 |
| R2 | 90 | 85 | 92 | 88 | 91 | 89.2 |
| R3 | 96 | 93 | 97 | 95 | 96 | 95.4 |
| R4 | 99 | 98 | 99 | 99 | 99 | 98.8 |
| **R5** | **100** | **100** | **100** | **99** | **100** | **99.8** ✅ |

### 10.2 구현체 리뷰 (2 Round)

| Round | LLM-Eval | Senior-ML | Clean-Arch | LangGraph | Code-Review | 평균 |
|-------|----------|-----------|------------|-----------|-------------|------|
| R1 | 82 | 80 | 85 | 87 | 82 | 83.2 |
| **R2** | **97.5** | **94** | **100** | **97** | **97** | **97.1** ✅ |

### 10.3 R1→R2 주요 개선 사항

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

## 11. 설계 결정 요약

| 결정 | 근거 | ADR 참조 |
|------|------|----------|
| 3-Tier Swiss Cheese Model | 단일 Grader는 동일 편향의 사각지대 반복 | [ADR-1](https://rooftopsnow.tistory.com/273) |
| BARS 5점 척도 (1-5) | 7점은 정보량 +0.36비트 대비 신뢰도 하락, 3점은 해상도 부족 | [ADR-2](https://rooftopsnow.tistory.com/274) |
| 비대칭 가중치 | Faithfulness(0.30)는 환경 도메인에서 안전 직결 | [ADR-2](https://rooftopsnow.tistory.com/274) |
| Self-Consistency (경계 점수만) | 전수 재평가는 비용 3-5배, 경계만 하면 ~1.4배 | [ADR-2](https://rooftopsnow.tistory.com/274) |
| CUSUM (h=4.0, k=0.5) | Shewhart보다 미세 변화 탐지에 유리 | [ADR-4](https://rooftopsnow.tistory.com/276) |
| FAIL_OPEN (실패 시 B등급) | 평가 장애가 서비스에 영향 안 줌 | [ADR-1](https://rooftopsnow.tistory.com/273) |
| **Async Fire-and-Forget** | 스트리밍 후 딜레이 해소, 업계 표준 (LangSmith/Langfuse) | Section 3 |
| **재생성 미채택** | UX 문제 + 업계 사례 (Claude Code/Copilot 미지원) | Section 3.4 |
| **GPT-5.2 평가 모델** | BARS 5축 채점 정확도/일관성 향상 | — |
| Protocol-Based Ports | 구조적 서브타이핑으로 테스트 용이 | Clean Architecture Skill |
| Send API 병렬 팬아웃 | L1/L2/L3 독립 실행으로 지연시간 최소화 | [ADR-4](https://rooftopsnow.tistory.com/276) |
| 5-Round 설계 리뷰 | 69.4→99.8점 점진적 개선으로 설계 품질 보장 | [ADR-3](https://rooftopsnow.tistory.com/275) |

---

## 12. SDK Structured Output 점검

BARS Evaluator의 LLM 호출이 **SDK 레벨 Structured Output**을 사용하는지 점검한 결과입니다.

### 12.1 호출 체인

```
OpenAIBARSEvaluator._call_structured(schema=BARSEvalOutput)
  → LLMClientPort.generate_structured(response_schema=schema)
    → 어댑터별 SDK-level API 호출
```

### 12.2 어댑터별 검증 결과

| 어댑터 | SDK 레벨 | 메커니즘 | 검증 파일:라인 |
|--------|---------|---------|--------------|
| **OpenAI** | **YES** | 1차: Agents SDK `output_type=schema` → 2차: Responses API `{type: "json_schema", strict: True}` | `openai_client.py:205,250` |
| **Gemini** | **YES** | `response_mime_type="application/json"` + `response_schema=schema` | `gemini_client.py:361` |
| **LangChain** | **YES** | `beta.chat.completions.parse(response_format=schema)` | `langchain_runnable_wrapper.py:358` |

### 12.3 결론

**갭 없음.** 설계안 §3.2.2의 "SDK-level Structured Output 보장" 요구사항을 정확히 충족합니다.

---

## 13. Phase별 구현 히스토리

### 13.1 Phase 1+2: Domain + Application + Infrastructure

- Domain Layer (EvalGrade, Value Objects, EvalScoringService)
- Application Layer (DTOs, Ports, Services, Command)
- Infrastructure (BARS evaluator, rubric prompts, eval subgraph)
- 108개 단위 테스트

### 13.2 Phase 3: Gateway Adapters + DI Wiring

| 카테고리 | 파일 | 역할 |
|----------|------|------|
| Migration | `V005__create_eval_schema.sql` | chat.eval_results + chat.calibration_drift_log DDL |
| Fixture | `calibration_set.json` | 8 샘플 × 6 Intent, v1.0-2026-02-10 |
| Counter | `redis_eval_counter.py` | Redis INCR pipeline (INCR + EXPIRE, TTL=2d) |
| Redis Adapter | `redis_eval_result_adapter.py` | L2 Hot Storage (LPUSH, LTRIM, INCRBYFLOAT) |
| PG Adapter | `postgres_eval_result_adapter.py` | L3 Cold Storage (asyncpg pool 주입) |
| Composite | `composite_eval_gateway.py` | Redis+PG 동시 저장, Redis-first 조회, PG non-blocking |
| Calibration | `json_calibration_adapter.py` | JSON→CalibrationSample 변환 + 메모리 캐시 |
| Tests | 52개 신규 테스트 | adapter 단위 + DI 통합 |

### 13.3 Phase 4: Config + PG DI + SSE + Logging + Skill

| # | 파일 | 변경 내용 |
|---|------|-----------|
| 1 | `setup/config.py` | `enable_eval_pipeline` 기본값 `True` + PG DSN 필드 3개 추가 |
| 2 | `setup/dependencies.py` | `get_eval_pg_pool()`, `close_eval_pg_pool()`, `_get_eval_pg_adapter()` + gateway PG adapter 주입 |
| 3 | `events/redis_progress_notifier.py` | STAGE_ORDER에 `"eval": 17` 추가 |
| 4 | `services/progress_tracker.py` | PHASE_PROGRESS `eval(90,98)`, NODE_TO_PHASE, NODE_MESSAGES 추가 |
| 5 | `commands/process_chat.py` | done 이벤트 result에 eval 결과 포함 (초기 구현) |
| 6 | `nodes/eval_node.py` | eval_entry 구조화 로깅 (intent, answer_len, should_calibrate) |
| 7 | `eval_graph_factory.py` | code_grader, llm_grader, aggregator, decision 노드별 결과 로깅 |
| 8 | `.claude/skills/eval-feedback-loop/SKILL.md` | 5-expert 피드백 루프 스킬 신규 생성 |

### 13.4 Phase 4+: Async Fire-and-Forget 전환

> **변경 이유**: 스트리밍 후 딜레이 해소. 업계 조사 결과 LangSmith/Langfuse=fire-and-forget, Claude Code/Copilot=post-gen eval 없음.

| # | 파일 | 변경 내용 | 변경 이유 |
|---|------|-----------|-----------|
| 1 | `factory.py` | Eval 서브그래프를 메인 그래프에서 제거, `answer → END` 복원 | 메인 그래프의 eval 블로킹 제거, 관심사 분리 |
| 2 | `dependencies.py` | `get_eval_subgraph()` 독립 캐시 + `ProcessChatCommand`에 eval_subgraph 주입 | eval 서비스 조립을 메인 그래프와 분리 |
| 3 | `process_chat.py` | `_run_eval_async()` 추가, done 후 `asyncio.create_task` | 사용자 지연 0ms 보장 |
| 4 | `eval_config.py` | `eval_model: "gpt-4o-mini"` → `"gpt-5.2"` | 평가 정확도/일관성 향상 |

**핵심 코드 변경** (`process_chat.py:366-372`):

```python
# 6. Eval Pipeline (비동기 fire-and-forget)
# done 이벤트 발행 후 실행 → 사용자 체감 지연 없음
if self._eval_subgraph is not None:
    asyncio.create_task(
        self._run_eval_async(result, log_ctx),
        name=f"eval-{request.job_id}",
    )
```

**핵심 코드 변경** (`factory.py:642-649`):

```python
# Eval Pipeline은 비동기 fire-and-forget으로 분리 (process_chat.py에서 실행)
# 그래프에서는 항상 answer → END
graph.add_edge("answer", END)
if eval_config is not None and eval_config.enable_eval_pipeline:
    logger.info(
        "Eval pipeline enabled (async fire-and-forget, mode=%s)",
        eval_config.eval_mode,
    )
```

---

## 14. Known Limitations

### 14.1 해결된 제한사항

| Phase | 제한사항 | 해결 |
|-------|---------|------|
| Phase 1+2 → 3 | Gateway 어댑터 미구현 | ✅ CompositeEvalGateway |
| Phase 1+2 → 3 | DI Wiring 미완성 | ✅ 5개 팩토리 함수 |
| Phase 1+2 → 3 | Calibration 트리거가 stopgap | ✅ RedisEvalCounter |
| Phase 1+2 → 3 | Integration Test 미작성 | ✅ 17개 DI wiring 테스트 |
| Phase 3 → 4 | asyncpg Pool 미주입 | ✅ `get_eval_pg_pool()` |
| Phase 3 → 4 | Composite Gateway PG wiring 미완성 | ✅ `_get_eval_pg_adapter()` |
| Phase 4 → 4+ | 스트리밍 후 딜레이 | ✅ Async fire-and-forget |

### 14.2 현재 제한사항

| # | 제한사항 | 영향 | 해결 계획 |
|---|---------|------|-----------|
| 1 | `recalibrate()` stub | HITL 인프라 미구축 — 경고 로그만 남김 | Phase 5+: HITL 재교정 파이프라인 |
| 2 | pyproject.toml 마커 미등록 | `eval_unit`, `eval_regression` 등 pytest 마커가 공식 등록 안 됨 | Phase 5 |
| 3 | E2E 통합 테스트 미작성 | 실제 Redis/PG 컨테이너 기반 검증 없음 | Phase 5+ |

---

## 15. Next Steps (Phase 5+)

1. **HITL Recalibrate 구현**: Calibration Set 재채점 → Baseline 갱신 → Version bump
2. **pyproject.toml 마커 등록**: `eval_unit`, `eval_regression`, `eval_capability`
3. **E2E 통합 테스트**: 실제 Redis/PG 컨테이너 기반 어댑터 검증
4. **Grafana 대시보드**: eval 메트릭 (grade 분포, cost, drift 상태) 시각화
5. **A/B Test 인프라**: shadow 모드로 새 프롬프트/모델 비교 파이프라인
6. **C등급 빈도 모니터링**: 데이터 축적 후 재생성 필요성 재검토

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

## Appendix C: Async Fire-and-Forget 실행 흐름

```python
# process_chat.py — 실행 순서
async def execute(self, request):
    # 1. 파이프라인 실행 (스트리밍)
    result = await self._execute_streaming(...)

    # 2. 토큰 스트림 완료
    await self._progress_notifier.finalize_token_stream(...)

    # 3. done 이벤트 발행 (사용자에게 완료 전달)
    await self._progress_notifier.notify_stage(stage="done", ...)

    # 4. Eval Pipeline (비동기 fire-and-forget)
    #    done 이벤트 발행 후 실행 → 사용자 체감 지연 없음
    if self._eval_subgraph is not None:
        asyncio.create_task(
            self._run_eval_async(result, log_ctx),
            name=f"eval-{request.job_id}",
        )

    # 5. 즉시 응답 반환 (eval 완료를 기다리지 않음)
    return ProcessChatResponse(status="completed", ...)
```

---

> Service: frontend.dev.growbin.app
> GitHub: github.com/eco2-team/backend
> Blog: rooftopsnow.tistory.com
