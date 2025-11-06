# 🏗️ 도메인별 네임스페이스 구조 개선안

## 📊 현재 네임스페이스 구조

### 기존 구조 (혼재)

```yaml
현재 네임스페이스:
  - default:      PostgreSQL, Redis, API Services
  - messaging:    RabbitMQ
  - monitoring:   Prometheus, Grafana
  - argocd:       ArgoCD
  - waste:        AI Workers (Vision, RAG, LLM)

문제점:
  ❌ API Services가 default에 혼재
  ❌ 도메인 경계 불명확
  ❌ 확장성 제한
  ❌ RBAC 설정 복잡
```

---

## 🎯 개선된 네임스페이스 구조

### 도메인 기반 분리

```yaml
# 1. Application Layer (도메인별)
api:                    # API 서비스 전체
  └── Deployments:
      - waste-api
      - users-api
      - auth-api
      - recycling-api
      - locations-api

workers:                # Async Workers 전체
  └── Deployments:
      - preprocess-worker
      - vision-worker
      - rag-worker
      - llm-worker

# 2. Infrastructure Layer (기능별)
data:                   # 데이터 스토어
  └── StatefulSets:
      - postgresql
      - redis

messaging:              # 메시지 브로커 (기존 유지)
  └── RabbitMQ Cluster

# 3. Platform Layer (플랫폼 서비스)
argocd:                 # GitOps (기존 유지)
  └── ArgoCD

monitoring:             # 모니터링 (기존 유지)
  └── Prometheus, Grafana

ingress-system:         # Ingress 컨트롤러
  └── ALB Controller
```

---

## 📋 상세 네임스페이스 설계

### 1. `api` Namespace

```yaml
용도: 모든 REST API 서비스
소유: Application Team

서비스:
  - waste-api:      쓰레기 분류 API
  - users-api:      사용자 관리 API
  - auth-api:       인증/인가 API
  - recycling-api:  재활용 정보 API
  - locations-api:  위치 기반 서비스 API

특징:
  - 동기 처리 (FastAPI)
  - NodePort Service
  - Ingress 연결
  - HPA 적용

리소스 쿼터:
  requests.cpu: 10 cores
  requests.memory: 20Gi
  persistentvolumeclaims: 0  # Stateless
```

### 2. `workers` Namespace

```yaml
용도: 비동기 작업 처리 (Celery Workers)
소유: Application Team

워커:
  - preprocess-worker:  이미지 전처리
  - vision-worker:      GPT-5 Vision 분석
  - rag-worker:         RAG 조회
  - llm-worker:         GPT-4o mini 응답

특징:
  - Celery + RabbitMQ
  - ClusterIP Service (내부 전용)
  - HPA 적용 (vision-worker)
  - 외부 API 연동 (OpenAI)

리소스 쿼터:
  requests.cpu: 5 cores
  requests.memory: 10Gi
  persistentvolumeclaims: 0  # Stateless
```

### 3. `data` Namespace

```yaml
용도: 영구 데이터 저장소
소유: Infrastructure Team

서비스:
  - postgresql:  주 데이터베이스
  - redis:       캐시 & 세션

특징:
  - StatefulSet (영구 스토리지)
  - PersistentVolumeClaims
  - 백업 자동화
  - 네트워크 정책 (접근 제한)

리소스 쿼터:
  requests.cpu: 2 cores
  requests.memory: 10Gi
  persistentvolumeclaims: 2
    - postgresql: 50Gi
    - redis: 10Gi

백업:
  - PostgreSQL: 매일 3AM (etcd-backup)
  - Redis: AOF 영구 저장
```

### 4. `messaging` Namespace (기존 유지)

```yaml
용도: 메시지 브로커
소유: Infrastructure Team

서비스:
  - rabbitmq:  메시지 큐 (Celery Backend)

특징:
  - RabbitMQ Cluster Operator
  - PersistentVolumeClaim
  - Management UI
  - Prometheus 메트릭

리소스 쿼터:
  requests.cpu: 2 cores
  requests.memory: 2Gi
  persistentvolumeclaims: 1 (10Gi)
```

