# ArgoCD · Helm · Kustomize 통합 구조

> **참조 문서**  
> - `docs/architecture/gitops/ARGOCD_SYNC_WAVE_PLAN.md`  
> - `docs/architecture/gitops/SYNC_WAVE_SECRET_MATRIX.md`  
> - `docs/architecture/deployment/HELM_PLATFORM_STACK_GUIDE.md`  
> - `docs/architecture/deployment/KUSTOMIZE_BASE_OVERLAY_GUIDE.md`

ArgoCD App-of-Apps는 `argocd/apps/root-app.yaml`에서 시작하며, `ARGOCD_SYNC_WAVE_PLAN.md`에 정의된 Wave 번호대로 `argocd/apps/*.yaml`이 Sync 된다. 각 Wave에 필요한 ConfigMap/Secret 선행 조건은 `SYNC_WAVE_SECRET_MATRIX.md`의 표를 따른다.

---

## 1. 최상위 디렉터리

| 경로 | 설명 | Wave | 비고 |
|------|------|------|------|
| `argocd/apps/root-app.yaml` | App-of-Apps Application (dev/prod) | - | 하위 `argocd/apps/*.yaml` 재귀 Sync |
| `argocd/apps/*.yaml` | Wave별 Application / ApplicationSet 선언 | -1 ~ 70+ | 파일명에 Wave 명시 (`00-*.yaml`) |
| `platform/crds/*` | ALB / Prometheus / Postgres / ESO CRD 원본 | -1 | `argocd/apps/00-namespaces.yaml`에서 적용 |
| `platform/helm/*` | 벤더 Helm 스택 (cert-manager, alb-controller 등) | 10~50 | Helm `values/{env}.yaml` |
| `k8s/*` & `workloads/*` | Kustomize base/overlay (namespaces, data CR 등) | 0~70 | `argocd/apps/**` 에서 참조 |

---

## 2. `argocd/apps` 구성 (Wave 순서)

| 파일 | Wave | 주요 내용 | 필요한 CM/Secrets (예시) |
|------|------|-----------|---------------------------|
| `00-namespaces.yaml` | -1 | 네임스페이스, Core CRD (Prometheus 등) | 없음 |
| `01-infrastructure.yaml` | 0 | RBAC, ServiceAccount, StorageClass | `cluster-config`, `irsa-role-arn` |
| `05-network.yaml` *(예정)* | 5 | Calico 기본 정책, 노드 라벨/taint | `network-policy-defaults` (선택) |
| `10-platform.yaml` | 10 | cert-manager, external-dns, external-secrets | `route53-credentials`, `acme-email` |
| `15-ingress.yaml` | 15 | AWS Load Balancer Controller + ClusterIssuer | `alb-controller-values` Secret |
| `20-monitoring-operators.yaml` | 20 | Prometheus Operator, Alertmanager CRD | `alertmanager-config`, `grafana-datasource` |
| `25-data-operators.yaml` | 25 | Postgres / Redis / RabbitMQ Operator | `s3-backup-credentials` |
| `30-monitoring-instances.yaml` | 30 | kube-prometheus-stack (Prom/Grafana) | Prometheus Rule, Grafana Dashboard CM |
| `35-data-clusters.yaml` | 35 | PostgresCluster, RedisCluster, PVC | `postgresql-secret`, `redis-secret`, TLS Secret |
| `40-exporters.yaml` | 40 | DB/Cache Exporters, ServiceMonitor | Metrics User Secret (재사용) |
| `50-tools.yaml` | 50 | Atlantis, Argo Workflow, 기타 Ops 도구 | `atlantis-github-token`, `slack-webhook` |
| `58-secrets.yaml` | 58 | ExternalSecret / SOPS Secret Overlay | External Secrets Operator Ready (Wave 10) |
| `60-apis-app-of-apps.yaml` | 60+ | API/Worker ApplicationSet | `ghcr-secret`, 서비스별 Config/Secret |
| `70-applications-ingress.yaml` | 70+ | 서비스 Ingress (Instance+NodePort) | ACM/Issuer Secret, Host Routing Config |

> dev/prod 환경 모두 동일한 리스트를 사용하며, `values/{env}.yaml` 및 `workloads/**/overlays/{env}`에서 환경별 차이를 둔다.

---

## 3. `platform/helm` 구성

```
platform/
├─ helm/
│  ├─ alb-controller/
│  │  ├─ app.yaml            # Wave 15 Application 템플릿
│  │  └─ values/{dev,prod}.yaml
│  ├─ kube-prometheus-stack/ (Wave 20)
│  ├─ postgres-operator/     (Wave 25)
│  ├─ redis-operator/        (Wave 25)
│  ├─ external-secrets-operator/ (Wave 10)
│  ├─ cert-manager/          (Wave 10)
│  ├─ external-dns/          (Wave 10)
│  └─ atlantis/              (Wave 50)
└─ crds/
   ├─ alb-controller/*.yaml
   ├─ prometheus-operator/*.yaml
   ├─ postgres-operator/*.yaml
   └─ external-secrets/*.yaml
```

각 `app.yaml`은 다음 공통 규칙을 따른다.

