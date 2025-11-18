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

| Wave | 파일 (dev/prod 공통) | 설명 | Source Path |
|------|----------------------|------|-------------|
| 0 | `00-crds.yaml` | External Secrets / Prometheus / Postgres 등 필수 CRD | `platform/crds/{env}` |
| 2 | `02-namespaces.yaml` | 13개 비즈니스/데이터/플랫폼 Namespace | `workloads/namespaces/{env}` |
| 3 | `03-rbac-storage.yaml` | ServiceAccount, ClusterRole, StorageClass | `workloads/rbac-storage/{env}` |
| 5 | `05-calico.yaml` | Calico CNI (Helm) | `platform/helm/calico/{env}` |
| 6 | `06-network-policies.yaml` | Tier 기반 NetworkPolicy | `workloads/network-policies/{env}` |
| 10 | `10-secrets-operator.yaml` | External Secrets Operator (Helm) | `platform/helm/external-secrets/{env}` |
| 11 | `11-secrets-cr.yaml` | SSM → K8s Secret ExternalSecret | `workloads/secrets/external-secrets/{env}` |
| 15 | `15-alb-controller.yaml` | AWS Load Balancer Controller (Helm) | `platform/helm/alb-controller/{env}` |
| 16 | `16-external-dns.yaml` | ExternalDNS (Helm) | `platform/helm/external-dns/{env}` |
| 20 | `20-monitoring-operator.yaml` | kube-prometheus-stack (Helm) | `platform/helm/kube-prometheus-stack/{env}` |
| 21 | `21-grafana.yaml` | Grafana (Helm) | `platform/helm/grafana/{env}` |
| 25 | `25-data-operators.yaml` | Postgres / Redis / RabbitMQ Operators | `platform/helm/{postgres,redis,rabbitmq}-operator/{env}` |
| 35 | `35-data-cr.yaml` | PostgresCluster, RedisReplication/Sentinel, RabbitmqCluster | `platform/cr/{env}` |
| 60 | `60-apis-appset.yaml` | 7개 API ApplicationSet (auth/my/…) | `workloads/apis/*/{env}` |
| 70 | `70-ingress.yaml` | ALB Ingress / Path Routing | `workloads/ingress/apps/{env}` |

> Helm chart 설정은 `platform/helm/<component>/base/application.yaml`(공통)과 `platform/helm/<component>/{env}/patch-application.yaml`(env overlay)에 정의하며, 클러스터 루트 App은 각 env 디렉터리의 `kustomization.yaml`을 참조합니다.

## 3. 검증/문서
- `workloads/README.md`: Kustomize 디렉터리 구조 및 작성 규칙  
- `docs/deployment/LOCAL_CLUSTER_BOOTSTRAP.md`: Terraform → Ansible → Argo CD 부트스트랩 절차  
- `docs/troubleshooting/TROUBLESHOOTING.md`: Sync Wave별 문제 사례 정리

필요 시 새 환경을 추가하려면 `clusters/{env}` 디렉터리를 복제한 뒤 `apps/`의 `path`/`project`/`namespace` 값을 해당 환경에 맞게 수정하면 됩니다.

