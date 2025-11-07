# 🔄 GitOps 배포 가이드 (ArgoCD + Helm)

> **배포 전략**: GitHub Actions (CI) + ArgoCD (CD) + Helm Charts  
> **레지스트리**: GitHub Container Registry (GHCR) - 무료  
> **날짜**: 2025-10-30

## 📋 목차

1. [배포 아키텍처](#배포-아키텍처)
2. [GitHub Actions CI](#github-actions-ci)
3. [Helm Charts 구조](#helm-charts-구조)
4. [ArgoCD 설정](#argocd-설정)
5. [배포 프로세스](#배포-프로세스)
6. [운영 가이드](#운영-가이드)

---

## 🏗️ 배포 아키텍처

### GitOps 전체 흐름

```mermaid
sequenceDiagram
    actor Dev as 개발자
    participant GH as GitHub
    participant GHA as GitHub Actions
    participant DH as Docker Hub
    participant Helm as Helm Charts<br/>(Git)
    participant Argo as ArgoCD
    participant K8s as Kubernetes Cluster
    
    Dev->>GH: 1. services/auth/ 코드 수정 후 Push
    GH->>GHA: 2. ci-build-auth.yml 트리거
    
    activate GHA
    GHA->>GHA: 3. Lint & Test (PEP 8, pytest)
    GHA->>GHA: 4. Docker Build
    GHA->>DH: 5. Push sesacthon/auth:abc123
    GHA->>Helm: 6. Update values-prod.yaml<br/>image.tag: abc123
    GHA->>GH: 7. Commit & Push
    deactivate GHA
    
    Note over Argo: 8. Git 폴링 (3분마다)
    
    activate Argo
    Argo->>Helm: 9. 변경 감지!
    Argo->>Argo: 10. Helm Diff 계산
    Argo->>K8s: 11. kubectl apply (자동 Sync)
    deactivate Argo
    
    activate K8s
    K8s->>DH: 12. Pull sesacthon/auth:abc123
    K8s->>K8s: 13. Rolling Update
    K8s->>K8s: 14. Health Check
    deactivate K8s
    
    K8s-->>Argo: 15. Sync 완료
    Argo-->>Dev: 16. Slack 알림: ✅ auth 배포 완료
```

### 핵심 구성 요소

```mermaid
graph TB
    subgraph CI["CI: GitHub Actions"]
        GHA[서비스별 워크플로우<br/>ci-build-auth.yml<br/>ci-build-waste.yml<br/>etc.]
    end
    
    subgraph Registry["GitHub Container Registry (GHCR)"]
        DH[ghcr.io/your-org/sesacthon/auth-service<br/>ghcr.io/your-org/sesacthon/waste-service<br/>ghcr.io/your-org/sesacthon/recycling-service<br/>ghcr.io/your-org/sesacthon/users-service<br/>ghcr.io/your-org/sesacthon/locations-service]
    end
    
    subgraph GitOps["Git Repository"]
        Charts[charts/<br/>├─ auth/<br/>├─ waste/<br/>├─ recycling/<br/>├─ users/<br/>└─ locations/]
    end
    
    subgraph CD["CD: ArgoCD"]
        Argo[ArgoCD<br/>- Git 모니터링<br/>- Helm 렌더링<br/>- 자동 Sync]
    end
    
    subgraph K8s["k3s Cluster"]
        Pods[Pods<br/>auth, waste, recycling<br/>users, locations<br/>+ Workers]
    end
    
    GHA -->|빌드 & 푸시| DH
    GHA -->|values 업데이트| Charts
    Charts -->|모니터링| Argo
    Argo -->|배포| Pods
    Pods -->|이미지 Pull| DH
    
    style GHA fill:#cce5ff,stroke:#007bff,stroke-width:3px,color:#000
    style DH fill:#cccccc,stroke:#333333,stroke-width:4px,color:#000
    style Charts fill:#d1f2eb,stroke:#28a745,stroke-width:3px,color:#000
    style Argo fill:#e6d5ff,stroke:#8844ff,stroke-width:4px,color:#000
    style Pods fill:#ffd1d1,stroke:#dc3545,stroke-width:3px,color:#000
```

---

## ⚙️ GitHub Actions CI

### 서비스별 워크플로우

```
.github/workflows/
├── ci-build-auth.yml        # Auth 서비스
├── ci-build-users.yml       # Users 서비스
├── ci-build-waste.yml       # Waste 서비스
├── ci-build-recycling.yml   # Recycling 서비스
├── ci-build-locations.yml   # Locations 서비스
└── ci-common.yml            # 공유 라이브러리 (shared/)
```

### 공통 CI 단계

```yaml
# 모든 서비스 공통
jobs:
  lint-and-test:
    # 1. PEP 8 검사
    # 2. Black, isort 검사
    # 3. Flake8 린트
    # 4. pytest 테스트
  
  build-and-push:
    # 5. Docker 빌드
    # 6. Docker Hub 푸시 (sesacthon/{service}:sha)
    # 7. Helm values-prod.yaml 업데이트
    # 8. Git commit & push
```

### GHCR 태그 전략

```
이미지 태그:
├─ {short-sha}: abc1234 (Git commit)
├─ latest: 항상 최신 (main 브랜치)
├─ {branch}: main, develop
└─ v{version}: v1.0.0 (태그 시)

예시:
ghcr.io/your-org/sesacthon-backend/auth-service:abc1234
ghcr.io/your-org/sesacthon-backend/auth-service:latest
ghcr.io/your-org/sesacthon-backend/waste-service:abc1234
ghcr.io/your-org/sesacthon-backend/waste-service:latest

장점:
✅ 무료 (Private 레포지토리도 무료)
✅ GitHub과 통합 (별도 계정 불필요)
✅ GitHub Actions에서 자동 인증 (GITHUB_TOKEN)
✅ 용량 제한 없음
```

---

## 📦 Helm Charts 구조

### 프로젝트 레이아웃

```
charts/
├── auth/
│   ├── Chart.yaml
│   ├── values.yaml              # 기본값
│   ├── values-dev.yaml          # 개발 환경
│   ├── values-prod.yaml         # 프로덕션 (ArgoCD가 사용)
│   └── templates/
│       ├── deployment.yaml
│       ├── service.yaml
│       ├── ingress.yaml
│       ├── configmap.yaml
│       ├── secret.yaml
│       └── hpa.yaml
│
├── waste/
│   ├── Chart.yaml
│   ├── values-prod.yaml
│   └── templates/
│       ├── deployment.yaml      # API Server
│       ├── fast-worker.yaml     # Fast Worker
│       ├── external-worker.yaml # External Worker
│       ├── service.yaml
│       ├── ingress.yaml
│       └── hpa.yaml
│
├── recycling/
├── users/
└── locations/
```

### Chart.yaml 예시

```yaml
# charts/auth/Chart.yaml
apiVersion: v2
name: auth-service
description: 인증/인가 서비스
type: application
version: 1.0.0
appVersion: "1.0.0"
keywords:
  - auth
  - oauth
  - jwt
maintainers:
  - name: SeSACTHON Backend Team
```

### values-prod.yaml 예시

```yaml
# charts/auth/values-prod.yaml
replicaCount: 2

image:
  repository: ghcr.io/your-org/sesacthon-backend/auth-service
  tag: abc1234  # ⭐ GitHub Actions가 자동 업데이트
  pullPolicy: Always

# imagePullSecrets:  # Private 레포지토리인 경우만
#   - name: ghcr-secret

service:
  type: ClusterIP
  port: 80
  targetPort: 8000

ingress:
  enabled: true
  annotations:
    kubernetes.io/ingress.class: alb
    alb.ingress.kubernetes.io/scheme: internet-facing
    alb.ingress.kubernetes.io/target-type: ip
    alb.ingress.kubernetes.io/certificate-arn: arn:aws:acm:ap-northeast-2:xxxxx:certificate/xxxxx
    alb.ingress.kubernetes.io/group.name: ecoeco-alb
  hosts:
    - host: api.yourdomain.com
      paths:
        - path: /api/v1/auth
          pathType: Prefix
  tls:
    - secretName: api-tls
      hosts:
        - api.yourdomain.com

resources:
  requests:
    cpu: 100m
    memory: 128Mi
  limits:
    cpu: 500m
    memory: 256Mi

autoscaling:
  enabled: true
  minReplicas: 2
  maxReplicas: 5
  targetCPUUtilizationPercentage: 70

nodeSelector:
  workload: light  # Worker 3

env:
  - name: DATABASE_URL
    valueFrom:
      secretKeyRef:
        name: auth-secrets
        key: database-url
  - name: REDIS_URL
    value: "redis://redis.default.svc.cluster.local:6379/0"
  - name: JWT_SECRET_KEY
    valueFrom:
      secretKeyRef:
        name: auth-secrets
        key: jwt-secret
```

### Deployment 템플릿

```yaml
# charts/auth/templates/deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: {{ include "auth-service.fullname" . }}
  namespace: {{ .Release.Namespace }}
  labels:
    {{- include "auth-service.labels" . | nindent 4 }}
spec:
  replicas: {{ .Values.replicaCount }}
  selector:
    matchLabels:
      {{- include "auth-service.selectorLabels" . | nindent 6 }}
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxSurge: 1
      maxUnavailable: 0  # 무중단 배포
  template:
    metadata:
      labels:
        {{- include "auth-service.selectorLabels" . | nindent 8 }}
    spec:
      {{- with .Values.nodeSelector }}
      nodeSelector:
        {{- toYaml . | nindent 8 }}
      {{- end }}
      containers:
      - name: {{ .Chart.Name }}
        image: "{{ .Values.image.repository }}:{{ .Values.image.tag }}"
        imagePullPolicy: {{ .Values.image.pullPolicy }}
        ports:
        - name: http
          containerPort: 8000
          protocol: TCP
        env:
        {{- toYaml .Values.env | nindent 8 }}
        livenessProbe:
          httpGet:
            path: /health
            port: http
          initialDelaySeconds: 30
          periodSeconds: 10
        readinessProbe:
          httpGet:
            path: /health
            port: http
          initialDelaySeconds: 10
          periodSeconds: 5
        resources:
          {{- toYaml .Values.resources | nindent 12 }}
```

---

## 🚀 ArgoCD 설정

### ArgoCD 설치 (Kubernetes)

```bash
# 1. ArgoCD 설치
kubectl create namespace argocd
kubectl apply -n argocd -f \
  https://raw.githubusercontent.com/argoproj/argo-cd/stable/manifests/install.yaml

# 설치 확인
kubectl get pods -n argocd -w
# 모든 Pod가 Running이 될 때까지 대기 (2-3분)

# 2. ArgoCD CLI 설치
curl -sSL -o argocd-linux-amd64 \
  https://github.com/argoproj/argo-cd/releases/latest/download/argocd-linux-amd64
sudo install -m 555 argocd-linux-amd64 /usr/local/bin/argocd
rm argocd-linux-amd64

# 3. ArgoCD UI 접근
kubectl port-forward svc/argocd-server -n argocd 8080:443

# 4. 초기 비밀번호
kubectl -n argocd get secret argocd-initial-admin-secret \
  -o jsonpath="{.data.password}" | base64 -d && echo

# 5. Ingress 설정 (선택)
kubectl apply -f argocd/ingress.yaml
```

### ArgoCD Application 정의

```yaml
# argocd/applications/auth.yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: auth-service
  namespace: argocd
  finalizers:
    - resources-finalizer.argocd.argoproj.io
spec:
  project: default
  
  source:
    repoURL: https://github.com/your-org/sesacthon-backend.git
    targetRevision: main
    path: charts/auth
    helm:
      valueFiles:
        - values-prod.yaml
  
  destination:
    server: https://kubernetes.default.svc
    namespace: auth
  
  syncPolicy:
    automated:
      prune: true        # 불필요한 리소스 자동 삭제
      selfHeal: true     # Drift 자동 복구
      allowEmpty: false
    syncOptions:
      - CreateNamespace=true
      - PrunePropagationPolicy=foreground
      - PruneLast=true
    retry:
      limit: 5
      backoff:
        duration: 5s
        factor: 2
        maxDuration: 3m
  
  # Health Check
  ignoreDifferences:
  - group: apps
    kind: Deployment
    jsonPointers:
    - /spec/replicas  # HPA가 관리
```

### 모든 서비스 등록

```yaml
# argocd/applications/all-services.yaml
apiVersion: v1
kind: List
items:
  # Auth Service
  - apiVersion: argoproj.io/v1alpha1
    kind: Application
    metadata:
      name: auth-service
      namespace: argocd
    spec:
      # (위 spec과 동일)
  
  # Waste Service
  - apiVersion: argoproj.io/v1alpha1
    kind: Application
    metadata:
      name: waste-service
      namespace: argocd
    spec:
      source:
        path: charts/waste
      destination:
        namespace: waste
      syncPolicy:
        automated:
          prune: true
          selfHeal: true
  
  # Recycling Service
  - apiVersion: argoproj.io/v1alpha1
    kind: Application
    metadata:
      name: recycling-service
      namespace: argocd
    spec:
      source:
        path: charts/recycling
      destination:
        namespace: recycling
      syncPolicy:
        automated:
          prune: true
          selfHeal: true
  
  # Users Service
  - apiVersion: argoproj.io/v1alpha1
    kind: Application
    metadata:
      name: users-service
      namespace: argocd
    spec:
      source:
        path: charts/users
      destination:
        namespace: users
      syncPolicy:
        automated:
          prune: true
          selfHeal: true
  
  # Locations Service
  - apiVersion: argoproj.io/v1alpha1
    kind: Application
    metadata:
      name: locations-service
      namespace: argocd
    spec:
      source:
        path: charts/locations
      destination:
        namespace: locations
      syncPolicy:
        automated:
          prune: true
          selfHeal: true
```

### ArgoCD Applications 등록

```bash
# 모든 서비스 한 번에 등록
kubectl apply -f argocd/applications/all-services.yaml

# ArgoCD UI에서 확인
# http://localhost:8080
# 또는
argocd app list
```

---

## 🔄 배포 프로세스

### 정상 배포 흐름

```mermaid
flowchart TD
    A[코드 수정] --> B[Git Push]
    B --> C{Path Filter}
    
    C -->|services/auth/**| D1[CI: auth]
    C -->|services/waste/**| D2[CI: waste]
    C -->|shared/**| D3[CI: 전체]
    
    D1 --> E1[Lint & Test]
    E1 --> F1[Docker Build]
    F1 --> G1[Docker Hub Push<br/>sesacthon/auth:abc123]
    G1 --> H1[Helm values 업데이트<br/>image.tag: abc123]
    H1 --> I1[Git Commit]
    
    I1 --> J[ArgoCD 감지<br/>3분 이내]
    J --> K[Helm Diff]
    K --> L{Auto Sync?}
    L -->|Yes| M[kubectl apply]
    L -->|No| N[수동 Sync 대기]
    
    M --> O[Rolling Update]
    O --> P[Health Check]
    P --> Q{성공?}
    Q -->|Yes| R[✅ 배포 완료]
    Q -->|No| S[자동 Rollback]
    
    style A fill:#cce5ff,stroke:#007bff,stroke-width:3px,color:#000
    style G1 fill:#ffe0b3,stroke:#fd7e14,stroke-width:3px,color:#000
    style J fill:#e6d5ff,stroke:#8844ff,stroke-width:4px,color:#000
    style M fill:#d1f2eb,stroke:#28a745,stroke-width:3px,color:#000
    style R fill:#d1f2eb,stroke:#28a745,stroke-width:4px,color:#000
    style S fill:#ffd1d1,stroke:#dc3545,stroke-width:3px,color:#000
```

### 수동 배포

```bash
# 1. 이미지 빌드 (로컬)
cd services/auth
docker build -t sesacthon/auth-service:dev .
docker push sesacthon/auth-service:dev

# 2. Helm values 수정
vim charts/auth/values-prod.yaml
# image.tag: dev

# 3. Git Push
git add charts/auth/values-prod.yaml
git commit -m "chore: Deploy auth-service dev version"
git push

# 4. ArgoCD 즉시 Sync (대기하기 싫으면)
argocd app sync auth-service

# 5. 진행 상황 확인
argocd app get auth-service
kubectl get pods -n auth -w
```

---

## 🎯 핵심 설정

### GitHub Secrets 필요

```
Repository → Settings → Secrets

필수:
└─ SLACK_WEBHOOK_URL: Slack 알림 (선택)

불필요 (GHCR 사용):
✅ GITHUB_TOKEN: 자동 제공 (별도 설정 불필요)
❌ DOCKERHUB_USERNAME, DOCKERHUB_TOKEN (불필요)
❌ EC2_HOST, EC2_USER, EC2_SSH_KEY (ArgoCD 사용으로 불필요)
```

### GHCR 사용 설정

```
Repository → Settings → Packages

1. Package visibility 설정
   - Public: 누구나 Pull 가능 (권장)
   - Private: 조직 내부만

2. GitHub Actions 권한 (자동)
   - GITHUB_TOKEN이 자동으로 GHCR 접근 권한 가짐
   - 별도 설정 불필요!

3. Kubernetes에서 Pull (Public인 경우)
   - imagePullSecrets 불필요
   - Public이면 누구나 Pull 가능

4. Private인 경우 (선택)
   kubectl create secret docker-registry ghcr-secret \
     --docker-server=ghcr.io \
     --docker-username=$GITHUB_USERNAME \
     --docker-password=$GITHUB_TOKEN \
     --docker-email=$GITHUB_EMAIL \
     -n auth
```

### ArgoCD Repository 연결

```bash
# 1. GitHub 리포지토리 등록
argocd repo add https://github.com/your-org/sesacthon-backend.git

# Private 리포지토리면 SSH 키 또는 Token 필요
argocd repo add https://github.com/your-org/sesacthon-backend.git \
  --username <github-username> \
  --password <github-token>

# 2. 연결 확인
argocd repo list
```

---

## 📊 서비스별 설정

### Waste Service (복잡한 예시)

```yaml
# charts/waste/values-prod.yaml
# API Server
api:
  replicaCount: 2
  image:
    repository: sesacthon/waste-service
    tag: abc1234  # ⭐ GitHub Actions 자동 업데이트
  resources:
    requests:
      cpu: 200m
      memory: 256Mi
  nodeSelector:
    workload: cpu

# Fast Worker
fastWorker:
  enabled: true
  replicaCount: 5
  image:
    repository: sesacthon/waste-service  # 동일 이미지
    tag: abc1234
  command:
    - celery
    - -A
    - workers.fast_worker
    - worker
    - --queues=q.fast
    - --concurrency=10
  resources:
    requests:
      cpu: 500m
      memory: 512Mi
  nodeSelector:
    workload: cpu

# External Worker
externalWorker:
  enabled: true
  replicaCount: 3
  command:
    - celery
    - -A
    - workers.external_worker
    - worker
    - --queues=q.external
    - --concurrency=20
    - --pool=gevent
  resources:
    requests:
      cpu: 200m
      memory: 256Mi
  nodeSelector:
    workload: network

# 환경변수
env:
  - name: CELERY_BROKER_URL
    value: "amqp://admin:password@rabbitmq.messaging:5672//"
  - name: CELERY_RESULT_BACKEND
    value: "redis://redis.default:6379/1"
  - name: AI_VISION_API_URL
    valueFrom:
      secretKeyRef:
        name: waste-secrets
        key: ai-api-url
```

---

## 🔍 운영 가이드

### ArgoCD 모니터링

```bash
# 1. 전체 앱 상태
argocd app list

# 출력:
# NAME            CLUSTER    NAMESPACE  PROJECT  STATUS   HEALTH   SYNCPOLICY
# auth-service    in-cluster auth       default  Synced   Healthy  Auto
# waste-service   in-cluster waste      default  Synced   Healthy  Auto
# ...

# 2. 특정 앱 상세
argocd app get waste-service

# 3. Sync 이력
argocd app history waste-service

# 4. 실시간 로그
argocd app logs waste-service -f
```

### 배포 상태 확인

```bash
# ArgoCD 상태
kubectl get applications -n argocd

# Pod 상태
kubectl get pods -n auth
kubectl get pods -n waste

# Ingress 확인
kubectl get ingress -A

# HPA 상태
kubectl get hpa -A
```

### 수동 Sync

```bash
# 자동 Sync 비활성화
argocd app set auth-service --sync-policy none

# 수동 Sync
argocd app sync auth-service

# Sync 옵션
argocd app sync auth-service \
  --prune \
  --force \
  --async
```

### Rollback

```bash
# 이전 버전으로 롤백
argocd app rollback auth-service

# 특정 리비전으로
argocd app rollback auth-service --id 5

# 또는 Git에서 revert
git revert HEAD  # values-prod.yaml 이전 버전으로
git push
# → ArgoCD가 자동으로 이전 버전 배포
```

---

## 🎯 장점

### GitOps 이점

```
1. Git = Single Source of Truth
   ✅ 모든 배포가 Git에 기록됨
   ✅ 배포 이력 추적 가능
   ✅ 특정 시점으로 롤백 쉬움

2. 자동 동기화
   ✅ Helm values 변경 → 3분 내 자동 배포
   ✅ Drift 감지 (실제 vs 선언 차이)
   ✅ Self-healing (수동 변경 자동 복구)

3. 선언적 배포
   ✅ kubectl apply 불필요
   ✅ Helm values만 수정
   ✅ ArgoCD가 알아서 처리

4. 감사 추적
   ✅ 누가 언제 무엇을 배포했는지
   ✅ Git Blame으로 추적
   ✅ 책임 소재 명확
```

### vs 기존 방식 (SSH 배포)

```
기존 (SSH + Docker Compose):
❌ SSH로 서버 접속
❌ docker-compose down/up
❌ 수동 작업 많음
❌ 배포 이력 추적 어려움
❌ Drift 감지 불가

GitOps (ArgoCD):
✅ Git Push만
✅ 자동 배포
✅ 이력 Git에 기록
✅ Drift 자동 감지
✅ Rollback 간단
```

---

## 📚 파일 체크리스트

### 생성/수정 필요

```bash
# GitHub Actions
.github/workflows/
├─ ci-build-auth.yml     ✅ 생성됨
├─ ci-build-users.yml    (auth 복사)
├─ ci-build-waste.yml    (auth 복사)
├─ ci-build-recycling.yml
├─ ci-build-locations.yml
└─ ci-common.yml         (shared/ 변경 시)

# Helm Charts
charts/
├─ auth/                 (생성 필요)
├─ users/
├─ waste/
├─ recycling/
└─ locations/

# ArgoCD
argocd/
├─ applications/
│   └─ all-services.yaml (생성 필요)
└─ ingress.yaml

# 삭제
.github/workflows/
├─ deploy.yml            (제거 또는 주석)
└─ deploy-aws-ecs.yml    (제거)
```

---

## 🚀 다음 단계

### 1. Helm Charts 생성

```bash
# 각 서비스별
helm create charts/auth
helm create charts/users
helm create charts/waste
helm create charts/recycling
helm create charts/locations

# values-prod.yaml 커스터마이징
```

### 2. GitHub Actions 복제

```bash
# auth 워크플로우 복사
for svc in users waste recycling locations; do
  cp .github/workflows/ci-build-auth.yml \
     .github/workflows/ci-build-$svc.yml
  
  # SERVICE_NAME 변경
  sed -i "s/SERVICE_NAME: auth/SERVICE_NAME: $svc/g" \
    .github/workflows/ci-build-$svc.yml
done
```

### 3. ArgoCD Applications 등록

```bash
kubectl apply -f argocd/applications/all-services.yaml
```

### 4. 첫 배포 테스트

```bash
# Auth 서비스 수정
echo "# test" >> services/auth/app/main.py
git add services/auth/
git commit -m "test: Test GitOps pipeline"
git push

# GitHub Actions 확인
# → Docker Hub 푸시
# → Helm values 업데이트
# → ArgoCD 자동 배포 (3분 이내)
```

---

## 📋 운영 체크리스트

### 배포 전

- [ ] Docker Hub 계정 생성
- [ ] GitHub Secrets 설정
- [ ] k3s 클러스터 준비
- [ ] ArgoCD 설치
- [ ] Helm Charts 작성 (5개 서비스)
- [ ] ArgoCD Applications 등록
- [ ] Ingress & SSL 설정

### 배포 후

- [ ] 모든 Application Synced 상태
- [ ] 모든 Pod Running 상태
- [ ] Ingress 접속 확인
- [ ] Health Check 정상
- [ ] 로그 확인 (에러 없음)

---

## 📚 참고 자료

- [ArgoCD 공식 문서](https://argo-cd.readthedocs.io/)
- [Helm 차트 작성 가이드](https://helm.sh/docs/chart_template_guide/)
- [GitOps Principles](https://www.gitops.tech/)

---

**작성일**: 2025-10-30  
**배포 방식**: GitHub Actions (CI) + ArgoCD (CD)  
**레지스트리**: Docker Hub  
**상태**: ✅ 최종 확정

