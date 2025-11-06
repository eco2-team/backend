# 🎯 Helm Chart 기반 통합 배포 구조 (권장)

## 💡 핵심 개념

### 왜 Helm Chart인가?

```yaml
Option 1 (ArgoCD Application):
  개발 후 배포 시:
    ❌ 새 서비스마다 Application YAML 추가
    ❌ k8s/service1/, k8s/service2/ ... 디렉토리 늘어남
    ❌ 중복된 설정 (replicas, resources 등)
    ❌ 관리 포인트 증가

Option 2 (Helm Chart):
  개발 후 배포 시:
    ✅ charts/ 하나만 수정
    ✅ 환경별 values만 변경
    ✅ 템플릿 재사용
    ✅ 관리 포인트 단순화
```

---

## 🏗️ 통합 Helm Chart 구조

### 디렉토리 구조

```
backend/
├── charts/
│   └── growbin-backend/  # ⬅️ 전체 백엔드를 하나의 Chart로!
│       ├── Chart.yaml
│       ├── values.yaml
│       ├── values-dev.yaml
│       ├── values-staging.yaml
│       ├── values-prod.yaml
│       └── templates/
│           ├── _helpers.tpl  # 공통 템플릿
│           │
│           ├── ai-workers/  # AI Worker
│           │   ├── preprocess-deployment.yaml
│           │   ├── vision-deployment.yaml
│           │   ├── rag-deployment.yaml
│           │   ├── llm-deployment.yaml
│           │   └── hpa.yaml
│           │
│           ├── api/  # FastAPI 서비스
│           │   ├── waste-deployment.yaml
│           │   ├── users-deployment.yaml
│           │   ├── auth-deployment.yaml
│           │   ├── recycling-deployment.yaml
│           │   └── locations-deployment.yaml
│           │
│           ├── ingress/  # Ingress 설정
│           │   └── api-ingress.yaml
│           │
│           └── monitoring/  # 모니터링
│               ├── servicemonitor.yaml
│               └── prometheusrule.yaml
│
├── k8s/
│   └── argocd/
│       └── growbin-backend-app.yaml  # ⬅️ ArgoCD Application 1개만!
│
├── app/
│   ├── api/
│   │   ├── waste/
│   │   ├── users/
│   │   └── auth/
│   └── tasks/
│       ├── preprocess.py
│       ├── vision.py
│       ├── rag.py
│       └── llm.py
│
└── workers/
    ├── preprocess_worker.py
    ├── vision_worker.py
    ├── rag_worker.py
    └── llm_worker.py
```

---

## 📝 핵심 파일 예시

### 1. Chart.yaml (메타데이터)

```yaml
# charts/growbin-backend/Chart.yaml
apiVersion: v2
name: growbin-backend
description: GrowBin Backend - Complete Application Stack
type: application
version: 1.0.0  # Chart 버전
appVersion: "1.0.0"  # 앱 버전

keywords:
  - backend
  - fastapi
  - ai
  - celery
  - waste-management

maintainers:
  - name: GrowBin Team
    email: team@growbin.app

dependencies: []  # 외부 Chart 의존성 (필요 시)
```

### 2. values.yaml (기본 설정)

```yaml
# charts/growbin-backend/values.yaml

# Global 설정
global:
  image:
    registry: ghcr.io
    repository: your-org/growbin-backend
    tag: latest  # ⬅️ 배포 시 자동 업데이트
    pullPolicy: IfNotPresent
  
  domain: growbin.app
  environment: production

# Celery/RabbitMQ
celery:
  broker: "amqp://admin:password@rabbitmq.messaging:5672//"
  backend: "redis://redis.default:6379/1"

# OpenAI
openai:
  apiKeySecret: openai-secrets
  models:
    vision: "gpt-5-vision-preview"
    llm: "gpt-4o-mini"

#
# AI Workers
#
aiWorkers:
  enabled: true  # ⬅️ 활성화/비활성화 간단
  
  preprocess:
    enabled: true
    replicas: 3
    resources:
      requests: { cpu: 300m, memory: 256Mi }
      limits: { cpu: 1000m, memory: 512Mi }
    nodeSelector:
      workload: async-workers
  
  vision:
    enabled: true
    replicas: 5
    resources:
      requests: { cpu: 100m, memory: 256Mi }
      limits: { cpu: 500m, memory: 512Mi }
    autoscaling:
      enabled: true
      minReplicas: 5
      maxReplicas: 8
      targetCPUUtilizationPercentage: 70
  
  rag:
    enabled: true
    replicas: 2
    resources:
      requests: { cpu: 100m, memory: 128Mi }
      limits: { cpu: 300m, memory: 256Mi }
  
  llm:
    enabled: true
    replicas: 3
    resources:
      requests: { cpu: 100m, memory: 256Mi }
      limits: { cpu: 500m, memory: 512Mi }

#
# FastAPI Services
#
api:
  enabled: true
  
  waste:
    enabled: true
    replicas: 3
    resources:
      requests: { cpu: 200m, memory: 256Mi }
      limits: { cpu: 1000m, memory: 512Mi }
    path: /api/v1/waste
  
  users:
    enabled: true
    replicas: 2
    resources:
      requests: { cpu: 100m, memory: 128Mi }
      limits: { cpu: 500m, memory: 256Mi }
    path: /api/v1/users
  
  auth:
    enabled: true
    replicas: 2
    resources:
      requests: { cpu: 100m, memory: 128Mi }
      limits: { cpu: 500m, memory: 256Mi }
    path: /api/v1/auth
  
  recycling:
    enabled: false  # ⬅️ 아직 개발 안 됨
    replicas: 2
    path: /api/v1/recycling
  
  locations:
    enabled: false  # ⬅️ 아직 개발 안 됨
    replicas: 2
    path: /api/v1/locations

#
# Ingress
#
ingress:
  enabled: true
  className: alb
  annotations:
    alb.ingress.kubernetes.io/scheme: internet-facing
    alb.ingress.kubernetes.io/target-type: instance
    alb.ingress.kubernetes.io/group.name: growbin-alb
  tls:
    enabled: true
    certificateArn: "arn:aws:acm:..."

#
# Monitoring
#
monitoring:
  enabled: true
  serviceMonitor:
    enabled: true
    interval: 30s
  prometheusRule:
    enabled: true
```

