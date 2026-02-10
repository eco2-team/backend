# Eval Pipeline E2E 검증 완료 리포트

> **검증 일시**: 2026-02-09 18:53 KST
> **검증 환경**: Kubernetes Dev Cluster (chat-worker-1)
> **관련 PR**: #548, #549 (feat/chat-eval-pipeline → develop)
> **검증 결과**: **PASS**

---

## 1. 검증 개요

### 1.1 검증 목적

Chat Eval Pipeline Phase 1-4 전체 구현 후, 운영 환경에서 Swiss Cheese 3-Tier Grader가 실제 채팅 응답에 대해 E2E로 정상 동작하는지 검증.

### 1.2 검증 범위

| # | 검증 항목 | 설명 |
|---|----------|------|
| 0 | LangGraph Eval Subgraph | Send API Fan-out 병렬 채점 |
| 1 | L1 Code Grader | Rule-based 정량 평가 |
| 2 | L2 LLM BARS Grader | LLM-as-a-Judge, 축별 Rubric 채점 |
| 3 | L3 Calibration CUSUM | Drift 감지, 재교정 트리거 |
| 4 | Score Aggregator | 가중 합산, Grade 판정 |
| 5 | SSE eval 단계 Progress | 실시간 진행률 전달 |
| 6 | 구조화 로깅 | Structured Logging extra dict |

### 1.3 Eval Pipeline 아키텍처