```yaml
metadata:
  annotations:
    argocd.argoproj.io/sync-wave: "<Wave>"
    sesacthon.io/required-secrets: "comma,separated,list"
spec:
  source:
    helm:
      valueFiles:
        - values/{{env}}.yaml
```

Secrets/ConfigMap 선행 조건은 `SYNC_WAVE_SECRET_MATRIX.md`의 “필요한 CM/Secret” 열을 그대로 사용한다. 예) ALB Controller → `/sesacthon/{env}/network/(vpc-id|public-subnets|alb-sg)` Parameter → ExternalSecret → `alb-controller-values` Secret.

---

## 4. `workloads` 구성 (Kustomize)

| 디렉터리 | 역할 | Wave | 비고 |
|----------|------|------|------|
| `workloads/namespaces` | Namespace 정의 + Tier label | 0 | base + overlay(dev/prod) |
| `workloads/rbac-storage` | SA/RBAC, StorageClass, IRSA annotations | 0 | `commonLabels.tier` 유지 |
| `workloads/network-policies` | default-deny + 허용 정책 | 5 | Calico L3/L4 정책 |
| `workloads/data/postgres` | `PostgresCluster` CR | 35 | Operator: Postgres (Wave 25) |
| `workloads/data/redis` | `RedisCluster` 또는 StatefulSet | 35 | Operator: Redis |
| `workloads/monitoring/prometheus` | Prometheus, ServiceMonitor, Rule | 30 | `selector.matchLabels.tier=*` |
| `workloads/monitoring/grafana` | Datasource/Dashboard CM or Grafana CR | 30 | `grafana-dashboard` ConfigMap |
| `workloads/ingress/ingressclassparams` | ALB IngressClassParams | 15 | Subnet/SG ConfigMap 참조 |
| `workloads/ingress/apps` | 서비스별 Ingress (Route) | 70+ | TLS Secret 사전 요구 |
| `workloads/secrets/external-secrets` | ExternalSecret CR (ASM/SSM) | 58 | `/sesacthon/{env}/*` Parameter |
| `workloads/secrets/sops` | 암호화 Secret (선택) | 58 | `sops.yaml` 정책 |
| `workloads/apis/{service}/overlays/{env}` | Deployment/Service/CM | 60+ | `sync-wave` per service 가능 |

### API Overlay 공통 항목
- `kustomization.yaml`에 `namespace`, `commonLabels` (`tier=business-logic`, `domain=*`) 지정  
- `deployment-patch.yaml`에서 `image: ghcr.io/...` 및 Secret 참조  
- `configmap-env.yaml`로 비민감 설정을 제공하고, Secret은 ExternalSecret 출력 사용 (`envFrom.secretRef`)  
- `argocd.argoproj.io/sync-wave`를 60 이상으로 지정하고, 상위 ApplicationSet (`60-apis-appset.yaml`)에서 `wave` 파라미터를 주입

---

## 5. 예시: `argocd/apps/25-data-operators.yaml`

```yaml
apiVersion: argoproj.io/v1alpha1
kind: ApplicationSet
metadata:
  name: data-operators
  annotations:
    argocd.argoproj.io/sync-wave: "25"
    sesacthon.io/required-secrets: "s3-backup-credentials"
spec:
  generators:
    - list:
        elements:
          - name: postgres-operator
            path: platform/helm/postgres-operator
          - name: redis-operator
            path: platform/helm/redis-operator
  template:
    metadata:
      name: dev-{{name}}
    spec:
      project: dev
      source:
        repoURL: https://github.com/SeSACTHON/backend.git
        path: '{{path}}'
        helm:
          valueFiles:
            - values/dev.yaml
      destination:
        server: https://kubernetes.default.svc
        namespace: data-system
      syncPolicy:
        automated:
          prune: true
          selfHeal: true
        syncOptions:
          - CreateNamespace=true
```

---

## 6. 운영 체크리스트

1. **Wave 일관성**: 모든 `argocd/apps/*.yaml`에 `argocd.argoproj.io/sync-wave`가 `ARGOCD_SYNC_WAVE_PLAN.md`의 값과 동일한지 확인한다.  
2. **Secret 선행**: `sesacthon.io/required-secrets` 어노테이션을 기반으로 ArgoCD PreSync 훅 또는 External Secrets Ready 상태를 검증한다.  
3. **환경 Overlay**: dev/prod의 `values/{env}.yaml`, `workloads/**/overlays/{env}`가 존재하는지 CI에서 확인한다.  
4. **App-of-Apps 검증**: `argocd app get root-app` (또는 환경 별 명칭)으로 하위 Application 상태 및 wave 순서 확인.  
5. **문서 연계**: 변경 시 `ARGOCD_SYNC_WAVE_PLAN.md`, `SYNC_WAVE_SECRET_MATRIX.md`, `RBAC_NAMESPACE_POLICY.md`를 동시 업데이트한다.

---

> 이 문서는 GitOps 디렉터리 구조와 Wave 기반 배포 규칙을 단일 레퍼런스로 제공한다. 신규 컴포넌트 추가 시, 먼저 Wave와 필요한 ConfigMap/Secret을 정의하고 해당 경로에 매니페스트를 추가한 뒤, `clusters/{env}/apps`에 Application을 등록한다.

