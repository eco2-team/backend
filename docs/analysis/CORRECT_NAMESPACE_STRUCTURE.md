# 🏗️ 올바른 네임스페이스 구조 (실제 클러스터 기반)

## 📊 실제 클러스터 구성

### Worker 노드 (실제)

```yaml
k8s-worker-1:
  역할: Application Worker (Sync)
  타입: t3.medium (2 vCPU, 4GB RAM)
  라벨: workload=application
  워크로드:
    - FastAPI Pods (REST API)
    - 동기 처리 서비스

k8s-worker-2:
  역할: Async Worker (비동기)
  타입: t3.medium (2 vCPU, 4GB RAM)
  라벨: workload=async-workers
  워크로드:
    - Celery Workers (AI 작업)
    - 비동기 처리 작업
```

---

## 🎯 올바른 네임스페이스 구조

### 최종 결정

```yaml
# Application Layer
api:                    # ✅ REST API 서비스 (Worker-1)
  워크로드:
    - waste-api
    - users-api
    - auth-api
    - recycling-api
    - locations-api
  노드: Worker-1 (workload=application)

async:                  # ✅ Async Workers (Worker-2)
  워크로드:
    - preprocess-worker
    - vision-worker
    - rag-worker
    - llm-worker
  노드: Worker-2 (workload=async-workers)

# Infrastructure Layer
data:                   # 데이터 스토어
  워크로드:
    - postgresql (전용 노드)
    - redis (전용 노드)

messaging:              # 메시지 브로커 (기존 유지)
  워크로드:
    - rabbitmq (전용 노드)

# Platform Layer
monitoring:             # 모니터링 (기존 유지)
  워크로드:
    - prometheus
    - grafana

argocd:                 # GitOps (기존 유지)
  워크로드:
    - argocd-server
```

---

## 🔄 수정된 이유

### ❌ 이전 제안 (잘못됨)

```yaml
api:
  rest:    # REST API
  async:   # Async Workers ← 하위 디렉토리
```

**문제**: `async`가 `api`의 하위로 표현됨

### ✅ 올바른 구조

```yaml
api:      # Sync API (Worker-1)
async:    # Async Workers (Worker-2)
```

**이유**:
1. **물리적 분리**: Worker-1 vs Worker-2
2. **워크로드 특성**: Sync vs Async
3. **네임스페이스 분리**: 독립적 관리

---

## 📝 최종 네임스페이스 설계

### 1. `api` Namespace

```yaml
용도: REST API 서비스 (동기)
노드: Worker-1 (workload=application)
Pod Selector: workload=application

서비스:
  - waste-api (3 replicas)
  - users-api (2 replicas)
  - auth-api (2 replicas)
  - recycling-api (2 replicas)
  - locations-api (2 replicas)

특징:
  - FastAPI
  - 동기 HTTP 요청/응답
  - Ingress 연결
  - HPA 적용

리소스:
  가용: 4GB RAM (Worker-1)
  요청: 2-3GB (예상)
  상태: ✅ 충분
```

### 2. `async` Namespace

```yaml
용도: 비동기 작업 처리 (Celery Workers)
노드: Worker-2 (workload=async-workers)
Pod Selector: workload=async-workers

워커:
  - preprocess-worker (3 replicas)
  - vision-worker (5 replicas, HPA)
  - rag-worker (2 replicas)
  - llm-worker (3 replicas)

특징:
  - Celery + RabbitMQ
  - 비동기 작업 (AI 처리)
  - 외부 API 연동 (OpenAI)
  - HPA 적용 (vision-worker)

리소스:
  가용: 4GB RAM (Worker-2)
  요청: 3-3.5GB (예상)
  상태: ✅ 충분
```

### 3. `data` Namespace

```yaml
용도: 데이터 스토어
노드: 전용 노드

서비스:
  - postgresql (k8s-postgresql 전용)
  - redis (k8s-redis 전용)

특징:
  - StatefulSet
  - PersistentVolumeClaim
  - 전용 노드 격리
```

### 4. `messaging` Namespace (기존 유지)

```yaml
용도: 메시지 브로커
노드: k8s-rabbitmq (전용)

서비스:
  - rabbitmq

특징:
  - RabbitMQ Cluster Operator
  - 전용 노드 격리
```

### 5. `monitoring` Namespace (기존 유지)