### 5. `monitoring` Namespace (기존 유지)

```yaml
용도: 모니터링 및 관찰성
소유: SRE Team

서비스:
  - prometheus:     메트릭 수집
  - grafana:        대시보드
  - alertmanager:   알람

특징:
  - Prometheus Operator
  - Grafana Dashboard
  - Slack/Email 알림

리소스 쿼터:
  requests.cpu: 2 cores
  requests.memory: 8Gi
  persistentvolumeclaims: 1 (60Gi)
```

### 6. `argocd` Namespace (기존 유지)

```yaml
용도: GitOps CD
소유: Platform Team

서비스:
  - argocd-server
  - argocd-application-controller
  - argocd-repo-server

리소스 쿼터:
  requests.cpu: 1 core
  requests.memory: 2Gi
```

### 7. `ingress-system` Namespace (신규)

```yaml
용도: Ingress 컨트롤러
소유: Platform Team

서비스:
  - aws-load-balancer-controller

특징:
  - ALB 자동 생성
  - Path-based Routing
  - SSL/TLS Termination

리소스 쿼터:
  requests.cpu: 500m
  requests.memory: 512Mi
```

---

## 🔄 마이그레이션 계획

### Phase 1: 네임스페이스 생성 (5분)

```bash
#!/bin/bash
# scripts/create-namespaces.sh

# Application Layer
kubectl create namespace api
kubectl create namespace workers

# Infrastructure Layer
kubectl create namespace data
# messaging은 이미 존재
# monitoring은 이미 존재

# Platform Layer
# argocd는 이미 존재
kubectl create namespace ingress-system

# Labels 추가 (관리 용이)
kubectl label namespace api       layer=application team=backend
kubectl label namespace workers   layer=application team=backend
kubectl label namespace data      layer=infrastructure team=platform
kubectl label namespace messaging layer=infrastructure team=platform
kubectl label namespace monitoring layer=platform team=sre
kubectl label namespace argocd    layer=platform team=platform
kubectl label namespace ingress-system layer=platform team=platform
```

### Phase 2: ResourceQuota 설정 (10분)

```yaml
# k8s/namespaces/api-resourcequota.yaml
apiVersion: v1
kind: ResourceQuota
metadata:
  name: api-quota
  namespace: api
spec:
  hard:
    requests.cpu: "10"
    requests.memory: 20Gi
    limits.cpu: "20"
    limits.memory: 40Gi
    persistentvolumeclaims: "0"
    services.loadbalancers: "0"
    services.nodeports: "10"

---
# k8s/namespaces/workers-resourcequota.yaml
apiVersion: v1
kind: ResourceQuota
metadata:
  name: workers-quota
  namespace: workers
spec:
  hard:
    requests.cpu: "5"
    requests.memory: 10Gi
    limits.cpu: "10"
    limits.memory: 20Gi
    persistentvolumeclaims: "0"

---
# k8s/namespaces/data-resourcequota.yaml
apiVersion: v1
kind: ResourceQuota
metadata:
  name: data-quota
  namespace: data
spec:
  hard:
    requests.cpu: "2"
    requests.memory: 10Gi
    limits.cpu: "4"
    limits.memory: 20Gi
    persistentvolumeclaims: "2"
```

### Phase 3: NetworkPolicy 설정 (15분)

