---
name: eval-feedback-loop
description: Chat Eval Pipeline 코드에 대한 5-expert 피드백 루프 리뷰 가이드
command: eval-feedback-loop
user_invocable: true
---

# Eval Feedback Loop

Chat Eval Pipeline 코드를 5명의 전문가 관점에서 반복 리뷰하는 피드백 루프 가이드입니다.

## Expert Panel (5명)

| # | 역할 | 스킬 | 평가 초점 |
|---|------|------|----------|
| 1 | LLM Evaluation Specialist | `llm-evaluation` | BARS 척도, Self-Consistency, Calibration Drift, 평가 품질 |
| 2 | Senior ML Engineer | `senior-ml-engineer` | MLOps, 모델 배포, 피처 스토어, 모니터링, 성능 |
| 3 | LangGraph Pipeline Architect | `langgraph-pipeline` | StateGraph, Send API, Checkpointer, 노드 설계 |
| 4 | Clean Architecture Expert | `clean-architecture` | Port/Adapter, DIP, Layer 의존성, CQRS |
| 5 | Code Reviewer | `code-review` | 코드 품질, 보안, 테스트 커버리지, 아키텍처 준수 |

## 리뷰 절차

### Round 1: 초기 평가

각 전문가가 다음을 평가합니다:
1. 해당 전문 영역의 Best Practice 준수 여부
2. 잠재적 문제점 및 개선 사항
3. 0-100 점수 부여 (세부 항목별)

### Round 2+: 개선 반복

1. Round 1 피드백 기반 코드 수정
2. 재평가 실시
3. 목표: 전문가 평균 95+/100 달성

## 평가 체크리스트

### CI/CD
- [ ] `black --check` 통과
- [ ] `ruff check` 통과
- [ ] 전체 테스트 PASS (`pytest -m eval_unit`)
- [ ] 신규 테스트 추가 확인

### 아키텍처
- [ ] Layer 의존성 방향 준수 (Domain ← App ← Infra)
- [ ] Port/Adapter 패턴 일관성
- [ ] EvalConfig를 통한 설정 주입 (state에 config 저장 금지)
- [ ] EvalResult.frozen=True 불변성 유지

### 보안/성능
- [ ] API 키/시크릿 노출 없음
- [ ] 비용 가드레일 (eval_cost_budget_daily_usd) 동작
- [ ] eval_sample_rate 적용 확인
- [ ] asyncpg pool 사이즈 적정성

### 테스트
- [ ] 단위 테스트 커버리지 (각 서비스별)
- [ ] 통합 테스트 (DI wiring, subgraph)
- [ ] 엣지 케이스 (실패 fallback, 빈 입력, 타임아웃)
- [ ] pytest 마커 (`@pytest.mark.eval_unit`) 일관성

## 점수 추적 템플릿

```markdown
| Round | Expert | Score | Key Issues |
|-------|--------|-------|------------|
| R1 | LLM Eval | /100 | |
| R1 | ML Eng | /100 | |
| R1 | LangGraph | /100 | |
| R1 | Clean Arch | /100 | |
| R1 | Code Review | /100 | |
| **R1 Avg** | | **/100** | |
```

## 핵심 파일 목록

```
apps/chat_worker/
├── application/
│   ├── dto/eval_config.py          # 설정 DTO
│   ├── dto/eval_result.py          # 결과 VO
│   ├── services/eval/              # 서비스 레이어
│   │   ├── code_grader.py          # L1 Code Grader
│   │   ├── llm_grader.py           # L2 LLM Grader
│   │   ├── score_aggregator.py     # 점수 통합
│   │   └── calibration_monitor.py  # L3 Drift 감지
│   └── ports/eval/                 # 포트 인터페이스
├── infrastructure/
│   ├── orchestration/langgraph/
│   │   ├── eval_graph_factory.py   # 서브그래프 빌더
│   │   └── nodes/eval_node.py      # Entry 노드
│   └── persistence/eval/           # Gateway 어댑터
├── setup/
│   ├── config.py                   # 설정
│   └── dependencies.py             # DI 팩토리
└── tests/
    ├── unit/                       # 단위 테스트
    └── integration/eval/           # 통합 테스트
```

## 실행 방법

```bash
# 1. 전체 eval 테스트
.venv/bin/python -m pytest apps/chat_worker/tests/ -m eval_unit -v --tb=short

# 2. CI lint
black --check apps/chat_worker/ && ruff check apps/chat_worker/

# 3. 특정 파일 리뷰 요청
# "eval_graph_factory.py를 /eval-feedback-loop로 리뷰해줘"
```
