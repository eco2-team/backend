# Scan Worker 배포 전 정합성 점검 보고서

> 작성일: 2026-01-07  
> 최종 수정: 2026-01-07 (Exchange 정합성 이슈 추가)  
> 상태: Resolved

---

## 1. 개요

Scan Worker를 Clean Architecture로 마이그레이션한 후 배포 전 전체 정합성을 점검했습니다.

### 점검 범위

- Celery Task ↔ Queue 이름 일치 (1:1 매핑 정책)
- `apps/scan_worker` ↔ `apps/scan` 호출 정합성
- Kubernetes Manifest ↔ 코드 환경변수 정합성
- RabbitMQ 큐 존재 여부
- External Secret 설정 정합성

---

## 2. 큐 라우팅 정합성

### 2.1 Scan 내부 큐 (✅ 통과)

| Task | Queue | scan_worker | scan API | RabbitMQ |
|------|-------|:-----------:|:--------:|:--------:|
| `scan.vision` | `scan.vision` | ✅ | ✅ | ✅ |
| `scan.rule` | `scan.rule` | ✅ | ✅ | ✅ |
| `scan.answer` | `scan.answer` | ✅ | ✅ | ✅ |
| `scan.reward` | `scan.reward` | ✅ | ✅ | ✅ |

**검증 위치:**

- `apps/scan_worker/setup/celery.py`: `SCAN_TASK_ROUTES`
- `apps/scan/setup/celery_app.py`: `task_routes`
- `apps/scan_worker/presentation/tasks/*.py`: `@celery_app.task(name=..., queue=...)`

### 2.2 External 서비스 호출 (⚠️ 이슈 발견 → ✅ 해결됨)

| Task | Queue | Exchange | Routing Key | Target Worker |
|------|-------|----------|-------------|:-------------:|
| `character.match` | `character.match` | `character.direct` | `character.match` | character-match-worker |
| `character.save_ownership` | `character.save_ownership` | `character.direct` | `character.save_ownership` | character-worker |
| `users.save_character` | `users.save_character` | `users.direct` | `users.save_character` | users-worker |
| `character.grant_default` | `character.grant_default` | `character.direct` | `character.grant_default` | character-worker |

### 2.3 Cross-Domain Exchange 정합성 (🔴 Critical → ✅ 해결됨)

**문제:** `apps/scan_worker`가 cross-domain 태스크 발행 시 메시지 유실

| 발신 앱 | 기본 Exchange | 대상 Exchange | 결과 |
|---------|---------------|---------------|:----:|
| `apps/scan_worker` | `celery` (topic) | `character.direct` | ❌ 유실 |
| `domains/scan` | `""` (default) | - | ✅ 작동 |

**원인 분석:**

```
scan-worker (Celery app)
├── CELERY_EXCHANGE = Exchange("celery", type="topic")
└── send_task("character.match", queue="character.match")
    └── → celery (topic) exchange로 발행
        └── character.match 큐 바인딩 없음 → 메시지 유실

RabbitMQ Topology CR
├── character.direct (direct) ← character.match 바인딩됨
├── users.direct (direct) ← users.save_character 바인딩됨
└── celery (topic) ← scan.* 큐만 바인딩됨
```

**해결:**

```python
# Before (잘못됨)
self._celery.send_task(
    "character.match",
    queue="character.match",
)  # → celery exchange로 발행 → 유실

# After (수정됨)
self._celery.send_task(
    "character.match",
    queue="character.match",
    exchange="character.direct",
    routing_key="character.match",
)  # → character.direct exchange로 발행 → 정상 전달
```

**수정된 파일:**

| 파일 | 수정 내용 |
|------|----------|
| `apps/scan_worker/application/classify/steps/reward_step.py` | `character.match`, `character.save_ownership`, `users.save_character` exchange 명시 |
| `apps/users/infrastructure/messaging/default_character_publisher_celery.py` | `character.grant_default` exchange 명시 |

**커밋:**

- `7b469e70` fix(scan-worker): use correct exchange for cross-worker task dispatch
- `6b79dccb` fix(users): add explicit exchange for character.grant_default dispatch

---

## 3. 발견된 이슈

### 3.1 Cross-Domain Exchange 불일치 (🔴 Critical → ✅ 해결됨)

**증상:**

```
[WARNING] Character match failed
```

scan-worker에서 `character.match` 호출 시 메시지가 character-match-worker에 전달되지 않음.

**원인:**

