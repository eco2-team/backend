# 🎯 최소 변경으로 통합 배포 전략

## 📊 현재 상황 분석

### ✅ 발견 사항

```yaml
현재 클러스터 상태:
  ArgoCD: ✅ 설치됨 (Ansible)
  ArgoCD Applications: ❌ 등록 안 됨
  charts/ 디렉토리: ❌ 없음
  k8s/ 디렉토리: ✅ AI Worker YAML 있음

결론: 
  → ArgoCD는 설치만 되어 있음
  → 아직 어떤 Application도 등록 안 됨
  → 완전 재구축 불필요! ✅
```

---

## 🚀 통합 배포 전략 (최소 변경)

### Option A: Helm Chart 구조 (권장 ⭐)

**완전 재구축 불필요! 단순 디렉토리 추가만 하면 됨**

#### 1. 파일 구조 변경

```bash
현재:
backend/
├── k8s/
│   ├── waste/
│   │   └── ai-workers-deployment.yaml
│   └── monitoring/
│       ├── ai-pipeline-alerts.yaml
│       └── ai-pipeline-dashboard.json
├── app/
│   └── tasks/
└── workers/

변경 후:
backend/
├── charts/  # ⬅️ 새로 추가
│   └── ai-workers/
│       ├── Chart.yaml
│       ├── values.yaml
│       ├── values-prod.yaml
│       └── templates/
│           ├── preprocess-deployment.yaml  # k8s/waste/ 에서 이동
│           ├── vision-deployment.yaml
│           ├── rag-deployment.yaml
│           ├── llm-deployment.yaml
│           ├── hpa.yaml
│           └── servicemonitor.yaml
├── k8s/
│   └── argocd/  # ⬅️ 새로 추가
│       └── ai-workers-app.yaml
├── app/
│   └── tasks/
└── workers/
```

#### 2. 구현 단계 (30분)

```bash
# Step 1: Helm Chart 생성 (5분)
helm create charts/ai-workers
rm -rf charts/ai-workers/templates/*  # 기본 템플릿 삭제

# Step 2: 기존 YAML을 4개로 분리 (15분)
# k8s/waste/ai-workers-deployment.yaml 내용을 분리:
#   → charts/ai-workers/templates/preprocess-deployment.yaml
#   → charts/ai-workers/templates/vision-deployment.yaml
#   → charts/ai-workers/templates/rag-deployment.yaml
#   → charts/ai-workers/templates/llm-deployment.yaml

# Step 3: Chart.yaml 작성 (2분)
cat > charts/ai-workers/Chart.yaml <<EOF
apiVersion: v2
name: ai-workers
description: AI Worker Pipeline
version: 1.0.0
appVersion: "1.0.0"
EOF

# Step 4: values.yaml 작성 (5분)
cat > charts/ai-workers/values.yaml <<EOF
image:
  registry: ghcr.io
  repository: your-org/waste-service
  tag: latest

celery:
  broker: "amqp://admin:password@rabbitmq.messaging:5672//"
  backend: "redis://redis.default:6379/1"

preprocessWorker:
  replicas: 3
  resources:
    requests:
      cpu: 300m
      memory: 256Mi
# ... (나머지 설정)
EOF

# Step 5: ArgoCD Application 생성 (3분)
mkdir -p k8s/argocd
cat > k8s/argocd/ai-workers-app.yaml <<EOF
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: ai-workers
  namespace: argocd
spec:
  project: default
  source:
    repoURL: https://github.com/your-org/sesacthon-backend.git
    targetRevision: main
    path: charts/ai-workers  # ⬅️ 여기!
    helm:
      valueFiles:
        - values.yaml
  destination:
    server: https://kubernetes.default.svc
    namespace: waste
  syncPolicy:
    automated:
      prune: true
      selfHeal: true
    syncOptions:
      - CreateNamespace=true
EOF
```

#### 3. 배포 (즉시)

```bash
# 1. Main에 Push
git add charts/ k8s/argocd/
git commit -m "feat: Add Helm Chart for AI Workers"
git push origin feature/queue-structure-update

# 2. PR Merge

# 3. 클러스터에 ArgoCD Application 등록
kubectl apply -f k8s/argocd/ai-workers-app.yaml

# 4. 자동 동기화 확인
argocd app get ai-workers
argocd app sync ai-workers  # 수동 sync (필요 시)

# ✅ 완료! 이후로는 자동 배포됨
```

---

### Option B: k8s/ 디렉토리 직접 사용 (빠름 ⚡)

**가장 빠른 방법! 5분 완료**

#### 1. ArgoCD Application만 추가

```bash
# Step 1: ArgoCD Application 생성 (3분)
mkdir -p k8s/argocd
cat > k8s/argocd/ai-workers-app.yaml <<EOF
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: ai-workers
  namespace: argocd
spec:
  project: default
  source:
    repoURL: https://github.com/your-org/sesacthon-backend.git
    targetRevision: main
    path: k8s/waste  # ⬅️ 기존 YAML 경로
  destination:
    server: https://kubernetes.default.svc
    namespace: waste
  syncPolicy:
    automated:
      prune: true
      selfHeal: true
    syncOptions:
      - CreateNamespace=true
EOF

# Step 2: 배포 (2분)
git add k8s/argocd/
git commit -m "feat: Add ArgoCD Application for AI Workers"
git push origin feature/queue-structure-update

# PR Merge 후
kubectl apply -f k8s/argocd/ai-workers-app.yaml

# ✅ 완료! 자동 배포 시작
```

