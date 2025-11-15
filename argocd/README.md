# ArgoCD Applications (App of Apps Pattern)

> **현재 브랜치**: `develop`  
> **아키텍처**: Kustomize + App of Apps 패턴  
> **날짜**: 2025-11-14

---

## 📁 디렉토리 구조

```
argocd/
├── root-app.yaml                    # 최상위 App of Apps
│
├── apps/                            # ✨ 신규 App of Apps 구조
│   ├── infrastructure.yaml          # Wave 0: Namespaces, NetworkPolicies
│   └── api-services.yaml            # Wave 3: API Services (ApplicationSet)
│
└── applications-archive/            # 🗄️ Legacy (참고용)
    ├── ecoeco-14nodes-appset.yaml   # 14-Node 아키텍처 (구버전)
    ├── api-services-appset.yaml     # API Services (Helm 기반)
    ├── worker-services-appset.yaml  # Worker Services
    └── ... (기타 legacy 파일들)
```

---

## 🎯 현재 App of Apps 패턴

### Wave 기반 배포 순서

```
Root Application (argocd/root-app.yaml)
  │
  ├─ Wave 0: Infrastructure (apps/infrastructure.yaml)
  │  └─ k8s/infrastructure/
  │     ├─ namespaces/domain-based.yaml
  │     └─ networkpolicies/domain-isolation.yaml
  │
  └─ Wave 3: API Services (apps/api-services.yaml)
     └─ ApplicationSet → k8s/overlays/{domain}/
        ├─ auth (Phase 1)
        ├─ my (Phase 1)
        ├─ scan (Phase 1)
        ├─ character (Phase 2)
        ├─ location (Phase 2)
        ├─ info (Phase 3)
        └─ chat (Phase 3)
```

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

- [Kustomize + App of Apps 가이드](../../docs/architecture/KUSTOMIZE_APP_OF_APPS.md)
- [GitOps 베스트 프랙티스](../../docs/architecture/GITOPS_BEST_PRACTICES.md)
- [ArgoCD 운영 가이드](../../docs/guides/ARGOCD_GUIDE.md)

---

**작성일**: 2025-11-14  
**상태**: App of Apps 패턴 적용 완료 ✅  
**다음**: develop 브랜치 merge 및 프로덕션 배포

