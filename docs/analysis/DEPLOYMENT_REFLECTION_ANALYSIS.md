# 🔍 현재 배포 구조 분석 및 반영 범위

## 📊 현재 상황

### 1. **ArgoCD GitOps 구조**

```yaml
현재 ArgoCD 설정:
  source:
    repoURL: https://github.com/your-org/sesacthon-backend.git
    targetRevision: main
    path: charts/waste  # ⚠️ Helm Chart 경로
  
  syncPolicy:
    automated:
      prune: true
      selfHeal: true
```

**문제점**: 
- ✅ ArgoCD는 `charts/` 디렉토리만 모니터링
- ❌ 현재 저장소에는 `charts/` 디렉토리가 **존재하지 않음**
- ❌ `k8s/` 디렉토리에 YAML 파일이 있지만 ArgoCD가 모니터링 안 함

---

## 🎯 Main에 PR 시 반영 범위

### ✅ 자동 반영되는 것

#### 1. **문서 업데이트**
```
docs/
├── architecture/
│   └── ai-worker-queue-design.md  ✅ 자동 반영
└── plans/
    └── ...  ✅ 자동 반영

AI_WORKER_README.md  ✅ 자동 반영
```

#### 2. **코드 변경** (GitHub Actions가 있다면)
```
app/
├── core/
│   ├── celery_app.py
│   └── celery_config.py
└── tasks/
    ├── preprocess.py
    ├── vision.py
    ├── rag.py
    └── llm.py

workers/
├── preprocess_worker.py
├── vision_worker.py
├── rag_worker.py
└── llm_worker.py
```

**조건**: GitHub Actions에서 이미지 빌드 + GHCR 푸시 설정이 있어야 함

---

### ❌ 자동 반영되지 않는 것

#### 1. **Kubernetes 리소스** (가장 중요!)
```
k8s/
├── waste/
│   └── ai-workers-deployment.yaml  ❌ 자동 반영 안 됨
└── monitoring/
    ├── ai-pipeline-alerts.yaml  ❌ 자동 반영 안 됨
    └── ai-pipeline-dashboard.json  ❌ 자동 반영 안 됨
```

**이유**: ArgoCD가 `charts/` 경로를 모니터링하는데, 실제 파일은 `k8s/`에 있음

#### 2. **Worker 배치**
- Worker Pods (preprocess, vision, rag, llm)
- HPA (Horizontal Pod Autoscaler)
- ServiceMonitor (Prometheus)

---

## 🚧 인프라 반영 방법

### 현재 방식: Ansible로 수동 배포

```bash
# Terraform으로 인프라 생성
cd terraform
terraform apply

# Ansible로 클러스터 구성 (RabbitMQ, PostgreSQL, Redis 등)
cd ../ansible
ansible-playbook site.yml

# ArgoCD 설치 (Ansible)
ansible-playbook roles/argocd/tasks/main.yml
```

**특징**:
- ✅ 인프라 레벨 (노드, 네트워크, 스토리지): Terraform + Ansible로 관리
- ✅ 클러스터 애드온 (ArgoCD, RabbitMQ, PostgreSQL): Ansible로 관리
- ❌ 애플리케이션 배포: **현재 자동화 안 됨**

---

## 🔧 자동 배포를 위한 필요 작업

### Option 1: Helm Chart 추가 (권장)

```bash
# 1. Helm Chart 생성
helm create charts/waste

# 2. AI Worker Deployment를 Helm으로 변환
charts/waste/
├── Chart.yaml
├── values.yaml
└── templates/
    ├── ai-workers-deployment.yaml  # k8s/waste/ai-workers-deployment.yaml 이동
    ├── hpa.yaml
    └── servicemonitor.yaml

# 3. ArgoCD가 자동 감지
```

**장점**:
- ✅ ArgoCD 기존 설정과 호환
- ✅ 버전 관리 용이
- ✅ 환경별 설정 분리 (dev/staging/prod)

**단점**:
- ⚠️ Helm Chart 작성 시간 필요
- ⚠️ 기존 YAML 파일 변환 필요

---

### Option 2: ArgoCD Application 수정

```yaml
# argocd/applications/ai-workers.yaml (신규 생성)
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
    path: k8s/waste  # ⬅️ k8s/ 경로 직접 모니터링
  destination:
    server: https://kubernetes.default.svc
    namespace: waste
  syncPolicy:
    automated:
      prune: true
      selfHeal: true
```

```bash
# ArgoCD Application 등록
kubectl apply -f argocd/applications/ai-workers.yaml
```

**장점**:
- ✅ 빠른 적용 (추가 변환 작업 불필요)
- ✅ 현재 YAML 파일 그대로 사용

**단점**:
- ⚠️ 환경별 설정 분리 어려움
- ⚠️ 버전 관리 제한적

---

### Option 3: 수동 배포 (현재)

```bash
# Main에 PR 후 수동으로 배포
git pull origin main
kubectl apply -f k8s/waste/ai-workers-deployment.yaml
kubectl apply -f k8s/monitoring/ai-pipeline-alerts.yaml
```

**특징**:
- ✅ 즉시 배포 가능
- ❌ 자동화 안 됨
- ❌ 사람 실수 가능성

---

## 📋 요약: Main PR 후 자동 반영 여부

| 항목 | 자동 반영 | 방법 |
|------|----------|------|
| **문서 업데이트** | ✅ 예 | Git Merge만 하면 됨 |
| **코드 변경** | ⚠️ 조건부 | GitHub Actions + 이미지 빌드 필요 |
| **Kubernetes 리소스** | ❌ 아니오 | **수동 배포 필요** (kubectl apply) |
| **Worker 배치** | ❌ 아니오 | **수동 배포 필요** |
| **Monitoring 설정** | ❌ 아니오 | **수동 배포 필요** |
| **인프라 변경** | ❌ 아니오 | Terraform + Ansible 재실행 |

---

## 🎯 권장 사항

### 즉시 (현재 PR)

```bash
# 1. Main에 PR + Merge
git push origin feature/queue-structure-update
# GitHub에서 PR 생성 → Merge

# 2. 클러스터에 수동 배포
kubectl apply -f k8s/waste/ai-workers-deployment.yaml
kubectl apply -f k8s/monitoring/ai-pipeline-alerts.yaml

# 3. ConfigMap 생성 (JSON 규칙 파일)
kubectl create configmap waste-rules \
  --from-file=rules/ \
  --namespace=waste

# 4. Secret 생성 (OpenAI API Key)
kubectl create secret generic openai-secrets \
  --from-literal=api-key=sk-... \
  --namespace=waste
```

### 단기 (1주 내)

**Helm Chart 작성 또는 ArgoCD Application 추가**

```bash
# Option A: Helm Chart
helm create charts/waste
mv k8s/waste/* charts/waste/templates/

# Option B: ArgoCD Application
cat > argocd/applications/ai-workers.yaml <<EOF
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: ai-workers
  namespace: argocd
spec:
  source:
    path: k8s/waste
  syncPolicy:
    automated:
      prune: true
      selfHeal: true
EOF

kubectl apply -f argocd/applications/ai-workers.yaml
```

---

**최종 답변**: 
- **문서만 자동 반영됨** (Git Merge 시)
- **큐 로직 (코드)**은 GitHub Actions 설정 필요
- **인프라 (K8s 리소스)**는 **자동 반영 안 됨** → 수동 배포 필수
- **자동화 원한다면**: Helm Chart 작성 또는 ArgoCD Application 추가 필요

