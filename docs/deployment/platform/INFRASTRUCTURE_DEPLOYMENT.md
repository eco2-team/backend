# Infrastructure Deployment - GitOps Architecture

## 📊 전체 구조

```
┌─────────────────────────────────────────────────────────────────┐
│ GitOps Architecture (완전한 선언적 구조)                         │
└─────────────────────────────────────────────────────────────────┘

1️⃣ Terraform (Infrastructure as Code)
   └─ Atlantis (PR 기반 GitOps)
      ├─ PR 생성 → atlantis plan
      ├─ 리뷰 → atlantis apply
      └─ State: S3 Backend

2️⃣ Kubernetes (Cluster Management)
   └─ Ansible (초기 부트스트랩)
      ├─ K8s 설치
      ├─ ArgoCD 설치
      └─ Atlantis 설치

3️⃣ Applications (App Deployment)
   └─ ArgoCD App of Apps
      ├─ Wave 0: Infrastructure (Kustomize)
      ├─ Wave 1: Databases (Ansible roles)
      └─ Wave 3: API Services (Kustomize + ApplicationSet)
```

---

## 🚀 배포 방법

### 초기 설정 (한 번만)

#### Step 1: Terraform으로 Infrastructure 생성

Atlantis를 사용하거나 로컬에서 실행:

```bash
# Option A: Atlantis (권장 - PR 기반)
# 1. terraform/ 변경사항을 담은 PR 생성
# 2. PR에 코멘트: atlantis plan
# 3. 결과 확인 후: atlantis apply

# Option B: 로컬 실행 (초기 설정)
cd terraform
terraform init
terraform apply
```

#### Step 2: Ansible로 Kubernetes 부트스트랩

GitHub Actions 또는 로컬에서 실행:

```bash
# Option A: GitHub Actions (권장)
# Repository → Actions → Infrastructure Bootstrap → Run workflow

# Option B: 로컬 실행
cd ansible
ansible-playbook site.yml -i inventory/hosts.ini
```

#### Step 3: ArgoCD Root Application 배포

```bash
# Kubernetes 클러스터에 접속 후
kubectl apply -f argocd/root-app.yaml

# 동기화 확인
kubectl get applications -n argocd
argocd app get root-app
```

---

## 📁 디렉토리 구조

```
backend/
├── terraform/                    # Terraform (Atlantis 관리)
│   ├── main.tf
│   ├── outputs.tf
│   └── ...
│
├── ansible/                      # Ansible (초기 부트스트랩)
│   ├── site.yml                 # 전체 플레이북
│   ├── playbooks/
│   │   ├── 09-atlantis.yml     # Atlantis 설치
│   │   └── ...
│   └── roles/
│       ├── argocd/
│       ├── postgresql/
│       ├── redis/
│       └── rabbitmq/
│
├── argocd/                       # ArgoCD Applications
│   ├── root-app.yaml            # App of Apps (최상위)
│   └── apps/                    # 하위 Applications
│       ├── infrastructure.yaml   # Wave 0
│       └── api-services.yaml    # Wave 3
│
├── k8s/                          # Kubernetes Manifests
│   ├── infrastructure/          # Wave 0 (Kustomize)
│   │   ├── namespaces/
│   │   ├── networkpolicies/
│   │   ├── monitoring/
│   │   └── kustomization.yaml
│   │
│   ├── base/                    # API 공통 (Kustomize)
│   │   └── kustomization.yaml
│   │
│   └── overlays/                # API 도메인별 (Kustomize)
│       ├── auth/
│       ├── my/
│       └── scan/
│
└── .github/workflows/
    └── infrastructure-bootstrap.yml  # 초기 부트스트랩용
```

---

## 🔄 운영 방법

### Terraform 변경 (Atlantis)

```bash
# 1. terraform/ 변경
git checkout -b feat/add-new-node
# ... terraform 파일 수정 ...
git commit -m "feat: Add new API node"
git push origin feat/add-new-node

# 2. PR 생성
# GitHub에서 PR 생성

# 3. Atlantis Plan
# PR에 코멘트: atlantis plan

# 4. 리뷰 및 승인

# 5. Atlantis Apply
# PR에 코멘트: atlantis apply

# 6. PR 머지
```

### Infrastructure 변경 (ArgoCD)

```bash
# 1. k8s/infrastructure/ 변경
git checkout -b feat/update-networkpolicy
# ... YAML 파일 수정 ...
git commit -m "feat: Update network policy"
git push origin feat/update-networkpolicy

# 2. PR 생성 및 머지

# 3. ArgoCD 자동 동기화
# ArgoCD가 변경사항을 감지하고 자동 적용
```

### Application 배포 (ArgoCD)

```bash
# 1. k8s/overlays/{domain}/ 변경
git checkout -b feat/update-auth-api
# ... deployment-patch.yaml 수정 ...
git commit -m "feat: Update auth API deployment"
git push origin feat/update-auth-api

# 2. PR 생성 및 머지

# 3. ArgoCD 자동 동기화
# 해당 도메인의 Application만 업데이트
```

---

## 🎯 배포 순서 (Sync Waves)

ArgoCD는 다음 순서로 배포합니다:

```
Wave 0: Infrastructure (먼저)
  ├─ Namespaces
  ├─ NetworkPolicies
  └─ ServiceMonitors

Wave 1: Databases (Ansible roles - 수동)
  ├─ PostgreSQL
  ├─ Redis
  └─ RabbitMQ

Wave 3: API Services (마지막)
  ├─ Phase 1: auth, my, scan
  ├─ Phase 2: character, location
  └─ Phase 3: info, chat
```

---

## ✅ 장점

### Terraform + Atlantis
- ✅ PR 기반 리뷰 (Code Review)
- ✅ 자동 Lock 관리
- ✅ Git 히스토리 연동
- ✅ State 안전 관리

### ArgoCD + Kustomize
- ✅ 선언적 상태 관리
- ✅ Git = Single Source of Truth
- ✅ 자동 Drift 감지 및 복구
- ✅ 쉬운 롤백 (Git revert)

### App of Apps 패턴
- ✅ 명확한 배포 순서
- ✅ 계층적 구조
- ✅ 대규모 확장 용이

---

## 🔗 참고 문서

- [GITOPS_BEST_PRACTICES.md](../architecture/gitops/GITOPS_BEST_PRACTICES.md)
- [KUSTOMIZE_APP_OF_APPS.md](../architecture/gitops/KUSTOMIZE_APP_OF_APPS.md)
- [Atlantis Setup Guide](../deployment/gitops/ATLANTIS_SETUP.md)
- [ArgoCD Documentation](https://argo-cd.readthedocs.io/)

---

**작성일**: 2025-11-14  
**상태**: GitOps Architecture 완성 ✅  
**다음**: 초기 배포 및 검증

