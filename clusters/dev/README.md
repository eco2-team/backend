# Dev Environment Cluster Apps

Dev 환경 ArgoCD App-of-Apps 구조.

## 진입점

`clusters/dev/root-app.yaml`: 이 Application을 ArgoCD에 등록하면 `apps/*.yaml`을 재귀로 Sync한다.

```bash
kubectl apply -f clusters/dev/root-app.yaml
argocd app sync dev-root
```

## Wave 순서 (완전)

| 파일 | Wave | 내용 | 경로 |
|------|------|------|------|
| `00-crds.yaml` | -1 | Platform CRDs | `platform/crds` |
| `05-namespaces.yaml` | 0 | Namespaces (13개) | `workloads/namespaces/dev` |
| `08-rbac-storage.yaml` | 0 | RBAC + StorageClass | `workloads/rbac-storage/dev` |
| `10-network-policies.yaml` | 5 | NetworkPolicy (L3/L4) | `workloads/network-policies/dev` |
| `12-calico.yaml` | 5 | Calico CNI (VXLAN) | `platform/helm/calico` |
| `15-platform.yaml` | 10 | ExternalSecrets Operator | Helm: `external-secrets` |
| `20-alb-controller.yaml` | 15 | ALB Controller | `platform/helm/alb-controller` |
| `25-monitoring-operator.yaml` | 20 | kube-prometheus-stack | `platform/helm/kube-prometheus-stack` |
| `30-data-operators.yaml` | 25 | Postgres/Redis/RabbitMQ Operators | `platform/helm/*-operator` |
| `45-data-cr.yaml` | 35 | DB Clusters (CR) | `workloads/data/*/dev` |
| `58-secrets.yaml` | 58 | ExternalSecrets (SSM → K8s) | `workloads/secrets/external-secrets/dev` |
| `60-apis-appset.yaml` | 60 | 7개 API ApplicationSet | `workloads/apis/*/dev` |
| `70-ingress.yaml` | 70 | ALB Ingress (Path routing) | `workloads/ingress/apps/dev` |

## 참고

- `docs/architecture/gitops/ARGOCD_SYNC_WAVE_PLAN.md`
- `docs/architecture/gitops/ARGOCD_HELM_KUSTOMIZE_STRUCTURE.md`