### 3. values-prod.yaml (프로덕션 오버라이드)

```yaml
# charts/growbin-backend/values-prod.yaml

global:
  image:
    tag: "v1.2.3"  # ⬅️ 프로덕션 태그
  environment: production

# AI Worker 증가
aiWorkers:
  vision:
    replicas: 8
    autoscaling:
      minReplicas: 8
      maxReplicas: 12

# API 서비스 증가
api:
  waste:
    replicas: 5
  users:
    replicas: 3
  auth:
    replicas: 3

# 리소스 증가
resources:
  requests:
    cpu: 500m
    memory: 512Mi
```

### 4. ArgoCD Application (1개만!)

```yaml
# k8s/argocd/growbin-backend-app.yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: growbin-backend
  namespace: argocd
  finalizers:
    - resources-finalizer.argocd.argoproj.io
spec:
  project: default
  
  source:
    repoURL: https://github.com/your-org/sesacthon-backend.git
    targetRevision: main
    path: charts/growbin-backend  # ⬅️ 하나의 Chart
    helm:
      valueFiles:
        - values-prod.yaml  # ⬅️ 환경별 values만 변경
  
  destination:
    server: https://kubernetes.default.svc
    namespace: default
  
  syncPolicy:
    automated:
      prune: true
      selfHeal: true
    syncOptions:
      - CreateNamespace=true
  
  ignoreDifferences:
  - group: apps
    kind: Deployment
    jsonPointers:
    - /spec/replicas
```

---

## 🚀 개발 후 배포 워크플로우

### 시나리오 1: 새로운 API 서비스 추가

```bash
# 예: Locations Service 개발 완료

# 1. values.yaml만 수정 (1분)
vim charts/growbin-backend/values.yaml
```

```yaml
api:
  locations:
    enabled: true  # ⬅️ false → true
    replicas: 2
    path: /api/v1/locations
```

```bash
# 2. 템플릿 추가 (5분)
cat > charts/growbin-backend/templates/api/locations-deployment.yaml <<EOF
{{- if .Values.api.locations.enabled }}
apiVersion: apps/v1
kind: Deployment
metadata:
  name: {{ include "growbin-backend.fullname" . }}-locations
spec:
  replicas: {{ .Values.api.locations.replicas }}
  # ... (템플릿 활용)
{{- end }}
EOF

# 3. Git Push (자동 배포!)
git add charts/
git commit -m "feat: Add Locations API"
git push origin main

# ✅ 완료! ArgoCD가 자동으로 배포
# ✅ 새로운 Application 생성 불필요!
```

### 시나리오 2: Vision Worker Replica 증가

```bash
# 1. values-prod.yaml만 수정
vim charts/growbin-backend/values-prod.yaml
```

```yaml
aiWorkers:
  vision:
    replicas: 10  # ⬅️ 5 → 10
```

```bash
# 2. Git Push
git commit -am "scale: Increase vision worker replicas to 10"
git push origin main

# ✅ 완료! 자동 스케일 아웃
```

### 시나리오 3: 새 기능 배포 (이미지 업데이트)

```bash
# GitHub Actions가 자동으로:
# 1. 이미지 빌드: ghcr.io/org/growbin-backend:v1.3.0
# 2. values.yaml 업데이트:

sed -i 's/tag: .*/tag: v1.3.0/' charts/growbin-backend/values.yaml
git commit -am "chore: Update image to v1.3.0"
git push

# ✅ ArgoCD가 감지하고 자동 배포!
```

---

## 📊 비교: 개발 후 배포 시