| 구성 요소 | scan-worker 설정 | 실제 RabbitMQ 바인딩 |
|-----------|------------------|---------------------|
| Exchange | `celery` (topic) | `character.direct` (direct) |
| Binding | `scan.*` only | `character.match` |

scan-worker가 `celery` (topic) exchange에 메시지를 발행하지만, `character.match` 큐는 `character.direct` exchange에만 바인딩되어 있어 메시지 유실.

**수정:**

```python
# send_task 호출 시 exchange 명시
self._celery.send_task(
    "character.match",
    queue="character.match",
    exchange="character.direct",      # ← 추가
    routing_key="character.match",    # ← 추가
)
```

**영향 범위:**

| 태스크 | 수정 전 Exchange | 수정 후 Exchange |
|--------|------------------|------------------|
| `character.match` | `celery` (유실) | `character.direct` |
| `character.save_ownership` | `celery` (유실) | `character.direct` |
| `users.save_character` | `celery` (유실) | `users.direct` |
| `character.grant_default` | 미지정 | `character.direct` |

### 3.2 RabbitMQ 사용자명 불일치 (🔴 Critical)

**증상:**

```
consumer: Cannot connect to amqp://rabbitmq:**@eco2-rabbitmq...
```

**원인 분석:**

| 파일 | 설정된 사용자명 | 올바른 값 |
|------|:--------------:|:--------:|
| `dev/users-api-secrets.yaml` | `rabbitmq` | `admin` |
| `prod/users-api-secrets.yaml` | `rabbitmq` | `admin` |
| `dev/api-secrets.yaml` (auth) | `rabbitmq` | `admin` |

**수정:**

```yaml
# Before
CELERY_BROKER_URL: amqp://rabbitmq:{{ .rabbitmqPassword }}@...

# After
CELERY_BROKER_URL: amqp://admin:{{ .rabbitmqPassword }}@...
```

### 3.3 환경변수 Prefix 불일치 (🟡 Medium)

**증상:** scan_worker가 환경변수를 읽지 못함

**원인:**

```python
# config.py에서 SCAN_WORKER_ prefix 사용
model_config = SettingsConfigDict(
    env_prefix="SCAN_WORKER_",  # ❌ 문제
    ...
)
```

```yaml
# deployment.yaml에서 prefix 없이 주입
- name: CELERY_BROKER_URL  # SCAN_WORKER_CELERY_BROKER_URL가 아님
  valueFrom:
    secretKeyRef:
      name: scan-secret
      key: CELERY_BROKER_URL
```

**수정:**

```python
# env_prefix 제거
model_config = SettingsConfigDict(
    env_file=".env",
    env_file_encoding="utf-8",
    extra="ignore",
)
```

---

## 4. Manifest-Code 정합성

### 4.1 Deployment (✅ 통과)

| 항목 | 값 | 상태 |
|------|-----|:----:|
| Celery app 경로 | `apps.scan_worker.setup.celery:celery_app` | ✅ |
| Queue 목록 | `scan.vision,scan.rule,scan.answer,scan.reward` | ✅ |
| Pool 타입 | `gevent` | ✅ |
| Concurrency | `100` | ✅ |

### 4.2 ConfigMap (✅ 통과)

| 키 | 값 | 용도 |
|-----|-----|------|
| `CHECKPOINT_TTL` | `3600` | 체크포인트 TTL (1시간) |
| `DEFAULT_MODEL` | `gpt-5.2` | 기본 LLM 모델 |
| `SUPPORTED_GPT_MODELS` | `gpt-5.2,...` | GPT 허용 목록 |
| `SUPPORTED_GEMINI_MODELS` | `gemini-3-pro-preview,...` | Gemini 허용 목록 |

### 4.3 ExternalSecret (✅ 통과)

| 키 | SSM 경로 | 상태 |
|-----|----------|:----:|
| `OPENAI_API_KEY` | `/sesacthon/dev/api/chat/openai-api-key` | ✅ |
| `GEMINI_API_KEY` | `/sesacthon/dev/api/scan/gemini-api-key` | ✅ |
| `CELERY_BROKER_URL` | (template) | ✅ |

---

## 5. 로직 정합성

### 5.1 파이프라인 흐름 (✅ 통과)

```
Vision → Rule → Answer → Reward
  │        │       │        │
  ▼        ▼       ▼        ▼
 분류    규정검색  답변생성  보상처리
```

