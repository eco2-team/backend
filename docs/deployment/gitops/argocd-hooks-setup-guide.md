# ArgoCD Hooks 설정 가이드 (Phase 3)

## 🎯 개요

Phase 3에서는 **ArgoCD Hooks**를 사용하여 Ansible 실행을 완전히 ArgoCD로 통합합니다. 이로써 **완전한 GitOps**를 달성합니다.

```yaml
Phase 2 (Atlantis + GitHub Actions):
  - Atlantis: Terraform
  - GitHub Actions: Ansible + ArgoCD Sync

Phase 3 (Atlantis + ArgoCD Hooks): ⭐
  - Atlantis: Terraform + ConfigMap 저장
  - ArgoCD PreSync Hook: Ansible (자동)
  - ArgoCD PostSync Hook: Node Labeling (자동)
  - GitHub Actions: 최소화 (ArgoCD Trigger만)
```

---

## 📊 최종 워크플로우 (Phase 3)

```yaml
┌─────────────────────────┐
│ 개발자: Feature PR      │
└──────────┬──────────────┘
           │
           ↓ (자동)
┌──────────────────────────────────────────┐
│ Atlantis: terraform plan                 │
│ - PR 코멘트에 Plan 결과 표시              │
└──────────┬───────────────────────────────┘
           │
           ↓ (팀원 승인 + "atlantis apply")
┌──────────────────────────────────────────┐
│ Atlantis: terraform apply                │
│ - EC2 인스턴스 생성 (10분)                │
│ - Terraform Outputs → ConfigMap 저장 ⭐   │
│ - ArgoCD Sync 트리거 (선택)               │
└──────────┬───────────────────────────────┘
           │
           ↓ (자동 Merge)
┌──────────────────────────────────────────┐
│ GitHub Actions: ArgoCD Sync Trigger      │
│ - 최소한의 역할만 수행                    │
└──────────┬───────────────────────────────┘
           │
           ↓ (자동)
┌──────────────────────────────────────────┐
│ ArgoCD PreSync Hook: Ansible Bootstrap   │ ⭐
│ - ConfigMap에서 인벤토리 읽기             │
│ - Ansible site.yml 실행 (20분)           │
└──────────┬───────────────────────────────┘
           │
           ↓ (자동)
┌──────────────────────────────────────────┐
│ ArgoCD Sync: K8s 리소스 배포             │
│ - Helm Chart 배포 (5분)                   │
└──────────┬───────────────────────────────┘
           │
           ↓ (자동)
┌──────────────────────────────────────────┐
│ ArgoCD PostSync Hook: Node Labeling      │ ⭐
│ - 노드 라벨링 자동 실행 (1분)             │
└──────────┬───────────────────────────────┘
           │
           ↓
┌──────────────────────────────────────────┐
│ Complete ✅                              │
└──────────────────────────────────────────┘

총 소요 시간: 36-40분
수동 개입: 2회 (PR 승인, "atlantis apply")
```

---

## ✅ 1단계: SSH Key Secret 생성

ArgoCD Hooks에서 Ansible이 SSH로 접속하려면 Secret이 필요합니다.

```bash
# SSH Key를 K8s Secret으로 생성
kubectl create secret generic k8s-cluster-ssh-key \
  --from-file=ssh-privatekey=~/.ssh/k8s-cluster-key.pem \
  --namespace=argocd

# Secret 확인
kubectl get secret k8s-cluster-ssh-key -n argocd
```

---

## ✅ 2단계: ArgoCD Application 배포

### Application with Hooks 적용

```bash
# ArgoCD Application 배포 (Hooks 포함)
kubectl apply -f argocd/application-14nodes-with-hooks.yaml

# Application 상태 확인
argocd app get sesacthon-infrastructure

# 또는 kubectl로 확인
kubectl get application sesacthon-infrastructure -n argocd
```

---

## ✅ 3단계: Atlantis Workflow 업데이트 완료 확인

`atlantis.yaml` 파일이 이미 업데이트되어 있습니다.

### 주요 변경사항