```yaml
용도: 모니터링
노드: k8s-monitoring (전용)

서비스:
  - prometheus
  - grafana

특징:
  - t3.large (8GB RAM)
  - 전용 노드
```

### 6. `argocd` Namespace (기존 유지)

```yaml
용도: GitOps
노드: Master

서비스:
  - argocd-server
```

---

## 🏗️ Helm Chart 구조

### 디렉토리 구조

```
charts/growbin-backend/
├── Chart.yaml
├── values.yaml
├── values-dev.yaml
├── values-prod.yaml
└── templates/
    ├── _helpers.tpl
    │
    ├── api/            # ✅ Sync API (Worker-1)
    │   ├── waste-deployment.yaml
    │   ├── users-deployment.yaml
    │   ├── auth-deployment.yaml
    │   ├── recycling-deployment.yaml
    │   └── locations-deployment.yaml
    │
    ├── async/          # ✅ Async Workers (Worker-2)
    │   ├── preprocess-deployment.yaml
    │   ├── vision-deployment.yaml
    │   ├── rag-deployment.yaml
    │   ├── llm-deployment.yaml
    │   └── hpa.yaml
    │
    ├── data/
    │   ├── postgresql-statefulset.yaml
    │   └── redis-statefulset.yaml
    │
    ├── ingress/
    │   └── api-ingress.yaml
    │
    └── monitoring/
        ├── servicemonitor.yaml
        └── prometheusrule.yaml
```

---

## 📝 values.yaml

```yaml
# charts/growbin-backend/values.yaml

# Namespace 설정
namespaces:
  api: api              # ✅ Sync API
  async: async          # ✅ Async Workers
  data: data
  messaging: messaging

# Global 설정
global:
  image:
    registry: ghcr.io
    repository: your-org/growbin-backend
    tag: latest

# API Services (Sync)
api:
  namespace: api
  nodeSelector:
    workload: application  # ⬅️ Worker-1
  
  waste:
    enabled: true
    replicas: 3
    port: 8000
    path: /api/v1/waste
    resources:
      requests: { cpu: 200m, memory: 256Mi }
      limits: { cpu: 1000m, memory: 512Mi }
  
  users:
    enabled: true
    replicas: 2
    # ...
  
  auth:
    enabled: true
    replicas: 2
    # ...

# Async Workers
async:
  namespace: async
  nodeSelector:
    workload: async-workers  # ⬹️ Worker-2
  
  preprocess:
    enabled: true
    replicas: 3
    queue: q.preprocess
    pool: processes
    concurrency: 8
    resources:
      requests: { cpu: 300m, memory: 256Mi }
      limits: { cpu: 1000m, memory: 512Mi }
  
  vision:
    enabled: true
    replicas: 5
    queue: q.vision
    pool: gevent
    concurrency: 20
    resources:
      requests: { cpu: 100m, memory: 256Mi }
      limits: { cpu: 500m, memory: 512Mi }
    autoscaling:
      enabled: true
      minReplicas: 5
      maxReplicas: 8
  
  rag:
    enabled: true
    replicas: 2
    # ...
  
  llm:
    enabled: true
    replicas: 3
    # ...

# Data Stores
data:
  namespace: data
  
  postgresql:
    enabled: true
    nodeSelector:
      workload: database  # k8s-postgresql 전용
    # ...
  
  redis:
    enabled: true
    nodeSelector:
      workload: cache  # k8s-redis 전용
    # ...

# Messaging
messaging:
  namespace: messaging
  rabbitmq:
    enabled: true
    nodeSelector:
      workload: message-queue  # k8s-rabbitmq 전용
```

---

## 🎯 배포 예시

### 템플릿 예시

#### API Service

```yaml
# charts/growbin-backend/templates/api/waste-deployment.yaml
{{- if .Values.api.waste.enabled }}
apiVersion: apps/v1
kind: Deployment
metadata:
  name: {{ include "growbin-backend.fullname" . }}-api-waste
  namespace: {{ .Values.namespaces.api }}  # ⬅️ "api" namespace
  labels:
    app.kubernetes.io/component: api-sync
    app.kubernetes.io/name: waste
spec:
  replicas: {{ .Values.api.waste.replicas }}
  template:
    spec:
      {{- with .Values.api.nodeSelector }}
      nodeSelector:
        {{- toYaml . | nindent 8 }}  # workload=application
      {{- end }}
      containers:
      - name: api
        image: "{{ .Values.global.image.registry }}/{{ .Values.global.image.repository }}:{{ .Values.global.image.tag }}"
        ports:
        - containerPort: {{ .Values.api.waste.port }}
        # ...
{{- end }}
```

