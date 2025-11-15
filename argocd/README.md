# ArgoCD Applications (App of Apps)

> **브랜치**: `develop`  
> **아키텍처**: Kustomize + Helm (Wave 기반)  
> **최종 업데이트**: 2025-11-16

---

## 📁 디렉토리 구조

```
argocd/
├── root-app.yaml              # Root Application (path=argocd/apps)
├── apps/                      # Wave별 Application 정의
│   ├── 00-foundations.yaml
│   ├── 10-infrastructure.yaml
│   ├── 20-alb-controller.yaml
│   ├── 30-platform.yaml
│   ├── 40-monitoring.yaml     # Helm → charts/observability/…
│   ├── 50-data-operators.yaml
│   ├── 60-data-clusters.yaml  # Helm → charts/data/databases
│   ├── 70-gitops-tools.yaml   # Helm → charts/platform/atlantis
│   └── 80-apis-app-of-apps.yaml (ApplicationSet)
└── applications-archive/      # Legacy manifest (참고용)
```

---

## 🎯 현재 App of Apps 패턴

### Wave 기반 배포 순서

| Wave | 파일 | 설명 |
|------|------|------|
| -2 | `root-app.yaml` | 모든 Application을 bootstrap |
| -1 | `00-foundations.yaml` | Namespace + CRD (Kustomize) |
| 0  | `10-infrastructure.yaml` | NetworkPolicy, Metrics Server, Calico 정책 |
| 20 | `20-alb-controller.yaml` | Helm `eks/aws-load-balancer-controller` |
| 30 | `30-platform.yaml` | (예약) Node Lifecycle / External Secrets |
| 40 | `40-monitoring.yaml` | Helm `charts/observability/kube-prometheus-stack` |
| 50 | `50-data-operators.yaml` | Operator placeholder (Zalando/Redis/RabbitMQ) |
| 60 | `60-data-clusters.yaml` | Helm `charts/data/databases` |
| 70 | `70-gitops-tools.yaml` | Helm `charts/platform/atlantis` |
| 80 | `80-apis-app-of-apps.yaml` | ApplicationSet → `k8s/overlays/<domain>` |

---

## 🚀 사용 방법

### 1. Root Application 배포

```bash
# Root App 배포 (모든 하위 App 자동 생성)
kubectl apply -f argocd/root-app.yaml

# 상태 확인
kubectl get applications -n argocd
```

### 2. 개별 Application 확인

```bash
# Infrastructure
kubectl get application infrastructure -n argocd

# API Services
kubectl get applicationset api-services -n argocd

# 생성된 개별 API Application 확인
kubectl get applications -n argocd | grep api-
```

---

## 📊 브랜치 전략

### targetRevision 규칙

| 환경 | 브랜치 | 용도 |
|------|--------|------|
| **Development** | `develop` | 개발 환경 |
| **Feature** | `feature/*` 또는 `refactor/*` | 기능 개발/리팩토링 |
| **Production** | `main` | 프로덕션 |

**현재 브랜치**: `develop`
- 모든 `apps/` 디렉토리의 Application은 현재 브랜치를 참조합니다.
- `develop` 브랜치로 merge 후 `targetRevision: develop`으로 변경 예정

---

## 🔄 마이그레이션 히스토리

### Legacy → App of Apps

**Before** (`applications/`):
- ❌ ApplicationSet만 사용 (Helm 기반)
- ❌ 배포 순서 제어 어려움
- ❌ Infrastructure와 Application 구분 없음

**After** (`apps/`):
- ✅ App of Apps 패턴
- ✅ Sync Wave로 배포 순서 제어
- ✅ Kustomize 기반 (Infrastructure)
- ✅ 명확한 계층 구조

---

## 📝 주요 변경 사항

### 1. Infrastructure를 Kustomize로 관리

**Before**:
```bash
# Ansible Playbook으로 배포
ansible-playbook k8s/namespaces/domain-based.yaml
```

**After**:
```yaml
# ArgoCD Application으로 관리
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: infrastructure
spec:
  source:
    path: k8s/infrastructure  # Kustomize
```

### 2. API Services는 Kustomize Overlay 사용

**Before**:
```yaml
# Helm Chart values 수정
charts/ecoeco-backend/values-14nodes.yaml
```

**After**:
```yaml
# Kustomize overlays 사용
k8s/overlays/auth/kustomization.yaml
k8s/overlays/my/kustomization.yaml
...
```

---

## 🗄️ Archive 디렉토리

`applications-archive/` 디렉토리는 참고용으로 보관되며, 실제 배포에 사용되지 않습니다.

**보관된 파일들**:
- `ecoeco-14nodes-appset.yaml`: 14-Node Helm 기반 ApplicationSet
- `api-services-appset.yaml`: 13-Node Helm 기반 ApplicationSet
- `worker-services-appset.yaml`: Worker Services ApplicationSet
- `ecoeco-appset-kustomize.yaml`: 초기 Kustomize 실험
- `ecoeco-backend*.yaml`: 통합 Application (구버전)
- `test-auth-app.yaml`: 테스트용 Application

**삭제하지 않는 이유**:
- 📚 히스토리 참고
- 🔄 롤백 가능성
- 📖 학습 자료

---

## 🔗 관련 문서

- [App of Apps 의사결정](../docs/architecture/gitops/APP-OF-APPS-DECISION.md)
- [Atlantis Terraform 흐름](../docs/architecture/gitops/ATLANTIS_TERRAFORM_FLOW.md)
- [Troubleshooting Guide](../docs/TROUBLESHOOTING.md)

---

**작성일**: 2025-11-14  
**상태**: App of Apps 패턴 적용 완료 ✅  
**다음**: develop 브랜치 merge 및 프로덕션 배포

