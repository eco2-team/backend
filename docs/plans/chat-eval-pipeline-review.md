# Chat Eval Pipeline - Expert Review Tracker

> 전문가 리뷰 진행 현황 및 스코어링 추적

---

## Review Rounds Summary

| Round | Date | Avg Score | Target | Status |
|-------|------|-----------|--------|--------|
| 1 | 2026-02-09 | 69.4/100 | 96+ | Completed |
| 2 | 2026-02-09 | 89.2/100 | 96+ | Completed |
| 3 | 2026-02-09 | 95.4/100 | 96+ | Completed |
| 4 | 2026-02-09 | **98.8/100** | 96+ | **PASSED** ✅ |
| 5 | 2026-02-09 | **99.8/100** | 96+ | **PASSED** ✅ |

**Target**: All experts >= 96/100

---

## Round 1: Initial Draft Review

| Expert | Skill | Score | Status |
|--------|-------|-------|--------|
| LLM Evaluation Expert | `llm-evaluation` | **78/100** | Done |
| Clean Architecture Expert | `clean-architecture` | **72/100** | Done |
| Code Review Expert | `code-review` | **66/100** | Done |
| LangGraph Pipeline Expert | `langgraph-pipeline` | **66/100** | Done |
| Senior ML Engineer | `senior-ml-engineer` | **65/100** | Done |

### LLM Evaluation Expert (78/100)

**Dimension Scores**: Strategy 17, Metrics 16, Bias 15, Calibration 14, Implementability 16

**Key Strengths**: Swiss Cheese 3-tier 잘 매핑됨, BARS 도메인 특화 앵커 우수, 정보 손실 추적 독창적