| Step | Port | Adapter | 출력 |
|------|------|---------|------|
| `VisionStep` | `VisionModelPort` | `GPTVisionAdapter` | `classification` |
| `RuleStep` | `RetrieverPort` | `JsonRegulationRetriever` | `disposal_rules` |
| `AnswerStep` | `LLMPort` | `GPTLLMAdapter` | `final_answer` |
| `RewardStep` | (Celery) | - | `reward` |

### 5.2 Redis Streams 이벤트 형식 (✅ 호환)

**Event Publisher 출력 필드:**

```python
# apps/scan_worker/infrastructure/persistence_redis/event_publisher_impl.py
'job_id', 'stage', 'status', 'seq', 'ts', 'progress', 'result'
```

**Event Router 기대 필드:**

```python
# domains/event-router/core/consumer.py
event["job_id"], event["stage"], event["status"], event["seq"], event["progress"], event["result"]
```

→ **형식 일치 확인 완료**

### 5.3 결과 캐시 키 형식 (✅ 통과)

```python
# apps/scan_worker
cache_key = f"scan:result:{task_id}"

# apps/scan (결과 조회)
cache_key = f"scan:result:{job_id}"
```

### 5.4 Context 직렬화 (✅ 통과)

| 내부 필드 | 직렬화 키 | 복원 |
|-----------|----------|:----:|
| `classification` | `classification_result` | ✅ |
| `disposal_rules` | `disposal_rules` | ✅ |
| `final_answer` | `final_answer` | ✅ |
| `latencies` | `metadata` | ✅ |

### 5.5 DI 주입 흐름 (✅ 통과)

```
1. Task receives: task_id, user_id, image_url, model
2. create_context() → ClassifyContext with llm_model
3. get_vision_step(model) → VisionStep with GPTVisionAdapter
4. Step.run(ctx) → ctx with classification
5. ctx.to_dict() → next Task
```

### 5.6 Reward 로직 검증 (✅ 통과)

| 조건 | 검증 |
|------|:----:|
| `major_category == "재활용폐기물"` | ✅ |
| `disposal_rules` 존재 | ✅ |
| `insufficiencies` 없음 | ✅ |
| `character.match` 동기 호출 (10초 타임아웃) | ✅ |
| `character.save_ownership` Fire & Forget | ✅ |
| `users.save_character` Fire & Forget | ✅ |
| 결과 캐시 저장 후 `done` 이벤트 발행 | ✅ |

---

## 6. 배포 후 검증 절차

### RabbitMQ 큐 확인

```bash
kubectl exec -n rabbitmq eco2-rabbitmq-server-0 -- \
  rabbitmqctl list_queues -p eco2 | grep -E "scan\.|users\."
```

**기대 결과:**

```
scan.vision       0
scan.rule         0
scan.answer       0
scan.reward       0
users.save_character  0
```

### Workers 상태 확인

```bash
kubectl get pod -n scan | grep worker
kubectl get pod -n users | grep worker
```

### Celery 연결 확인

```bash
kubectl exec -n scan deployment/scan-worker -- \
  celery -A apps.scan_worker.setup.celery:celery_app inspect ping
```

---

## 7. Legacy vs Apps 정합성 비교

### 7.1 API Endpoint 비교

| 항목 | domains/scan | apps/scan | 정합성 |
|------|:-----------:|:---------:|:------:|
| Endpoint | `POST /scan` | `POST /scan` | ✅ |
| 인증 방식 | JWT (FastAPI Depends) | Ext-Authz (X-User-ID 헤더) | 🔄 변경 |
| Idempotency | `X-Idempotency-Key` | `X-Idempotency-Key` | ✅ |
| 모델 선택 | ❌ | `model` 필드 | ➕ 추가 |
| 응답 스키마 | `ScanSubmitResponse` | `ScanSubmitResponse` | ✅ |

### 7.2 Celery Chain 비교

**domains/scan (레거시):**

```python
pipeline = chain(
    vision_task.s(job_id, user_id, image_url, user_input),
    rule_task.s(),
    answer_task.s(),
    scan_reward_task.s(),
)
```

**apps/scan (Clean Architecture):**

```python
pipeline = chain(
    self._celery_app.signature(
        "scan.vision",
        args=[job_id, request.user_id, request.image_url, user_input],
        kwargs={"model": model},
        queue="scan.vision",
    ),
    self._celery_app.signature("scan.rule", queue="scan.rule"),
    self._celery_app.signature("scan.answer", queue="scan.answer"),
    self._celery_app.signature("scan.reward", queue="scan.reward"),
)
```

