# Kubernetes Label & Annotation 체계 (14-Node Architecture)

## 🎯 개요

14-Node 아키텍처에서 API별 자동 분류, 모니터링 자동 발견, 스케일링 정책 적용을 위한 Label/Annotation 표준화 문서입니다.

---

## 📋 노드 레이블 체계

### 1️⃣ Master Node

```yaml
Labels:
  node-role.sesacthon.io/control-plane: ""
  sesacthon.io/hostname: k8s-master
```

### 2️⃣ API Nodes (7개)

```yaml
# Phase 1
k8s-api-auth:
  sesacthon.io/node-role: api
  sesacthon.io/service: auth
  workload: api
  domain: auth
  tier: business-logic
  phase: "1"

k8s-api-my:
  sesacthon.io/node-role: api
  sesacthon.io/service: my
  workload: api
  domain: my
  tier: business-logic
  phase: "1"

# Phase 2
k8s-api-scan:
  sesacthon.io/node-role: api
  sesacthon.io/service: scan
  workload: api
  domain: scan
  tier: business-logic
  phase: "2"

k8s-api-character:
  sesacthon.io/node-role: api
  sesacthon.io/service: character
  workload: api
  domain: character
  tier: business-logic
  phase: "2"

k8s-api-location:
  sesacthon.io/node-role: api
  sesacthon.io/service: location
  workload: api
  domain: location
  tier: business-logic
  phase: "2"

# Phase 3
k8s-api-info:
  sesacthon.io/node-role: api
  sesacthon.io/service: info
  workload: api
  domain: info
  tier: business-logic
  phase: "3"

k8s-api-chat:
  sesacthon.io/node-role: api
  sesacthon.io/service: chat
  workload: api
  domain: chat
  tier: business-logic
  phase: "3"
```

### 3️⃣ Worker Nodes (2개)

```yaml
k8s-worker-storage:
  sesacthon.io/node-role: worker
  sesacthon.io/worker-type: storage
  workload: worker-storage
  worker-type: io-bound
  tier: worker
  phase: "4"

k8s-worker-ai:
  sesacthon.io/node-role: worker
  sesacthon.io/worker-type: ai
  workload: worker-ai
  worker-type: network-bound
  tier: worker
  phase: "4"
```

### 4️⃣ Infrastructure Nodes (4개)

```yaml
k8s-postgresql:
  sesacthon.io/node-role: infrastructure
  sesacthon.io/infra-type: postgresql
  workload: database
  tier: data
  phase: "1"

k8s-redis:
  sesacthon.io/node-role: infrastructure
  sesacthon.io/infra-type: redis
  workload: cache
  tier: data
  phase: "1"

k8s-rabbitmq:
  sesacthon.io/node-role: infrastructure
  sesacthon.io/infra-type: rabbitmq
  workload: message-queue
  tier: platform
  phase: "4"

k8s-monitoring:
  sesacthon.io/node-role: infrastructure
  sesacthon.io/infra-type: monitoring
  workload: monitoring
  tier: observability
  phase: "4"
```

---

## 🏷️ Pod Label & Annotation 체계

### API Deployments

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: auth-api
  namespace: api
  labels:
    app: auth-api
    domain: auth                    # 도메인 분류
    tier: api                       # 계층 분류
    version: v1.0.0                 # 버전
    phase: "1"                      # 배포 단계
  annotations:
    prometheus.io/scrape: "true"   # Prometheus 자동 발견
    prometheus.io/port: "8000"     # 메트릭 포트
    prometheus.io/path: "/metrics" # 메트릭 경로
spec:
  selector:
    matchLabels:
      app: auth-api
      domain: auth
  template:
    metadata:
      labels:
        app: auth-api
        domain: auth
        tier: api
        version: v1.0.0
      annotations:
        prometheus.io/scrape: "true"
        prometheus.io/port: "8000"
        prometheus.io/path: "/metrics"
