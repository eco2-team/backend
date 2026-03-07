# Scan Worker 마이그레이션 로드맵

> **참고 문서**
> - [Eco² Clean Architecture #13: Scan 도메인 마이그레이션 로드맵](https://rooftopsnow.tistory.com/142)
> - [Eco² Clean Architecture #11: API 서버 캐시 레이어 통합](https://rooftopsnow.tistory.com/137)

## 1. 현재 상태 분석

### 1.1 정합성 분석 결과

| 항목 | domains/scan | apps/scan_worker | 정합성 |
|------|-------------|------------------|--------|
| **Vision** | `analyze_images` 재사용 | `analyze_images` 재사용 | ✅ 동일 |
| **Rule** | `get_disposal_rules` 재사용 | `get_disposal_rules` 재사용 | ⚠️ 중복 코드 |
| **Answer** | `generate_answer` 재사용 | `generate_answer` 재사용 | ⚠️ 응답 필드 차이 |
| **Reward** | 전체 로직 구현 | 전체 로직 복사 | ❌ 코드 중복 심각 |
| **Event** | `publish_stage_event` 재사용 | `publish_stage_event` 재사용 | ✅ 동일 |
| **LLM** | 하드코딩 (gpt-5.1) | 하드코딩 (동일) | ⚠️ DI 미적용 |

### 1.2 발견된 문제점

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  ❌ 문제 1: 파일 내 코드 중복                                                │
│  ├── rule_task.py: 동일 코드 2회 반복 (L1-103, L104-204)                    │
│  ├── reward_task.py: 동일 코드 2회 반복 (L1-397, L398-792)                  │
│  └── answer_task.py: 기본 답변 필드명 차이 (answer vs user_answer)          │
├─────────────────────────────────────────────────────────────────────────────┤
│  ⚠️ 문제 2: LLM DI 미적용                                                   │
│  ├── scan-api에서 llm_config 전달하도록 구현됨                               │
│  └── scan_worker에서 llm_config를 받지만 사용하지 않음 (하드코딩)            │
├─────────────────────────────────────────────────────────────────────────────┤
│  ⚠️ 문제 3: domains 의존성                                                  │
│  ├── waste_pipeline/vision.py (OpenAI 직접 호출)                            │
│  ├── waste_pipeline/answer.py (OpenAI 직접 호출)                            │
│  └── waste_pipeline/rag.py (파일 I/O)                                       │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 1.3 파이프라인 흐름

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  Scan Pipeline Architecture                                                  │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  [Client]                                                                    │
│     │                                                                        │
│     ├── POST /scan {"provider": "openai"}                                    │
│     │         │                                                              │
│     │         ▼                                                              │
│     │    [scan-api]                                                          │
│     │         │                                                              │
│     │         ├── LLMProvider → Model 결정 (gpt-5.2)                         │
│     │         ├── job_id 생성                                                │
│     │         ├── Redis Streams: queued 이벤트                               │
│     │         └── Celery Chain 발행                                          │
│     │              │                                                         │
│     │              ▼                                                         │
│     │    [RabbitMQ]                                                          │
│     │         │                                                              │
│     │         ├── scan.vision ──────────────────────────────┐                │
│     │         │                                              │               │
│     │         │    ┌────────────────────────────────────────┼───────┐       │
│     │         │    │  [scan-worker]                         │        │       │
│     │         │    │                                         ▼        │       │
│     │         │    │  vision_task                                    │       │
│     │         │    │    ├── analyze_images() ← waste_pipeline        │       │
│     │         │    │    └── Redis Streams: vision completed          │       │
│     │         │    │              │                                   │       │
│     │         │    │              ▼                                   │       │
│     │         │    │  rule_task                                      │       │
│     │         │    │    ├── get_disposal_rules() ← waste_pipeline    │       │
│     │         │    │    └── Redis Streams: rule completed            │       │
│     │         │    │              │                                   │       │
│     │         │    │              ▼                                   │       │
│     │         │    │  answer_task                                    │       │
│     │         │    │    ├── generate_answer() ← waste_pipeline       │       │
│     │         │    │    └── Redis Streams: answer completed          │       │
│     │         │    │              │                                   │       │
│     │         │    │              ▼                                   │       │
│     │         │    │  reward_task                                    │       │
│     │         │    │    ├── character.match (동기 대기)              │       │
│     │         │    │    ├── _dispatch_save_tasks (Fire & Forget)     │       │
│     │         │    │    ├── Redis Cache: 결과 저장                   │       │
│     │         │    │    └── Redis Streams: done 이벤트               │       │
│     │         │    │                                                 │       │
│     │         │    └─────────────────────────────────────────────────┘       │
│     │         │                                                              │
│     │         ▼                                                              │
│     │    [Redis Streams]                                                     │
│     │         │                                                              │
│     │         ▼                                                              │
│     │    [Event Router] ──► [Redis Pub/Sub] ──► [SSE Gateway]               │
│     │                                                  │                     │
│     │◄─────────────────── GET /stream?job_id=... ◄────┘                     │
│     │                                                                        │
│     └── GET /scan/result/{job_id}                                           │
│              │                                                               │
│              ▼                                                               │
│         [Redis Cache]                                                        │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. 로드맵

### Phase 1: 코드 정리 (즉시)

**목표:** 중복 코드 제거, 정합성 확보

| 작업 | 설명 | 우선순위 |
|------|------|----------|
| 1.1 | `rule_task.py` 중복 코드 제거 | 🔴 높음 |
| 1.2 | `reward_task.py` 중복 코드 제거 | 🔴 높음 |
| 1.3 | `answer_task.py` 기본 답변 필드명 통일 | 🟡 중간 |
| 1.4 | `vision_task.py` _to_dict 함수 추가 (domains와 동일) | 🟡 중간 |

**정합성 기준:**
- `domains/scan/tasks/*.py`와 **동일한 로직** 유지
- `domains/_shared/waste_pipeline/*.py` **직접 import**하여 재사용
- `domains/_shared/events.py` **직접 import**하여 재사용

### Phase 2: LLM DI 준비 (선택적)

**목표:** LangChain 기반 DI 인프라 구축

```
apps/scan_worker/
├── application/
│   └── ports/
│       └── llm_client.py          ← Port (인터페이스)
│
├── infrastructure/
│   └── llm/
│       ├── __init__.py
│       └── langchain_client.py    ← Adapter (LangChain 구현)
│
└── setup/
    └── llm_factory.py             ← Factory (DI 컴포지션 루트)
```

**주의:** 현재는 `llm_config`를 받지만 **사용하지 않음**.
DI 적용 시에도 `domains/_shared/waste_pipeline` 의존성 때문에 효과가 제한적.

### Phase 3: waste_pipeline 내재화 (장기)

**목표:** `domains/_shared/waste_pipeline`을 `apps/scan_worker`로 이전

```
domains/_shared/waste_pipeline/          apps/scan_worker/infrastructure/
├── vision.py          ──────────►       ├── llm/
├── answer.py                            │   ├── vision_analyzer.py
├── rag.py             ──────────►       │   └── answer_generator.py
└── data/                                │
    ├── item_class.yaml                  └── rules/
    └── disposal_rules/                      ├── rule_repository.py
        └── *.json                           └── data/
                                                 ├── item_class.yaml
                                                 └── disposal_rules/
```

**이 작업은 다음 조건에서만 진행:**
- `domains/scan` 완전 삭제 결정 시
- LLM 교체 요구사항 발생 시

---

## 3. 즉시 수행할 작업

### 3.1 rule_task.py 수정

```python
# apps/scan_worker/presentation/tasks/rule_task.py
# 중복 코드(L104-204) 삭제, L1-103만 유지
```

### 3.2 reward_task.py 수정

```python
# apps/scan_worker/presentation/tasks/reward_task.py
# 중복 코드(L398-792) 삭제, L1-397만 유지
```

### 3.3 answer_task.py 수정 (기본 답변 필드명)

```python
# 현재 apps/scan_worker (L63-68)
if not disposal_rules:
    final_answer = {
        "disposal_steps": {},  # ← domains와 다름
        "insufficiencies": ["배출 규정 매칭 실패"],
        "user_answer": "죄송합니다...",  # ← domains와 다름
    }

# 수정 후 (domains/scan과 동일하게)
if not disposal_rules:
    final_answer = {
        "answer": "죄송합니다...",  # ← domains와 동일
        "insufficiencies": ["배출 규정 매칭 실패"],
    }
```

### 3.4 vision_task.py 수정 (_to_dict 추가)

```python
# domains/scan/tasks/vision.py의 _to_dict 함수 추가
def _to_dict(payload: Any) -> dict[str, Any]:
    """분류 결과를 dictionary로 변환."""
    if isinstance(payload, dict):
        return payload
    if isinstance(payload, str):
        try:
            return json.loads(payload)
        except json.JSONDecodeError as exc:
            raise VisionPipelineError(f"분류 결과 파싱 실패: {exc}") from exc
    raise VisionPipelineError("분류 결과 형식이 올바르지 않습니다.")
```

---

## 4. 검증 체크리스트

### 4.1 정합성 검증

| 항목 | 기준 | 검증 방법 |
|------|------|----------|
| Task 이름 | `scan.vision`, `scan.rule`, `scan.answer`, `scan.reward` | Celery 등록 확인 |
| Queue 이름 | 각 task 전용 queue | `celery_app.conf` 확인 |
| Event 발행 | `publish_stage_event` 동일 호출 | 로그 비교 |
| Progress | 0→25→50→75→100 | SSE 이벤트 확인 |
| 결과 캐시 | `scan:result:{task_id}` 키 패턴 | Redis 확인 |

### 4.2 테스트

```bash
# 단위 테스트
pytest apps/scan_worker/tests/ -v

# E2E 테스트 (로컬)
docker-compose -f docker-compose.scan-worker-local.yml up --build
curl -X POST http://localhost:8000/scan \
  -H "Content-Type: application/json" \
  -d '{"image_url": "https://...", "provider": "openai"}'
```

---

## 5. 의사결정 기록

### Q1: waste_pipeline을 scan_worker로 이전해야 하는가?

**결정: 아니오 (현재)**

**이유:**
1. `domains/_shared/waste_pipeline`은 character, scan 등 여러 도메인에서 공유
2. 이전 시 중복 코드 발생 또는 shared 의존성 유지 필요
3. 현재는 `import`로 재사용하는 것이 Clean Architecture에 부합

**재검토 조건:**
- `domains/` 폴더 완전 삭제 결정 시
- LLM Provider별 분기 로직 필요 시

### Q2: LLM DI를 적용해야 하는가?

**결정: 선택적 (Phase 2)**

**이유:**
1. 현재 `waste_pipeline`이 OpenAI를 직접 호출
2. DI 적용해도 `waste_pipeline` 내부 변경 필요
3. `llm_config` 전달 구조는 준비됨 (향후 확장 가능)

**즉시 효과:**
- scan-api에서 provider 선택 가능 (openai/gemini)
- ConfigMap으로 모델명 변경 가능

### Q3: Stateless Reducer 패턴을 적용해야 하는가?

**결정: 아니오 (현재)**

**이유:**
1. 현재 파이프라인이 완전히 순차적 (병렬화 불가)
2. Celery Chain이 이미 상태를 prev_result로 전달
3. 품질 향상보다 정합성 확보가 우선

**참고:** [Stateless Reducer 패턴 문서](../foundations/22-stateless-reducer-pattern.md)

---

## 6. 참고 자료

- [domains/scan/tasks/vision.py](../../domains/scan/tasks/vision.py)
- [domains/scan/tasks/rule.py](../../domains/scan/tasks/rule.py)
- [domains/scan/tasks/answer.py](../../domains/scan/tasks/answer.py)
- [domains/scan/tasks/reward.py](../../domains/scan/tasks/reward.py)
- [domains/_shared/waste_pipeline/](../../domains/_shared/waste_pipeline/)
- [Eco² Clean Architecture #13](https://rooftopsnow.tistory.com/142)
- [Eco² Clean Architecture #11](https://rooftopsnow.tistory.com/137)

