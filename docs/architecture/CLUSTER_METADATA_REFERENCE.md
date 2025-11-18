# Cluster Metadata Reference

본 문서는 현재 14-Node 클러스터에서 사용 중인 **네임스페이스·서비스 그룹·라벨·어노테이션** 체계를 한 곳에 정리한 요약본입니다. 세부 배경은 `docs/infrastructure/k8s-label-annotation-system.md` 를 참고하세요.

---

## 1. 네임스페이스 인벤토리

| Namespace | Tier | Role / Domain | 주요 워크로드 |
|-----------|------|---------------|----------------|
| `auth`, `my`, `scan`, `character`, `location`, `info`, `chat` | business-logic | `role=api`, `domain=<service>` | 각 API Deployment (FastAPI) |
| `postgres`, `redis`, `rabbitmq` | data / integration | `role=database/cache/messaging`, `infra-type=` | ZALANDO PG Operator, Redis Failover, RabbitMQ Operator |
| `prometheus`, `grafana` | observability | `role=metrics/dashboards` | kube-prometheus-stack, Grafana |
| `platform-system` | infrastructure | `role=platform-core` | ExternalDNS, ExternalSecrets, ALB Controller 등 플랫폼 컴포넌트 |
| `data-system`, `messaging-system` | infrastructure | `role=operators` | Postgres / RabbitMQ Operator CRDs |
| `argocd` | platform | `role=gitops` | Argo CD control plane |
| `kube-system`, `kube-public`, `kube-node-lease` | Kubernetes 기본 | - | CoreDNS, kube-proxy, etc. |

> `workloads/namespaces/base/namespaces.yaml` 에 정의된 모든 Namespace는 `app.kubernetes.io/part-of: ecoeco-backend` 혹은 `ecoeco-platform` 라벨을 기본으로 갖습니다. 환경별(Kustomize overlay)로는 `environment: dev|prod` 라벨이 추가됩니다.

---

## 2. 노드 라벨 & 테인트 요약

| 노드 그룹 | 필수 라벨 | Taint (NoSchedule) | 설명 |
|-----------|-----------|--------------------|------|
| Control Plane (`k8s-master`) | `role=control-plane`, `domain=control-plane`, `service=platform-system`, `tier=infrastructure` | `role=control-plane`, `node-role.kubernetes.io/control-plane` | 마스터 전용, 일반 워크로드 스케줄 금지 |
| API Nodes (`k8s-api-*`) | `role=api`, `domain=<auth|my|...>`, `service=<동일>` , `tier=business-logic`, `phase=1..3` | `domain=<service>` | 도메인 단위로 격리된 API Pod 배치 |
| Worker Nodes (`k8s-worker-*`) | `role=worker`, `worker-type=<storage|ai>`, `workload=<worker-storage|worker-ai>`, `tier=worker` | (필요시) `domain=<worker-*>` | 비동기 작업자/AI 파이프라인 |
| Infrastructure Nodes (`k8s-postgresql`, `k8s-redis`, `k8s-rabbitmq`, `k8s-monitoring`) | `role=infrastructure`, `infra-type=<postgresql|redis|...>`, `domain=<data|integration|observability>` | `domain=<data|integration|observability>` | 데이터/플랫폼/관측 스택 전용 |

- **도메인 기반 스케줄링**: API/Worker/Infra Deployment 는 반드시 `nodeSelector/affinity` 로 해당 domain/service 혹은 infra-type 라벨을 사용.
- **Toleration 규칙**: Pod는 자신이 접근할 도메인의 `domain=<value>` taint 를 tolerate 해야 함.

---

## 3. Pod / Service 라벨 표준

| 구분 | 필수 라벨 | 비고 |
|------|-----------|------|
| 공통 | `app`, `domain`, `tier`, `version`, `phase` | `app.kubernetes.io/name` 계열 라벨과 병행 사용 |
| API Deployments | `role=api`, `service=<name>` | `domain` 과 동일 값 유지 |
| Worker Deployments | `workload=<worker-*>`, `worker-type=<storage|ai>` | Celery/파이프라인 스케줄링 기준 |
| Infra Operators | `infra-type=<postgresql|redis|rabbitmq|monitoring>` | Operator CR와 Pod 모두 동일 라벨 |
| ServiceMonitor/Service | `domain`, `tier`, `role` | Prometheus selector가 matchLabels로 사용 |