```

### Worker Deployments

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: worker-storage
  namespace: workers
  labels:
    app: worker-storage
    workload: worker-storage
    worker-type: io-bound            # Worker 타입
    pool-type: eventlet              # Celery Pool 타입
    domain: scan                     # 담당 도메인
    tier: worker
    version: v1.0.0
  annotations:
    prometheus.io/scrape: "true"
    prometheus.io/port: "9090"       # Celery exporter
    prometheus.io/path: "/metrics"
spec:
  selector:
    matchLabels:
      app: worker-storage
      workload: worker-storage
```

---

## 🎯 NodeSelector & NodeAffinity 전략

### 1️⃣ API Pod → 해당 도메인 노드 배치

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: auth-api
spec:
  template:
    spec:
      # 방법 1: NodeSelector (간단) - sesacthon.io/service 사용
      nodeSelector:
        sesacthon.io/service: auth

      # 방법 2: domain 라벨 사용 (대안)
      # nodeSelector:
      #   domain: auth

      # 방법 3: NodeAffinity (복잡하지만 유연)
      affinity:
        nodeAffinity:
          requiredDuringSchedulingIgnoredDuringExecution:
            nodeSelectorTerms:
              - matchExpressions:
                  - key: sesacthon.io/service
                    operator: In
                    values:
                      - auth
          preferredDuringSchedulingIgnoredDuringExecution:
            - weight: 100
              preference:
                matchExpressions:
                  - key: phase
                    operator: In
                    values:
                      - "1"
      
      # Toleration for domain taint
      tolerations:
        - key: domain
          operator: Equal
          value: auth
          effect: NoSchedule
```

### 2️⃣ Worker Pod → Worker 노드 배치

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: worker-storage
spec:
  template:
    spec:
      # 방법 1: sesacthon.io/worker-type 사용 (권장)
      nodeSelector:
        sesacthon.io/worker-type: storage

      # 방법 2: workload 라벨 사용 (대안)
      # nodeSelector:
      #   workload: worker-storage

      affinity:
        nodeAffinity:
          requiredDuringSchedulingIgnoredDuringExecution:
            nodeSelectorTerms:
              - matchExpressions:
                  - key: sesacthon.io/worker-type
                    operator: In
                    values:
                      - storage
```

### 3️⃣ Infrastructure Pod → Infrastructure 노드 배치 + Toleration

```yaml
apiVersion: acid.zalan.do/v1
kind: postgresql
metadata:
  name: postgres-main
spec:
  # PostgreSQL Operator는 nodeAffinity 사용
  nodeAffinity:
    requiredDuringSchedulingIgnoredDuringExecution:
      nodeSelectorTerms:
        - matchExpressions:
            - key: sesacthon.io/infra-type
              operator: In
              values:
                - postgresql
  
  tolerations:
    - key: sesacthon.io/infrastructure
      operator: Equal
      value: "true"
      effect: NoSchedule

---
# Redis Operator 예시
apiVersion: databases.spotahome.com/v1
kind: RedisFailover
metadata:
  name: redis-main
spec:
  redis:
    nodeSelector:
      sesacthon.io/infra-type: redis
    tolerations:
      - key: sesacthon.io/infrastructure
        operator: Equal
        value: "true"
        effect: NoSchedule
  
  sentinel:
    nodeSelector:
      sesacthon.io/infra-type: redis
    tolerations:
      - key: sesacthon.io/infrastructure
        operator: Equal
        value: "true"
        effect: NoSchedule
```

---

## 🔍 Prometheus ServiceMonitor 자동 발견

### ServiceMonitor 예시 (auth-api)

```yaml
apiVersion: monitoring.coreos.com/v1
kind: ServiceMonitor
metadata:
  name: auth-api
  namespace: monitoring
  labels:
    release: prometheus
spec:
  selector:
    matchLabels:
      domain: auth          # Pod Label 기반 자동 발견
      tier: api
  namespaceSelector:
    matchNames:
      - api
  endpoints:
    - port: http            # Service port name
      path: /metrics        # Annotation에서 지정한 경로
      interval: 30s
      scrapeTimeout: 10s
```

### ServiceMonitor for All APIs (하나로 통합)