```yaml
# k8s/namespaces/network-policies.yaml

# 1. API → Data 접근 허용
---
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: allow-api-to-data
  namespace: data
spec:
  podSelector: {}
  policyTypes:
  - Ingress
  ingress:
  - from:
    - namespaceSelector:
        matchLabels:
          layer: application
    ports:
    - protocol: TCP
      port: 5432  # PostgreSQL
    - protocol: TCP
      port: 6379  # Redis

# 2. Workers → Data 접근 허용
---
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: allow-workers-to-data
  namespace: data
spec:
  podSelector: {}
  policyTypes:
  - Ingress
  ingress:
  - from:
    - namespaceSelector:
        matchLabels:
          kubernetes.io/metadata.name: workers
    ports:
    - protocol: TCP
      port: 5432
    - protocol: TCP
      port: 6379

# 3. Workers → Messaging 접근 허용
---
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: allow-workers-to-messaging
  namespace: messaging
spec:
  podSelector: {}
  policyTypes:
  - Ingress
  ingress:
  - from:
    - namespaceSelector:
        matchLabels:
          layer: application
    ports:
    - protocol: TCP
      port: 5672  # AMQP
    - protocol: TCP
      port: 15672  # Management

# 4. Monitoring → 모든 네임스페이스 (메트릭 수집)
---
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: allow-monitoring
  namespace: api
spec:
  podSelector: {}
  policyTypes:
  - Ingress
  ingress:
  - from:
    - namespaceSelector:
        matchLabels:
          team: sre
    ports:
    - protocol: TCP
      port: 9090  # Metrics
```

### Phase 4: 리소스 마이그레이션 (30분)

```bash
#!/bin/bash
# scripts/migrate-namespaces.sh

echo "🔄 네임스페이스 마이그레이션 시작..."

# 1. AI Workers: waste → workers
echo "1️⃣ AI Workers 마이그레이션 (waste → workers)"
kubectl get deployment -n waste -o yaml | \
  sed 's/namespace: waste/namespace: workers/g' | \
  kubectl apply -f -

# 검증
kubectl get pods -n workers

# 2. PostgreSQL: default → data
echo "2️⃣ PostgreSQL 마이그레이션 (default → data)"
# 주의: StatefulSet은 재생성 필요
kubectl get statefulset -n default postgres -o yaml | \
  sed 's/namespace: default/namespace: data/g' > /tmp/postgres-data.yaml

# PVC 백업 후 마이그레이션
kubectl get pvc -n default postgres-data-postgres-0 -o yaml | \
  sed 's/namespace: default/namespace: data/g' > /tmp/postgres-pvc.yaml

# 3. Redis: default → data
echo "3️⃣ Redis 마이그레이션 (default → data)"
kubectl get deployment -n default redis -o yaml | \
  sed 's/namespace: default/namespace: data/g' | \
  kubectl apply -f -

echo "✅ 마이그레이션 완료!"
```

---

## 📝 Helm Chart 수정

### values.yaml (네임스페이스 분리)

```yaml
# charts/growbin-backend/values.yaml

# Namespace 설정
namespaces:
  api: api
  workers: workers
  data: data
  messaging: messaging

# API Services
api:
  namespace: api  # ⬅️ 명시적 네임스페이스
  rest:
    waste:
      enabled: true
      replicas: 3
      # ...

# Async Workers
workers:
  namespace: workers  # ⬅️ 명시적 네임스페이스
  async:
    vision:
      enabled: true
      replicas: 5
      # ...

# Data Stores
data:
  namespace: data  # ⬅️ 명시적 네임스페이스
  postgresql:
    enabled: true
    # ...
  redis:
    enabled: true
    # ...
```

### 템플릿 수정

```yaml
# charts/growbin-backend/templates/api/rest/waste-deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: {{ include "growbin-backend.fullname" . }}-api-waste
  namespace: {{ .Values.namespaces.api }}  # ⬅️ 동적 네임스페이스
  labels:
    # ...
```

---

## 🔐 RBAC 설정

### 네임스페이스별 ServiceAccount

```yaml
# k8s/rbac/api-serviceaccount.yaml
---
apiVersion: v1
kind: ServiceAccount
metadata:
  name: api-sa
  namespace: api

---
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: api-role
  namespace: api
rules:
- apiGroups: [""]
  resources: ["pods", "services"]
  verbs: ["get", "list", "watch"]
- apiGroups: ["apps"]
  resources: ["deployments"]
  verbs: ["get", "list", "watch"]

---
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: api-rolebinding
  namespace: api
subjects:
- kind: ServiceAccount
  name: api-sa
  namespace: api
roleRef:
  kind: Role
  name: api-role
  apiGroup: rbac.authorization.k8s.io

---
# Cross-namespace 접근 (data namespace)
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: api-data-access
  namespace: data
rules:
- apiGroups: [""]
  resources: ["services"]
  verbs: ["get"]

---
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: api-data-access
  namespace: data
subjects:
- kind: ServiceAccount
  name: api-sa
  namespace: api
roleRef:
  kind: Role
  name: api-data-access
  apiGroup: rbac.authorization.k8s.io
```