**Critical Improvements**:
1. Calibration Set Ground Truth 방법론 미정의 (annotator protocol, Cohen's kappa)
2. Verbosity Bias / Self-Enhancement Bias 누락
3. 축 간 판별 타당도(Discriminant Validity) 검증 없음
4. LLM Judge 출력 파싱 견고성 부족 (Structured Output 미사용)
5. Latency Budget / Async 아키텍처 미정의
6. 기존 FeedbackResult ↔ 신규 EvalResult 경계 불명확
7. Human Layer 부재 (HITL 샘플링 전략)
8. CUSUM 알고리즘 오류 (proper two-sided CUSUM 아님)
9. 비용 모델링 없음

### Clean Architecture Expert (72/100)

**Dimension Scores**: Layer Separation 15, Dependency Rule 14, Port/Adapter 13, Testability 14, Consistency 16

**Key Strengths**: Node as Thin Adapter 패턴 정확, Command 오케스트레이션 적절, DTO 배치 일관

**Critical Improvements**:
1. Domain Layer 빈약 (Value Objects: AxisScore, ContinuousScore 누락)
2. AXIS_WEIGHTS/등급 경계 로직을 Domain으로 이동
3. BARSEvaluatorPort 누락 (application/ports/eval/)
4. CalibrationDataGateway Port 누락
5. Protocol 사용 (ABC 대신)
6. EvalStorePort → Command/Query 분리 (CQRS)
7. llm_grader.py 경계 모호 (오케스트레이터 vs 어댑터)
8. 레이어별 Exception 정의 없음
9. ChatState 직렬화 경계 문서화

### Code Review Expert (66/100)

**Dimension Scores**: Quality 15, Testing 10, API Design 14, Error Handling 11, Maintainability 16

**Key Strengths**: 이론적 토대 견고, Clean Architecture 정렬 실질적, 정보 손실 추적 신규

**Critical Improvements**:
1. 의사코드 버그 (AXIS_WEIGHTS zip 오류)
2. EvalGrade Enum vs Literal 불일치
3. 테스트 파일 구조 + 테스트 케이스 전무
4. LLM Mock 전략 없음
5. 타임아웃/Circuit Breaker 없음
6. 재생성 루프 안전 미흡 (retry count in state)
7. ChatState 확장 reducer 불일치
8. FeedbackResult ↔ EvalResult 관계 미정의
9. 설정값 하드코딩 (외부화 필요)
10. Prometheus 메트릭 없음
11. fire-and-forget 설계 없음
12. SSE 스트리밍 재생성 시 UX 문제

### LangGraph Pipeline Expert (66/100)

**Dimension Scores**: Graph Architecture 14, State Management 13, Routing 15, LangGraph 1.0+ 10, Integration 14

**Key Strengths**: 3-tier grader 직교성 우수, BARS 루브릭 프로덕션급, Layered Memory 적절

**Critical Improvements**:
1. 진짜 LangGraph Subgraph로 구현 (StateGraph + compile)
2. Send API로 병렬 Grader 실행
3. EvalState 별도 TypedDict + 적절한 reducer
4. answer_node → END 엣지 충돌 해결
5. fire-and-forget async 모드 (Celery 연동)
6. contracts.py에 eval_node 등록
7. NodePolicy + CircuitBreaker 적용
8. Checkpointing 상호작용 명시

### Senior ML Engineer (65/100)

**Dimension Scores**: MLOps 12, Scalability 11, Data Pipeline 15, Monitoring 14, Production 13

**Key Strengths**: 이론 기반 우수, BARS 프로덕션급, Clean Architecture 정렬 탁월

**Critical Improvements**:
1. CI/CD 통합 없음 (pytest marker, GitHub Actions)
2. 모델/프롬프트 버전닝 없음
3. Latency Budget + Async 디커플링 미정의
4. Prometheus 메트릭 + Grafana 대시보드 스펙 없음
5. Feature flags / Gradual rollout 없음
6. A/B 테스트 인프라 없음
7. 비용 가드레일 없음
8. LLM Judge 실패 시 에러 처리 체인
9. Calibration Set 데이터 파이프라인 미완
10. PostgreSQL Cold Storage 스키마 없음

---

## Round 1 통합 개선 항목 (우선순위별)

### P0: 아키텍처 핵심 (5개 전문가 공통)

| # | 개선 항목 | 지적 전문가 | 예상 점수 영향 |
|---|----------|-----------|--------------|
| 1 | **Async/Sync 듀얼 모드 + Latency Budget** | LLM, Code, LangGraph, ML | +15 전체 |
| 2 | **LangGraph Subgraph + Send API 병렬 Grader** | LangGraph, Code | +12 전체 |
| 3 | **EvalState TypedDict + Reducer 정합성** | LangGraph, Code | +8 전체 |
| 4 | **Feature Flags + Shadow/Gradual Rollout** | ML, Code | +8 전체 |
| 5 | **answer→END 엣지 충돌 + 재생성 UX** | LangGraph, Code | +7 전체 |

### P1: Clean Architecture 정합성

| # | 개선 항목 | 지적 전문가 | 예상 점수 영향 |
|---|----------|-----------|--------------|
| 6 | **Domain Value Objects (AxisScore, ContinuousScore)** | CleanArch | +8 |
| 7 | **3개 Port 정의 (BARSEvaluator, CalibrationData, EvalStore)** | CleanArch, LLM | +7 |
| 8 | **Protocol 사용 (ABC → Protocol)** | CleanArch, Code | +2 |
| 9 | **레이어별 Exception 체계** | CleanArch, Code | +4 |
| 10 | **FeedbackResult ↔ EvalResult 경계 명확화** | LLM, Code | +4 |

### P2: 운영 성숙도

| # | 개선 항목 | 지적 전문가 | 예상 점수 영향 |
|---|----------|-----------|--------------|
| 11 | **Prometheus 메트릭 + Grafana 스펙** | ML, Code | +8 |
| 12 | **CI/CD 통합 (pytest marker, Actions)** | ML | +4 |
| 13 | **모델/프롬프트 버전닝** | ML | +3 |
| 14 | **NodePolicy + CircuitBreaker** | LangGraph, Code | +5 |
| 15 | **contracts.py 등록** | LangGraph | +3 |

### P3: 테스트 + 데이터

| # | 개선 항목 | 지적 전문가 | 예상 점수 영향 |
|---|----------|-----------|--------------|
| 16 | **테스트 전략 + 파일 구조 + Mock 전략** | Code | +10 |
| 17 | **Calibration Ground Truth 프로토콜** | LLM | +5 |
| 18 | **PostgreSQL 스키마 정의** | ML | +2 |
| 19 | **비용 모델링 + 가드레일** | LLM, ML | +3 |

### P4: 평가 품질

| # | 개선 항목 | 지적 전문가 | 예상 점수 영향 |
|---|----------|-----------|--------------|
| 20 | **Verbosity/Self-Enhancement Bias 추가** | LLM | +3 |
| 21 | **축 판별 타당도 검증** | LLM | +3 |
| 22 | **CUSUM 알고리즘 수정 (proper two-sided)** | LLM, ML | +2 |
| 23 | **Structured Output 사용 (regex 파싱 → Pydantic)** | LLM, ML | +2 |
| 24 | **HITL 샘플링 전략** | LLM | +2 |

---

## Round 2: v2 Review

| Expert | Skill | R1 | R2 | Delta | Status |
|--------|-------|----|----|-------|--------|
| LLM Evaluation Expert | `llm-evaluation` | 78 | **92** | +14 | Done |
| Senior ML Engineer | `senior-ml-engineer` | 65 | **89** | +24 | Done |
| LangGraph Pipeline Expert | `langgraph-pipeline` | 66 | **89** | +23 | Done |
| Clean Architecture Expert | `clean-architecture` | 72 | **88** | +16 | Done |
| Code Review Expert | `code-review` | 66 | **88** | +22 | Done |

**Round 2 Average: 89.2/100**

### Round 2 잔여 갭 (v2.1 Appendix로 해결)

| # | Gap | 지적 전문가 | 해결 Appendix |
|---|-----|-----------|-------------|
| 1 | ChatState ↔ EvalState 브릿징 | LangGraph, Code | A.1 |
| 2 | NodePolicy 스키마 확장 | LangGraph, Code | A.2 |
| 3 | Aggregator Nullable + Reducer 계약 | LangGraph, CleanArch, Code | A.3 |
| 4 | Protocol vs ABC 컨벤션 | CleanArch | A.4 |
| 5 | Base Exception 클래스 | CleanArch | A.5 |
| 6 | domain/services/ 패턴 노트 | CleanArch | A.6 |
| 7 | Self-Consistency 집계 (Median) | LLM | A.7 |
| 8 | Cross-Model Divergence 임계치 | LLM | A.8 |
| 9 | 재생성 품질 게이트 | LLM | A.9 |
| 10 | Lifecycle Phase 전환 자동화 | LLM | A.10 |
| 11 | Alerting Rules | ML | A.11 |
| 12 | EvalResult.failed() 기본값 | Code | A.12 |
| 13 | grade_boundary_distance 네이밍 | Code | A.13 |
| 14 | Cost Guardrail 테스트 | Code | A.14 |
| 15 | Calibration Set 크기 근거 | LLM | A.15 |
| 16 | Data Retention + Partitioning | ML | A.16 |

---

## Round 3: v2.1 Review

| Expert | Skill | R2 | R3 | Delta | Status |
|--------|-------|----|----|-------|--------|
| LLM Evaluation Expert | `llm-evaluation` | 92 | **97** | +5 | Done |
| Senior ML Engineer | `senior-ml-engineer` | 89 | **95** | +6 | Done |
| LangGraph Pipeline Expert | `langgraph-pipeline` | 89 | **95** | +6 | Done |
| Clean Architecture Expert | `clean-architecture` | 88 | **95** | +7 | Done |
| Code Review Expert | `code-review` | 88 | **95** | +7 | Done |

**Round 3 Average: 95.4/100**

### Round 3 잔여 갭 (v2.2 Appendix B로 해결)

| # | Gap | 지적 전문가 | 해결 Appendix |
|---|-----|-----------|-------------|
| 1 | CircuitBreaker 파라미터명 (recovery_timeout) | LangGraph | B.1 |
| 2 | `_prev_eval_score` 필드 미선언 | LangGraph | B.2 |
| 3 | eval_bridge → eval_entry 서브그래프 내부화 | LangGraph, Code, CleanArch | B.3 |
| 4 | 서브그래프 출력 키 매핑 검증 테스트 | LangGraph, Code, CleanArch | B.4 |
| 5 | conftest.py eval 픽스처 + pyproject.toml 마커 | Code | B.5 |
| 6 | BARSEvaluator Port rubric 파라미터 제거 | CleanArch | B.6 |
| 7 | Domain 레이어 배치 원칙 명문화 | CleanArch | B.7 |
| 8 | eval NodePolicy 동적 타임아웃 | CleanArch, Code | B.8 |
| 9 | Shadow Mode Observability 구체 스펙 | LLM | B.9 |
| 10 | Calibration Set 도메인 진화 대응 | LLM, ML | B.10 |
| 11 | Power Analysis SD 가정 검증 노트 | LLM | B.11 |
| 12 | Runbook + On-Call 에스컬레이션 | ML | B.12 |
| 13 | 버전 비교 통계 방법 (Wilcoxon + Bootstrap CI) | ML | B.13 |
| 14 | Celery Eval Worker 오토스케일링 (KEDA) | ML | B.14 |
| 15 | contracts.py eval 노드 의미 구분 | LangGraph | B.15 |

---

## Round 4: v2.2 Review ✅ ALL PASSED

| Expert | Skill | R3 | R4 | Delta | Status |
|--------|-------|----|----|-------|--------|
| LLM Evaluation Expert | `llm-evaluation` | 97 | **100** | +3 | ✅ PASS |
| Senior ML Engineer | `senior-ml-engineer` | 95 | **99** | +4 | ✅ PASS |
| LangGraph Pipeline Expert | `langgraph-pipeline` | 95 | **99** | +4 | ✅ PASS |
| Clean Architecture Expert | `clean-architecture` | 95 | **99** | +4 | ✅ PASS |
| Code Review Expert | `code-review` | 95 | **97** | +2 | ✅ PASS |

**Round 4 Average: 98.8/100** — **All experts ≥ 96. Target achieved.**

### Round 4 잔여 갭 (minor, non-blocking)

| # | Gap | Expert | Severity |
|---|-----|--------|----------|
| 1 | Calibration version migration 실패 경로 미정의 (r < 0.85 시 행동) | ML | Minor |
| 2 | B.3 vs Section 2.2 `route_to_graders` 패턴 불일치 (node vs conditional edge) | LangGraph | Minor |
| 3 | `EvalResultQueryGateway` Port에 `get_intent_distribution` 메서드 미선언 | CleanArch | Minor |
| 4 | `eval_entry` 에러 → `EvalResult.failed()` 서브그래프 전파 통합테스트 부재 | Code | Minor |
| 5 | 서브그래프 내 에러 short-circuit 엣지 명시 부족 | Code | Minor |
| 6 | Runbook 파일 생성 (`docs/runbooks/eval-pipeline.md`)이 Phase 로드맵에 미포함 | Code | Minor |

---

## Round 5: v2.2 Gap Fix Review ✅ ALL PASSED

| Expert | Skill | R4 | R5 | Delta | Status |
|--------|-------|----|----|-------|--------|
| LLM Evaluation Expert | `llm-evaluation` | 100 | **100** | 0 | ✅ PASS |
| Senior ML Engineer | `senior-ml-engineer` | 99 | **100** | +1 | ✅ PASS |
| LangGraph Pipeline Expert | `langgraph-pipeline` | 99 | **100** | +1 | ✅ PASS |
| Clean Architecture Expert | `clean-architecture` | 99 | **99** | 0 | ✅ PASS |
| Code Review Expert | `code-review` | 97 | **100** | +3 | ✅ PASS |

**Round 5 Average: 99.8/100** — **All experts ≥ 96. Final confirmation.**

### Round 4 갭 해결 현황

| # | Gap | 해결 방법 | Status |
|---|-----|----------|--------|
| 1 | Calibration migration 실패 경로 | B.10에 5단계 실패 절차 추가 (auto-block → alert → 진단 → HITL → 재시작) | ✅ Resolved |
| 2 | `route_to_graders` 패턴 불일치 | B.3에서 `add_node` 제거, `add_conditional_edges` 통일 | ✅ Resolved |
| 3 | `get_intent_distribution` Port 미선언 | Section 5.1 `EvalResultQueryGateway`에 메서드 추가 | ✅ Resolved |
| 4 | `eval_entry` 에러 전파 통합테스트 | Section 12.2에 `test_eval_subgraph_entry_failure_degrades_gracefully` 추가 | ✅ Resolved |
| 5 | 에러 short-circuit 엣지 | B.3에 `_entry_failed` 플래그 + `route_to_graders` short-circuit 로직 추가 | ✅ Resolved |
| 6 | Runbook Phase 로드맵 누락 | Phase 3에 `docs/runbooks/eval-pipeline.md` 작성 항목 추가 | ✅ Resolved |

### Round 5 잔여 갭 (1건, minor)

| # | Gap | Expert | Severity |
|---|-----|--------|----------|
| 1 | `CalibrationDataGateway` Port에 `get_calibration_intent_set()` 메서드 미선언 | CleanArch | Minor (본문 패치 완료) |

---

## Improvement Log

| Round | Date | Changes Made | Avg Score Before | Avg Score After |
|-------|------|-------------|-----------------|-----------------|
| 1 | 2026-02-09 | Initial draft | - | 69.4 |
| 2 | 2026-02-09 | P0-P4 전체 반영 (24개 항목) | 69.4 | 89.2 |
| 3 | 2026-02-09 | Appendix A.1-A.16 (16개 잔여 갭) | 89.2 | 95.4 |
| 4 | 2026-02-09 | Appendix B.1-B.15 (15개 잔여 갭) + 본문 수정 | 95.4 | **98.8** ✅ |
| 5 | 2026-02-09 | Round 4 잔여 갭 6건 수정 + Port 메서드 보완 + 톤 정돈 | 98.8 | **99.8** ✅ |