```yaml
apiVersion: monitoring.coreos.com/v1
kind: ServiceMonitor
metadata:
  name: all-api-services
  namespace: monitoring
  labels:
    release: prometheus
spec:
  selector:
    matchLabels:
      tier: api             # 모든 API 자동 발견
  namespaceSelector:
    matchNames:
      - api
  endpoints:
    - port: http
      path: /metrics
      interval: 30s
      scrapeTimeout: 10s
      relabelings:
        - sourceLabels: [__meta_kubernetes_pod_label_domain]
          targetLabel: domain
        - sourceLabels: [__meta_kubernetes_pod_label_version]
          targetLabel: version
```

### ServiceMonitor for Workers

```yaml
apiVersion: monitoring.coreos.com/v1
kind: ServiceMonitor
metadata:
  name: all-workers
  namespace: monitoring
spec:
  selector:
    matchLabels:
      tier: worker
  namespaceSelector:
    matchNames:
      - workers
  endpoints:
    - port: metrics         # Celery exporter port
      path: /metrics
      interval: 30s
      relabelings:
        - sourceLabels: [__meta_kubernetes_pod_label_workload]
          targetLabel: workload
        - sourceLabels: [__meta_kubernetes_pod_label_worker_type]
          targetLabel: worker_type
        - sourceLabels: [__meta_kubernetes_pod_label_pool_type]
          targetLabel: pool_type
```

---

## 🎨 Grafana Dashboard 자동 분류

### Dashboard Variables (Prometheus Query 기반)

```yaml
# Dashboard JSON 변수 정의
{
  "templating": {
    "list": [
      {
        "name": "domain",
        "type": "query",
        "query": "label_values(domain)",
        "label": "API Domain",
        "multi": true,
        "includeAll": true
      },
      {
        "name": "workload",
        "type": "query",
        "query": "label_values(workload)",
        "label": "Worker Type",
        "multi": true,
        "includeAll": true
      },
      {
        "name": "phase",
        "type": "query",
        "query": "label_values(phase)",
        "label": "Deployment Phase",
        "multi": true,
        "includeAll": true
      }
    ]
  }
}
```

### Prometheus Query 예시

```promql
# API별 요청 수
sum(rate(http_requests_total{domain="$domain"}[5m])) by (domain)

# Worker별 Task 처리량
sum(rate(celery_task_total{workload="$workload"}[5m])) by (workload)

# Phase별 Pod 상태
count(kube_pod_status_phase{phase="$phase"}) by (phase, pod_phase)

# 도메인별 평균 응답 시간
avg(http_request_duration_seconds{domain="$domain"}) by (domain)

# Worker Type별 Queue 길이
celery_queue_length{worker_type="$worker_type"}
```

---

## 🚀 HPA (Horizontal Pod Autoscaler) 설정

### API HPA

```yaml
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: auth-api-hpa
  namespace: api
  labels:
    domain: auth
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: auth-api
  minReplicas: 1
  maxReplicas: 5
  metrics:
    - type: Resource
      resource:
        name: cpu
        target:
          type: Utilization
          averageUtilization: 70
    - type: Resource
      resource:
        name: memory
        target:
          type: Utilization
          averageUtilization: 80
    - type: Pods
      pods:
        metric:
          name: http_requests_per_second
        target:
          type: AverageValue
          averageValue: "1000"
```

### Worker HPA

```yaml
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: worker-storage-hpa
  namespace: workers
  labels:
    workload: worker-storage
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: worker-storage
  minReplicas: 1
  maxReplicas: 10
  metrics:
    - type: External
      external:
        metric:
          name: celery_queue_length
          selector:
            matchLabels:
              queue: scan.image_uploader
        target:
          type: AverageValue
          averageValue: "10"
```

---

## 📊 Label 기반 리소스 쿼리

### kubectl 명령어