### ❌ 개별 Application 방식

```bash
# 새 서비스 추가마다:

1. k8s/service-name/ 디렉토리 생성
2. deployment.yaml, service.yaml 작성
3. k8s/argocd/service-name-app.yaml 생성  # ⬅️ 매번!
4. kubectl apply -f k8s/argocd/service-name-app.yaml

관리 포인트:
  - ArgoCD Applications: 10개+
  - 디렉토리: k8s/service1/, k8s/service2/, ...
  - 중복 설정 다수
```

### ✅ Helm Chart 방식

```bash
# 새 서비스 추가 시:

1. values.yaml에 enabled: true  # ⬅️ 1줄!
2. templates/ 템플릿 추가 (재사용)
3. git push

관리 포인트:
  - ArgoCD Applications: 1개
  - 디렉토리: charts/growbin-backend/
  - 설정 중앙화
```

---

## 🎯 실전 예시: 5개 서비스 운영

### Helm Chart 구조

```yaml
# values.yaml (중앙 관리)
api:
  waste:    { enabled: true,  replicas: 3 }
  users:    { enabled: true,  replicas: 2 }
  auth:     { enabled: true,  replicas: 2 }
  recycling: { enabled: true,  replicas: 2 }  # ⬅️ 새로 추가
  locations: { enabled: true,  replicas: 2 }  # ⬅️ 새로 추가

aiWorkers:
  preprocess: { enabled: true, replicas: 3 }
  vision:     { enabled: true, replicas: 5 }
  rag:        { enabled: true, replicas: 2 }
  llm:        { enabled: true, replicas: 3 }
```

**ArgoCD Application**: 1개
**배포**: `git push` 한 번

---

## 🔧 마이그레이션 계획

### Phase 1: Helm Chart 생성 (1시간)

```bash
# 1. Chart 생성
helm create charts/growbin-backend
rm -rf charts/growbin-backend/templates/*

# 2. 기존 k8s/waste/ → charts/templates/ai-workers/ 이동
mkdir -p charts/growbin-backend/templates/ai-workers
mv k8s/waste/ai-workers-deployment.yaml \
   charts/growbin-backend/templates/ai-workers/

# 3. 템플릿화 (변수 치환)
# replicas: 3 → replicas: {{ .Values.aiWorkers.preprocess.replicas }}

# 4. values.yaml 작성
vim charts/growbin-backend/values.yaml
```

### Phase 2: ArgoCD Application 업데이트 (5분)

```yaml
# k8s/argocd/growbin-backend-app.yaml
spec:
  source:
    path: charts/growbin-backend  # ⬅️ 변경
    helm:
      valueFiles:
        - values-prod.yaml
```

```bash
kubectl apply -f k8s/argocd/growbin-backend-app.yaml
argocd app sync growbin-backend
```

### Phase 3: 검증 (10분)

```bash
# 배포 확인
argocd app get growbin-backend
kubectl get pods -n waste
kubectl get pods -n default

# Rollback 테스트
git revert HEAD
git push
# → 자동 롤백됨
```

---

## 💡 최종 권장 사항

### ✅ Helm Chart 구조로 시작 (1시간 투자)

**이유**:
1. **효율성**: 새 서비스 추가 시 1분
2. **중앙 관리**: values.yaml 하나만 보면 됨
3. **환경 분리**: dev/staging/prod 간단
4. **확장성**: 10개, 20개 서비스도 동일

**투자 대비 효과**:
```
초기: 1시간 소요
이후: 매번 5분 절약 × 20회 배포 = 100분 절약
ROI: 약 10,000% ⚡
```

### 📋 체크리스트

```bash
✅ 1. Helm Chart 생성
  helm create charts/growbin-backend

✅ 2. 기존 YAML 이동 및 템플릿화
  k8s/waste/ → charts/templates/ai-workers/
  
✅ 3. values.yaml 작성
  전역 설정, 서비스별 설정
  
✅ 4. ArgoCD Application 수정
  path: charts/growbin-backend
  
✅ 5. 배포 및 검증
  kubectl apply -f k8s/argocd/
  argocd app sync growbin-backend

✅ 6. CI/CD 통합
  GitHub Actions → 이미지 태그 업데이트
```

---

## 🚀 다음 단계

```bash
# 1. Helm Chart 스켈레톤 생성 스크립트 실행
./scripts/create-helm-chart.sh

# 2. 기존 YAML 템플릿화
./scripts/migrate-to-helm.sh

# 3. 배포
git add charts/
git commit -m "feat: Migrate to Helm Chart structure"
git push origin main

# 4. ArgoCD Application 업데이트
kubectl apply -f k8s/argocd/growbin-backend-app.yaml

# ✅ 완료! 이후 모든 배포가 간단해짐
```

---

**결론**: Helm Chart 구조가 장기적으로 훨씬 효율적입니다! 1시간 투자로 이후 모든 배포가 간단해집니다. 🎯