```yaml
# atlantis.yaml의 Apply Workflow

apply:
  steps:
    - init
    - apply
    
    # ⭐ ConfigMap에 Outputs 저장 (argocd namespace)
    - run: |
        terraform output -json > /tmp/tf-outputs.json
        terraform output -raw ansible_inventory > /tmp/ansible-inventory.ini
        
        kubectl create configmap terraform-outputs \
          --from-file=tf-outputs.json=/tmp/tf-outputs.json \
          --from-file=ansible-inventory.ini=/tmp/ansible-inventory.ini \
          --namespace=argocd \
          --dry-run=client -o yaml | kubectl apply -f -
        
        # ⭐ ArgoCD Sync 트리거 (선택)
        argocd app sync sesacthon-infrastructure --prune || true
```

---

## ✅ 4단계: 테스트 실행

### 전체 흐름 테스트

```bash
# 1. Feature 브랜치 생성
git checkout -b feature/test-phase3
vim terraform/main.tf  # 작은 변경 (주석 추가 등)
git add terraform/
git commit -m "Test Phase 3 ArgoCD Hooks"
git push origin feature/test-phase3

# 2. GitHub에서 PR 생성
# → Atlantis가 자동으로 terraform plan 실행

# 3. PR 승인 후 코멘트
# "atlantis apply -p infrastructure"

# → Atlantis가 terraform apply 실행
# → Terraform Outputs를 ConfigMap에 저장
# → ArgoCD Sync 트리거 (자동 또는 수동)

# 4. ArgoCD에서 확인
argocd app get sesacthon-infrastructure

# 5. Hook Job 로그 확인
# PreSync Hook (Ansible)
kubectl logs -n argocd job/ansible-bootstrap -f

# PostSync Hook (Node Labeling)
kubectl logs -n argocd job/label-nodes -f

# 6. 최종 결과 확인
kubectl get nodes --show-labels
kubectl get pods --all-namespaces
```

---

## 🔍 Hook 동작 확인

### PreSync Hook (Ansible Bootstrap)

```bash
# Job 상태 확인
kubectl get jobs -n argocd | grep ansible-bootstrap

# 로그 확인
kubectl logs -n argocd job/ansible-bootstrap -f

# 예상 로그:
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 🚀 Starting Ansible Bootstrap
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 📥 Cloning repository...
# 📝 Creating Ansible Inventory from ConfigMap...
# 🔍 Testing SSH connectivity...
# ⚙️ Running Ansible site.yml...
# ✅ Ansible Bootstrap Complete
```

### PostSync Hook (Node Labeling)

```bash
# Job 상태 확인
kubectl get jobs -n argocd | grep label-nodes

# 로그 확인
kubectl logs -n argocd job/label-nodes -f

# 예상 로그:
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 🏷️ Labeling Kubernetes Nodes
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 🔖 Labeling API Nodes...
#   - k8s-api-auth (domain=auth)
#   - k8s-api-my (domain=my)
#   ...
# ✅ Node Labeling Complete
```

---

## 📊 Phase 2 vs Phase 3 비교

### 역할 분담

| 구성 요소 | Phase 2 | Phase 3 | 개선 |
|----------|---------|---------|------|
| **Terraform** | Atlantis | Atlantis | 동일 |
| **Ansible** | GitHub Actions | ArgoCD PreSync Hook | GitOps |
| **Node Labels** | GitHub Actions | ArgoCD PostSync Hook | GitOps |
| **Outputs 전달** | GitHub Actions Artifact | ConfigMap (K8s Native) | 통합 |
| **GitHub Actions** | 3 Jobs (복잡) | 1 Job (단순) | 경량화 |

### GitHub Actions 역할 변화

```yaml
Phase 2 (GitHub Actions가 많은 일):
  - Terraform Plan/Apply
  - Ansible Bootstrap ← 제거됨
  - Node Labeling ← 제거됨
  - ArgoCD Sync

Phase 3 (GitHub Actions는 최소):
  - ArgoCD Sync Trigger만
  - 나머지는 Atlantis + ArgoCD가 처리
```

---

## 🎯 Phase 3의 핵심 이점

### 1️⃣ 완전한 GitOps

```yaml
모든 것이 Git + Kubernetes Native:
  ✅ Terraform State: S3 (Atlantis)
  ✅ Ansible Inventory: ConfigMap (K8s)
  ✅ Ansible 실행: ArgoCD Hook (K8s Job)
  ✅ Node Labeling: ArgoCD Hook (K8s Job)
  ✅ 앱 배포: ArgoCD Sync (K8s)

GitHub Actions는 옵션:
  - ArgoCD Sync는 Atlantis에서도 트리거 가능
  - GitHub Actions는 완전히 제거 가능
```