예시 (API):
```yaml
metadata:
  labels:
    app: auth-api
    domain: auth
    tier: api
    role: api
    version: v1.0.0
    phase: "1"
spec:
  template:
    metadata:
      labels: (동일)
```

예시 (Worker):
```yaml
metadata:
  labels:
    app: worker-storage
    workload: worker-storage
    worker-type: storage
    domain: scan
    tier: worker
```

---

## 4. 표준 어노테이션

| Annotation | 적용 대상 | 설명 |
|------------|-----------|------|
| `prometheus.io/scrape: "true"` | API / Worker Pod, Service | Prometheus 자동 수집 플래그 |
| `prometheus.io/port`, `prometheus.io/path` | 동일 | 메트릭 포트/경로 명시 |
| `argocd.argoproj.io/sync-wave` | ArgoCD Application | 배포 순서 제어 |
| `argocd.argoproj.io/sync-options` | ArgoCD Application | `CreateNamespace=true`, `PruneLast=true` 등 |
| `environment: dev|prod` | Namespace/Pod/Service | Overlay에서 자동 주입되는 환경 라벨 (Namespace에는 labels 섹션에 포함) |

Prometheus ServiceMonitor 예시:
```yaml
apiVersion: monitoring.coreos.com/v1
kind: ServiceMonitor
metadata:
  labels:
    release: prometheus
spec:
  selector:
    matchLabels:
      domain: auth
      tier: api
  namespaceSelector:
    matchNames:
      - auth
  endpoints:
    - port: http
      path: /metrics
```

---

## 5. 참조 문서

- `docs/infrastructure/k8s-label-annotation-system.md`
- `docs/namespace/RBAC_NAMESPACE_POLICY.md`
- `workloads/namespaces/base/namespaces.yaml`
- `docs/troubleshooting/CALICO_GITOPS_INCIDENT_2025-11-18.md` (네트워크 장애 사례)

---

## 6. ArgoCD Application ↔ Namespace 매핑

모든 Argo Application 객체는 `argocd` 네임스페이스에 존재하지만, 실제 워크로드는 아래 매핑에 따라 배포됩니다. (App-of-Apps 패턴으로 `clusters/*/apps/*.yaml` → `platform/**` → Helm/Kustomize가 연결됩니다.)

| Application (`clusters/dev/apps`) | Source 경로 | 실제 워크로드 Namespace | 비고 |
|-----------------------------------|-------------|--------------------------|------|
| `dev-crds` | `platform/crds/dev` | Cluster 전역 | Prometheus/ExternalSecrets/RabbitMQ/Postgres CRD |
| `dev-namespaces` | `workloads/namespaces/dev` | N/A (Namespace 생성) | 문서의 Namespace 표와 일치 |
| `dev-network-policies` | `workloads/network-policies/dev` | 각 Namespace | 기본 네트워크 정책 |
| `dev-rbac-storage` | `workloads/rbac-storage/dev` | `platform-system`, `data-system`, `messaging-system`, `kube-system` | ServiceAccount/ClusterRole |
| `dev-alb-controller` | `platform/helm/alb-controller/dev` | `kube-system` | AWS Load Balancer Controller |
| `dev-external-dns` | `platform/helm/external-dns/dev` | `platform-system` | ExternalDNS (Route53) |
| `dev-external-secrets` | `platform/helm/external-secrets/dev` | `platform-system` | External Secrets Operator |
| `dev-secrets` | `workloads/secrets/external-secrets/dev` | `platform-system` (Secret manifests) | IRSA 자격증명/파라미터 주입 |
| `dev-kube-prom-stack` | `platform/helm/kube-prometheus-stack/dev` | `prometheus` | Prometheus Operator/Alertmanager |
| `dev-grafana` | `platform/helm/grafana/dev` | `grafana` | Grafana Helm Chart (datasource=Prometheus) |
| `dev-data-operators` | `platform/helm/{postgres,redis,rabbitmq}-operator/dev` | `data-system`, `messaging-system` | Operator (Zalando, Spotahome 등) |
| `dev-data-clusters` | `platform/cr/dev` | `postgres`, `redis`, `rabbitmq` | 실제 데이터 클러스터 |
| `dev-root` | `clusters/dev/apps` 전체 | - | App-of-Apps 루트 |

> 따라서 Application 객체가 `argocd` 네임스페이스에만 보이는 것은 정상이며, **실제 리소스는 위 표의 Namespace에 생성**됩니다. 문제가 발생하면 해당 Namespace에서 Pod/Secret/ConfigMap 상태를 점검하세요.

