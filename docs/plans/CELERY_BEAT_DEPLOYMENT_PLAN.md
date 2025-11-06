# 🕐 Celery Beat Scheduler 배치 분석

## 📊 현재 상황

### 문제점

```yaml
❌ Celery Beat가 실제로 배포되지 않음
  - 문서에만 기술됨 (docs/architecture/task-queue-design.md)
  - Kubernetes Deployment 없음
  - Worker 코드 없음
  
❌ 문서 불일치:
  - final-k8s-architecture.md: "Worker-3에 Beat 배치"
  - task-queue-design.md: "analytics namespace"
  - 실제: 배포 없음
```

---

## 🎯 Celery Beat란?

### 역할

```yaml
Celery Beat:
  역할: 주기적 작업 스케줄러
  비유: Linux cron과 유사
  
기능:
  ✅ 예약된 시간에 Task 발행
  ✅ 반복 작업 (매시간, 매일, 매주)
  ✅ Cron 스케줄 지원
  
예시:
  - 매일 03:00 → 오래된 이미지 정리
  - 매시간 00분 → 캐시 정리
  - 매주 월요일 → 주간 리포트
```

### 제약사항

```yaml
⚠️ 반드시 1개만 실행!
  이유:
    - Beat가 2개 이상 → 중복 Task 발행
    - 중복 실행 = 데이터 중복, 비용 증가
    - 예: 이미지 정리 2번 실행 ❌

해결책:
  ✅ Deployment replicas: 1
  ✅ PersistentScheduler 사용 (재시작 시 상태 복구)
  ✅ Redis 기반 스케줄 저장
```

---

## 🏗️ 배치 전략

### 옵션 1: Worker-Network에 배치 (추천) ✅

```yaml
노드: Worker-Network (t3.medium, 4GB)
네임스페이스: workers

장점:
  ✅ 이미 Worker 노드에 배치
  ✅ 리소스 사용 극히 낮음 (50m CPU, 128Mi RAM)
  ✅ 추가 노드 불필요
  ✅ RabbitMQ 접근 용이

단점:
  ⚠️ Worker-Network 장애 시 Beat도 중단
  ⚠️ 여유 리소스 적음 (0.3GB)

배치:
  Worker-Network (4GB):
    - vision-worker: 5-8 Pods (HPA)
    - llm-worker: 3 Pods
    - beat: 1 Pod ← 여기!
```

### 옵션 2: Master 노드에 배치

```yaml
노드: Master (t3.large, 8GB)
네임스페이스: workers

장점:
  ✅ Master는 리소스 여유 있음 (8GB)
  ✅ 독립성 (Worker 장애와 격리)
  ✅ Beat는 중요 컴포넌트

단점:
  ⚠️ Master에 Application Pod 배치 (원칙 위반)
  ⚠️ Master Taint 제거 필요

배치:
  Master (8GB):
    - Control Plane
    - ArgoCD
    - beat: 1 Pod ← 여기!
```

### 옵션 3: 전용 노드 추가

```yaml
노드: Scheduler (t3.small, 2GB) ← 신규
네임스페이스: workers

장점:
  ✅ 완전 격리
  ✅ 안정성 최대
  ✅ 확장 여지 (미래 Scheduler 추가)

단점:
  ❌ 추가 비용 (~$15/월)
  ❌ Beat만을 위한 노드는 비효율

배치:
  Scheduler (2GB):
    - beat: 1 Pod
    - (여유: 1.5GB 낭비)
```

---

## 🎯 최종 권장: 옵션 1 (Worker-Network)

### 이유

```yaml
1. 비용 효율:
   ✅ 추가 노드 불필요
   ✅ Beat 리소스 극히 낮음

2. 충분한 격리:
   ✅ Beat는 Task 발행만 수행
   ✅ 실제 작업은 다른 Worker가 처리
   ✅ Beat 장애 → 새 Task 발행 중단
   ✅ 기존 Task는 계속 처리됨

3. 실용성:
   ✅ 대부분의 프로덕션 환경에서 사용
   ✅ Instagram, Robinhood도 유사 구조
```