### 2️⃣ Kubernetes Native

```yaml
모든 워크로드가 K8s Job:
  ✅ 재시도 자동 (backoffLimit: 3)
  ✅ 리소스 제한 (CPU, Memory)
  ✅ 로그 추적 (kubectl logs)
  ✅ 자동 정리 (ttlSecondsAfterFinished)
```

### 3️⃣ 간극 완전 제거

```yaml
Before (Phase 2):
  Atlantis → ConfigMap → GitHub Actions → Ansible → ArgoCD
     ↓           ↓             ↓             ↓         ↓
   간극 1     간극 2        간극 3        간극 4    간극 5

After (Phase 3):
  Atlantis → ConfigMap → ArgoCD (PreSync → Sync → PostSync)
     ↓           ↓           ↓
  자동       자동         자동 (간극 0개!)
```

---

## 🔧 문제 해결

### 1. PreSync Hook (Ansible) 실패

```bash
# Job 상태 확인
kubectl get jobs -n argocd ansible-bootstrap

# 로그 확인
kubectl logs -n argocd job/ansible-bootstrap

# 일반적인 원인:
#   1. ConfigMap이 없음 (Atlantis가 아직 Apply 안함)
#   2. SSH Key Secret이 없음
#   3. EC2 인스턴스가 아직 준비 안됨
#   4. Security Group에서 SSH 차단

# 해결:
#   1. Atlantis로 먼저 terraform apply 실행
#   2. SSH Key Secret 생성 확인
#   3. EC2 상태 확인 (AWS Console)
#   4. Security Group 규칙 확인
```

### 2. PostSync Hook (Node Labeling) 실패

```bash
# Job 상태 확인
kubectl get jobs -n argocd label-nodes

# 로그 확인
kubectl logs -n argocd job/label-nodes

# 일반적인 원인:
#   1. 노드가 아직 Ready 상태가 아님
#   2. ServiceAccount 권한 부족

# 해결:
#   1. kubectl get nodes (Ready 상태 확인)
#   2. ServiceAccount 권한 확인:
#      kubectl auth can-i label nodes --as=system:serviceaccount:argocd:argocd-application-controller
```

### 3. ConfigMap에 Outputs 없음

```bash
# ConfigMap 확인
kubectl get configmap terraform-outputs -n argocd

# ConfigMap 내용 확인
kubectl get configmap terraform-outputs -n argocd -o yaml

# 원인:
#   - Atlantis가 아직 Apply 안함
#   - Atlantis Pod에 kubectl 권한 없음

# 해결:
#   1. Atlantis로 terraform apply 실행
#   2. Atlantis Pod의 kubeconfig 확인
```

---

## 🎉 최종 상태

### 달성한 목표

✅ **완전한 GitOps**: 모든 것이 Git + Kubernetes Native  
✅ **간극 제거**: Atlantis → ArgoCD (자동)  
✅ **GitHub Actions 최소화**: 1 Job만 (선택사항)  
✅ **Kubernetes Native**: 모든 워크로드가 K8s Job  
✅ **재시도 자동**: Job이 실패하면 자동 재시도  

### 스크립트 현황

```bash
제거: deploy-full-stack.sh, update-inventory.sh, validate-cluster.sh
유지: destroy-with-cleanup.sh, check-cluster-health.sh (응급용만)
총 스크립트: 2개 (최소화)
```

---

## 📊 전체 진행 상황

```yaml
✅ Phase 1: GitHub Actions (완료)
  - Terraform/Ansible/ArgoCD 자동화
  - 간극 제거 (Git Push → 완료)

✅ Phase 2: Atlantis (완료)
  - PR 기반 Terraform 관리
  - Terraform Lock 자동 관리

✅ Phase 3: ArgoCD Hooks (완료)
  - Ansible을 ArgoCD로 이동
  - 완전한 GitOps 달성
  - GitHub Actions 최소화
```

---

**작성일**: 2025-11-08  
**버전**: Phase 3 - ArgoCD Hooks  
**상태**: 완전한 GitOps 달성 ✅  
**다음**: SSH Key Secret 생성 → Application 배포 → 테스트

