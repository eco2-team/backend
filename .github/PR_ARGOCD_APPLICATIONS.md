# Pull Request: ArgoCD App of Apps (Kustomize + Helm)

## 📋 개요
- **브랜치**: `feature/argocd-refactor` → `develop`
- **타입**: CI/CD
- **목적**: ArgoCD Root App이 Kustomize/Helm 계층을 Wave 순서로 자동 배포하도록 구조화

## 🎯 변경 사항

### 1. Root Application (`argocd/root-app.yaml`)
- `path: argocd/apps`, `directory.recurse=false`
- Sync Wave = -2 (모든 하위 App보다 먼저 실행)
- `CreateNamespace`, `PruneLast`, `retry` 등 운영 기본값 명시

### 2. Wave별 Application 정의 (`argocd/apps/*.yaml`)
| 파일 | Wave | 설명 |
|------|------|------|
| `00-foundations.yaml` | -1 | Namespaces + CRD (Kustomize) |
| `10-infrastructure.yaml` | 0 | NetworkPolicy, Metrics Server 등 Kustomize |
| `20-platform.yaml` | 10 | (추가 예정) Node Lifecycle, External Secrets |
| `30-monitoring.yaml` | 20 | `charts/observability/kube-prometheus-stack` Helm |
| `40-data-operators.yaml` | 25 | PostgreSQL/Redis/RabbitMQ Operators (Kustomize placeholder) |
| `50-data-clusters.yaml` | 30 | `charts/data/databases` Helm |
| `60-gitops-tools.yaml` | 50 | `charts/platform/atlantis` Helm |
| `70-apis-app-of-apps.yaml` | 60 | ApplicationSet → `k8s/overlays/<domain>` |

### 3. API ApplicationSet 강화
- `spec.source.kustomize.images` 추가 → `ghcr.io/sesacthon/{{domain}}-api`
- ArgoCD Image Updater 연동 준비 (tag 자동 업데이트 가능)
- Namespace/phase 라벨 표준화

### 4. Helm/Kustomize 분리 명시
- Helm: `charts/observability`, `charts/data`, `charts/platform`
- Kustomize: `k8s/infrastructure`, `k8s/namespaces`, `k8s/networkpolicies`, `k8s/overlays`

## 🔄 GitOps 배포 흐름

```mermaid
graph TD
    A[Root App] --> B[00-foundations]
    B --> C[10-infrastructure]
    C --> D[20-platform]
    D --> E[30-monitoring (Helm)]
    E --> F[40-data-operators]
    F --> G[50-data-clusters (Helm)]
    G --> H[60-gitops-tools (Helm)]
    H --> I[70-apis ApplicationSet]
```

## ✅ 테스트 체크리스트
- [ ] `kubectl apply -f argocd/root-app.yaml`
- [ ] `argocd app get root-app -n argocd`
- [ ] `kubectl get applications -n argocd --sort-by=.metadata.annotations.argocd\.argoproj\.io/sync-wave`
- [ ] `kubectl get pods -n monitoring,databases,atlantis,auth,...`

## 📚 참고 문서
- `docs/architecture/gitops/APP-OF-APPS-DECISION.md`
- `docs/deployment/gitops/TERRAFORM-OPERATOR-PIPELINE.md`
- `docs/architecture/gitops/ATLANTIS_TERRAFORM_FLOW.md`