### 리소스 계산

```yaml
Worker-Network (t3.medium, 4GB):

  기존:
    - vision-worker (5 Pods): 5 × 256Mi = 1.25GB
    - llm-worker (3 Pods): 3 × 256Mi = 768Mi
    - 소계: 2.02GB
  
  추가:
    - beat (1 Pod): 128Mi
  
  총 사용: 2.15GB
  가용: 4GB
  여유: 1.85GB ✅

결론: 충분히 배치 가능!
```

---

## 📝 구현 계획

### 1. Beat Worker 코드 생성

```python
# workers/beat_worker.py
from celery import Celery
from celery.schedules import crontab

app = Celery("beat")

app.conf.update(
    broker_url="amqp://admin:password@rabbitmq.messaging:5672//",
    result_backend="redis://redis.default:6379/0",
    
    # Beat Schedule
    beat_schedule={
        # 매일 새벽 3시: 오래된 이미지 정리
        "cleanup-old-images": {
            "task": "app.tasks.preprocess.cleanup_old_images",
            "schedule": crontab(hour=3, minute=0),
            "args": (30,),  # 30일 이상
            "options": {
                "queue": "q.preprocess",
            },
        },
        
        # 매시간: 캐시 정리
        "cleanup-cache": {
            "task": "app.tasks.preprocess.cleanup_cache",
            "schedule": crontab(minute=0),  # 매시간
            "options": {
                "queue": "q.preprocess",
            },
        },
        
        # 매일 02:00: 일일 통계
        "daily-stats": {
            "task": "app.tasks.analytics.daily_stats",
            "schedule": crontab(hour=2, minute=0),
            "options": {
                "queue": "q.rag",  # 가벼운 작업
            },
        },
    },
    
    # Persistent Scheduler (재시작 시 상태 복구)
    beat_scheduler="celery.beat:PersistentScheduler",
    beat_schedule_filename="/tmp/celerybeat-schedule",
    
    timezone="Asia/Seoul",
)

if __name__ == "__main__":
    app.start()
```

### 2. Kubernetes Deployment

```yaml
# k8s/workers/beat-deployment.yaml
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: celery-beat
  namespace: workers
  labels:
    app: celery-beat
    component: scheduler
spec:
  replicas: 1  # ⚠️ 반드시 1개만!
  strategy:
    type: Recreate  # ⚠️ RollingUpdate 금지 (중복 실행 방지)
  selector:
    matchLabels:
      app: celery-beat
  template:
    metadata:
      labels:
        app: celery-beat
        component: scheduler
    spec:
      nodeSelector:
        workload: compute-network  # Worker-Network에 배치
      
      # Anti-Affinity: 동일 노드에 Beat 2개 방지
      affinity:
        podAntiAffinity:
          requiredDuringSchedulingIgnoredDuringExecution:
          - labelSelector:
              matchLabels:
                app: celery-beat
            topologyKey: kubernetes.io/hostname
      
      containers:
      - name: beat
        image: ghcr.io/your-org/growbin-backend:latest
        command:
        - celery
        - -A
        - workers.beat_worker
        - beat
        - --loglevel=info
        - --scheduler=celery.beat:PersistentScheduler
        
        env:
        - name: CELERY_BROKER_URL
          value: "amqp://admin:password@rabbitmq.messaging:5672//"
        - name: CELERY_RESULT_BACKEND
          value: "redis://redis.default:6379/0"
        
        resources:
          requests:
            cpu: 50m      # 매우 낮음
            memory: 128Mi
          limits:
            cpu: 200m
            memory: 256Mi
        
        # Liveness Probe (Beat 정상 동작 확인)
        livenessProbe:
          exec:
            command:
            - celery
            - -A
            - workers.beat_worker
            - inspect
            - ping
          initialDelaySeconds: 30
          periodSeconds: 60
          timeoutSeconds: 10
        
        # Volume Mount (Beat Schedule 영구 저장)
        volumeMounts:
        - name: beat-schedule
          mountPath: /tmp
      
      volumes:
      - name: beat-schedule
        emptyDir: {}  # 또는 PersistentVolumeClaim

---
# Service (메트릭 수집용)
apiVersion: v1
kind: Service
metadata:
  name: celery-beat
  namespace: workers
  labels:
    app: celery-beat
spec:
  selector:
    app: celery-beat
  ports:
  - name: metrics
    port: 9090
    targetPort: 9090
  type: ClusterIP
```

