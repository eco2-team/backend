# Prod Environment Cluster Apps

Prod 환경 ArgoCD App-of-Apps 구조.

## 진입점

`clusters/prod/root-app.yaml`: 이 Application을 ArgoCD에 등록하면 `apps/*.yaml`을 재귀로 Sync한다.

```bash
kubectl apply -f clusters/prod/root-app.yaml
argocd app sync prod-root
```

## Wave 순서 (완전)

| 파일 | Wave | 내용 | 경로 |
|------|------|------|------|
| `00-crds.yaml` | -1 | Platform CRDs | `platform/crds` |
| `05-namespaces.yaml` | 0 | Namespaces (13개) | `workloads/namespaces/prod` |
| `08-rbac-storage.yaml` | 0 | RBAC + StorageClass | `workloads/rbac-storage/prod` |
| `10-network-policies.yaml` | 5 | NetworkPolicy (L3/L4) | `workloads/network-policies/prod` |
| `12-calico.yaml` | 5 | Calico CNI (VXLAN) | `platform/helm/calico` |
| `15-platform.yaml` | 10 | ExternalSecrets Operator | Helm: `external-secrets` |
| `20-alb-controller.yaml` | 15 | ALB Controller | `platform/helm/alb-controller` |
| `25-monitoring-operator.yaml` | 20 | kube-prometheus-stack | `platform/helm/kube-prometheus-stack` |
| `30-data-operators.yaml` | 25 | Postgres/Redis/RabbitMQ Operators | `platform/helm/*-operator` |
| `45-data-cr.yaml` | 35 | DB Clusters (CR) | `workloads/data/*/prod` |
| `58-secrets.yaml` | 58 | ExternalSecrets (SSM → K8s) | `workloads/secrets/external-secrets/prod` |
| `60-apis-appset.yaml` | 60 | 7개 API ApplicationSet | `workloads/apis/*/prod` |
| `70-ingress.yaml` | 70 | ALB Ingress (Path routing) | `workloads/ingress/apps/prod` |

## Prod 환경 특징

- **RBAC**: ServiceAccount별 최소 권한 (Least Privilege)
- **Replicas**: Postgres 1, Redis 1 (Sentinel 3)
- **Storage**: Postgres 100Gi, Redis 50Gi
- **Backup**: Logical backup 활성화 (S3)
- **Monitoring**: Retention 30d, Storage 200Gi

## 참고

- `docs/architecture/gitops/ARGOCD_SYNC_WAVE_PLAN.md`
- `docs/architecture/deployment/ENVIRONMENT_DEPLOYMENT_STRATEGY.md`

