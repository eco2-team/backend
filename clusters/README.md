# Clusters (Argo CD App-of-Apps)

`clusters/` 디렉터리는 환경별(예: `dev`, `prod`) Argo CD Root Application과 Sync Wave 정의를 모아둡니다.

```
clusters/
 ├── dev/
 │   ├── apps/        # 환경별 App(Application / ApplicationSet) 선언
 │   └── root-app.yaml
 └── prod/
     ├── apps/
     └── root-app.yaml
```

## 1. Root App
- `clusters/{env}/root-app.yaml` 을 Argo CD에 등록하면 동일 디렉터리의 `apps/` 하위 파일을 재귀로 Synchronize 합니다.
- 수동 적용 예시:
  ```bash
  kubectl apply -f clusters/dev/root-app.yaml
  argocd app sync dev-root
  ```

## 2. Sync Wave 개요

| Wave | 파일 (dev/prod 공통) | 설명 | Source Path / Repo |
|------|----------------------|------|--------------------|
| 0 | `00-crds.yaml` | ALB / External Secrets / Postgres / Redis / Prometheus 등 플랫폼 CRD 번들 | `platform/crds/{env}` |
| 2 | `02-namespaces.yaml` | 비즈니스·데이터·플랫폼 Namespace 정의 | `workloads/namespaces/{env}` |
| 3 | `03-rbac-storage.yaml` | ServiceAccount, RBAC, StorageClass, GHCR Pull Secret | `workloads/rbac-storage/{env}` |
| 6 | `06-network-policies.yaml` | Tier 기반 NetworkPolicy (default deny + DNS 허용) | `workloads/network-policies/{env}` |
| 10 | `10-secrets-operator.yaml` | External Secrets Operator Helm | Helm repo `charts.external-secrets.io` |
| 11 | `11-secrets-cr.yaml` | SSM Parameter → Kubernetes Secret ExternalSecret | `workloads/secrets/external-secrets/{env}` |
| 15 | `15-alb-controller.yaml` | AWS Load Balancer Controller Helm | Helm repo `aws/eks-charts` |
| 16 | `16-external-dns.yaml` | ExternalDNS Helm (Route53 자동화) | Helm repo `kubernetes-sigs/external-dns` |
| 20 | `20-monitoring-operator.yaml` | kube-prometheus-stack Helm | Helm repo `prometheus-community/kube-prometheus-stack` |
| 21 | `21-grafana.yaml` | Grafana Helm (독립 UI) | Helm repo `grafana/grafana` |
| 27 | `27-postgresql.yaml` | Bitnami PostgreSQL (standalone) | Helm repo `bitnami/postgresql` |
| 28 | `28-redis-operator.yaml` | Bitnami Redis Replication + Sentinel | Helm repo `bitnami/redis` |
| 60 | `60-apis-appset.yaml` | 도메인 API ApplicationSet (auth, my, scan, character, location, image, chat) | `workloads/domains/<service>/{env}` |
| 70 | `70-ingresses.yaml` | API·Argocd·Grafana Ingress ApplicationSet | `workloads/ingress/{service}/{env}` |

> Calico CNI는 Ansible(kubeadm bootstrap)에서 1회 설치하며, RabbitMQ Operator/CR은 안정화 완료 후 재도입합니다. `image` 도메인은 Wave 60에 편성 예정이므로 디렉터리 생성 후 `60-apis-appset.yaml` generator에 추가합니다.

## 3. 검증/문서
- `workloads/README.md`: Kustomize 디렉터리 구조 및 작성 규칙
- `platform/crds/README.md`: CRD 번들 및 webhook patch 기준
- `platform/cr/README.md`: Postgres/Redis CR 스펙 및 환경별 패치
- `docs/deployment/LOCAL_CLUSTER_BOOTSTRAP.md`: Terraform → Ansible → Argo CD 부트스트랩 절차
- `docs/troubleshooting/TROUBLESHOOTING.md`: Sync Wave별 문제 사례 정리

필요 시 새 환경을 추가하려면 `clusters/{env}` 디렉터리를 복제한 뒤 `apps/`의 `path`/`project`/`namespace` 값을 해당 환경에 맞게 수정하면 됩니다.
