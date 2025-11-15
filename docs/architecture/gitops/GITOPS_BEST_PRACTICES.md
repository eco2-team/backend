# GitOps 베스트 프랙티스 - Infrastructure & Application 통합

## 📋 현재 구조의 문제점

### ❌ 일관성 없는 배포 방식

```
Infrastructure: GitHub Actions (Push) → Cluster
Application:   Git → ArgoCD (Pull) → Cluster
```

**문제**:
1. Push vs Pull 방식 혼재
2. GitOps 원칙 부분 적용
3. Infrastructure 변경 추적 어려움
4. 롤백 복잡도 증가

---

## ✅ 권장 구조: App of Apps 패턴

### 구조도

```
┌────────────────────────────────────────────────────────────────┐
│ Git Repository (Single Source of Truth)                        │
│                                                                 │
│ backend/                                                        │
│ ├─ terraform/           # Terraform으로 EC2/VPC 생성          │
│ ├─ argocd/                                                     │
│ │  ├─ root-app.yaml    # Root Application (App of Apps)       │
│ │  └─ applications/                                            │
│ │     ├─ infrastructure.yaml  # Sync Wave 0                   │
│ │     ├─ databases.yaml       # Sync Wave 1                   │
│ │     └─ apis.yaml            # Sync Wave 2                   │
│ ├─ k8s/                 # Kubernetes Manifests                 │
│ │  ├─ namespaces/                                              │
│ │  ├─ networkpolicies/                                         │
│ │  └─ monitoring/                                              │
│ └─ charts/              # Helm Charts                          │
│    ├─ postgresql/                                              │
│    ├─ redis/                                                   │
│    └─ ecoeco-backend/                                          │
└────────────────────────────────────────────────────────────────┘
                              │
                              ↓ (ArgoCD Pull)
┌────────────────────────────────────────────────────────────────┐
│ Kubernetes Cluster                                             │
│                                                                 │
│ ArgoCD Root Application                                        │
│ ├─ Infrastructure (Wave 0) ─────────────────┐                 │
│ │  ├─ Namespaces                             │                 │
│ │  ├─ NetworkPolicies                        │                 │
│ │  ├─ StorageClasses                         │                 │
│ │  └─ ServiceMonitors                        │                 │
│ │                                             │                 │
│ ├─ Databases (Wave 1) ──────────────────────┤                 │
│ │  ├─ PostgreSQL (k8s-postgresql node)       │                 │
│ │  ├─ Redis (k8s-redis node)                 │                 │
│ │  └─ RabbitMQ (k8s-rabbitmq node)           │                 │
│ │                                             │                 │
│ ├─ Workers (Wave 2) ─────────────────────────┤                 │
│ │  ├─ Storage Worker                          │                 │
│ │  └─ AI Worker                               │                 │
│ │                                             │                 │
│ └─ API Services (Wave 3) ────────────────────┘                 │
│    ├─ auth-api                                                 │
│    ├─ my-api                                                   │
│    ├─ scan-api                                                 │
│    ├─ character-api                                            │
│    ├─ location-api                                             │
│    ├─ info-api                                                 │
│    └─ chat-api                                                 │
└────────────────────────────────────────────────────────────────┘
```

---

## 🚀 구현 단계

### Phase 1: 초기 클러스터 생성 (한 번만)

```bash
# 1. Terraform으로 EC2 인스턴스 생성
cd terraform
terraform init
terraform apply

# 2. Ansible로 Kubernetes 설치
cd ../ansible
ansible-playbook site.yml

# 3. ArgoCD 설치
kubectl create namespace argocd
kubectl apply -n argocd -f https://raw.githubusercontent.com/argoproj/argo-cd/stable/manifests/install.yaml

# 4. Root Application 배포
kubectl apply -f argocd/root-app.yaml
```

### Phase 2: Infrastructure를 ArgoCD로 관리

#### 1. Root Application 생성

```yaml
# argocd/root-app.yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: root-app
  namespace: argocd
spec:
  project: default
  source:
    repoURL: https://github.com/SeSACTHON/backend
    targetRevision: main
    path: argocd/applications
  destination:
    server: https://kubernetes.default.svc
    namespace: argocd
  syncPolicy:
    automated:
      prune: true
      selfHeal: true
```

#### 2. Infrastructure Application

```yaml
# argocd/applications/infrastructure.yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: infrastructure
  namespace: argocd
  annotations:
    argocd.argoproj.io/sync-wave: "0"  # 가장 먼저 배포
spec:
  project: default
  source:
    repoURL: https://github.com/SeSACTHON/backend
    targetRevision: main
    path: k8s/infrastructure  # namespaces, networkpolicies 등
  destination:
    server: https://kubernetes.default.svc
    namespace: default
  syncPolicy:
    automated:
      prune: true
      selfHeal: true
    syncOptions:
      - CreateNamespace=true
```

#### 3. Database Application

```yaml
# argocd/applications/databases.yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: databases
  namespace: argocd
  annotations:
    argocd.argoproj.io/sync-wave: "1"  # Infrastructure 다음
spec:
  project: default
  source:
    repoURL: https://github.com/SeSACTHON/backend
    targetRevision: main
    path: charts/databases  # PostgreSQL, Redis, RabbitMQ
    helm:
      valueFiles:
        - values-production.yaml
  destination:
    server: https://kubernetes.default.svc
    namespace: databases
  syncPolicy:
    automated:
      prune: true
      selfHeal: true
```

#### 4. API Services Application