#### Async Worker

```yaml
# charts/growbin-backend/templates/async/vision-deployment.yaml
{{- if .Values.async.vision.enabled }}
apiVersion: apps/v1
kind: Deployment
metadata:
  name: {{ include "growbin-backend.fullname" . }}-async-vision
  namespace: {{ .Values.namespaces.async }}  # ⬅️ "async" namespace
  labels:
    app.kubernetes.io/component: async-worker
    app.kubernetes.io/name: vision
spec:
  replicas: {{ .Values.async.vision.replicas }}
  template:
    spec:
      {{- with .Values.async.nodeSelector }}
      nodeSelector:
        {{- toYaml . | nindent 8 }}  # workload=async-workers
      {{- end }}
      containers:
      - name: worker
        image: "{{ .Values.global.image.registry }}/{{ .Values.global.image.repository }}:{{ .Values.global.image.tag }}"
        command:
        - python
        - workers/vision_worker.py
        # ...
{{- end }}
```

---

## 📊 최종 구조 시각화

```
┌─────────────────────────────────────────────────────────┐
│           Kubernetes Cluster (7 Nodes)                  │
├─────────────────────────────────────────────────────────┤
│                                                           │
│  ┌─── Application Layer ─────────────────────┐          │
│  │                                             │          │
│  │  📦 api (Namespace)                        │          │
│  │    Worker-1 (workload=application)        │          │
│  │    ├─ waste-api (3)                        │          │
│  │    ├─ users-api (2)                        │          │
│  │    ├─ auth-api (2)                         │          │
│  │    ├─ recycling-api (2)                    │          │
│  │    └─ locations-api (2)                    │          │
│  │                                             │          │
│  │  ⚙️ async (Namespace)                      │          │
│  │    Worker-2 (workload=async-workers)      │          │
│  │    ├─ preprocess-worker (3)                │          │
│  │    ├─ vision-worker (5, HPA)               │          │
│  │    ├─ rag-worker (2)                       │          │
│  │    └─ llm-worker (3)                       │          │
│  └─────────────────────────────────────────────┘          │
│                                                           │
│  ┌─── Infrastructure Layer ─────────────────┐          │
│  │                                             │          │
│  │  💾 data (Namespace)                       │          │
│  │    ├─ postgresql (k8s-postgresql)          │          │
│  │    └─ redis (k8s-redis)                    │          │
│  │                                             │          │
│  │  📨 messaging (Namespace)                  │          │
│  │    └─ rabbitmq (k8s-rabbitmq)              │          │
│  └─────────────────────────────────────────────┘          │
│                                                           │
│  ┌─── Platform Layer ───────────────────────┐          │
│  │                                             │          │
│  │  📊 monitoring (Namespace)                 │          │
│  │    └─ prometheus, grafana (k8s-monitoring)│          │
│  │                                             │          │
│  │  🚀 argocd (Namespace)                     │          │
│  │    └─ argocd-server (Master)               │          │
│  └─────────────────────────────────────────────┘          │
│                                                           │
└─────────────────────────────────────────────────────────┘
```

---

## ✅ 핵심 정리

### 네임스페이스 vs Worker 노드 매핑

```yaml
api (namespace)     → Worker-1 (workload=application)
async (namespace)   → Worker-2 (workload=async-workers)
data (namespace)    → 전용 노드 (k8s-postgresql, k8s-redis)
messaging (namespace) → 전용 노드 (k8s-rabbitmq)
monitoring (namespace) → 전용 노드 (k8s-monitoring)
argocd (namespace)  → Master 노드
```

### 왜 이렇게?

1. **물리적 분리**: Worker-1 (Sync) vs Worker-2 (Async)
2. **논리적 분리**: api (REST) vs async (Celery)
3. **확장 용이**: 새 API → api NS, 새 Worker → async NS
4. **리소스 격리**: ResourceQuota per namespace
5. **보안**: NetworkPolicy per namespace

---

**결론**: `api`와 `async` 두 개의 독립 네임스페이스가 올바른 구조입니다! ✅

