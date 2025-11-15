# ArgoCD `apps/` 디렉터리 가이드

이 디렉터리는 **App of Apps의 Application 정의**를 보관합니다.  
Kustomize 리소스와 Helm Chart를 모두 참조하며, 실제 매니페스트/Chart는 각각 `k8s/` 와 `charts/` 아래에 위치합니다.

## 현재 구조

```
apps/
└── apis/
    ├── auth/
    ├── my/
    ├── scan/
    ├── character/
    ├── location/
    ├── info/
    ├── chat/
    └── workers/ (Placeholder)
```

- `apis/` : `k8s/overlays/<domain>` 을 재노출하기 위한 thin wrapper.  
  ApplicationSet(`argocd/apps/80-apis-app-of-apps.yaml`)이 이 경로를 순회하여 각 도메인 서비스를 생성합니다.
- `workers/` : 추후 Celery/Flower 등 비동기 워커가 필요할 때 추가될 placeholder입니다.

## Helm으로 이전된 계층

| Wave | 리소스 | 패키징 | 경로 |
|------|--------|--------|------|
| 40 | Monitoring (kube-prometheus-stack) | Helm | `charts/observability/kube-prometheus-stack` |
| 60 | Data Clusters (PostgreSQL/Redis/RabbitMQ) | Helm | `charts/data/databases` |
| 70 | GitOps Tools (Atlantis) | Helm | `charts/platform/atlantis` |

따라서 `apps/data/*`, `apps/mq/*` 같은 Kustomize placeholder 는 더 이상 사용하지 않으며 제거되었습니다. 데이터/메시징 계층을 수정하려면 대응하는 Helm Chart를 업데이트하고 ArgoCD Application(`argocd/apps/40-monitoring.yaml`, `60-data-clusters.yaml`, `70-gitops-tools.yaml` 등)을 통해 배포하세요.

## 참조

- Wave 정의 및 패키징 기준: `docs/architecture/gitops/APP-OF-APPS-DECISION.md`
- Helm/Kustomize 병행 전략: `charts/README.md`