### 3. Task 구현

```python
# app/tasks/preprocess.py
from celery import shared_task
from datetime import datetime, timedelta
import boto3

@shared_task(name="app.tasks.preprocess.cleanup_old_images")
def cleanup_old_images(days: int = 30):
    """오래된 이미지 정리 (S3)"""
    s3 = boto3.client("s3")
    bucket = "growbin-waste-images"
    
    cutoff_date = datetime.now() - timedelta(days=days)
    
    deleted = 0
    for obj in s3.list_objects_v2(Bucket=bucket).get("Contents", []):
        if obj["LastModified"] < cutoff_date:
            s3.delete_object(Bucket=bucket, Key=obj["Key"])
            deleted += 1
    
    return f"Deleted {deleted} images older than {days} days"


@shared_task(name="app.tasks.preprocess.cleanup_cache")
def cleanup_cache():
    """Redis 캐시 정리"""
    import redis
    r = redis.from_url("redis://redis.default:6379/1")
    
    # 오래된 캐시 키 정리
    pattern = "image:hash:*"
    keys = r.keys(pattern)
    
    deleted = 0
    for key in keys:
        ttl = r.ttl(key)
        if ttl == -1:  # TTL 없음
            r.delete(key)
            deleted += 1
    
    return f"Deleted {deleted} expired cache keys"


# app/tasks/analytics.py
@shared_task(name="app.tasks.analytics.daily_stats")
def daily_stats():
    """일일 통계 집계"""
    from app.models import WasteAnalysis
    from datetime import date
    
    today = date.today()
    
    # 통계 집계
    stats = WasteAnalysis.objects.filter(
        created_at__date=today
    ).aggregate(
        total=Count("id"),
        by_category=Count("id", distinct="category"),
    )
    
    # 결과 저장 또는 알림
    return f"Daily stats: {stats}"
```

---

## 📊 모니터링

### Prometheus 메트릭

```yaml
# Celery Beat 메트릭
celery_beat_tasks_total:
  설명: Beat가 발행한 Task 수
  라벨: task_name

celery_beat_scheduler_heartbeat:
  설명: Beat 마지막 Heartbeat 시간
  알람: 5분 이상 응답 없으면 Critical

celery_beat_schedule_entries:
  설명: 등록된 스케줄 수
  예상: 3개 (cleanup-images, cleanup-cache, daily-stats)
```

### Grafana Dashboard

```promql
# Beat 정상 동작 확인
up{job="celery-beat"} == 1

# 마지막 Task 발행 시간
time() - celery_beat_last_task_time < 3600  # 1시간 이내

# 예약 작업 실행 횟수
sum(rate(celery_beat_tasks_total[1h])) by (task_name)
```

---

## ✅ 최종 구조 (8 노드 + Beat)

```yaml
총 노드: 8개
추가 비용: $60/월

네임스페이스:
  api:
    - 모든 FastAPI 서비스
    - 노드: API-1, API-2
  
  workers:
    - preprocess-worker (Worker-CPU)
    - rag-worker (Worker-CPU)
    - vision-worker (Worker-Network)
    - llm-worker (Worker-Network)
    - beat ← 여기! (Worker-Network)
  
  data, messaging, monitoring, argocd: 기존 유지

Beat 배치:
  ✅ Worker-Network (4GB)
  ✅ replicas: 1
  ✅ 리소스: 50m CPU, 128Mi RAM
  ✅ 여유 리소스: 1.85GB
```

---

**결론**: Celery Beat를 Worker-Network 노드에 배치하는 것이 가장 효율적입니다! ⏰

