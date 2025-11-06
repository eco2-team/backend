# 🐦 Canary 배포 적용 가이드

**현재 7노드 클러스터 구조에서 Canary 배포 적용 시 고려사항**

- **작성일**: 2025-11-05
- **대상 클러스터**: 7 노드 (1 Master + 6 Workers)
- **전제 조건**: Argo Rollouts 도입 필요

---

## 📋 목차

1. [현재 구조 분석](#현재-구조-분석)
2. [주요 고려사항](#주요-고려사항)
3. [Argo Rollouts 설치](#argo-rollouts-설치)
4. [구현 전략](#구현-전략)
5. [리소스 계획](#리소스-계획)
6. [마이그레이션 계획](#마이그레이션-계획)

---

## 🏗️ 현재 구조 분석

### Application Worker 노드

```yaml
k8s-worker-1:
  - 인스턴스: t3.medium (2 vCPU, 4GB RAM)
  - AZ: ap-northeast-2b
  - 라벨: workload=application
  - 역할: FastAPI 동기 API

k8s-worker-2:
  - 인스턴스: t3.medium (2 vCPU, 4GB RAM)
  - AZ: ap-northeast-2c
  - 라벨: workload=async-workers
  - 역할: Celery 비동기 작업

총 Application 리소스:
  - vCPU: 4 cores
  - RAM: 8GB
  - 노드: 2개
```

### 현재 배포 방식

```yaml
방식: Rolling Update
설정:
  maxSurge: 1
  maxUnavailable: 0
  
특징:
  - Kubernetes 기본 전략
  - 순차적 Pod 교체
  - 트래픽 제어 불가
  - 롤백 느림
```

---

## ⚠️ 주요 고려사항

### 1. 트래픽 라우팅 제약

#### 문제

**Kubernetes 기본 Service는 정밀한 트래픽 제어 불가**

```yaml
현재 구조:
  - CNI: Calico (Overlay Network)
  - Ingress: AWS ALB Ingress Controller
  - Service Type: ClusterIP
  - Routing: NodePort

제약:
  - Service는 Round-robin 로드밸런싱만 가능
  - Pod 수로만 트래픽 비율 제어 (근사치)
  - 정확한 % 제어 불가
```

**예시: 10% 트래픽 제어**

```yaml
# 기본 Kubernetes Service
Total Pods: 10
Canary: 1 Pod (실제론 10% 트래픽 보장 안 됨)
Stable: 9 Pods

문제:
  - 로드밸런싱 알고리즘에 따라 실제 비율 변동
  - 세션 어피니티 있으면 더 부정확
  - ALB Health Check도 영향
```

#### 해결 방안

**Option 1: Argo Rollouts (권장)**

```yaml
방법: Argo Rollouts Controller 사용
트래픽 제어: ReplicaSet 기반 (Pod 수 조절)
정확도: ~90% (근사치)
장점: 
  - Istio 불필요
  - 현재 구조 유지
  - ArgoCD와 네이티브 통합
단점:
  - 정밀한 % 제어는 한계
```

**Option 2: Istio Service Mesh (미래)**

```yaml
방법: Istio VirtualService 사용
트래픽 제어: L7 라우팅 (정밀)
정확도: 100% (정확한 % 제어)
장점:
  - 정밀한 트래픽 제어
  - Header/Cookie 기반 라우팅
  - 고급 기능 다수
단점:
  - 복잡도 매우 높음
  - 모든 Pod에 Sidecar 필요
  - 리소스 오버헤드 큼 (각 Pod마다 ~100MB)
  - 7개 노드에서 Istio는 과도
```

**권장: Argo Rollouts (Istio 없이)**

---

### 2. 리소스 관리

#### Application Pod 리소스

```yaml
현재 설정 (예상):
  requests:
    memory: "256Mi"
    cpu: "100m"
  limits:
    memory: "512Mi"
    cpu: "500m"

최대 Replica: 8~10개
최대 메모리: 8 x 512MB = 4GB
가용 메모리: 8GB (worker-1: 4GB, worker-2: 4GB)
여유: 충분 ✅
```

#### Canary 단계별 리소스

```yaml
Phase 1 (10% Canary):
  Stable: 9 Pods x 512MB = 4.5GB
  Canary: 1 Pod x 512MB = 0.5GB
  Total: 5GB
  상태: ⚠️ 여유 부족 (8GB 중 5GB 사용)

Phase 2 (30% Canary):
  Stable: 7 Pods x 512MB = 3.5GB
  Canary: 3 Pods x 512MB = 1.5GB
  Total: 5GB
  상태: ⚠️ 여유 부족

Phase 3 (50% Canary):
  Stable: 5 Pods x 512MB = 2.5GB
  Canary: 5 Pods x 512MB = 2.5GB
  Total: 5GB
  상태: ⚠️ 여유 부족
```

**문제: 기존 10 Replica는 과도**

#### 해결 방안

**Replica 수 조정 (권장)**

```yaml
# 기본 Replica: 5개로 조정
replicas: 5

Phase 1 (10% Canary):
  Stable: 4-5 Pods = 2.5GB
  Canary: 0-1 Pod = 0.5GB
  Total: 3GB ✅

Phase 2 (30% Canary):
  Stable: 3-4 Pods = 2GB
  Canary: 1-2 Pods = 1GB
  Total: 3GB ✅

Phase 3 (50% Canary):
  Stable: 2-3 Pods = 1.5GB
  Canary: 2-3 Pods = 1.5GB
  Total: 3GB ✅

여유: 5GB (8GB 중 3GB 사용) ✅
```

---

### 3. NodeSelector 설정

#### 필수 설정

```yaml
# Rollout 리소스에 NodeSelector 추가 필수
spec:
  template:
    spec:
      nodeSelector:
        workload: application  # worker-1, worker-2만 타게팅
      
      # 또는 NodeAffinity 사용
      affinity:
        nodeAffinity:
          requiredDuringSchedulingIgnoredDuringExecution:
            nodeSelectorTerms:
              - matchExpressions:
                  - key: workload
                    operator: In
                    values:
                      - application
```

**이유**

```yaml
Infrastructure 노드 (전용):
  - k8s-rabbitmq: RabbitMQ 전용
  - k8s-postgresql: PostgreSQL 전용
  - k8s-redis: Redis 전용
  - k8s-monitoring: Prometheus/Grafana 전용

Application Pod은:
  - k8s-worker-1, k8s-worker-2에만 배포 가능
  - NodeSelector 없으면 Infrastructure 노드에 배포될 수 있음
  - 리소스 경합 발생 가능
```

---

### 4. Analysis Template 구성

#### Prometheus 메트릭 확인

**필수 메트릭 사전 설정**

```yaml
필요 메트릭:
  1. http_requests_total (성공/실패 카운터)
  2. http_request_duration_seconds (레이턴시 히스토그램)
  3. error_rate (에러율)

확인 방법:
  - Prometheus UI 접속
  - 메트릭 존재 여부 확인
  - Label 구조 확인 (service, pod, status 등)
```

**Application 계측 필요**

```python
# FastAPI에 Prometheus 계측 추가 (예시)
from prometheus_client import Counter, Histogram, make_asgi_app
from fastapi import FastAPI

app = FastAPI()

# 메트릭 정의
http_requests_total = Counter(
    'http_requests_total',
    'Total HTTP requests',
    ['service', 'method', 'endpoint', 'status']
)

http_request_duration_seconds = Histogram(
    'http_request_duration_seconds',
    'HTTP request latency',
    ['service', 'method', 'endpoint']
)

# Prometheus 엔드포인트
metrics_app = make_asgi_app()
app.mount("/metrics", metrics_app)
```

**Analysis Template**

```yaml
apiVersion: argoproj.io/v1alpha1
kind: AnalysisTemplate
metadata:
  name: success-rate
spec:
  args:
    - name: service-name
  metrics:
    - name: success-rate
      interval: 1m
      successCondition: result >= 0.95
      failureLimit: 3
      provider:
        prometheus:
          address: http://prometheus.monitoring:9090
          query: |
            sum(rate(http_requests_total{
              service="{{args.service-name}}",
              status!~"5.."
            }[5m])) /
            sum(rate(http_requests_total{
              service="{{args.service-name}}"
            }[5m]))
```

---

### 5. 전용 Monitoring 노드 활용

#### 현재 구조의 장점

```yaml
k8s-monitoring:
  - 인스턴스: t3.large (2 vCPU, 8GB RAM)
  - 워크로드: Prometheus + Grafana 전용
  - 스토리지: 60GB (TSDB)
  
장점:
  ✅ Prometheus가 안정적으로 동작
  ✅ 메트릭 수집 영향 없음
  ✅ Analysis Template 안정성 보장
```

#### Prometheus 설정 확인

```yaml
필요 설정:
  - Service Discovery: Kubernetes API 연동
  - ServiceMonitor: Application Pod 메트릭 수집
  - Retention: 7일 이상 권장
  - Query Performance: 높음 필요
```

---

### 6. Deployment → Rollout 마이그레이션

#### 기존 Deployment 확인

```bash
# 현재 Deployment 확인
kubectl get deployments -o yaml > current-deployment.yaml

# Replica, Resource, NodeSelector 확인
kubectl describe deployment backend
```

#### 마이그레이션 전략

**Option 1: 직접 전환 (권장)**

```yaml
단계:
  1. Deployment YAML을 Rollout YAML로 변환
  2. Deployment 삭제
  3. Rollout 생성
  
장점:
  - 깔끔한 전환
  - Rollout이 ReplicaSet 관리

단점:
  - 일시적 다운타임 (1~2분)
```

**Option 2: Blue-Green 전환**

```yaml
단계:
  1. Rollout 생성 (다른 이름)
  2. Service를 Rollout으로 전환
  3. 기존 Deployment 삭제

장점:
  - 다운타임 없음
  - 안전한 전환

단점:
  - 일시적 리소스 2배
```

---

### 7. ArgoCD 통합

#### ArgoCD Application 수정

```yaml
# 기존: Deployment 사용
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: backend
spec:
  source:
    path: k8s/deployment  # ❌ 변경 필요

# 변경: Rollout 사용
spec:
  source:
    path: k8s/rollouts   # ✅ 새 경로
```

#### Argo Rollouts Plugin

```bash
# ArgoCD에 Rollouts Plugin 추가
kubectl patch configmap argocd-cm -n argocd --type merge -p '
{
  "data": {
    "resource.customizations": |
      argoproj.io/Rollout:
        health.lua: |
          hs = {}
          if obj.status ~= nil then
            if obj.status.phase == "Healthy" then
              hs.status = "Healthy"
              hs.message = obj.status.message
              return hs
            elseif obj.status.phase == "Degraded" then
              hs.status = "Degraded"
              hs.message = obj.status.message
              return hs
            end
          end
          hs.status = "Progressing"
          hs.message = "Waiting for rollout"
          return hs
  }
}'

# ArgoCD 재시작
kubectl rollout restart deployment argocd-server -n argocd
```

---

## 🚀 Argo Rollouts 설치

### 1. Controller 설치

```bash
# Namespace 생성
kubectl create namespace argo-rollouts

# Argo Rollouts 설치
kubectl apply -n argo-rollouts -f \
  https://github.com/argoproj/argo-rollouts/releases/latest/download/install.yaml

# 설치 확인
kubectl get pods -n argo-rollouts
```

### 2. Kubectl Plugin 설치

```bash
# Plugin 다운로드
curl -LO https://github.com/argoproj/argo-rollouts/releases/latest/download/kubectl-argo-rollouts-linux-amd64

# 실행 권한 부여
chmod +x kubectl-argo-rollouts-linux-amd64

# 설치
sudo mv kubectl-argo-rollouts-linux-amd64 /usr/local/bin/kubectl-argo-rollouts

# 설치 확인
kubectl argo rollouts version
```

### 3. Dashboard (선택)

```bash
# Dashboard 실행
kubectl argo rollouts dashboard

# 포트 포워딩 (로컬 접속)
kubectl port-forward -n argo-rollouts \
  svc/argo-rollouts-dashboard 3100:3100

# 브라우저: http://localhost:3100
```

---

## 📝 구현 전략

### Phase 1: 준비 (1주)

```yaml
Week 1:
  Day 1-2:
    - Argo Rollouts 설치
    - Dashboard 설정
    - Kubectl Plugin 설치
    - 팀 교육
    
  Day 3-4:
    - Application 메트릭 추가
    - Prometheus 설정 확인
    - ServiceMonitor 생성
    - 메트릭 수집 검증
    
  Day 5:
    - Analysis Template 작성
    - 테스트 환경 구축 (Kind 또는 스테이징)
    - PoC 실행
```

### Phase 2: 개발 환경 적용 (1주)

```yaml
Week 2:
  Day 1-2:
    - Deployment → Rollout 변환
    - NodeSelector 설정
    - Replica 수 조정 (10 → 5)
    
  Day 3-4:
    - 개발 환경 배포
    - Canary 배포 테스트
    - Analysis Template 튜닝
    
  Day 5:
    - 모니터링 검증
    - 자동 롤백 테스트
    - 문서 작성
```

### Phase 3: 프로덕션 적용 (1주)

```yaml
Week 3:
  Day 1-2:
    - 프로덕션 Rollout YAML 작성
    - 리소스 재확인
    - ArgoCD Application 업데이트
    
  Day 3:
    - 낮은 트래픽 시간대 배포
    - Canary 10% 테스트
    - 모니터링
    
  Day 4-5:
    - Canary 30%, 50% 테스트
    - 자동 승격 검증
    - 회고 및 개선
```

---

## 📊 리소스 계획

### 권장 Rollout 설정

```yaml
apiVersion: argoproj.io/v1alpha1
kind: Rollout
metadata:
  name: backend
spec:
  replicas: 5  # 10 → 5로 조정
  
  selector:
    matchLabels:
      app: backend
  
  template:
    metadata:
      labels:
        app: backend
    spec:
      # NodeSelector 필수
      nodeSelector:
        workload: application
      
      containers:
        - name: backend
          image: ghcr.io/org/backend:latest
          
          # 리소스 제한
          resources:
            requests:
              memory: "256Mi"
              cpu: "100m"
            limits:
              memory: "512Mi"
              cpu: "500m"
          
          # Health Check
          livenessProbe:
            httpGet:
              path: /health
              port: 8000
            initialDelaySeconds: 30
            periodSeconds: 10
          
          readinessProbe:
            httpGet:
              path: /ready
              port: 8000
            initialDelaySeconds: 5
            periodSeconds: 5
  
  strategy:
    canary:
      # Canary 단계
      steps:
        # 10% Canary
        - setWeight: 20  # 5개 중 1개 = 20%
        - pause: {duration: 5m}
        - analysis:
            templates:
              - templateName: success-rate
              - templateName: latency
        
        # 50% Canary
        - setWeight: 50
        - pause: {duration: 5m}
        - analysis:
            templates:
              - templateName: success-rate
              - templateName: latency
      
      # 자동 승격 비활성화 (수동 제어)
      autoPromotionEnabled: false
```

---

## 🗺️ 마이그레이션 계획

### 1. 사전 준비

```bash
# 1. 현재 Deployment 백업
kubectl get deployment backend -o yaml > backup-deployment.yaml

# 2. 현재 Pod 수 확인
kubectl get pods -l app=backend

# 3. 리소스 사용량 확인
kubectl top pods -l app=backend
kubectl top nodes k8s-worker-1 k8s-worker-2
```

### 2. Rollout 배포 (Blue-Green 방식)

```bash
# 1. Rollout 생성 (다른 이름)
kubectl apply -f backend-rollout.yaml

# 2. Rollout Pod 확인
kubectl get pods -l app=backend-rollout

# 3. Service를 Rollout으로 전환
kubectl patch service backend -p '
{
  "spec": {
    "selector": {
      "app": "backend-rollout"
    }
  }
}'

# 4. 기존 Deployment 삭제
kubectl delete deployment backend

# 5. Rollout 이름 변경 (backend-rollout → backend)
# 또는 처음부터 backend로 생성
```

### 3. 첫 Canary 배포

```bash
# 1. 이미지 업데이트
kubectl argo rollouts set image backend backend=ghcr.io/org/backend:v2.0.0

# 2. Rollout 상태 확인
kubectl argo rollouts get rollout backend --watch

# 3. 수동 승격
kubectl argo rollouts promote backend

# 4. 롤백 (문제 발생 시)
kubectl argo rollouts undo backend
```

---

## ⚡ 빠른 시작

### 최소 구성으로 시작

```yaml
# 1. Argo Rollouts 설치만
kubectl create namespace argo-rollouts
kubectl apply -n argo-rollouts -f \
  https://github.com/argoproj/argo-rollouts/releases/latest/download/install.yaml

# 2. 간단한 Rollout (Analysis 없이)
apiVersion: argoproj.io/v1alpha1
kind: Rollout
metadata:
  name: backend
spec:
  replicas: 5
  selector:
    matchLabels:
      app: backend
  template:
    # ... (기존 Pod spec)
  strategy:
    canary:
      steps:
        - setWeight: 20
        - pause: {duration: 5m}
        - setWeight: 50
        - pause: {duration: 5m}

# 3. 배포 및 수동 승격
kubectl argo rollouts set image backend backend=new-image:tag
kubectl argo rollouts promote backend
```

---

## 📚 참고 자료

- [Argo Rollouts 공식 문서](https://argoproj.github.io/argo-rollouts/)
- [배포 전략 비교](DEPLOYMENT_STRATEGIES_COMPARISON.md)
- [클러스터 리소스 현황](../infrastructure/CLUSTER_RESOURCES.md)
- [CI/CD 파이프라인](../architecture/CI_CD_PIPELINE.md)

---

**문서 버전**: 1.0  
**최종 업데이트**: 2025-11-05  
**대상**: 7노드 클러스터 (14 vCPU, 30GB RAM)  
**상태**: 구현 가능, Phase 2 추진 권장