---

## 📊 최종 네임스페이스 구조

### 시각화

```
┌─────────────────────────────────────────────────────────────┐
│                    Kubernetes Cluster                        │
├─────────────────────────────────────────────────────────────┤
│                                                               │
│  ┌─── Application Layer ────────────────────────────┐       │
│  │                                                    │       │
│  │  📦 api (Namespace)                              │       │
│  │    ├─ waste-api                                  │       │
│  │    ├─ users-api                                  │       │
│  │    ├─ auth-api                                   │       │
│  │    ├─ recycling-api                              │       │
│  │    └─ locations-api                              │       │
│  │                                                    │       │
│  │  ⚙️ workers (Namespace)                          │       │
│  │    ├─ preprocess-worker                          │       │
│  │    ├─ vision-worker                              │       │
│  │    ├─ rag-worker                                 │       │
│  │    └─ llm-worker                                 │       │
│  └────────────────────────────────────────────────────┘       │
│                                                               │
│  ┌─── Infrastructure Layer ─────────────────────────┐       │
│  │                                                    │       │
│  │  💾 data (Namespace)                             │       │
│  │    ├─ postgresql (StatefulSet)                   │       │
│  │    └─ redis (StatefulSet)                        │       │
│  │                                                    │       │
│  │  📨 messaging (Namespace)                        │       │
│  │    └─ rabbitmq (StatefulSet)                     │       │
│  └────────────────────────────────────────────────────┘       │
│                                                               │
│  ┌─── Platform Layer ──────────────────────────────┐       │
│  │                                                    │       │
│  │  🚀 argocd (Namespace)                           │       │
│  │    └─ ArgoCD Server                              │       │
│  │                                                    │       │
│  │  📊 monitoring (Namespace)                       │       │
│  │    ├─ Prometheus                                 │       │
│  │    └─ Grafana                                    │       │
│  │                                                    │       │
│  │  🔀 ingress-system (Namespace)                  │       │
│  │    └─ ALB Controller                             │       │
│  └────────────────────────────────────────────────────┘       │
│                                                               │
└─────────────────────────────────────────────────────────────┘
```

---

## ✅ 장점 요약

### 1. **명확한 도메인 분리**
```
api:      REST API 서비스
workers:  비동기 작업
data:     데이터 스토어
```

### 2. **리소스 관리 용이**
```yaml
ResourceQuota per namespace:
  api:     10 cores, 20Gi
  workers: 5 cores, 10Gi
  data:    2 cores, 10Gi
```

### 3. **보안 강화**
```yaml
NetworkPolicy:
  - api → data (허용)
  - workers → data (허용)
  - workers → messaging (허용)
  - 기타 차단
```

### 4. **RBAC 세분화**
```
ServiceAccount per namespace:
  - api-sa
  - workers-sa
  - data-sa
```

### 5. **확장성**
```
새 도메인 추가 시:
  - 새 네임스페이스 생성
  - ResourceQuota 설정
  - NetworkPolicy 추가
```

---

## 🚀 실행 계획

### 즉시 실행

```bash
# 1. 네임스페이스 생성
./scripts/create-namespaces.sh

# 2. ResourceQuota 적용
kubectl apply -f k8s/namespaces/

# 3. NetworkPolicy 적용
kubectl apply -f k8s/namespaces/network-policies.yaml

# 4. 리소스 마이그레이션
./scripts/migrate-namespaces.sh

# 5. Helm Chart 업데이트
git add charts/
git commit -m "refactor: Migrate to domain-based namespaces"
git push

# 6. ArgoCD Sync
argocd app sync growbin-backend
```

---

**결론**: 도메인별 네임스페이스 분리로 관리성, 보안성, 확장성이 대폭 향상됩니다! 🎯