```bash
# 1. 특정 도메인 API Pod 조회
kubectl get pods -n api -l domain=auth

# 2. 특정 Phase의 모든 Pod 조회
kubectl get pods --all-namespaces -l phase=1

# 3. Worker 타입별 조회
kubectl get pods -n workers -l worker-type=io-bound

# 4. 모든 API 노드 조회
kubectl get nodes -l sesacthon.io/node-role=api
# 또는
kubectl get nodes -l workload=api

# 5. 특정 도메인의 HPA 상태 확인
kubectl get hpa -n api -l domain=scan

# 6. 모든 Infrastructure 노드 조회
kubectl get nodes -l sesacthon.io/node-role=infrastructure

# 7. 특정 서비스의 노드 조회
kubectl get nodes -l sesacthon.io/service=auth

# 8. PostgreSQL 노드 조회
kubectl get nodes -l sesacthon.io/infra-type=postgresql

# 9. Worker 노드 조회
kubectl get nodes -l sesacthon.io/worker-type=storage

# 10. Prometheus가 스크랩하는 모든 Pod 조회
kubectl get pods --all-namespaces -l prometheus.io/scrape=true
```

---

## 🎯 최종 정리

### 노드 Label 체계 (Ansible이 설정)

```yaml
# sesacthon.io/* 네임스페이스 라벨 (커스텀 도메인)
1. sesacthon.io/node-role      # 노드 역할 (api, worker, infrastructure)
2. sesacthon.io/service        # API 서비스명 (auth, my, scan, etc.)
3. sesacthon.io/worker-type    # Worker 타입 (storage, ai)
4. sesacthon.io/infra-type     # Infrastructure 타입 (postgresql, redis, rabbitmq, monitoring)
5. sesacthon.io/infrastructure # Infrastructure taint 키 (true)

# 범용 라벨
6. workload     # Workload 타입 (api, worker-storage, worker-ai, database, cache, message-queue, monitoring)
7. domain       # 도메인 분류 (auth, my, scan, character, location, info, chat)
8. tier         # 계층 분류 (business-logic, worker, data, platform, observability)
9. phase        # 배포 단계 (1, 2, 3, 4)
```

### Pod Label 사용 우선순위

```yaml
1. domain       # API 도메인 분류 (auth, my, scan, character, location, info, chat)
2. workload     # Workload 타입 (api, worker-storage, worker-ai, database, cache, message-queue, monitoring)
3. tier         # 계층 분류 (api, worker, infrastructure)
4. phase        # 배포 단계 (1, 2, 3, 4)
5. version      # 애플리케이션 버전 (v1.0.0, v1.1.0)
6. worker-type  # Worker 특성 (io-bound, network-bound)
```

### NodeSelector 매핑 (Deployment → Node)

```yaml
# API Deployments
nodeSelector:
  sesacthon.io/service: auth    # → k8s-api-auth 노드

# Worker Deployments  
nodeSelector:
  sesacthon.io/worker-type: storage   # → k8s-worker-storage 노드

# Infrastructure (PostgreSQL Operator)
nodeAffinity:
  matchExpressions:
    - key: sesacthon.io/infra-type
      operator: In
      values: [postgresql]        # → k8s-postgresql 노드

# Infrastructure (Redis Operator)
nodeSelector:
  sesacthon.io/infra-type: redis  # → k8s-redis 노드
```

### Annotation 사용 우선순위

```yaml
1. prometheus.io/scrape  # Prometheus 자동 발견 활성화
2. prometheus.io/port    # 메트릭 포트
3. prometheus.io/path    # 메트릭 경로
4. app.sesacthon.io/*   # Kubernetes 표준 메타데이터
```

---

## ⚠️ 중요: Ansible과 Kustomize 동기화

이 문서의 라벨 체계는 **Ansible playbook** (`ansible/playbooks/fix-node-labels.yml`)에서 설정하는 노드 라벨과 **완전히 동기화**되어 있습니다.

### Ansible이 설정하는 라벨 예시:

```bash
--node-labels=sesacthon.io/node-role=api,sesacthon.io/service=auth,workload=api,domain=auth,tier=business-logic,phase=1
```

### Deployment가 사용하는 nodeSelector:

```yaml
nodeSelector:
  sesacthon.io/service: auth
```

**충돌 방지**: Ansible로 노드 라벨을 변경할 때는 반드시 모든 Deployment의 `nodeSelector`도 함께 업데이트해야 합니다.

---

**작성일**: 2025-11-08  
**최종 업데이트**: 2025-11-16 (Ansible 라벨 동기화)  
**적용 대상**: 14-Node Full Production Architecture  
**다음 단계**: ArgoCD ApplicationSet, Helm Values, Monitoring Dashboards 구성