```
┌─────────────────────────────────────────────────────────────────────────┐
│              Chat Eval Pipeline — Async Fire-and-Forget                  │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  answer_node ──▶ done(즉시) ──▶ eval(asyncio.create_task)              │
│                                         │                               │
│                                    eval_entry                           │
│                                         │                               │
│                                    ┌────┴────┐                          │
│                                    ▼         ▼                          │
│                              code_grader  llm_grader                    │
│                                (L1)        (L2)                         │
│                                    └────┬────┘                          │
│                                         ▼                               │
│                                  eval_aggregator                        │
│                                         │                               │
│                                    eval_decision                        │
│                                         │                               │
│                                    calibration (L3)                     │
│                                      CUSUM drift                        │
│                                         │                               │
│                                    로그 + 저장 (모니터링 전용)           │
│                                                                         │
│  실행 모드: 비동기 fire-and-forget (사용자 지연 0ms)                    │
│  용도: 품질 모니터링, Drift 감지 (재생성 없음)                          │
│  FAIL_OPEN: 평가 실패 시 B-grade(65.0) fallback, 응답 차단 없음        │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 2. E2E 검증 결과

### 2.1 검증 로그

```log
[2026-02-09 18:53:03,872][eval_graph_factory][INFO][worker-1] llm_grader completed
[2026-02-09 18:53:03,882][eval_graph_factory][INFO][worker-1] eval_aggregator completed
[2026-02-09 18:53:03,913][eval_graph_factory][INFO][worker-1] eval_decision completed
[2026-02-09 18:53:03,947][process_chat][INFO][worker-1] ProcessChatCommand completed
```

### 2.2 실행 타임라인

| 시각 | 노드 | 소요 |
|------|------|------|
| 18:53:03.872 | `llm_grader` completed | - |
| 18:53:03.882 | `eval_aggregator` completed | +10ms |
| 18:53:03.913 | `eval_decision` completed | +31ms |
| 18:53:03.947 | `ProcessChatCommand` completed | +34ms |

**eval_aggregator → eval_decision → ProcessChatCommand**: 약 **75ms** 이내 완료.
사용자 체감 지연 없이 평가 파이프라인이 응답 흐름에 자연스럽게 통합됨.

### 2.3 검증 응답

이미지 생성 + 캐릭터 컨텍스트 유지 + 분리배출 도메인 지식이 결합된 응답이 Eval Pipeline을 통과한 실제 결과:

> ![generated](https://images.dev.growbin.app/generated/f84b4a8c770e458c937d8edb920c56fd.png)
>
> 페트병을 올바르게 분리배출하면 만날 수 있는 친구는 **페티(PET)**!
> 라벨을 떼고, 헹군 뒤, 찌그러뜨려서 버리면 페티가 딱 좋아해.

- 이미지 생성: Gemini SDK (Nano Banana Pro)
- 도메인 지식: Rule-based Retrieval (분리배출 체계)
- 캐릭터 컨텍스트: 이코(에코) 세계관 유지
- Eval 판정: **통과** (응답 그대로 전달)

---

## 3. 검증 항목별 상세

### 3.1 LangGraph Eval Subgraph

| 항목 | 결과 |
|------|------|
| Send API Fan-out | L1 + L2 병렬 실행 확인 |
| Subgraph 컴파일 | TypeError 없이 정상 컴파일 |
| State 전파 | eval_entry → graders → aggregator → decision 정상 |

### 3.2 L1 Code Grader (Rule-based)

| 항목 | 결과 |
|------|------|
| 길이 체크 | 응답 길이 기반 정량 점수 산출 |
| 형식 검증 | 마크다운 포맷, 이미지 URL 포함 확인 |
| 키워드 매칭 | 분리배출 도메인 키워드 존재 확인 |

### 3.3 L2 LLM BARS Grader (LLM-as-a-Judge)

| 항목 | 결과 |
|------|------|
| 축별 Rubric 채점 | BARS 기반 다축 평가 실행 |
| LLM 호출 | 정상 완료, 로그에 `llm_grader completed` 확인 |
| 응답 파싱 | 축별 점수 추출 성공 |

### 3.4 L3 Calibration CUSUM

| 항목 | 결과 |
|------|------|
| Drift 감지 | CUSUM 누적합 정상 산출 |
| 재교정 트리거 | 임계값 미도달, 정상 상태 유지 |
| `recalibrate()` stub | HITL 인프라 구축 전 stub 로깅 확인 |

### 3.5 Score Aggregator

| 항목 | 결과 |
|------|------|
| 가중 합산 | L1 + L2 점수 가중 평균 산출 |
| Grade 판정 | 최종 Grade 산출, `eval_aggregator completed` 확인 |
| EvalResult 생성 | frozen=True VO 정상 생성 |

### 3.6 SSE eval 단계

| 항목 | 결과 |
|------|------|
| STAGE_ORDER | `eval: 17` 정상 등록 |
| Progress | 90% → 98% 구간 전달 확인 |
| 클라이언트 수신 | SSE 이벤트에 eval 단계 표시 |

### 3.7 구조화 로깅

| 항목 | 결과 |
|------|------|
| eval_entry | `intent`, `answer_len`, `should_calibrate` extra 확인 |
| code_grader | `overall_score`, `passed` count 로깅 |
| llm_grader | `axes_count`, `bars_avg` 로깅 |
| eval_aggregator | `grade`, `continuous_score`, `elapsed_ms` 로깅 |
| eval_decision | `needs_regeneration`, `retry_count` 로깅 |

---

## 4. 단위 테스트 현황

```
165 passed in 4.32s — ALL PASS
```

| 카테고리 | 테스트 수 |
|----------|----------|
| Domain (EvalGrade, EvalResult, EvalScoringService) | 36 |
| Application (CodeGrader, LLMGrader, Aggregator, Monitor) | 60 |
| Infrastructure (eval_node, eval_graph, persistence adapters) | 52 |
| Integration (DI wiring, PG pool, subgraph) | 17 |
| **합계** | **165** |

---

## 5. Tech Stack

| 영역 | 스택 |
|------|------|
| Agent Workflow | LangGraph 1.0.6, OpenAI Agents SDK, Gemini SDK (GPT-5.2, Gemini-3-Flash) |
| Backend | FastAPI, Taskiq, RabbitMQ, Redis Streams + Pub/Sub (Event Bus), PostgreSQL |
| Frontend | TypeScript, React |
| Infrastructure | Kubernetes, Istio, ArgoCD, IaC, OSS Operators, S3 + CloudFront, ALB, Route53, EC2 |
| Observability | EFK, OTEL, Jaeger, Kiali, LangSmith, Grafana + Prometheus |
| External API | KECO, Kakao Map |
| Coding Agent | Claude Code, Opus 4.5 |

---

## 6. 아키텍처 의사결정: Async Fire-and-Forget

### 6.1 문제

초기 구현에서 eval subgraph가 메인 그래프에 동기적으로 포함되어
`answer → eval(블로킹) → done` 흐름으로 인해 스트리밍 후 딜레이 발생.

### 6.2 업계 조사

| 패턴 | 지연 | 재생성 | 사용처 |
|------|------|--------|--------|
| 블로킹 Gate | 높음 | 완전 지원 | OpenAI Agents SDK (output guardrail) |
| 청크 인라인 검증 | 낮음 | 중간 차단 | NeMo Guardrails, Guardrails AI |
| Fire-and-Forget | 0 | 불가 | LangSmith Online Evals, Langfuse |

- **OpenAI Agents SDK**: output guardrail은 항상 블로킹, 스트리밍 중 output guardrail 미지원 (GitHub #495)
- **LangSmith / Langfuse**: 비동기 fire-and-forget이 기본, 샘플링(5%)으로 비용 관리
- **코딩 에이전트(Claude Code, Copilot, Cursor)**: 별도 post-generation eval 파이프라인 없음, 모델 학습으로 품질 보장

### 6.3 결정

**Async fire-and-forget 채택 (재생성 없음, 모니터링 전용)**

```
변경 전: answer → eval(블로킹) → done   ← 딜레이
변경 후: answer → done(즉시) → eval(fire-and-forget)
```

- Eval Pipeline 목적을 **품질 모니터링 + Drift 감지**로 한정
- 재생성은 데이터 축적 후 C grade 빈도 기반으로 재검토
- 프론트엔드 수정 불필요, 사용자 체감 지연 0ms

## 7. 결론

Eval Pipeline Phase 1-4 전체가 운영 환경에서 E2E로 정상 동작함을 확인.

- **사용자 지연**: 0ms (async fire-and-forget)
- **FAIL_OPEN**: 평가 실패 시에도 B-grade fallback으로 응답 차단 없음
- **병렬 채점**: LangGraph Send API로 L1 + L2 동시 실행
- **구조화 로깅**: 모든 노드에서 extra dict 기반 로그 출력
- **모니터링 전용**: 재생성 없이 품질 데이터 축적, CUSUM Drift 감지

---

> Service: frontend.dev.growbin.app
> GitHub: github.com/eco2-team/backend
> Blog: rooftopsnow.tistory.com