| 차이점 | 설명 |
|--------|------|
| Task 참조 | 직접 import → 이름으로 signature |
| Queue 지정 | decorator에서 → 호출 시 명시 |
| Model 전달 | ❌ → kwargs로 전달 |

### 7.3 Task Return 형식 비교

**vision_task 반환 형식:**

| 키 | domains/scan | apps/scan_worker | 정합성 |
|----|:-----------:|:----------------:|:------:|
| `task_id` | ✅ | ✅ | ✅ |
| `user_id` | ✅ | ✅ | ✅ |
| `image_url` | ✅ | ✅ | ✅ |
| `user_input` | ✅ | ✅ | ✅ |
| `classification_result` | ✅ | ✅ | ✅ |
| `metadata` | ✅ | ✅ | ✅ |
| `llm_provider` | ❌ | ✅ | ➕ 추가 |
| `llm_model` | ❌ | ✅ | ➕ 추가 |

### 7.4 Reward Task 큐 라우팅 비교

| Task | domains/scan 큐 | apps/scan_worker 큐 | 변경 |
|------|:--------------:|:------------------:|:----:|
| `character.save_ownership` | `character.reward` | `character.save_ownership` | 🔄 1:1 정책 |
| `users.save_character` | `users.character` | `users.save_character` | 🔄 1:1 정책 |
| `my.save_character` | `my.reward` | **제거됨** | ❌ deprecated |

### 7.5 이벤트 발행 비교

| 항목 | domains/scan | apps/scan_worker | 정합성 |
|------|:-----------:|:----------------:|:------:|
| 발행 함수 | `publish_stage_event()` | `EventPublisherPort.publish_stage_event()` | ✅ |
| Stream 키 | `scan:events:{shard}` | `scan:events:{shard}` | ✅ |
| 필드 형식 | `job_id, stage, status, seq, ts, progress, result` | 동일 | ✅ |
| 멱등성 | Lua Script | Lua Script | ✅ |

### 7.6 결과 캐시 비교

| 항목 | domains/scan | apps/scan_worker | 정합성 |
|------|:-----------:|:----------------:|:------:|
| 캐시 키 | `scan:result:{task_id}` | `scan:result:{task_id}` | ✅ |
| TTL | 3600초 (1시간) | 3600초 (1시간) | ✅ |
| 저장 시점 | done 이벤트 전 | done 이벤트 전 | ✅ |

### 7.7 정합성 결론

| 카테고리 | 상태 | 비고 |
|----------|:----:|------|
| API 스키마 | ✅ | 응답 형식 100% 호환 |
| Celery Chain | ✅ | Task 이름 및 순서 동일 |
| 이벤트 형식 | ✅ | Event Router/SSE Gateway 호환 |
| 결과 캐시 | ✅ | /result 엔드포인트 호환 |
| 큐 라우팅 | 🔄 | 1:1 정책으로 변경 (character-worker, users-worker에서 수용) |
| 인증 | 🔄 | JWT → Ext-Authz 변경 (인프라 수준) |
| my 도메인 | ❌ | 제거됨 (users로 통합) |

---

## 8. Scan 엔드포인트 흐름

### 8.1 전체 흐름도

