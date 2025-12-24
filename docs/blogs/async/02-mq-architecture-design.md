# 이코에코(Eco²) 비동기 전환 #2: MQ 구현 상세

> 이전 글: [비동기 전환 #1: MQ 적용 가능 영역 분석](./01-mq-optimization-opportunities.md)

---

## 개요

본 문서는 RabbitMQ + Celery 기반 비동기 메시징 인프라의 **구현 상세**를 다룬다.

- **기술 선정 근거**: [비동기 전환 #0: RabbitMQ + Celery 아키텍처 설계](./00-rabbitmq-celery-architecture.md)
- **적용 영역 분석**: [비동기 전환 #1: MQ 적용 가능 영역 분석](./01-mq-optimization-opportunities.md)

이 글에서는 7개 API 서비스로 구성된 Eco² 백엔드의 **Kubernetes 배포, 매니페스트, 모니터링** 구현을 공유한다.

### 배경

- **도입 전 상태**: 도메인 간 통신이 동기식 gRPC/HTTP로만 구현
- **문제점**: 
  - Scan → Character gRPC 호출 시 Character 장애가 Scan 전체 실패로 전파
  - AI 파이프라인 평균 ~10초 블로킹으로 사용자 이탈 (P99 12~25초)
  - Circuit Breaker Open 시 리워드 영구 손실
- **목표**: 비동기 메시징 기반 느슨한 결합, 실패 복구, 진행 상황 추적

---

## 1. 요구사항

### 1.1 기능 요구사항

| 요구사항 | 설명 | 우선순위 |
|---------|------|----------|
| **비동기 분류** | AI 파이프라인 백그라운드 처리 | P0 |
| **진행 상황 추적** | 프론트엔드 UI와 연동된 실시간 프로그레스 | P0 |
| **리워드 큐잉** | Character 서비스 장애 시 보상 지급 보류 및 복구 | P0 |
| **DLQ 관리** | 최종 실패 메시지 보관 및 수동 재처리 | P1 |
| **도메인 간 이벤트** | Scan 완료 → Character 리워드 이벤트 발행 | P2 |

### 1.2 비기능 요구사항

| 항목 | 목표 | 비고 |
|------|------|------|
| **가용성** | 99.9% | MQ 장애가 서비스에 영향 없어야 함 |
| **메시지 지연** | < 100ms | 발행 → Consumer 수신 |
| **재시도** | 3회 + Exponential Backoff | 최종 실패 시 DLQ |
| **저장 용량** | 10GB (7일) | 개발 환경 기준 |
| **리소스 격리** | Data 노드 배치 | API 서비스와 분리 |

---

## 2. 기술 선택

### 2.1 RabbitMQ vs Kafka 비교

#### 현재 워크로드 분석

```
현재 트래픽:
- Scan API: ~100 req/day (개발 환경)
- Character Reward: ~50 events/day
- 메시지 수명: 24시간 (결과 조회 후 삭제)

예상 트래픽 (프로덕션):
- Scan API: ~10,000 req/day
- Character Reward: ~5,000 events/day
```

#### 비교표

| 항목 | RabbitMQ + Celery | Kafka |
|------|-------------------|-------|
| **패턴** | Task Queue (Command) | Event Streaming (Log) |
| **메시지 수명** | 처리 후 삭제 (적합) | 영구 보관 (과다) |
| **재시도 + DLQ** | ✅ 네이티브 지원 | ⚠️ 수동 구현 필요 |
| **Task Chain** | ✅ Celery Canvas | ❌ Stream 조합 복잡 |
| **운영 복잡도** | 낮음 | 높음 (ZK/KRaft) |
| **리소스** | ~1GB RAM | ~3GB+ RAM |
| **학습 곡선** | 낮음 (Python 친화) | 높음 |

### 2.2 결론: **RabbitMQ + Celery 선택**

#### 🚫 Kafka 반려 이유

**1. 현재 워크로드에 과도한 인프라**

```
RabbitMQ 리소스:
├── Broker: 1GB RAM × 3 = 3GB
└── 총: 3GB

Kafka 리소스:
├── Broker: 2GB RAM × 3 = 6GB
├── ZooKeeper: 1GB × 3 = 3GB (또는 KRaft 컨트롤러)
└── 총: 9GB+
```

**2. Command 패턴 vs Event Log**

현재 요구사항은 **"이 이미지를 분류해줘"** (Command)이지, **"모든 분류 이벤트를 영구 보관해줘"** (Event Log)가 아님.

```
적합한 패턴:
├── Command: "classify this image" → RabbitMQ Task Queue
├── Event Log: "user classified image X" → Kafka (향후 분석용)
└── 현재 필요: Command
```

**3. Celery 통합**

Python 생태계에서 Celery + RabbitMQ는 사실상 표준:

```python
# 직관적인 Task 정의
@celery_app.task(bind=True, max_retries=3)
def vision_scan(self, task_id: str, image_url: str):
    # ...
    raise self.retry(exc=exc, countdown=2 ** self.request.retries)

# Chain, Group, Chord 지원
workflow = chain(vision_scan.s(), rule_match.s(), answer_gen.s())
```

### 2.3 Kafka가 필요한 시점 (미래)

| 시점 | 요구사항 | Kafka 필요성 |
|------|----------|-------------|
| **Event Sourcing** | 모든 분류 이벤트 영구 보관 | ✅ Log Compaction |
| **CDC** | DB 변경 스트리밍 (Debezium) | ✅ Connect 통합 |
| **분석 파이프라인** | 실시간 집계/ML 학습 데이터 | ✅ Stream Processing |
| **멀티 Consumer** | 여러 서비스가 동일 이벤트 구독 | ✅ Consumer Group |

---

## 3. Kubernetes 배포 전략

### 3.1 Operator vs Helm 비교

| 항목 | RabbitMQ Cluster Operator | Helm Chart (Bitnami) |
|------|---------------------------|---------------------|
| **라이프사이클** | ✅ 자동 (scaling, upgrade, recovery) | ❌ 수동 |
| **선언적 토폴로지** | ✅ Queue/Exchange CRD | ❌ init script |
| **장기 지원** | ✅ 공식 유지보수 | ❌ Bitnami deprecated (2025.09) |
| **TLS/인증** | ✅ 자동 구성 | ⚠️ 수동 |
| **프로덕션 권장** | ✅ | ❌ |

### 3.2 결론: **Operator 선택**

- RabbitMQ 공식 문서에서 프로덕션 환경에 Operator 강력 권장
- Bitnami Helm Chart 2025년 9월 deprecated 예정
- Queue, Exchange, Binding을 Kubernetes CRD로 선언적 관리

---

## 4. 아키텍처 설계

### 4.1 전체 아키텍처

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                              Frontend (React)                                 │
├──────────────────────────────────────────────────────────────────────────────┤
│  1. POST /classify/async  →  task_id 즉시 반환 (202 Accepted)                │
│  2. GET /task/{id}/status ←  Polling (500ms) 또는 SSE                        │
│  3. UI Progress Bar       :  확인 → 분석 → 배출방법                           │
└──────────────────────────────────────────────────────────────────────────────┘
                                       │
                                       ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│                           Scan API (FastAPI)                                  │
├──────────────────────────────────────────────────────────────────────────────┤
│  - task_id 생성 (UUID)                                                        │
│  - Redis 초기 상태: { status: "queued", step: "pending", progress: 0 }       │
│  - Celery Task Chain 발행 → 즉시 202 Accepted                                 │
└──────────────────────────────────────────────────────────────────────────────┘
                                       │
                                       ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│                         RabbitMQ Cluster (3 nodes)                            │
├──────────────────────────────────────────────────────────────────────────────┤
│                                                                               │
│   ┌─────────────────────────────────────────────────────────────────────┐    │
│   │                    Exchanges                                         │    │
│   │  ┌───────────────┐  ┌───────────────┐  ┌───────────────┐            │    │
│   │  │ scan.direct   │  │ reward.direct │  │ dlx (DLX)     │            │    │
│   │  └───────┬───────┘  └───────┬───────┘  └───────┬───────┘            │    │
│   └──────────┼──────────────────┼──────────────────┼─────────────────────┘    │
│              │                  │                  │                          │
│   ┌──────────┼──────────────────┼──────────────────┼─────────────────────┐    │
│   │          ▼                  ▼                  ▼          Queues     │    │
│   │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐               │    │
│   │  │scan.vision   │  │scan.reward   │  │scan.reward   │               │    │
│   │  │scan.rule     │  │              │  │.dlq          │               │    │
│   │  │scan.answer   │  │ DLX → dlq    │  │(Dead Letter) │               │    │
│   │  └──────────────┘  └──────────────┘  └──────────────┘               │    │
│   └─────────────────────────────────────────────────────────────────────┘    │
│                                                                               │
└──────────────────────────────────────────────────────────────────────────────┘
                                       │
                                       ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│                         Celery Workers                                        │
├──────────────────────────────────────────────────────────────────────────────┤
│                                                                               │
│   ┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐          │
│   │   scan-worker   │    │   scan-worker   │    │  reward-worker  │          │
│   │   (replicas: 2) │    │   (replicas: 2) │    │  (replicas: 1)  │          │
│   │                 │    │                 │    │                 │          │
│   │  ┌───────────┐  │    │  ┌───────────┐  │    │  ┌───────────┐  │          │
│   │  │vision_scan│──┼────┼─▶│rule_match │──┼────┼─▶│answer_gen │  │          │
│   │  └───────────┘  │    │  └───────────┘  │    │  └─────┬─────┘  │          │
│   │      ~3.5s      │    │      ~0.01s     │    │    ~7s   │      │          │
│   └─────────────────┘    └─────────────────┘    │          │      │          │
│                                                 │          ▼      │          │
│                                                 │  ┌───────────┐  │          │
│                                                 │  │reward_grant│ │          │
│                                                 │  └───────────┘  │          │
│                                                 └─────────────────┘          │
│                                                                               │
│   ┌─────────────────────────────────────────────────────────────────────┐    │
│   │                     Redis (상태 저장소)                              │    │
│   │  task:{id} → { status, step, progress, partial_result, result }     │    │
│   │  TTL: 3600s (1시간)                                                 │    │
│   └─────────────────────────────────────────────────────────────────────┘    │
│                                                                               │
└──────────────────────────────────────────────────────────────────────────────┘
                                       │
                                       ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│                         Character Service (gRPC)                              │
├──────────────────────────────────────────────────────────────────────────────┤
│  - reward_grant Task에서 gRPC 호출                                           │
│  - 실패 시 Celery 재시도 (3회, Exponential Backoff)                          │
│  - 최종 실패 시 DLQ 이동                                                     │
└──────────────────────────────────────────────────────────────────────────────┘
```

### 4.2 도메인 간 통신 패턴

#### AS-IS: 동기식 gRPC 직접 호출

```
┌──────────────┐     gRPC (동기)      ┌──────────────┐
│   Scan API   │ ──────────────────▶ │  Character   │
│              │                      │   Service    │
│  (블로킹)    │ ◀────────────────── │              │
└──────────────┘     Response         └──────────────┘
      │
      ▼ 문제점
- Character 장애 시 Scan 전체 실패
- Circuit Breaker Open 시 리워드 손실
- 7.5초 동안 HTTP 연결 유지
```

#### TO-BE: MQ 기반 비동기 통신

```
┌──────────────┐     Task 발행       ┌──────────────┐     gRPC      ┌──────────────┐
│   Scan API   │ ──────────────────▶ │   RabbitMQ   │ ◀──────────▶ │  Character   │
│              │                      │              │              │   Service    │
│  (즉시 응답) │                      │  reward.q    │              │              │
└──────────────┘                      └──────────────┘              └──────────────┘
      │                                     │
      │                                     ▼ 실패 시
      │                              ┌──────────────┐
      │                              │  reward.dlq  │
      │                              │ (Dead Letter)│
      │                              └──────────────┘
      ▼ 장점
- Scan API 즉시 응답 (202 Accepted)
- Character 장애 시 메시지 보류
- 자동 재시도 + DLQ 복구
```

### 4.3 UI 매핑

| 프론트 UI | 파이프라인 단계 | Celery Task | Redis step | progress |
|-----------|----------------|-------------|------------|----------|
| **확인** | Vision (GPT) | `vision_scan` | `scan` | 0-33% |
| **분석** | Rule-based RAG | `rule_match` | `analyze` | 33-66% |
| **배출방법** | Answer (GPT) | `answer_gen` | `answer` | 66-99% |
| **완료** | - | - | `complete` | 100% |

---

## 5. App-of-Apps Sync Wave 설계

### 5.1 기존 인프라 순서

```yaml
# clusters/dev/apps/
00-crds.yaml              # CRDs
02-namespaces.yaml        # Namespaces
05-istio.yaml             # Service Mesh
10-secrets-operator.yaml  # External Secrets Operator
20-monitoring-operator.yaml # Prometheus Operator
27-postgresql.yaml        # PostgreSQL (Helm)
28-redis-operator.yaml    # Redis (Helm)
```

### 5.2 RabbitMQ + Celery 추가

```yaml
# 신규 추가
29-rabbitmq-operator.yaml         # RabbitMQ Cluster Operator (CRD + Controller)
30-rabbitmq-topology-operator.yaml # Messaging Topology Operator (선택)
31-rabbitmq-cluster.yaml          # RabbitmqCluster CR
32-rabbitmq-topology.yaml         # Queue, Exchange, Binding CRs (선택)

# API 서비스 (기존)
40-apis-appset.yaml              # scan-api, scan-worker 포함
```

### 5.3 Sync Wave 의존성

```
┌─────────────────────────────────────────────────────────────────┐
│                      Infrastructure Layer                        │
├─────────────────────────────────────────────────────────────────┤
│  wave 27: PostgreSQL                                            │
│  wave 28: Redis                                                 │
│  wave 29: RabbitMQ Cluster Operator ─────┐                      │
│  wave 30: RabbitMQ Topology Operator ────┤                      │
│  wave 31: RabbitmqCluster CR ────────────┤                      │
│  wave 32: Queue/Exchange CRs ────────────┘                      │
├─────────────────────────────────────────────────────────────────┤
│                       Application Layer                          │
├─────────────────────────────────────────────────────────────────┤
│  wave 40: scan-api (depends: PostgreSQL, Redis, RabbitMQ)       │
│           scan-worker (depends: Redis, RabbitMQ)                │
│           character-api                                          │
│           ...                                                    │
└─────────────────────────────────────────────────────────────────┘
```

---

## 6. 디렉토리 구조

```
backend/
├── clusters/
│   └── dev/
│       └── apps/
│           ├── 29-rabbitmq-operator.yaml      # Cluster Operator
│           ├── 30-rabbitmq-topology-operator.yaml  # Topology Operator
│           ├── 31-rabbitmq-cluster.yaml       # RabbitmqCluster CR
│           └── 32-rabbitmq-topology.yaml      # Vhost, Queue, Exchange, Binding
│
├── workloads/
│   ├── rabbitmq/
│   │   ├── base/
│   │   │   ├── kustomization.yaml
│   │   │   ├── namespace.yaml
│   │   │   ├── cluster.yaml                   # RabbitmqCluster
│   │   │   └── topology/
│   │   │       ├── vhost.yaml                 # celery vhost
│   │   │       ├── queues.yaml                # scan.*, reward.*, dlq
│   │   │       ├── exchanges.yaml             # scan.direct, reward.direct, dlx
│   │   │       └── bindings.yaml              # Exchange → Queue bindings
│   │   ├── dev/
│   │   │   └── kustomization.yaml             # replicas: 1 (개발)
│   │   └── prod/
│   │       └── kustomization.yaml             # replicas: 3 (운영)
│   │
│   ├── network-policies/
│   │   └── rabbitmq/
│   │       ├── allow-scan-to-rabbitmq.yaml
│   │       ├── allow-character-to-rabbitmq.yaml
│   │       └── kustomization.yaml
│   │
│   └── domains/
│       └── scan/
│           ├── base/
│           │   ├── deployment-api.yaml
│           │   ├── deployment-worker.yaml     # 🆕 Celery Worker
│           │   └── configmap.yaml             # CELERY_BROKER_URL 추가
│           └── dev/
│               └── kustomization.yaml
│
└── domains/
    ├── _shared/
    │   └── taskqueue/                         # 🆕 공유 Celery 모듈
    │       ├── __init__.py
    │       ├── app.py                         # Celery App
    │       ├── config.py                      # CelerySettings
    │       └── state.py                       # TaskStateManager (Redis)
    │
    └── scan/
        ├── tasks/                             # 🆕 Celery Tasks
        │   ├── __init__.py
        │   ├── classification.py              # vision_scan, rule_match, answer_gen
        │   └── reward.py                      # reward_grant
        └── celery_worker.py                   # 🆕 Worker 엔트리포인트
```

---

## 7. 매니페스트 상세

### 7.1 RabbitMQ Cluster Operator

```yaml
# clusters/dev/apps/29-rabbitmq-operator.yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: dev-rabbitmq-operator
  namespace: argocd
  annotations:
    argocd.argoproj.io/sync-wave: "29"
  labels:
    env: dev
    tier: infra
spec:
  project: default
  source:
    repoURL: https://github.com/rabbitmq/cluster-operator
    path: config/default
    targetRevision: v2.11.0
  destination:
    server: https://kubernetes.default.svc
    namespace: rabbitmq-system
  syncPolicy:
    automated:
      prune: true
      selfHeal: true
    syncOptions:
      - CreateNamespace=true
      - ServerSideApply=true
```

### 7.2 RabbitmqCluster CR

```yaml
# workloads/rabbitmq/base/cluster.yaml
apiVersion: rabbitmq.com/v1beta1
kind: RabbitmqCluster
metadata:
  name: eco2-rabbitmq
  namespace: rabbitmq
spec:
  replicas: 3  # HA 구성
  
  image: rabbitmq:3.13-management
  
  resources:
    requests:
      cpu: 500m
      memory: 1Gi
    limits:
      cpu: 1000m
      memory: 2Gi
  
  persistence:
    storageClassName: gp3
    storage: 10Gi
  
  rabbitmq:
    additionalConfig: |
      # 메모리 관리
      vm_memory_high_watermark.relative = 0.8
      disk_free_limit.relative = 1.5
      
      # 클러스터 파티션 처리
      cluster_partition_handling = pause_minority
      queue_master_locator = min-masters
      
      # Celery 최적화
      consumer_timeout = 1800000  # 30분
      
    additionalPlugins:
      - rabbitmq_prometheus
      - rabbitmq_management
  
  affinity:
    nodeAffinity:
      requiredDuringSchedulingIgnoredDuringExecution:
        nodeSelectorTerms:
          - matchExpressions:
              - key: domain
                operator: In
                values:
                  - data
  
  tolerations:
    - key: domain
      operator: Equal
      value: data
      effect: NoSchedule
```

### 7.3 Topology CRs (Queue, Exchange, DLQ)

```yaml
# workloads/rabbitmq/base/topology/vhost.yaml
apiVersion: rabbitmq.com/v1beta1
kind: Vhost
metadata:
  name: celery-vhost
  namespace: rabbitmq
spec:
  name: celery
  rabbitmqClusterReference:
    name: eco2-rabbitmq

---
# workloads/rabbitmq/base/topology/exchanges.yaml
apiVersion: rabbitmq.com/v1beta1
kind: Exchange
metadata:
  name: scan-exchange
  namespace: rabbitmq
spec:
  name: scan.direct
  vhost: celery
  type: direct
  durable: true
  autoDelete: false
  rabbitmqClusterReference:
    name: eco2-rabbitmq

---
apiVersion: rabbitmq.com/v1beta1
kind: Exchange
metadata:
  name: dlx-exchange
  namespace: rabbitmq
spec:
  name: dlx
  vhost: celery
  type: direct
  durable: true
  autoDelete: false
  rabbitmqClusterReference:
    name: eco2-rabbitmq

---
# workloads/rabbitmq/base/topology/queues.yaml
apiVersion: rabbitmq.com/v1beta1
kind: Queue
metadata:
  name: scan-vision-queue
  namespace: rabbitmq
spec:
  name: scan.vision
  vhost: celery
  type: quorum
  durable: true
  autoDelete: false
  rabbitmqClusterReference:
    name: eco2-rabbitmq

---
apiVersion: rabbitmq.com/v1beta1
kind: Queue
metadata:
  name: scan-reward-queue
  namespace: rabbitmq
spec:
  name: scan.reward
  vhost: celery
  type: quorum
  durable: true
  autoDelete: false
  arguments:
    x-dead-letter-exchange: dlx
    x-dead-letter-routing-key: reward.dlq
  rabbitmqClusterReference:
    name: eco2-rabbitmq

---
apiVersion: rabbitmq.com/v1beta1
kind: Queue
metadata:
  name: reward-dlq
  namespace: rabbitmq
spec:
  name: reward.dlq
  vhost: celery
  type: quorum
  durable: true
  autoDelete: false
  rabbitmqClusterReference:
    name: eco2-rabbitmq
```

### 7.4 Celery Worker Deployment

```yaml
# workloads/domains/scan/base/deployment-worker.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: scan-worker
  namespace: scan
spec:
  replicas: 2
  selector:
    matchLabels:
      app: scan-worker
  template:
    metadata:
      labels:
        app: scan-worker
    spec:
      containers:
        - name: worker
          image: mng990/eco2:scan-api-latest
          command: ["celery", "-A", "domains.scan.celery_worker", "worker", "-l", "info", "-Q", "scan.vision,scan.rule,scan.answer,scan.reward"]
          envFrom:
            - configMapRef:
                name: scan-config
            - secretRef:
                name: scan-secret
          env:
            - name: CELERY_BROKER_URL
              valueFrom:
                secretKeyRef:
                  name: rabbitmq-secret
                  key: broker-url
            - name: CELERY_RESULT_BACKEND
              value: "redis://dev-redis-master.redis:6379/1"
          resources:
            requests:
              cpu: 500m
              memory: 1Gi
            limits:
              cpu: 2000m
              memory: 4Gi
```

---

## 8. 모니터링

### 8.1 Prometheus Metrics

RabbitMQ Prometheus Plugin + ServiceMonitor:

```yaml
# workloads/rabbitmq/base/servicemonitor.yaml
apiVersion: monitoring.coreos.com/v1
kind: ServiceMonitor
metadata:
  name: rabbitmq-metrics
  namespace: rabbitmq
  labels:
    release: prometheus
spec:
  selector:
    matchLabels:
      app.kubernetes.io/name: eco2-rabbitmq
  endpoints:
    - port: prometheus
      interval: 30s
      path: /metrics
```

### 8.2 핵심 메트릭

| 메트릭 | 설명 | 알림 임계값 |
|--------|------|------------|
| `rabbitmq_queue_messages` | 대기 메시지 수 | > 1000 |
| `rabbitmq_queue_messages_unacked` | 미확인 메시지 | > 100 |
| `rabbitmq_queue_consumers` | Consumer 수 | = 0 |
| `celery_worker_tasks_active` | 활성 태스크 | > 50 |
| `celery_task_failed_total` | 실패 태스크 | > 10/min |

### 8.3 Grafana 대시보드

```
┌─────────────────────────────────────────────────────────────────┐
│                RabbitMQ Cluster Overview                         │
├─────────────────────────────────────────────────────────────────┤
│  ┌────────────────┐  ┌────────────────┐  ┌────────────────┐     │
│  │ Messages Rate  │  │ Queue Depth    │  │ Consumer Count │     │
│  │    150/min     │  │      12        │  │       6        │     │
│  └────────────────┘  └────────────────┘  └────────────────┘     │
│                                                                  │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │                    Queue Status                             │ │
│  │  scan.vision:  ████████░░ 80% (idle)                       │ │
│  │  scan.reward:  ████░░░░░░ 40% (processing)                 │ │
│  │  reward.dlq:   ░░░░░░░░░░  0% (empty)                      │ │
│  └────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
```

---

## 9. 점진적 확장 계획

### Phase 1 (현재): Scan 도메인 비동기화

```
┌─────────────────────────────────────────────────────────────────┐
│                      Phase 1 Scope                               │
├─────────────────────────────────────────────────────────────────┤
│  ✅ RabbitMQ Cluster Operator 배포                              │
│  ✅ RabbitmqCluster CR (replicas: 1, 개발 환경)                 │
│  ✅ Scan API 비동기 분류 엔드포인트                              │
│  ✅ Redis 상태 관리 (TaskStateManager)                          │
│  ✅ Celery Worker (scan-worker)                                 │
│  ✅ Reward DLQ 구성                                             │
└─────────────────────────────────────────────────────────────────┘
```

### Phase 2: Command-Event Separation (Kafka + RabbitMQ 병행)

> **핵심 원칙**: RabbitMQ는 Task Queue(Command)로, Kafka는 Event Bus(Event)로 역할 분리

```
┌─────────────────────────────────────────────────────────────────┐
│                      Phase 2 Scope                               │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  Command (RabbitMQ + Celery)       Event (Kafka + CDC)          │
│  ────────────────────────────      ──────────────────           │
│                                                                  │
│  "이 이미지를 분류해"              "스캔이 완료되었다"           │
│  ProcessImage Task                 ScanCompleted Event           │
│                                                                  │
│  • 하나의 Worker가 처리            • 여러 Consumer가 구독       │
│  • 처리 후 삭제                    • 영구 보존 (Replay)         │
│  • Retry/DLQ 내장                  • Offset 기반 재처리         │
│                                                                  │
│  구현 항목:                                                      │
│  □ Strimzi Kafka Operator 배포                                  │
│  □ Event Store + Outbox 테이블 설계                             │
│  □ Debezium CDC (Outbox → Kafka)                                │
│  □ Character Consumer (ScanCompleted → 보상 지급)               │
│  □ My Consumer (Projection 업데이트)                            │
│  □ CloudEvents 형식 + Schema Evolution                          │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

**참고 Foundations**:
- [01. The Log](./foundations/01-the-log-jay-kreps.md) - Kafka 설계 철학
- [08. Transactional Outbox](./foundations/08-transactional-outbox.md) - At-Least-Once 보장
- [09. Debezium CDC](./foundations/09-debezium-outbox-event-router.md) - WAL Capture

---

## 10. 핵심 설계 결정 (ADR)

### ADR-001: RabbitMQ Operator 사용

**결정**: Helm Chart 대신 RabbitMQ Cluster Operator 사용

**이유**:
1. Bitnami Helm Chart 2025.09 deprecated 예정
2. Queue, Exchange를 CRD로 선언적 관리
3. Rolling Upgrade, 자동 복구 기능
4. TLS/인증 자동 구성

**트레이드오프**:
- Operator Pod 추가 리소스 (~200MB)
- CRD 학습 곡선

### ADR-002: Celery + RabbitMQ 선택

**결정**: Kafka 대신 RabbitMQ + Celery 사용

**이유**:
1. 현재 워크로드가 Command 패턴 (Task Queue)
2. Celery의 Task Chain, Retry, DLQ 네이티브 지원
3. 리소스 효율성 (RabbitMQ ~1GB vs Kafka ~3GB+)
4. Python 생태계 통합

**트레이드오프**:
- Event Sourcing 미지원 → Phase 3에서 Kafka 도입

### ADR-003: Redis 기반 상태 관리

**결정**: Celery Result Backend 외 별도 Redis 상태 저장소 운영

**이유**:
1. 부분 결과(partial_result) 저장 필요
2. 프론트엔드 Polling 지원
3. 1시간 TTL로 자동 정리

**트레이드오프**:
- Redis 의존성 증가
- 상태 동기화 복잡도

---

## 11. 참고 자료

### 외부 문서
- [RabbitMQ Cluster Operator 공식 문서](https://www.rabbitmq.com/kubernetes/operator/operator-overview)
- [Messaging Topology Operator](https://www.rabbitmq.com/kubernetes/operator/using-topology-operator)
- [Celery Best Practices](https://docs.celeryq.dev/en/stable/userguide/tasks.html)
- [RabbitMQ DLQ Pattern](https://www.rabbitmq.com/dlx.html)

### 내부 블로그 시리즈
- [비동기 전환 #0: RabbitMQ + Celery 아키텍처 설계](./00-rabbitmq-celery-architecture.md)
- [비동기 전환 #1: MQ 적용 가능 영역 분석](./01-mq-optimization-opportunities.md)
- [이코에코 Observability #0: 로깅 파이프라인 아키텍처 설계](https://rooftopsnow.tistory.com/32)

### Foundation 문서 (이론적 기반)
- [11. AMQP/RabbitMQ](./foundations/11-amqp-rabbitmq.md) - Exchange, Queue, Routing
- [12. Celery](./foundations/12-celery-distributed-task-queue.md) - Task Queue, Canvas
- [05. Enterprise Integration Patterns](./foundations/05-enterprise-integration-patterns.md) - 메시징 패턴
- [07. Sagas](./foundations/07-sagas-garcia-molina.md) - 보상 트랜잭션
- [전체 인덱스](./foundations/00-index.md)

---

## 변경 이력

| 날짜 | 버전 | 변경 내용 |
|------|------|----------|
| 2025-12-21 | 1.0 | 초안 작성 (아키텍처 설계, Sync Wave, 매니페스트) |
| 2025-12-21 | 1.1 | 역할 정리: 구현 상세 중심으로 재구성, 00번과 역할 분리 |
