# 이코에코(Eco²) 비동기 전환 #5: Celery 기반 Scan Pipeline 구현

> 이전 글: [비동기 전환 #4: RabbitMQ 트러블슈팅](./04-rabbitmq-troubleshooting.md)

---

## 개요

본 문서는 **Scan API의 AI 파이프라인을 Celery 기반 비동기 처리로 전환**한 과정을 기록한다. 현재 구현된 초안부터 큐 분리 계획, DLQ 재처리 전략, 그리고 Event-Driven Architecture로의 확장 방향까지 다룬다.

### 목표

- RabbitMQ + Celery 기반 비동기 AI 파이프라인 구축
- Webhook 콜백을 통한 결과 전달
- 캐릭터 보상 연동 (gRPC → Character 서비스)
- DLQ 기반 장애 복구 전략 수립

### 핵심 성과

| 항목 | Before | After |
|------|--------|-------|
| **응답 시간** | 10-35초 (동기 대기) | <100ms (즉시 응답) |
| **타임아웃** | API Gateway 30초 제한 | 5분까지 처리 가능 |
| **장애 복구** | 수동 재시도 | 자동 재시도 + DLQ |
| **확장성** | API Pod 스케일링 | Worker 독립 스케일링 |

---

## 1. 현재 구현: 단일 Celery Task

### 1.1 아키텍처

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        Phase 1: 단일 Task 구현 (현재)                         │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  Client                                                                      │
│     │                                                                        │
│     │ POST /v1/scan {"image_url": "...", "callback_url": "..."}             │
│     ▼                                                                        │
│  ┌──────────┐         ┌──────────────┐         ┌──────────────┐             │
│  │ scan-api │ ──────▶ │  RabbitMQ    │ ──────▶ │ scan-worker  │             │
│  │ (FastAPI)│  Task   │ scan.vision  │ Consume │   (Celery)   │             │
│  └────┬─────┘ Publish │    Queue     │         └──────┬───────┘             │
│       │               └──────────────┘                │                      │
│       │                                               │                      │
│       ▼ 즉시 응답                                     ▼ 파이프라인 실행       │
│  {"status": "processing",                      ┌──────────────┐             │
│   "task_id": "..."}                            │ classify_task│             │
│                                                │              │             │
│                                                │ 1. Vision    │             │
│                                                │ 2. RAG       │             │
│                                                │ 3. Answer    │             │
│                                                │ 4. Reward    │             │
│                                                └──────┬───────┘             │
│                                                       │                      │
│  Client ◀───────────────────────────────────── Webhook │                     │
│       {"status": "completed", "answer": "..."}        │                      │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 1.2 핵심 컴포넌트

#### Celery 설정 (`domains/_shared/celery/config.py`)

```python
class CelerySettings(BaseSettings):
    """환경변수 기반 Celery 설정"""
    
    # Broker (RabbitMQ)
    broker_url: str = Field(
        "amqp://guest:guest@localhost:5672/",
        description="RabbitMQ broker URL",
    )
    
    # Task 설정
    task_acks_late: bool = True      # 처리 완료 후 ACK
    task_reject_on_worker_lost: bool = True  # Worker 종료 시 재큐잉
    task_time_limit: int = 300       # 5분 Hard Limit
    task_soft_time_limit: int = 240  # 4분 Soft Limit
    
    # Worker 설정
    worker_prefetch_multiplier: int = 1  # Fair dispatch
    worker_concurrency: int = 2
    
    # Task 라우팅
    def get_celery_config(self) -> dict:
        return {
            ...
            "task_routes": {
                "scan.*": {"queue": "scan.vision"},
                "reward.*": {"queue": "reward.character"},
            },
        }
```

#### Base Task (`domains/_shared/celery/base_task.py`)

재시도 로직과 Webhook 전송을 캡슐화한 추상 Task 클래스:

```python
class BaseTask(Task):
    """재시도 로직 + 구조화된 로깅"""
    
    abstract = True
    autoretry_for = (Exception,)
    retry_backoff = True           # 지수 백오프
    retry_backoff_max = 120        # 최대 2분
    retry_jitter = True            # 랜덤 지터
    max_retries = 3


class WebhookTask(BaseTask):
    """결과를 Webhook으로 전송하는 Task"""
    
    abstract = True
    
    def send_webhook(self, callback_url: str, payload: dict) -> bool:
        """HTTP POST로 결과 전송"""
        with httpx.Client(timeout=10.0) as client:
            response = client.post(callback_url, json=payload)
            response.raise_for_status()
            return True
    
    def send_failure_webhook(self, callback_url: str, task_id: str, error: str):
        """실패 시 에러 정보 전송"""
        return self.send_webhook(callback_url, {
            "task_id": task_id,
            "status": "failed",
            "error": error,
        })
```

#### Classify Task (`domains/scan/tasks/classify.py`)

```python
@celery_app.task(
    bind=True,
    base=WebhookTask,
    name="scan.classify",
    queue="scan.vision",
    max_retries=2,
    soft_time_limit=240,
    time_limit=300,
)
def classify_task(
    self: WebhookTask,
    task_id: str,
    user_id: str,
    image_url: str,
    user_input: str | None,
    callback_url: str | None,
) -> dict:
    """AI 파이프라인 비동기 실행"""
    
    # AI 파이프라인 실행 (Vision → RAG → Answer)
    pipeline_result = process_waste_classification(
        prompt_text=user_input or "이 폐기물을 어떻게 분리배출해야 하나요?",
        image_url=image_url,
    )
    
    # 리워드 조건 충족 시 추가 Task 발행
    if _should_trigger_reward(pipeline_result):
        _trigger_reward_task(task_id, user_id, pipeline_result)
    
    # Webhook으로 결과 전송
    if callback_url:
        self.send_webhook(callback_url, {
            "task_id": task_id,
            "status": "completed",
            "category": pipeline_result.get("classification"),
            "answer": pipeline_result.get("final_answer"),
        })
    
    return pipeline_result
```

---

## 2. 실제 AI 파이프라인

### 2.1 파이프라인 단계

Scan API의 AI 파이프라인은 4단계로 구성된다:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        AI 파이프라인 상세                                     │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │  Step 1: Vision (GPT-4V)                                   5~15초   │   │
│  │  ─────────────────────────────────────────────────────────────────  │   │
│  │  • 이미지 분석 및 폐기물 분류                                        │   │
│  │  • Output: major_category, middle_category, minor_category          │   │
│  │  • Output: situation_tags (오염, 세척, 분리 등)                      │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
│                              │                                               │
│                              ▼                                               │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │  Step 2: Rule-based Retrieval (RAG)                        <1초     │   │
│  │  ─────────────────────────────────────────────────────────────────  │   │
│  │  • JSON 기반 배출 규정 검색                                          │   │
│  │  • 지자체별 규정 매칭                                                │   │
│  │  • Output: disposal_rules                                           │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
│                              │                                               │
│                              ▼                                               │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │  Step 3: Answer Generation (GPT-4)                         3~10초   │   │
│  │  ─────────────────────────────────────────────────────────────────  │   │
│  │  • 분류 결과 + 배출 규정 기반 최종 답변 생성                         │   │
│  │  • 사용자 친화적 설명 생성                                           │   │
│  │  • Output: final_answer, insufficiencies                            │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
│                              │                                               │
│                              ▼                                               │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │  Step 4: Reward Evaluation (gRPC)                          1~3초    │   │
│  │  ─────────────────────────────────────────────────────────────────  │   │
│  │  • 재활용폐기물 + 규정 존재 + 부족사항 없음 → 리워드 지급            │   │
│  │  • gRPC로 Character 서비스 호출                                      │   │
│  │  • Output: character_name, dialog, match_reason                     │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
│                                                                              │
│  총 소요 시간: 10~35초                                                       │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 2.2 캐릭터 보상 연동

리워드 지급 조건을 충족하면 별도의 Celery Task로 Character 서비스를 호출한다:

```python
def _should_trigger_reward(pipeline_result: dict) -> bool:
    """리워드 지급 조건 확인"""
    classification = pipeline_result.get("classification_result", {}).get("classification", {})
    
    # 조건 1: 재활용폐기물이어야 함
    if classification.get("major_category") != "재활용폐기물":
        return False
    
    # 조건 2: 배출 규정이 존재해야 함
    if not pipeline_result.get("disposal_rules"):
        return False
    
    # 조건 3: 부족사항이 없어야 함
    insufficiencies = pipeline_result.get("final_answer", {}).get("insufficiencies", [])
    if any(entry for entry in insufficiencies if entry):
        return False
    
    return True


def _trigger_reward_task(task_id: str, user_id: str, pipeline_result: dict):
    """Reward Task를 비동기로 발행"""
    from domains.scan.tasks.reward import process_reward_task
    
    classification = pipeline_result.get("classification_result", {}).get("classification", {})
    
    process_reward_task.delay(
        task_id=task_id,
        user_id=user_id,
        classification={
            "major_category": classification.get("major_category"),
            "middle_category": classification.get("middle_category"),
            "minor_category": classification.get("minor_category"),
        },
        situation_tags=pipeline_result.get("situation_tags", []),
        disposal_rules_present=True,
    )
```

---

## 3. 큐 분리 계획: Celery Chain

### 3.1 현재 문제점

단일 Task로 전체 파이프라인을 처리하면 다음 문제가 발생한다:

| 문제 | 설명 |
|------|------|
| **부분 실패 시 전체 재시도** | Vision 성공 후 Answer 실패 → Vision부터 재실행 |
| **GPU 비용 낭비** | GPT-4V 호출 중복 (재시도 시마다 $0.01+) |
| **모니터링 불가** | 어느 단계에서 병목인지 파악 어려움 |
| **독립 스케일링 불가** | Vision과 Rule 처리 Worker를 분리할 수 없음 |

### 3.2 Phase 2: 4단계 Celery Chain

파이프라인을 4개의 독립적인 Task로 분리하고, Celery `chain()`으로 연결한다:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        Phase 2: Celery Chain                                 │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  scan-api                                                                    │
│     │                                                                        │
│     │ chain(vision.s() | rule.s() | answer.s() | reward.s()).delay()        │
│     ▼                                                                        │
│  ┌──────────┐   ┌──────────┐   ┌──────────┐   ┌──────────┐                  │
│  │  scan.   │──▶│  scan.   │──▶│  scan.   │──▶│  scan.   │                  │
│  │  vision  │   │   rule   │   │  answer  │   │  reward  │                  │
│  │  Queue   │   │  Queue   │   │  Queue   │   │  Queue   │                  │
│  │  (5~15s) │   │  (<1s)   │   │ (3~10s)  │   │  (1~3s)  │                  │
│  └────┬─────┘   └────┬─────┘   └────┬─────┘   └────┬─────┘                  │
│       │              │              │              │                         │
│       ▼              ▼              ▼              ▼                         │
│  ┌──────────┐   ┌──────────┐   ┌──────────┐   ┌──────────┐                  │
│  │ dlq.scan │   │ dlq.scan │   │ dlq.scan │   │ dlq.scan │                  │
│  │ .vision  │   │  .rule   │   │ .answer  │   │ .reward  │                  │
│  └──────────┘   └──────────┘   └──────────┘   └──────────┘                  │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 3.3 구현 예시

```python
# domains/scan/tasks/pipeline.py
from celery import chain

@celery_app.task(name="scan.vision", queue="scan.vision")
def vision_task(task_id: str, user_id: str, image_url: str) -> dict:
    """Step 1: GPT Vision 분류"""
    result = call_gpt_vision(image_url)
    return {
        "task_id": task_id,
        "user_id": user_id,
        "image_url": image_url,
        "classification": result,
    }

@celery_app.task(name="scan.rule", queue="scan.rule")
def rule_task(prev_result: dict) -> dict:
    """Step 2: Rule-based Retrieval"""
    disposal_rules = retrieve_rules(prev_result["classification"])
    return {**prev_result, "disposal_rules": disposal_rules}

@celery_app.task(name="scan.answer", queue="scan.answer", bind=True)
def answer_task(self, prev_result: dict, callback_url: str) -> dict:
    """Step 3: Answer Generation + Webhook"""
    answer = generate_answer(prev_result["classification"], prev_result["disposal_rules"])
    result = {**prev_result, "answer": answer}
    
    # Webhook 전송 (Answer 완료 시점)
    self.send_webhook(callback_url, result)
    return result

@celery_app.task(name="scan.reward", queue="scan.reward")
def reward_task(prev_result: dict) -> dict:
    """Step 4: Reward Evaluation"""
    if should_trigger_reward(prev_result):
        reward = call_character_service(prev_result)
        return {**prev_result, "reward": reward}
    return {**prev_result, "reward": None}


# API에서 호출
def classify_async(task_id, user_id, image_url, callback_url):
    pipeline = chain(
        vision_task.s(str(task_id), str(user_id), image_url),
        rule_task.s(),
        answer_task.s(callback_url=callback_url),
        reward_task.s(),
    )
    pipeline.delay()
```

### 3.4 기대 효과

| 항목 | Before (단일 Task) | After (Chain) |
|------|-------------------|---------------|
| **Vision 실패 후 재시도** | 전체 재실행 | Vision만 재시도 |
| **Answer 실패 후 재시도** | Vision 포함 재실행 | Answer만 재시도 |
| **GPU 비용** | $0.01 × 재시도 횟수 | Vision 성공 시 추가 비용 없음 |
| **모니터링** | 전체 소요 시간만 | 단계별 소요 시간 |
| **Worker 스케일링** | 일괄 | Vision 2개, Rule 1개 등 |

---

## 4. DLQ 재처리 전략: Beat vs Shovel

### 4.1 문제 정의

Celery Task가 `max_retries`를 초과하면 메시지는 Dead Letter Queue(DLQ)로 이동한다.
이 메시지를 어떻게 재처리할 것인가?

```
scan.vision ──실패(3회)──▶ dlq.scan.vision ──???──▶ ???
```

### 4.2 Option A: RabbitMQ Shovel

RabbitMQ 내장 플러그인으로 DLQ 메시지를 원래 큐로 자동 이동:

```yaml
# Shovel 설정
srcQueue: dlq.scan.vision
destQueue: scan.vision
ackMode: on-confirm
```

**장점**: 코드 변경 없음, 고성능

**치명적 단점**: **무한 루프 위험**

```
scan.vision ──실패──▶ dlq.scan.vision ──Shovel──▶ scan.vision ──실패──▶ ...
                              │
                              └─ 즉시 이동 → 무한 반복!
```

Shovel은 메시지 도착 즉시 이동하므로, 재시도 횟수 제어가 불가능하다.

### 4.3 Option B: Celery Beat ✅ (권장)

스케줄 기반으로 DLQ를 주기적으로 확인하고 재처리:

```python
@celery_app.task(name="dlq.reprocess.scan.vision")
def reprocess_dlq_scan_vision(batch_size: int = 50, max_retries: int = 3):
    """DLQ 메시지 재처리"""
    connection = pika.BlockingConnection(...)
    channel = connection.channel()
    
    for _ in range(batch_size):
        method, properties, body = channel.basic_get("dlq.scan.vision")
        if method is None:
            break
        
        # 재시도 횟수 확인
        headers = properties.headers or {}
        retry_count = headers.get("x-retry-count", 0)
        
        if retry_count >= max_retries:
            # Archive 큐로 이동 (수동 처리 필요)
            channel.basic_publish(
                exchange="",
                routing_key="archive.scan.vision",
                body=body,
                properties=pika.BasicProperties(
                    headers={**headers, "archived_at": datetime.utcnow().isoformat()},
                ),
            )
            logger.warning("Message archived", extra={"retry_count": retry_count})
        else:
            # 원래 큐로 재발행 (retry count 증가)
            channel.basic_publish(
                exchange="",
                routing_key="scan.vision",
                body=body,
                properties=pika.BasicProperties(
                    headers={**headers, "x-retry-count": retry_count + 1},
                ),
            )
        
        channel.basic_ack(method.delivery_tag)

# Beat 스케줄 (5분마다 실행)
app.conf.beat_schedule = {
    "reprocess-dlq-scan-vision": {
        "task": "dlq.reprocess.scan.vision",
        "schedule": crontab(minute="*/5"),
        "kwargs": {"batch_size": 50, "max_retries": 3},
    },
}
```

### 4.4 비교 결론

| 항목 | Shovel | Celery Beat |
|------|--------|-------------|
| **재시도 횟수 제어** | ❌ 불가 | ✅ 헤더 기반 |
| **무한 루프 방지** | ❌ 위험 | ✅ retry count |
| **Archive 전략** | ❌ 별도 구현 | ✅ 내장 |
| **조건부 재처리** | ❌ 불가 | ✅ 가능 |
| **로깅/모니터링** | ⚠️ 제한적 | ✅ 상세 |

**결론: Celery Beat + Archive 전략 채택**

---

## 5. Phase 2 진행 방향

### 5.1 작업 목록

| # | 작업 | 우선순위 | 상태 |
|---|------|---------|------|
| 1 | RabbitMQ Queue 추가 (scan.rule, scan.answer) | 🔴 High | 📋 예정 |
| 2 | Celery Chain Task 분리 (4단계) | 🔴 High | 📋 예정 |
| 3 | DLQ 재처리 Task 구현 | 🟡 Medium | 📋 예정 |
| 4 | Celery Beat Deployment 작성 | 🟡 Medium | 📋 예정 |
| 5 | Archive Queue 생성 | 🟢 Low | 📋 예정 |
| 6 | 단계별 메트릭 수집 | 🟢 Low | 📋 예정 |

### 5.2 RabbitMQ Topology 변경

```yaml
# 추가할 Queue (workloads/rabbitmq/base/topology/queues.yaml)
---
apiVersion: rabbitmq.com/v1beta1
kind: Queue
metadata:
  name: scan-rule-queue
spec:
  name: scan.rule
  type: quorum
  arguments:
    x-dead-letter-exchange: dlx
    x-dead-letter-routing-key: dlq.scan.rule
    x-message-ttl: 60000      # 1분
    x-delivery-limit: 5       # 빠른 작업이므로 재시도 5회
---
apiVersion: rabbitmq.com/v1beta1
kind: Queue
metadata:
  name: scan-answer-queue
spec:
  name: scan.answer
  type: quorum
  arguments:
    x-dead-letter-exchange: dlx
    x-dead-letter-routing-key: dlq.scan.answer
    x-message-ttl: 3600000    # 1시간 (GPT 타임아웃)
    x-delivery-limit: 3
```

---

## 6. 결론

### 6.1 현재 달성

- ✅ RabbitMQ + Celery 기반 비동기 파이프라인 구축
- ✅ Webhook 콜백으로 즉시 응답 (100ms 이내)
- ✅ 캐릭터 보상 연동 (gRPC + 별도 Task)
- ✅ 재시도 로직 (Exponential Backoff + DLQ)

### 6.2 다음 단계 (Phase 2)

- 📋 4단계 Celery Chain으로 파이프라인 분리
- 📋 Celery Beat 기반 DLQ 재처리 자동화
- 📋 단계별 메트릭 수집 및 모니터링

### 6.3 Trade-off

| 항목 | 동기 처리 | 비동기 처리 (현재) |
|------|----------|-------------------|
| **복잡도** | 낮음 | 중간 |
| **인프라** | API만 | API + RabbitMQ + Worker |
| **응답 시간** | 10-35초 | <100ms |
| **장애 복구** | 수동 | 자동 (DLQ) |
| **확장성** | 제한적 | 독립적 스케일링 |

---

## 7. 확장 방향: Celery Events 기반 실시간 모니터링 (Phase 3)

Celery는 자체적으로 **Task Events**를 RabbitMQ로 발행한다. 이를 활용하면 Kafka 없이도 실시간 진행상황 전달과 외부 시스템 연동이 가능하다.

### 7.1 Celery Events 아키텍처 (Phase 3)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        Phase 3: Celery Events (RabbitMQ)                     │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  Client                                                                      │
│     │ POST /classify                                                         │
│     ▼                                                                        │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │                    scan-api                                           │   │
│  │  chain(vision | rule | answer).delay()                               │   │
│  │                           │                                           │   │
│  │  GET /progress/{task_id}  │                                           │   │
│  │       │                   │                                           │   │
│  │       ▼                   ▼                                           │   │
│  │  SSE StreamingResponse   RabbitMQ                                     │   │
│  │       ▲                   │                                           │   │
│  │       │                   │ Task Queue                                │   │
│  │       │                   ▼                                           │   │
│  │       │             scan-worker                                       │   │
│  │       │                   │                                           │   │
│  │       │                   │ Celery Events (자동 발행)                  │   │
│  │       │                   ▼                                           │   │
│  │       │         ┌─────────────────────┐                               │   │
│  │       │         │  celeryev Exchange  │                               │   │
│  │       │         │  task-sent          │                               │   │
│  │       │         │  task-started       │                               │   │
│  │       │         │  task-succeeded     │                               │   │
│  │       │         │  task-failed        │                               │   │
│  │       │         └─────────────────────┘                               │   │
│  │       │                   │                                           │   │
│  │       └───────────────────┘                                           │   │
│  │       Event Receiver                                                  │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
│                                                                              │
│  Browser ◀════════ SSE ═════════ scan-api                                   │
│  {"step": "vision", "status": "completed", "progress": 33}                  │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 7.2 Celery Events vs Kafka

| 항목 | Celery Events | Kafka |
|------|---------------|-------|
| **추가 인프라** | ❌ 불필요 (RabbitMQ 기존 활용) | ✅ Kafka Cluster 필요 |
| **이벤트 종류** | Task 상태만 | 자유롭게 정의 |
| **이벤트 영속성** | ❌ 없음 | ✅ Log 보관 |
| **다중 Consumer** | ✅ 가능 (임시 Queue) | ✅ Consumer Group |
| **복잡도** | 낮음 | 높음 |
| **비용** | $0 | +$30/월 (Kafka) |

### 7.3 구현 방향

**Celery 설정** (이미 활성화됨):

```python
# domains/_shared/celery/config.py
"task_send_sent_event": True,       # task-sent 이벤트 발행
"worker_send_task_events": True,    # worker 이벤트 발행
```

**SSE 엔드포인트**:

```python
@router.get("/{task_id}/progress")
async def stream_progress(task_id: str):
    async def event_generator():
        with celery_app.connection() as connection:
            recv = celery_app.events.Receiver(connection, handlers={
                'task-started': on_task_started,
                'task-succeeded': on_task_succeeded,
            })
            for event in recv.itercapture():
                if is_chain_task(event, task_id):
                    yield f"data: {json.dumps(event)}\n\n"
    
    return StreamingResponse(event_generator(), media_type="text/event-stream")
```

### 7.4 향후 Kafka 전환 (Phase 4)

Celery Events로는 한계가 있는 경우 Kafka 도입 검토:

- 이벤트 영속성 필요 (감사 로그, 리플레이)
- 다른 도메인의 비동기 연동 (CQRS)
- 대규모 이벤트 스트리밍 분석

자세한 내용은 [SCAN_PIPELINE_EVOLUTION_PLAN.md](../plans/SCAN_PIPELINE_EVOLUTION_PLAN.md) 참조.

---

## 참고 자료

### 공식 문서

- [Celery Documentation](https://docs.celeryq.dev/)
- [RabbitMQ Dead Lettering](https://www.rabbitmq.com/dlx.html)
- [RabbitMQ Shovel Plugin](https://www.rabbitmq.com/shovel.html)

### Foundations (이론적 기초)

| 주제 | 링크 | 핵심 내용 |
|------|------|----------|
| **Enterprise Integration Patterns** | [블로그](https://rooftopsnow.tistory.com/50) | Pub/Sub, Competing Consumers, DLQ, Idempotency |
| **Transactional Outbox** | [블로그](https://rooftopsnow.tistory.com/56) | 이중 쓰기 문제 해결, Polling Publisher |
| **Debezium Outbox Event Router** | [블로그](https://rooftopsnow.tistory.com/57) | CDC 기반 이벤트 발행, Log Tailing |
| **SAGAS** | [블로그](https://rooftopsnow.tistory.com/55) | 장기 실행 트랜잭션, Compensating Transaction |
| **Life Beyond Distributed Transactions** | [블로그](https://rooftopsnow.tistory.com/53) | 분산 트랜잭션의 한계, Eventual Consistency |
| **CQRS** | [블로그](https://rooftopsnow.tistory.com/51) | Command/Query 분리, 복잡도 트레이드오프 |
| **DDD Aggregate** | [블로그](https://rooftopsnow.tistory.com/52) | 트랜잭션 경계, 일관성 경계 |
| **Uber DOMA** | [블로그](https://rooftopsnow.tistory.com/49) | 도메인 지향 MSA, Layer/Gateway 원칙 |

### 프로젝트 내 문서

- [SCAN_PIPELINE_EVOLUTION_PLAN.md](../plans/SCAN_PIPELINE_EVOLUTION_PLAN.md) - Pipeline 진화 계획
- [KAFKA_CLUSTER_SEPARATION_PLAN.md](../plans/KAFKA_CLUSTER_SEPARATION_PLAN.md) - Kafka 클러스터 분리 계획
- [eda-roadmap.md](../plans/eda-roadmap.md) - EDA 로드맵

---

> 다음 글: [비동기 전환 #6: Celery Chain + Events 구현](./06-celery-chain-events.md)

---

## 변경 이력

| 날짜 | 버전 | 변경 내용 |
|------|------|----------|
| 2024-12-19 | 1.0 | 초안 작성 |
| 2024-12-22 | 1.1 | Phase 3 업데이트: Kafka → Celery Events 전환 |

