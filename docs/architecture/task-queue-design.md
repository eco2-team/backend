# 🐰 RabbitMQ + Celery Task Queue 설계

> **목표**: 한 큐 폭주 방지 + SLO 분리 + 장애 격리  
> **기반**: RabbitMQ Topic Exchange + Celery Best Practices  
> **날짜**: 2025-10-30

## 📋 목차

1. [설계 원칙](#설계-원칙)
2. [큐 설계 (5개)](#큐-설계-5개)
3. [실제 Task 매핑](#실제-task-매핑)
4. [Celery 설정](#celery-설정)
5. [K8s Worker 배치](#k8s-worker-배치)
6. [운영 가이드](#운영-가이드)

---

## 🎯 설계 원칙

### 3대 목표

```mermaid
graph TB
    A[RabbitMQ + Celery] --> B{설계 목표}
    
    B --> C1[🛡️ 한 큐 폭주 방지<br/>TTL + max-length + DLX]
    B --> C2[⚡ SLO 분리<br/>짧은 작업 vs 긴 작업]
    B --> C3[🔒 장애 격리<br/>외부 API 장애 시 다른 큐 정상]
    
    C1 --> D[안정적인<br/>서비스]
    C2 --> D
    C3 --> D
    
    style A fill:#ffe0b3,stroke:#fd7e14,stroke-width:4px,color:#000
    style C1 fill:#ffd1d1,stroke:#dc3545,stroke-width:3px,color:#000
    style C2 fill:#cce5ff,stroke:#007bff,stroke-width:3px,color:#000
    style C3 fill:#d1f2eb,stroke:#28a745,stroke-width:3px,color:#000
    style D fill:#e6d5ff,stroke:#8844ff,stroke-width:4px,color:#000
```

### 핵심 전략

```
1. 짧은 작업과 긴 작업 분리
   ✅ 짧은 작업(< 1초): q.fast (prefetch 높게)
   ✅ 긴 작업(5초+): q.bulk (prefetch=1, 공평성↑)

2. 외부 API 격리
   ✅ 불안정한 외부 API: q.external (재시도 엄격, DLX 필수)
   ✅ 장애 시 다른 큐 영향 없음

3. 예약 작업 분리
   ✅ Celery Beat 전용 큐: q.sched
   ✅ 대규모 예약 트래픽 브로커 보호

4. DLX(Dead Letter Exchange) 공통
   ✅ 모든 큐 → q.dlq로 실패 메시지 격리
   ✅ 수동 재처리 또는 분석용
```

---

## 📦 큐 설계 (5개)

### 전체 구조

```mermaid
graph TB
    subgraph Producer["FastAPI Services"]
        API[waste-service<br/>recycling-service<br/>etc.]
    end
    
    subgraph RabbitMQ["RabbitMQ Broker"]
        Exchange[Topic Exchange<br/>'tasks']
        DLX[Direct Exchange<br/>'dlx']
        
        Q1[q.fast<br/>Priority: 높음<br/>짧은 작업]
        Q2[q.bulk<br/>Priority: 보통<br/>긴 작업]
        Q3[q.external<br/>Priority: 높음<br/>외부 API]
        Q4[q.sched<br/>Priority: 보통<br/>예약 작업]
        Q5[q.dlq<br/>Dead Letter<br/>실패 메시지]
    end
    
    subgraph Workers["Celery Workers"]
        W1[Fast Workers ×5<br/>concurrency: 10<br/>prefetch: 높음]
        W2[Bulk Workers ×2<br/>concurrency: 4<br/>prefetch: 1]
        W3[External Workers ×3<br/>concurrency: 4<br/>prefetch: 2]
        W4[Sched Workers ×1<br/>concurrency: 4]
    end
    
    API --> Exchange
    Exchange -->|*.high.*| Q1
    Exchange -->|*.low.*| Q2
    Exchange -->|external.#| Q3
    Exchange -->|sched.#| Q4
    
    Q1 -.->|실패/TTL| DLX
    Q2 -.->|실패/TTL| DLX
    Q3 -.->|실패/TTL| DLX
    Q4 -.->|실패/TTL| DLX
    DLX --> Q5
    
    Q1 --> W1
    Q2 --> W2
    Q3 --> W3
    Q4 --> W4
    
    style Exchange fill:#ffe0b3,stroke:#fd7e14,stroke-width:4px,color:#000
    style DLX fill:#ffd1d1,stroke:#dc3545,stroke-width:3px,color:#000
    style Q1 fill:#cce5ff,stroke:#007bff,stroke-width:3px,color:#000
    style Q2 fill:#ffe0b3,stroke:#fd7e14,stroke-width:2px,color:#000
    style Q3 fill:#ffd1d1,stroke:#dc3545,stroke-width:3px,color:#000
    style Q4 fill:#d1f2eb,stroke:#28a745,stroke-width:2px,color:#000
    style Q5 fill:#ffb3b3,stroke:#dc3545,stroke-width:4px,color:#000
```

---

## 📋 큐별 상세 설계

### Queue 1: **q.fast** (사용자 응답 직결)

```yaml
큐 이름: q.fast
라우팅 키: *.high.*
목적: 사용자가 대기 중인 짧은 작업

담당 작업:
├─ 이미지 다운로드 (S3)
├─ 이미지 해시 계산 (pHash)
├─ 캐시 조회 (Redis)
├─ 결과 저장 (DB)
└─ 이미지 전처리 (리사이즈)

작업 특성:
├─ 실행 시간: < 1초
├─ 중요도: Critical (사용자 대기)
├─ CPU: 높음 (이미지 처리)
└─ 실패 영향: 전체 프로세스 중단

Worker 프로파일:
├─ Concurrency: 10 (멀티프로세싱)
├─ Prefetch Multiplier: 4 (빠른 처리)
├─ Pool: processes
└─ Replicas: 5개 (K8s)

정책 (RabbitMQ):
├─ TTL: 60초 (짧게, 빠른 실패)
├─ max-length: 5,000 (폭주 방지)
├─ DLX: dlx Exchange로 이동
├─ Priority: 지원 (0-10)
└─ Overflow: reject-publish (길이 초과 시 거부)

재시도/타임아웃:
├─ Task Time Limit: 60초
├─ Soft Time Limit: 50초
├─ Max Retries: 3회
├─ Retry Backoff: 지수 백오프 (1s, 2s, 4s)
└─ acks_late: False (빠른 ACK)
```

### Queue 2: **q.bulk** (배치/긴 작업)

```yaml
큐 이름: q.bulk
라우팅 키: *.low.*
목적: 시간이 걸리는 배치 작업

담당 작업:
├─ 일일 통계 리포트 생성
├─ CSV 내보내기
├─ 대량 데이터 처리
└─ 분석 이력 집계 (배치)

작업 특성:
├─ 실행 시간: 10초 ~ 수 분
├─ 중요도: Medium (배치 처리)
├─ I/O: DB 집약적
└─ 실패 영향: 낮음

Worker 프로파일:
├─ Concurrency: 4
├─ Prefetch Multiplier: 1 (공평성↑, 헤드오브라인 방지)
├─ Pool: gevent (I/O 대기)
└─ Replicas: 2개

정책 (RabbitMQ):
├─ TTL: 3600초 (1시간, 넉넉히)
├─ max-length: 1,000
├─ DLX: dlx
└─ Priority: 낮음 (1-3)

재시도/타임아웃:
├─ Task Time Limit: 600초 (10분)
├─ Soft Time Limit: 540초
├─ Max Retries: 2회
├─ Retry Backoff: True
└─ acks_late: True (처리 완료 후 ACK)

특이사항:
⚠️ prefetch=1로 긴 작업이 짧은 작업 굶기지 않도록!
⚠️ 체크포인팅 권장 (중간 저장)
```

### Queue 3: **q.external** (외부 API/불안정)

```yaml
큐 이름: q.external
라우팅 키: external.#
목적: 외부 API 호출 (AI Vision, LLM, Map)

담당 작업:
├─ AI Vision API (Roboflow, HuggingFace)
├─ LLM API (OpenAI GPT, Claude)
├─ 지도 API (Kakao Map)
└─ 기타 서드파티 연동

작업 특성:
├─ 실행 시간: 2-10초 (API 응답 시간)
├─ 중요도: Critical/High
├─ 네트워크: 매우 높음
├─ 불안정성: 높음 (외부 API 장애 가능)
└─ 사이드 이펙트: 주의 (중복 호출 비용)

Worker 프로파일:
├─ Concurrency: 4 (API Rate Limit 준수)
├─ Prefetch Multiplier: 1-2 (소수, 과부하 방지)
├─ Pool: gevent (네트워크 대기)
└─ Replicas: 3-5개 (외부 API별)

정책 (RabbitMQ):
├─ TTL: 300초 (5분, 필수!)
├─ max-length: 2,000
├─ DLX: dlx (필수!)
└─ Priority: 높음 (7-10)

재시도/타임아웃:
├─ Task Time Limit: 300초 (5분)
├─ Soft Time Limit: 240초
├─ Max Retries: 3회 (엄격, 사이드 이펙트 주의)
├─ Retry Backoff: True (지수 백오프)
├─ acks_late: True (API 성공 후 ACK)
└─ 멱등성: 필수! (중복 호출 대비)

특이사항:
🔴 외부 API 장애 시 이 큐만 영향
🔴 DLX 필수 (타임아웃/실패 메시지 격리)
🔴 Rate Limiting 엄격히 적용
```

### Queue 4: **q.sched** (예약/주기 작업)

```yaml
큐 이름: q.sched
라우팅 키: sched.#
목적: Celery Beat 예약 작업

담당 작업:
├─ 일일 통계 집계 (매일 02:00)
├─ 캐시 정리 (매시간)
├─ 오래된 이미지 삭제 (매일 03:00)
└─ 주간 리포트 (매주 월요일)

작업 특성:
├─ 실행 시간: 다양 (1초 ~ 10분)
├─ 중요도: Medium
├─ 빈도: 주기적 (cron)
└─ ETA/countdown 사용

Worker 프로파일:
├─ Concurrency: 4
├─ Prefetch Multiplier: 1
├─ Pool: gevent
└─ Replicas: 1개 (Beat도 1개!)

정책 (RabbitMQ):
├─ TTL: 3600초
├─ max-length: 500
├─ DLX: dlx
└─ Priority: 중간 (5)

Celery Beat:
├─ Replicas: 1개 (중복 실행 방지)
├─ Scheduler: DatabaseScheduler (분산 환경)
└─ Lock: Redis Lock (HA 시)

특이사항:
⚠️ Beat는 반드시 1개만 실행!
⚠️ 대규모 예약은 별도 워크플로 엔진 검토
⚠️ 예약 트래픽이 브로커 병목 유발 가능
```

### Queue 5: **q.dlq** (Dead Letter Queue)

```yaml
큐 이름: q.dlq
라우팅 키: dlq (Direct)
목적: 실패/만료 메시지 수집 및 분석

유입 경로:
├─ q.fast 실패 (3회 재시도 후)
├─ q.external 타임아웃 (5분 초과)
├─ q.bulk 실패
├─ q.sched 실패
└─ max-length 초과로 reject된 메시지

Worker 프로파일:
├─ 기본: 소비 안 함 (수동 재처리)
├─ 선택: 알람 전용 Worker (1개)
└─ 로그/분석만 수행

정책:
├─ TTL: 없음 (영구 보관)
├─ max-length: 10,000
└─ Overflow: drop-head (오래된 것부터 삭제)

모니터링:
✅ DLQ 길이 모니터링 (Prometheus)
✅ 길이 > 100 → Slack 알람
✅ 주기적 분석 (실패 원인 파악)
```

---

## 🎯 실제 Task 매핑

### 우리 프로젝트 Task 목록

| Task 함수명 | 예상 시간 | 외부 의존성 | SLO | 큐 | 라우팅 키 |
|------------|----------|------------|-----|-----|----------|
| `download_image` | 0.5초 | S3 | 1초 | q.fast | waste.high.download |
| `calculate_hash` | 0.3초 | 없음 | 1초 | q.fast | waste.high.hash |
| `check_cache` | 0.1초 | Redis | 1초 | q.fast | waste.high.cache |
| `preprocess_image` | 0.8초 | 없음 | 2초 | q.fast | waste.high.preprocess |
| `save_result` | 0.2초 | DB | 1초 | q.fast | waste.high.save |
| `ai_vision_classify` | 2-5초 | Roboflow API | 10초 | q.external | external.ai.vision |
| `llm_generate_feedback` | 3-8초 | OpenAI API | 15초 | q.external | external.llm.feedback |
| `search_nearby_bins` | 0.5-1초 | Kakao Map API | 5초 | q.external | external.map.location |
| `save_analytics` | 1-2초 | DB | 없음 | q.bulk | analytics.low.history |
| `daily_stats_report` | 30-60초 | DB | 없음 | q.sched | sched.daily.stats |
| `cleanup_old_images` | 10-30초 | S3 | 없음 | q.sched | sched.daily.cleanup |

### 라우팅 키 패턴

```
패턴: {도메인}.{우선순위}.{작업}

도메인:
├─ waste: 쓰레기 분석 관련
├─ recycling: 재활용 정보
├─ external: 외부 API
├─ analytics: 통계
└─ sched: 예약 작업

우선순위:
├─ high: 사용자 대기, 즉시 처리
├─ low: 배치, 백그라운드
└─ (external, sched는 우선순위 없음)

작업:
├─ download, hash, cache, preprocess, save
├─ ai.vision, llm.feedback
└─ stats, cleanup
```

---

## ⚙️ Celery 설정

### 공통 설정

```python
# app/core/celery_config.py
from kombu import Exchange, Queue

# Exchange 정의
TASKS_EXCHANGE = Exchange("tasks", type="topic")
DLX_EXCHANGE = Exchange("dlx", type="direct")

# Queue 정의
task_queues = (
    # q.fast: 짧고 긴급한 작업
    Queue(
        "q.fast",
        TASKS_EXCHANGE,
        routing_key="*.high.*",
        queue_arguments={
            "x-dead-letter-exchange": "dlx",
            "x-dead-letter-routing-key": "dlq",
            "x-message-ttl": 60_000,  # 60초
            "x-max-length": 5_000,
            "x-overflow": "reject-publish",
            "x-max-priority": 10,
        },
    ),
    
    # q.bulk: 긴 배치 작업
    Queue(
        "q.bulk",
        TASKS_EXCHANGE,
        routing_key="*.low.*",
        queue_arguments={
            "x-dead-letter-exchange": "dlx",
            "x-dead-letter-routing-key": "dlq",
            "x-message-ttl": 3_600_000,  # 1시간
            "x-max-length": 1_000,
            "x-overflow": "reject-publish",
        },
    ),
    
    # q.external: 외부 API (필수 DLX)
    Queue(
        "q.external",
        TASKS_EXCHANGE,
        routing_key="external.#",
        queue_arguments={
            "x-dead-letter-exchange": "dlx",
            "x-dead-letter-routing-key": "dlq",
            "x-message-ttl": 300_000,  # 5분 (필수!)
            "x-max-length": 2_000,
            "x-overflow": "reject-publish",
            "x-max-priority": 10,
        },
    ),
    
    # q.sched: 예약 작업
    Queue(
        "q.sched",
        TASKS_EXCHANGE,
        routing_key="sched.#",
        queue_arguments={
            "x-dead-letter-exchange": "dlx",
            "x-dead-letter-routing-key": "dlq",
            "x-message-ttl": 3_600_000,
            "x-max-length": 500,
        },
    ),
    
    # q.dlq: Dead Letter Queue
    Queue("q.dlq", DLX_EXCHANGE, routing_key="dlq"),
)

# Task 라우팅
task_routes = {
    # Fast 작업 (짧고 긴급)
    "tasks.image.download": {
        "queue": "q.fast",
        "routing_key": "waste.high.download",
        "priority": 10,
    },
    "tasks.image.hash": {
        "queue": "q.fast",
        "routing_key": "waste.high.hash",
        "priority": 10,
    },
    "tasks.cache.check": {
        "queue": "q.fast",
        "routing_key": "waste.high.cache",
        "priority": 10,
    },
    "tasks.image.preprocess": {
        "queue": "q.fast",
        "routing_key": "waste.high.preprocess",
        "priority": 9,
    },
    "tasks.result.save": {
        "queue": "q.fast",
        "routing_key": "waste.high.save",
        "priority": 10,
    },
    
    # External API (격리)
    "tasks.ai.vision": {
        "queue": "q.external",
        "routing_key": "external.ai.vision",
        "priority": 10,
    },
    "tasks.llm.feedback": {
        "queue": "q.external",
        "routing_key": "external.llm.feedback",
        "priority": 7,
    },
    "tasks.location.search": {
        "queue": "q.external",
        "routing_key": "external.map.location",
        "priority": 5,
    },
    
    # Bulk 작업 (배치)
    "tasks.analytics.save": {
        "queue": "q.bulk",
        "routing_key": "analytics.low.history",
        "priority": 1,
    },
    
    # Scheduled 작업
    "tasks.daily.stats": {
        "queue": "q.sched",
        "routing_key": "sched.daily.stats",
    },
    "tasks.cleanup.images": {
        "queue": "q.sched",
        "routing_key": "sched.daily.cleanup",
    },
}

# 공통 설정
broker_url = "amqp://admin:password@rabbitmq.messaging.svc.cluster.local:5672//"
result_backend = "redis://redis.default.svc.cluster.local:6379/1"

# 공평성 & 안정성
worker_prefetch_multiplier = 1  # 기본값, Worker별로 override
task_acks_late = True  # 처리 완료 후 ACK (재시도 안전)
task_reject_on_worker_lost = True
task_queue_max_priority = 10

# 재시도 기본값
task_autoretry_for = (Exception,)
task_retry_kwargs = {"max_retries": 3}
task_retry_backoff = True
task_retry_backoff_max = 60
```

---

## 🖥️ Worker 별 설정

### Fast Worker (q.fast 전용)

```python
# workers/fast_worker.py
from celery import Celery
from app.core.celery_config import *

app = Celery("fast_worker")

app.conf.update(
    broker_url=broker_url,
    result_backend=result_backend,
    task_queues=task_queues,
    
    # Fast Queue만 소비
    task_default_queue="q.fast",
    worker_queues=["q.fast"],
    
    # CPU 최적화
    worker_pool="processes",  # 멀티프로세싱
    worker_concurrency=10,    # CPU 코어 활용
    worker_prefetch_multiplier=4,  # 빠른 소비
    
    # 빠른 ACK
    task_acks_late=False,
    
    # 타임아웃
    task_time_limit=60,
    task_soft_time_limit=50,
)

if __name__ == "__main__":
    app.start()
```

### External Worker (q.external 전용)

```python
# workers/external_worker.py
app = Celery("external_worker")

app.conf.update(
    broker_url=broker_url,
    result_backend=result_backend,
    
    # External Queue만
    worker_queues=["q.external"],
    
    # 네트워크 최적화
    worker_pool="gevent",  # 비동기 I/O
    worker_concurrency=20,  # 네트워크 대기 활용
    worker_prefetch_multiplier=2,  # 소수 (과부하 방지)
    
    # Late ACK (API 성공 후)
    task_acks_late=True,
    
    # 긴 타임아웃
    task_time_limit=300,  # 5분
    task_soft_time_limit=240,
    
    # 재시도 정책
    task_autoretry_for=(ConnectionError, TimeoutError),
    task_retry_kwargs={"max_retries": 3},
    task_retry_backoff=True,
    task_retry_backoff_max=120,
)
```

### Bulk Worker (q.bulk 전용)

```python
# workers/bulk_worker.py
app = Celery("bulk_worker")

app.conf.update(
    broker_url=broker_url,
    result_backend=result_backend,
    
    worker_queues=["q.bulk"],
    
    # I/O 최적화
    worker_pool="gevent",
    worker_concurrency=4,
    worker_prefetch_multiplier=1,  # ⭐ 공평성! (헤드오브라인 방지)
    
    # Late ACK
    task_acks_late=True,
    
    # 넉넉한 타임아웃
    task_time_limit=600,  # 10분
    task_soft_time_limit=540,
)
```

### Scheduled Worker (q.sched 전용)

```python
# workers/sched_worker.py
app = Celery("sched_worker")

app.conf.update(
    broker_url=broker_url,
    result_backend=result_backend,
    
    worker_queues=["q.sched"],
    
    worker_pool="gevent",
    worker_concurrency=4,
    worker_prefetch_multiplier=1,
    
    task_acks_late=True,
    task_time_limit=600,
)

# Celery Beat Schedule
app.conf.beat_schedule = {
    "daily-stats": {
        "task": "tasks.daily.stats",
        "schedule": crontab(hour=2, minute=0),  # 매일 02:00
        "options": {
            "queue": "q.sched",
            "routing_key": "sched.daily.stats",
        },
    },
    "hourly-cache-cleanup": {
        "task": "tasks.cleanup.cache",
        "schedule": crontab(minute=0),  # 매시간
        "options": {
            "queue": "q.sched",
            "routing_key": "sched.hourly.cleanup",
        },
    },
    "daily-image-cleanup": {
        "task": "tasks.cleanup.images",
        "schedule": crontab(hour=3, minute=0),  # 매일 03:00
        "options": {
            "queue": "q.sched",
            "routing_key": "sched.daily.cleanup",
        },
    },
}
```

---

## 🏗️ K8s Worker 배치

### Deployment 구조

```mermaid
graph TB
    subgraph Master["Master Node (t3.medium)"]
        M[k3s Server<br/>+ RabbitMQ Pod]
    end
    
    subgraph Worker1["Worker 1 (t3.medium) - CPU"]
        W1[Fast Worker Pods ×5<br/>q.fast 소비<br/>processes pool<br/>concurrency: 10]
    end
    
    subgraph Worker2["Worker 2 (t3.medium) - Network"]
        W2a[External-AI Worker ×3<br/>q.external (AI)<br/>gevent pool]
        W2b[External-LLM Worker ×2<br/>q.external (LLM)<br/>gevent pool]
    end
    
    subgraph Worker3["Worker 3 (t3.small) - I/O & Sched"]
        W3a[Bulk Worker ×2<br/>q.bulk<br/>gevent pool]
        W3b[Sched Worker ×1<br/>q.sched<br/>gevent pool]
        W3c[Beat ×1<br/>스케줄러]
        W3d[API Services<br/>auth, users, locations]
    end
    
    M -.-> W1
    M -.-> W2a
    M -.-> W2b
    M -.-> W3a
    
    style M fill:#ffd1d1,stroke:#dc3545,stroke-width:4px,color:#000
    style W1 fill:#ffdddd,stroke:#ff4444,stroke-width:3px,color:#000
    style W2a fill:#cce5ff,stroke:#007bff,stroke-width:3px,color:#000
    style W2b fill:#e6d5ff,stroke:#8844ff,stroke-width:3px,color:#000
    style W3a fill:#ffe0b3,stroke:#fd7e14,stroke-width:2px,color:#000
    style W3b fill:#d1f2eb,stroke:#28a745,stroke-width:2px,color:#000
    style W3c fill:#ccf5f0,stroke:#20c997,stroke-width:3px,color:#000
    style W3d fill:#fff4dd,stroke:#ffc107,stroke-width:2px,color:#000
```

### K8s Deployment YAML

```yaml
# k8s/waste/fast-worker-deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: fast-worker
  namespace: waste
spec:
  replicas: 5
  selector:
    matchLabels:
      app: fast-worker
  template:
    metadata:
      labels:
        app: fast-worker
        queue: fast
    spec:
      nodeSelector:
        workload: cpu  # Worker 1
      containers:
      - name: worker
        image: waste-service:latest
        command:
        - celery
        - -A
        - workers.fast_worker
        - worker
        - --loglevel=info
        - --queues=q.fast
        - --concurrency=10
        - --pool=processes
        - --prefetch-multiplier=4
        env:
        - name: CELERY_BROKER_URL
          value: "amqp://admin:password@rabbitmq.messaging:5672//"
        - name: CELERY_RESULT_BACKEND
          value: "redis://redis.default:6379/1"
        resources:
          requests:
            cpu: 500m
            memory: 512Mi
          limits:
            cpu: 2000m
            memory: 1Gi

---
# k8s/waste/external-worker-deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: external-ai-worker
  namespace: waste
spec:
  replicas: 3
  template:
    spec:
      nodeSelector:
        workload: network  # Worker 2
      containers:
      - name: worker
        command:
        - celery
        - -A
        - workers.external_worker
        - worker
        - --loglevel=info
        - --queues=q.external
        - --concurrency=20
        - --pool=gevent
        - --prefetch-multiplier=2
        env:
        - name: AI_VISION_API_URL
          value: "https://api.roboflow.com/..."
        - name: OPENAI_API_KEY
          valueFrom:
            secretKeyRef:
              name: llm-secrets
              key: openai-api-key
        resources:
          requests:
            cpu: 200m
            memory: 256Mi
          limits:
            cpu: 1000m
            memory: 512Mi

---
# k8s/analytics/beat-deployment.yaml (⚠️ Replicas: 1)
apiVersion: apps/v1
kind: Deployment
metadata:
  name: celery-beat
  namespace: analytics
spec:
  replicas: 1  # ⚠️ 반드시 1개!
  template:
    spec:
      containers:
      - name: beat
        command:
        - celery
        - -A
        - workers.sched_worker
        - beat
        - --loglevel=info
        - --scheduler=celery.beat:PersistentScheduler
```

---

## 📊 노드별 리소스 배치

### 3노드 구성 ($91/월)

```
Master (t3.medium, $30/월):
├─ k3s Control Plane
├─ RabbitMQ (1 Pod)
├─ ArgoCD
└─ Prometheus

Worker 1 (t3.medium, $30/월) - CPU 집약:
├─ Fast Workers ×5 (q.fast)
│   └─ CPU: 2 cores 거의 풀 사용
└─ 리소스: CPU 90%, Memory 70%

Worker 2 (t3.medium, $30/월) - Network 집약:
├─ External-AI Workers ×3 (q.external - AI)
├─ External-LLM Workers ×2 (q.external - LLM)
└─ 리소스: CPU 30%, Memory 40%, Network 80%

Worker 3 (t3.small, $15/월) - I/O & Sched:
├─ Bulk Workers ×2 (q.bulk)
├─ Sched Worker ×1 (q.sched)
├─ Beat ×1 (스케줄러)
└─ API Services (auth, users, locations)
└─ 리소스: CPU 50%, Memory 60%

총: $105/월 (RabbitMQ 포함)
```

---

## ✅ 운영 체크리스트

### 배포 전 검증

```bash
# 1. RabbitMQ 큐 생성 확인
rabbitmqctl list_queues name messages consumers

# 예상 출력:
# q.fast         0    5
# q.bulk         0    2
# q.external     0    5
# q.sched        0    1
# q.dlq          0    0

# 2. Exchange 확인
rabbitmqctl list_exchanges

# 3. Binding 확인
rabbitmqctl list_bindings

# 4. Worker 연결 확인
celery -A workers.fast_worker inspect active_queues

# 5. DLQ 길이 모니터링
watch -n 5 'rabbitmqctl list_queues name messages | grep dlq'
```

### 운영 모니터링

```python
# Prometheus 메트릭
rabbitmq_queue_messages{queue="q.fast"}
rabbitmq_queue_messages{queue="q.dlq"}  # ⚠️ 증가 시 알람
celery_task_duration_seconds{queue="q.fast"}
celery_task_failures_total{queue="q.external"}

# 알람 조건:
- q.dlq 길이 > 100 → Critical
- q.fast 길이 > 1,000 → Warning
- q.external 실패율 > 10% → Warning
```

---

## 🎯 핵심 포인트

### 왜 이렇게 설계했는가?

```
1. 헤드오브라인 방지 (공평성)
   ✅ 긴 작업(q.bulk): prefetch=1
   ✅ 짧은 작업(q.fast): prefetch=4
   → 긴 작업이 짧은 작업 굶기지 않음!

2. 브로커 보호
   ✅ TTL: 메시지 만료 → DLQ 이동
   ✅ max-length: 큐 길이 제한 → 폭주 방지
   ✅ overflow: reject-publish → 거부

3. 장애 격리
   ✅ 외부 API 장애 → q.external만 영향
   ✅ q.fast, q.bulk는 계속 정상 작동

4. 멱등성 (중복 실행 대비)
   ✅ acks_late=True → 처리 완료 후 ACK
   ✅ Task는 반드시 멱등하게 설계
   ✅ 중복 호출되어도 안전
```

---

## 📚 참고 자료

- [Celery 공식 가이드 - Routing](https://docs.celeryq.dev/en/stable/userguide/routing.html)
- [RabbitMQ - Dead Letter Exchanges](https://www.rabbitmq.com/dlx.html)
- [Celery - Task Retry](https://docs.celeryq.dev/en/stable/userguide/tasks.html#retrying)
- [RabbitMQ - TTL and Expiry](https://www.rabbitmq.com/ttl.html)

---

**작성일**: 2025-10-30  
**상태**: 🔄 승인 대기  
**비용**: $105/월 (3노드 + RabbitMQ)