#### 2. 파일 구조 (변경 최소!)

```
backend/
├── k8s/
│   ├── argocd/  # ⬅️ 새로 추가 (1개 파일)
│   │   └── ai-workers-app.yaml
│   ├── waste/  # ⬅️ 기존 유지
│   │   └── ai-workers-deployment.yaml
│   └── monitoring/  # ⬅️ 기존 유지
│       ├── ai-pipeline-alerts.yaml
│       └── ai-pipeline-dashboard.json
├── app/
├── workers/
└── ... (나머지 기존 구조)
```

---

## 📊 비교표

| 항목 | Option A (Helm) | Option B (k8s/) |
|------|----------------|----------------|
| **작업 시간** | 30분 | 5분 ⚡ |
| **파일 변경** | 많음 (디렉토리 이동) | 최소 (1개 추가) |
| **환경별 설정** | ✅ 쉬움 (values) | ⚠️ 어려움 |
| **장기 유지보수** | ✅ 우수 | ⚠️ 보통 |
| **즉시 배포** | ✅ 가능 | ✅ 가능 |
| **재구축 필요** | ❌ 불필요 | ❌ 불필요 |

---

## 🎯 최종 권장 방안

### **단계적 접근 (Best!)** ⭐⭐⭐

```
Phase 1 (지금 - 5분):
  ✅ Option B로 즉시 자동화
  ✅ ArgoCD Application만 추가
  ✅ 완전 재구축 불필요
  ✅ 기존 구조 유지

  git add k8s/argocd/ai-workers-app.yaml
  kubectl apply -f k8s/argocd/ai-workers-app.yaml
  
  → 자동 배포 즉시 작동! ✅

Phase 2 (여유 있을 때 - 30분):
  ✅ Option A로 마이그레이션
  ✅ Helm Chart 구조로 전환
  ✅ 환경별 설정 분리
  ✅ 프로덕션 품질 확보

  helm create charts/ai-workers
  mv k8s/waste/* → charts/ai-workers/templates/
  
  → 점진적 개선! ✅
```

---

## 🚧 작업 스크립트 (Option B - 5분)

### 즉시 실행 가능한 스크립트

```bash
#!/bin/bash
# scripts/setup-argocd-app.sh

set -e

echo "🚀 ArgoCD Application 설정 중..."

# 1. argocd 디렉토리 생성
mkdir -p k8s/argocd

# 2. ArgoCD Application YAML 생성
cat > k8s/argocd/ai-workers-app.yaml <<'EOF'
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: ai-workers
  namespace: argocd
  finalizers:
    - resources-finalizer.argocd.argoproj.io
spec:
  project: default
  
  source:
    repoURL: https://github.com/your-org/sesacthon-backend.git
    targetRevision: main
    path: k8s/waste
  
  destination:
    server: https://kubernetes.default.svc
    namespace: waste
  
  syncPolicy:
    automated:
      prune: true
      selfHeal: true
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
  
  ignoreDifferences:
  - group: apps
    kind: Deployment
    jsonPointers:
    - /spec/replicas
EOF

echo "✅ ArgoCD Application YAML 생성 완료"
echo ""
echo "📋 다음 단계:"
echo "1. Git에 커밋:"
echo "   git add k8s/argocd/"
echo "   git commit -m 'feat: Add ArgoCD Application for AI Workers'"
echo "   git push origin feature/queue-structure-update"
echo ""
echo "2. PR Merge 후 배포:"
echo "   kubectl apply -f k8s/argocd/ai-workers-app.yaml"
echo ""
echo "3. 상태 확인:"
echo "   argocd app get ai-workers"
```

### 실행

```bash
# 스크립트 실행
chmod +x scripts/setup-argocd-app.sh
./scripts/setup-argocd-app.sh

# Git 커밋
git add k8s/argocd/
git commit -m "feat: Add ArgoCD Application for AI Workers"
git push

# PR Merge 후
kubectl apply -f k8s/argocd/ai-workers-app.yaml

# 확인
argocd app get ai-workers
kubectl get pods -n waste
```

---

## ✅ 결론

### 완전 재구축 불필요! ✅

```yaml
현재 상황:
  - ArgoCD 설치됨
  - Application은 등록 안 됨
  - 기존 인프라 정상

필요한 작업:
  - ArgoCD Application YAML 1개 추가
  - kubectl apply 1회 실행
  
소요 시간: 5분
재구축: 불필요
리스크: 매우 낮음
```

### 추천: Option B (5분) → 나중에 Option A (30분)

1. **지금 (5분)**
   - `k8s/argocd/ai-workers-app.yaml` 추가
   - `kubectl apply` 실행
   - ✅ 자동 배포 완성!

2. **나중에 (30분)**
   - Helm Chart로 마이그레이션
   - 환경별 설정 분리
   - ✅ 프로덕션 품질!

---

**어떤 방식으로 진행하시겠습니까?** 🤔
- A) Option B로 즉시 자동화 (5분) ⚡
- B) Option A로 Helm Chart 구조 (30분) 📦
- C) 단계적 접근 (Option B → A) ⭐

