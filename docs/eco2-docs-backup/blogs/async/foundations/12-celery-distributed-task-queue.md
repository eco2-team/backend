# Celery: Python 분산 태스크 큐

> **Part III: 메시징 패턴** | [← 11. AMQP](./11-amqp-rabbitmq.md) | [인덱스](./00-index.md)

> 원문: [Celery Documentation](https://docs.celeryq.dev/en/stable/)
> 저자: Ask Solem (2009~)

---

## 들어가며

Celery는 **Python으로 작성된 분산 태스크 큐 시스템**이다. 2009년 Ask Solem이 Django 프로젝트의 비동기 작업 처리를 위해 개발했으며, 현재 Python 생태계에서 가장 널리 사용되는 비동기 작업 처리 라이브러리다.

Celery의 핵심 철학:
- **단순함**: 복잡한 분산 시스템을 간단한 데코레이터로 추상화
- **유연함**: RabbitMQ, Redis 등 다양한 브로커 지원
- **신뢰성**: 재시도, DLQ, 모니터링 내장

---

## Celery 탄생 배경

### Django의 한계

2009년, Django 웹 애플리케이션들은 심각한 문제에 직면했다:

```
┌─────────────────────────────────────────────────────────────┐
│                  2009년 Django의 현실                        │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  User Request                                               │
│       │                                                     │
│       ▼                                                     │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  Django View                                         │   │
│  │                                                     │   │
│  │  def upload_image(request):                         │   │
│  │      image = request.FILES['image']                 │   │
│  │      # 10초 소요!                                   │   │
│  │      resized = resize_image(image)                  │   │
│  │      # 5초 소요!                                    │   │
│  │      send_email(user, "Upload complete")            │   │
│  │      # 3초 소요!                                    │   │
│  │      update_search_index(image)                     │   │
│  │                                                     │   │
│  │      return HttpResponse("Done!")  # 18초 후!      │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
│  문제:                                                      │
│  • 사용자가 18초 대기                                       │
│  • HTTP 타임아웃 위험                                       │
│  • 서버 리소스 점유                                         │
│  • 이메일 실패 시 전체 실패                                 │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### Celery의 해결책

```
┌─────────────────────────────────────────────────────────────┐
│                  Celery 적용 후                              │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  User Request                                               │
│       │                                                     │
│       ▼                                                     │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  Django View                                         │   │
│  │                                                     │   │
│  │  def upload_image(request):                         │   │
│  │      image = request.FILES['image']                 │   │
│  │      task_id = process_image.delay(image.id)        │   │
│  │      return HttpResponse(f"Processing: {task_id}")  │   │
│  │      # 즉시 응답! (< 100ms)                         │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
│                          │                                  │
│                          ▼                                  │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  RabbitMQ (Broker)                                   │   │
│  │  [process_image][send_email][update_index]          │   │
│  └─────────────────────────────────────────────────────┘   │
│                          │                                  │
│              ┌───────────┼───────────┐                     │
│              ▼           ▼           ▼                     │
│         Worker 1    Worker 2    Worker 3                   │
│         (resize)    (email)     (search)                   │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## Celery 핵심 개념

### 아키텍처

```
┌─────────────────────────────────────────────────────────────┐
│                  Celery 아키텍처                             │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌────────────────────────────────────────────────────────┐│
│  │                    Application                         ││
│  │                                                        ││
│  │  @celery_app.task                                     ││
│  │  def process_image(image_id):                         ││
│  │      ...                                               ││
│  │                                                        ││
│  │  # 호출                                                ││
│  │  process_image.delay(123)                             ││
│  └────────────────────────────────────────────────────────┘│
│           │                                                 │
│           │ 메시지 발행                                     │
│           ▼                                                 │
│  ┌────────────────────────────────────────────────────────┐│
│  │                    Broker                              ││
│  │                                                        ││
│  │  • RabbitMQ (권장)                                    ││
│  │  • Redis                                               ││
│  │  • Amazon SQS                                          ││
│  └────────────────────────────────────────────────────────┘│
│           │                                                 │
│           │ 메시지 소비                                     │
│           ▼                                                 │
│  ┌────────────────────────────────────────────────────────┐│
│  │                    Workers                             ││
│  │                                                        ││
│  │  celery -A app worker -l INFO -Q default              ││
│  │                                                        ││
│  │  • Prefork (프로세스 기반)                            ││
│  │  • Eventlet/Gevent (그린스레드)                       ││
│  │  • Solo (단일 스레드)                                  ││
│  └────────────────────────────────────────────────────────┘│
│           │                                                 │
│           │ 결과 저장 (선택)                               │
│           ▼                                                 │
│  ┌────────────────────────────────────────────────────────┐│
│  │                  Result Backend                        ││
│  │                                                        ││
│  │  • Redis (권장)                                       ││
│  │  • PostgreSQL/MySQL                                    ││
│  │  • MongoDB                                             ││
│  └────────────────────────────────────────────────────────┘│
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### Task 정의

```python
from celery import Celery

celery_app = Celery(
    'tasks',
    broker='amqp://localhost',
    backend='redis://localhost',
)


@celery_app.task
def add(x, y):
    """기본 Task"""
    return x + y


@celery_app.task(bind=True, max_retries=3)
def process_image(self, image_id: str):
    """재시도 가능한 Task"""
    try:
        image = Image.objects.get(id=image_id)
        result = resize(image)
        return result
    except TransientError as exc:
        # 재시도 (Exponential Backoff)
        raise self.retry(exc=exc, countdown=2 ** self.request.retries)


@celery_app.task(
    bind=True,
    autoretry_for=(ConnectionError,),
    retry_backoff=True,
    retry_kwargs={'max_retries': 5},
)
def send_email(self, user_id: str, subject: str, body: str):
    """자동 재시도 Task"""
    user = User.objects.get(id=user_id)
    email_service.send(user.email, subject, body)
```

---

## Celery Canvas (워크플로우)

### 기본 프리미티브

```
┌─────────────────────────────────────────────────────────────┐
│                  Celery Canvas                               │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  1. chain: 순차 실행                                        │
│  ────────────────────                                       │
│                                                             │
│  chain(task1.s(arg1), task2.s(), task3.s())                │
│                                                             │
│  task1 ──▶ task2 ──▶ task3                                 │
│  (이전 결과가 다음 Task의 첫 번째 인자로)                   │
│                                                             │
│  2. group: 병렬 실행                                        │
│  ───────────────────                                        │
│                                                             │
│  group(task1.s(1), task1.s(2), task1.s(3))                 │
│                                                             │
│  task1(1) ──┐                                               │
│  task1(2) ──┼──▶ [result1, result2, result3]               │
│  task1(3) ──┘                                               │
│                                                             │
│  3. chord: 병렬 실행 후 콜백                                │
│  ─────────────────────────                                  │
│                                                             │
│  chord([task1.s(1), task1.s(2)], callback.s())             │
│                                                             │
│  task1(1) ──┐                                               │
│             ├──▶ callback([result1, result2])               │
│  task1(2) ──┘                                               │
│                                                             │
│  4. map/starmap: 반복 실행                                  │
│  ────────────────────────                                   │
│                                                             │
│  task1.map([1, 2, 3])  # task1(1), task1(2), task1(3)     │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### AI 파이프라인 예제

```python
from celery import chain, group

# AI 파이프라인: Vision → Rule Match → Answer Gen
def create_scan_pipeline(task_id: str, image_url: str):
    workflow = chain(
        vision_scan.s(task_id, image_url),  # Step 1
        rule_match.s(task_id),               # Step 2
        answer_gen.s(task_id),               # Step 3
    )
    return workflow.apply_async()


# 병렬 처리 예제
def batch_process_images(image_ids: list[str]):
    # 모든 이미지를 병렬로 처리하고 결과 수집
    workflow = chord(
        [process_image.s(img_id) for img_id in image_ids],
        aggregate_results.s()
    )
    return workflow.apply_async()
```

---

## 재시도와 실패 처리

### Retry Pattern

```
┌─────────────────────────────────────────────────────────────┐
│                  Retry Pattern                               │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  Exponential Backoff                                        │
│  ───────────────────                                        │
│                                                             │
│  시도 1: 즉시 실행                                          │
│      │                                                      │
│      ▼ 실패                                                 │
│  시도 2: 2초 후                                             │
│      │                                                      │
│      ▼ 실패                                                 │
│  시도 3: 4초 후                                             │
│      │                                                      │
│      ▼ 실패                                                 │
│  시도 4: 8초 후                                             │
│      │                                                      │
│      ▼ 실패                                                 │
│  DLQ로 이동 (또는 영구 실패)                                │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

```python
@celery_app.task(
    bind=True,
    max_retries=5,
    default_retry_delay=60,  # 기본 60초
)
def unreliable_task(self, data):
    try:
        result = external_api.call(data)
        return result
    except (ConnectionError, TimeoutError) as exc:
        # Exponential Backoff
        countdown = 2 ** self.request.retries * 60  # 60, 120, 240, 480, 960
        raise self.retry(exc=exc, countdown=countdown)
    except PermanentError:
        # 재시도하지 않고 즉시 실패
        raise
```

### Dead Letter Queue

```python
# Celery 설정
celery_app.conf.update(
    task_reject_on_worker_lost=True,
    task_acks_late=True,
    
    # RabbitMQ DLX 설정
    task_queues={
        'scan.ai.pipeline': {
            'exchange': 'scan',
            'routing_key': 'scan.ai.pipeline',
            'queue_arguments': {
                'x-dead-letter-exchange': 'dlx',
                'x-dead-letter-routing-key': 'scan.ai.dlq',
            },
        },
    },
)


@celery_app.task(bind=True, max_retries=3)
def process_image(self, task_id: str):
    try:
        # 처리 로직
        pass
    except Exception as exc:
        if self.request.retries >= self.max_retries:
            # max_retries 초과: DLQ로 이동
            logger.error(f"Task {task_id} failed permanently")
            # RabbitMQ DLX가 자동으로 처리
        raise self.retry(exc=exc)
```

---

## 모니터링

### Flower

```
┌─────────────────────────────────────────────────────────────┐
│                  Flower Dashboard                            │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  실행: celery -A app flower --port=5555                    │
│                                                             │
│  기능:                                                      │
│  • 실시간 Task 모니터링                                    │
│  • Worker 상태 확인                                        │
│  • Task 통계 (성공/실패율)                                 │
│  • Queue 길이 모니터링                                     │
│  • Task 취소/재시도                                        │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  Workers                                             │   │
│  │  ─────────────────────────────────────────────────  │   │
│  │  worker-1    Online    CPU: 45%    Tasks: 123      │   │
│  │  worker-2    Online    CPU: 32%    Tasks: 98       │   │
│  │  worker-3    Offline   -           -               │   │
│  │                                                     │   │
│  │  Queues                                             │   │
│  │  ─────────────────────────────────────────────────  │   │
│  │  scan.ai.pipeline    42 messages                   │   │
│  │  notification        8 messages                    │   │
│  │  scan.ai.dlq         3 messages                    │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### Prometheus Metrics

```python
# celery_prometheus_exporter 사용
from prometheus_client import Counter, Histogram

task_counter = Counter(
    'celery_task_total',
    'Total Celery tasks',
    ['task_name', 'status']
)

task_latency = Histogram(
    'celery_task_latency_seconds',
    'Task execution latency',
    ['task_name']
)


@celery_app.task(bind=True)
def monitored_task(self, data):
    start = time.time()
    try:
        result = process(data)
        task_counter.labels(
            task_name=self.name,
            status='success'
        ).inc()
        return result
    except Exception:
        task_counter.labels(
            task_name=self.name,
            status='failure'
        ).inc()
        raise
    finally:
        task_latency.labels(task_name=self.name).observe(
            time.time() - start
        )
```

---

## 참고 자료

### 공식 문서
- [Celery User Guide](https://docs.celeryq.dev/en/stable/userguide/index.html)
- [Celery Best Practices](https://docs.celeryq.dev/en/stable/userguide/tasks.html#best-practices)
- [Canvas: Designing Work-flows](https://docs.celeryq.dev/en/stable/userguide/canvas.html)

### 관련 Foundation
- [11-amqp-rabbitmq.md](./11-amqp-rabbitmq.md) - Broker로서의 RabbitMQ
- [05-enterprise-integration-patterns.md](./05-enterprise-integration-patterns.md) - 메시징 패턴

---

## 부록: Eco² 적용 포인트

### AI 파이프라인 구현

```
┌─────────────────────────────────────────────────────────────┐
│              Eco² AI Pipeline (Celery)                       │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  POST /scan/classify                                        │
│       │                                                     │
│       ▼                                                     │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  Scan API                                            │   │
│  │                                                     │   │
│  │  task_id = uuid4()                                  │   │
│  │  redis.hset(f"task:{task_id}", "status", "queued") │   │
│  │                                                     │   │
│  │  # Celery Chain 발행                                │   │
│  │  chain(                                             │   │
│  │      vision_scan.s(task_id, image_url),            │   │
│  │      rule_match.s(task_id),                        │   │
│  │      answer_gen.s(task_id),                        │   │
│  │  ).apply_async()                                    │   │
│  │                                                     │   │
│  │  return 202, {"task_id": task_id}                  │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
│                          │                                  │
│                          ▼                                  │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  Celery Workers                                      │   │
│  │                                                     │   │
│  │  vision_scan (2-5초)                                │   │
│  │       │                                             │   │
│  │       ▼ Redis 상태: "vision_done"                   │   │
│  │  rule_match (< 1초)                                 │   │
│  │       │                                             │   │
│  │       ▼ Redis 상태: "rule_done"                     │   │
│  │  answer_gen (3-10초)                                │   │
│  │       │                                             │   │
│  │       ▼ Redis 상태: "completed"                     │   │
│  │                                                     │   │
│  │  # 완료 시 Event Store에 저장 → CDC → Kafka        │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### Task 구현

```python
# domains/scan/tasks/ai_pipeline.py

from celery import shared_task
from domains._shared.taskqueue.app import celery_app


@celery_app.task(bind=True, max_retries=3)
def vision_scan(self, task_id: str, image_url: str):
    """Step 1: GPT Vision 분석"""
    redis.hset(f"task:{task_id}", mapping={
        "status": "processing",
        "step": "vision",
        "progress": 10,
    })
    
    try:
        result = vision_api.analyze(image_url)
        
        redis.hset(f"task:{task_id}", mapping={
            "progress": 33,
            "vision_result": json.dumps(result),
        })
        
        return result
        
    except Exception as exc:
        redis.hset(f"task:{task_id}", "status", "retrying")
        raise self.retry(exc=exc, countdown=2 ** self.request.retries)


@celery_app.task
def rule_match(vision_result: dict, task_id: str):
    """Step 2: Rule-based RAG"""
    redis.hset(f"task:{task_id}", mapping={
        "step": "rule",
        "progress": 50,
    })
    
    rules = rule_engine.match(vision_result)
    
    redis.hset(f"task:{task_id}", "progress", 66)
    
    return {"vision_result": vision_result, "rules": rules}


@celery_app.task(bind=True, max_retries=3)
def answer_gen(self, prev_result: dict, task_id: str):
    """Step 3: GPT Answer 생성 + Event 발행"""
    redis.hset(f"task:{task_id}", mapping={
        "step": "answer",
        "progress": 75,
    })
    
    try:
        answer = llm_api.generate(prev_result)
        
        # Event Store + Outbox 저장
        with db.begin():
            event_store.append(ScanCompleted(
                task_id=task_id,
                classification=prev_result["vision_result"],
                answer=answer,
            ))
        
        redis.hset(f"task:{task_id}", mapping={
            "status": "completed",
            "step": "complete",
            "progress": 100,
            "result": json.dumps(answer),
        })
        
        return answer
        
    except Exception as exc:
        raise self.retry(exc=exc, countdown=2 ** self.request.retries)
```

### Celery 설정

```python
# domains/_shared/taskqueue/config.py

celery_app.conf.update(
    # Broker
    broker_url='amqp://eco2-rabbitmq.rabbitmq.svc.cluster.local:5672/celery',
    result_backend='redis://eco2-redis.redis.svc.cluster.local:6379/0',
    
    # Task 설정
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='Asia/Seoul',
    
    # Queue 라우팅
    task_routes={
        'scan.tasks.vision_scan': {'queue': 'scan.ai.pipeline'},
        'scan.tasks.rule_match': {'queue': 'scan.ai.pipeline'},
        'scan.tasks.answer_gen': {'queue': 'scan.ai.pipeline'},
        'notification.tasks.*': {'queue': 'notification'},
    },
    
    # 신뢰성
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    
    # 재시도
    task_default_retry_delay=60,
    task_max_retries=3,
)
```

| 원칙 | AS-IS (gRPC) | TO-BE (Celery) |
|------|-------------|----------------|
| **비동기 처리** | gRPC 블로킹 | Celery Task |
| **워크플로우** | 순차 호출 | Chain/Group/Chord |
| **재시도** | Circuit Breaker | Exponential Backoff |
| **실패 처리** | 포기 | DLQ + 수동 복구 |
| **상태 추적** | 없음 | Redis + Flower |
| **스케일링** | Pod 수 증가 | Worker 수 증가 |
| **Event 연동** | 없음 | Task → Event Store → CDC |