```
┌────────────────────────────────────────────┐
│ Client                                     │
│   POST /api/v1/scan                        │
│   { image_url, user_input?, model? }       │
│   Headers: X-User-ID, X-Idempotency-Key?   │
└────────────────────┬───────────────────────┘
                     ▼
┌────────────────────────────────────────────┐
│ apps/scan (API)                            │
│                                            │
│ Controller (scan.py)                       │
│   1. Ext-Authz에서 X-User-ID 추출          │
│   2. 모델 검증                             │
│   3. SubmitCommand.execute() 호출          │
│                                            │
│ SubmitClassificationCommand                │
│   1. Idempotency 체크 (Redis Cache)        │
│   2. job_id 생성 (UUID)                    │
│   3. "queued" 이벤트 발행                  │
│   4. Celery Chain 발행                     │
│   5. 응답 반환                             │
└────────────────────┬───────────────────────┘
                     ▼
┌────────────────────────────────────────────┐
│ RabbitMQ                                   │
│                                            │
│ scan.vision → scan.rule →                  │
│ scan.answer → scan.reward                  │
└────────────────────┬───────────────────────┘
                     ▼
┌────────────────────────────────────────────┐
│ apps/scan_worker                           │
│                                            │
│ [1] VisionTask (scan.vision)               │
│     - GPTVisionAdapter로 이미지 분류       │
│     - 체크포인트 저장                      │
│     - 이벤트 발행 (progress: 25%)          │
│                     ▼                      │
│ [2] RuleTask (scan.rule)                   │
│     - JsonRegulationRetriever로 규정 검색  │
│     - 체크포인트 저장                      │
│     - 이벤트 발행 (progress: 50%)          │
│                     ▼                      │
│ [3] AnswerTask (scan.answer)               │
│     - GPTLLMAdapter로 답변 생성            │
│     - 체크포인트 저장                      │
│     - 이벤트 발행 (progress: 75%)          │
│                     ▼                      │
│ [4] RewardTask (scan.reward)               │
│     a. 보상 조건 확인                      │
│     b. character.match 동기 호출           │
│     c. character.save_ownership 발행       │
│     d. users.save_character 발행           │
│     e. 결과 캐시 저장                      │
│     f. "done" 이벤트 발행 (100%)           │
└────────────────────┬───────────────────────┘
                     ▼
┌────────────────────────────────────────────┐
│ Redis Streams (scan:events:{shard})        │
│                                            │
│ queued → vision → rule → answer → done     │
│  (0%)    (25%)   (50%)   (75%)   (100%)    │
└────────────────────┬───────────────────────┘
                     ▼
┌────────────────────────────────────────────┐
│ Event Router → SSE Gateway                 │
│   XREADGROUP → WebSocket/SSE               │
└────────────────────┬───────────────────────┘
                     ▼
┌────────────────────────────────────────────┐
│ Client (실시간)                            │
│   GET /api/v1/stream?job_id=xxx            │
│   SSE: { stage, status, progress }         │
├────────────────────────────────────────────┤
│ Client (결과 조회)                         │
│   GET /api/v1/scan/{job_id}/result         │
│   → Redis Cache 조회                       │
│   → 200/202/404                            │
└────────────────────────────────────────────┘

### 8.2 RESTful 엔드포인트

| 기존 | 변경 후 | 비고 |
|------|---------|------|
| `/api/v1/scan/result/{id}` | `/api/v1/scan/{id}/result` | 결과 조회 |
| `/api/v1/stream?job_id={id}` | `/api/v1/scan/{id}/events` | SSE 스트리밍 |

**VirtualService 라우팅**:
- `/api/v1/scan/{id}/events` → SSE Gateway (regex 매칭)
- `/api/v1/scan/{id}/result` → Scan API
```

### 8.2 핵심 컴포넌트

| 단계 | 컴포넌트 | 역할 |
|:----:|----------|------|
| 1 | Controller | 요청 검증, Command 호출 |
| 2 | SubmitCommand | Idempotency, Celery Chain 발행 |
| 3 | VisionTask | 이미지 분류 (GPT Vision) |
| 4 | RuleTask | 규정 검색 (JSON Lite RAG) |
| 5 | AnswerTask | 답변 생성 (GPT LLM) |
| 6 | RewardTask | 보상 처리, 결과 캐싱, done 이벤트 |
| 7 | Event Router | Redis Streams 소비 |
| 8 | SSE Gateway | 클라이언트 실시간 전달 |

### 8.3 체크포인팅 흐름

```
Task 실행 시:
┌──────────────────────────────────────┐
│ CheckpointingStepRunner.run_step()   │
│                                      │
│ 1. 체크포인트 확인                   │
│    └─ 있으면 Skip (멱등성)           │
│                                      │
│ 2. Step.run(ctx) 실행                │
│                                      │
│ 3. 체크포인트 저장                   │
│    └─ scan:checkpoint:{task_id}:step │
│                                      │
│ 4. 이벤트 발행                       │
│    └─ scan:events:{shard}            │
└──────────────────────────────────────┘

실패 복구 시:
┌──────────────────────────────────────┐
│ resume_from_checkpoint(task_id)      │
│                                      │
│ 1. 마지막 체크포인트 조회            │
│    └─ vision → rule → answer 순서    │
│                                      │
│ 2. Context 복원                      │
│                                      │
│ 3. 다음 Step부터 재시작              │
│    └─ LLM 재호출 비용 절감           │
└──────────────────────────────────────┘
```

---

## 9. 관련 문서

- [Scan Worker Migration Roadmap](../../plans/scan-worker-migration-roadmap.md)
- [Stateless Reducer Pattern](../../plans/scan-worker-stateless-reducer.md)
- [Clean Architecture Migration](../clean-architecture/07-scan-migration-roadmap.md)