```yaml
# argocd/applications/api-services.yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: api-services
  namespace: argocd
  annotations:
    argocd.argoproj.io/sync-wave: "3"  # Databases 다음
spec:
  project: default
  source:
    repoURL: https://github.com/SeSACTHON/backend
    targetRevision: main
    path: charts/ecoeco-backend
    helm:
      valueFiles:
        - values-14nodes.yaml
  destination:
    server: https://kubernetes.default.svc
    namespace: api
  syncPolicy:
    automated:
      prune: true
      selfHeal: true
```

---

## 📊 배포 방식 비교

### Option 1: 완전한 GitOps (권장) ⭐

```
┌──────────────┐    ┌──────────────┐    ┌──────────────┐
│  Developer   │───▶│  Git Repo    │◀───│   ArgoCD     │
│  (Git Push)  │    │ (manifests)  │    │ (Pull/Sync)  │
└──────────────┘    └──────────────┘    └──────┬───────┘
                                               │
                                               ▼
                                      ┌──────────────┐
                                      │  Kubernetes  │
                                      │   Cluster    │
                                      └──────────────┘
```

**장점**:
- ✅ 선언적 상태 관리
- ✅ Git = Single Source of Truth
- ✅ 자동 Drift 감지 및 복구
- ✅ 쉬운 롤백 (Git revert)
- ✅ 감사 추적 (Git 히스토리)
- ✅ 환경 일관성 (dev/staging/prod)

**단점**:
- ⚠️ 초기 설정 복잡도
- ⚠️ ArgoCD 학습 곡선

### Option 2: 하이브리드 (현재 방식)

```
┌──────────────┐    ┌──────────────┐    ┌──────────────┐
│   GitHub     │───▶│  Terraform   │───▶│  Kubernetes  │
│   Actions    │    │   + Ansible  │    │   Cluster    │
└──────────────┘    └──────────────┘    └──────────────┘
       │                                         ▲
       │            ┌──────────────┐             │
       └───────────▶│  Git Repo    │◀────────────┤
                    │ (app code)   │      ArgoCD │
                    └──────────────┘      (Pull) │
```

**장점**:
- ✅ Infrastructure는 한 번만 배포 (비용 효율적)
- ✅ Application은 GitOps (빠른 배포)
- ✅ 익숙한 CI/CD 파이프라인

**단점**:
- ❌ 일관성 부족 (Push + Pull 혼재)
- ❌ Infrastructure 변경 추적 어려움
- ❌ 복잡한 롤백

### Option 3: CI/CD Only (GitOps 없음)

```
┌──────────────┐    ┌──────────────┐    ┌──────────────┐
│   GitHub     │───▶│  kubectl     │───▶│  Kubernetes  │
│   Actions    │    │   apply      │    │   Cluster    │
└──────────────┘    └──────────────┘    └──────────────┘
```

**장점**:
- ✅ 단순한 구조
- ✅ 빠른 배포

**단점**:
- ❌ Drift 감지 불가
- ❌ 수동 복구 필요
- ❌ 롤백 복잡

---

## 🎯 우리 프로젝트 권장사항

### 현재 상태: Option 2 (하이브리드)

```yaml
Infrastructure:
  ✅ Terraform: EC2 생성 (한 번만)
  ✅ Ansible: K8s 설치 + 설정 (한 번만)
  ✅ GitHub Actions: 자동화

Application:
  ✅ ArgoCD: GitOps 배포
  ✅ 자동 동기화
  ✅ Drift 복구
```

### 개선 방향: Option 1로 마이그레이션

#### Step 1: k8s/ 디렉토리 정리

```bash
k8s/
├─ infrastructure/
│  ├─ namespaces/
│  │  └─ domain-based.yaml
│  ├─ networkpolicies/
│  │  └─ domain-isolation.yaml
│  └─ monitoring/
│     └─ servicemonitors.yaml
├─ databases/
│  ├─ postgresql/
│  ├─ redis/
│  └─ rabbitmq/
└─ ingress/
   └─ alb-ingress.yaml
```

#### Step 2: ArgoCD Applications 생성

```bash
argocd/
├─ root-app.yaml              # App of Apps
└─ applications/
   ├─ infrastructure.yaml     # Wave 0
   ├─ databases.yaml          # Wave 1
   ├─ workers.yaml            # Wave 2
   └─ apis.yaml               # Wave 3
```

#### Step 3: GitHub Actions 역할 변경

```yaml
# Before: Infrastructure 배포
- terraform apply
- ansible-playbook site.yml

# After: 초기 부트스트랩만
- terraform apply (EC2 생성)
- ansible-playbook bootstrap.yml (K8s + ArgoCD 설치)
- kubectl apply -f argocd/root-app.yaml (Root App 배포)
```

---

## 📝 마이그레이션 체크리스트

- [ ] k8s/ 디렉토리 구조 정리
- [ ] ArgoCD Applications 생성
- [ ] Sync Wave 설정
- [ ] GitHub Actions 단순화
- [ ] 테스트 환경에서 검증
- [ ] 프로덕션 마이그레이션

---

## 🔗 참고 자료

- [ArgoCD Best Practices](https://argo-cd.readthedocs.io/en/stable/user-guide/best_practices/)
- [App of Apps Pattern](https://argo-cd.readthedocs.io/en/stable/operator-manual/cluster-bootstrapping/)
- [Sync Waves and Hooks](https://argo-cd.readthedocs.io/en/stable/user-guide/sync-waves/)

---

**작성일**: 2025-11-14  
**상태**: 권장사항 문서화 완료  
**다음**: 팀 논의 후 마이그레이션 계획 수립

