# ArgoCD Sync Wave Plan

> **목적**: ArgoCD App-of-Apps에서 Sync Wave를 이용해 인프라 → 데이터 → 애플리케이션 순으로 안전하게 배포하기 위한 기준 순서를 정의한다.  
> **작성일**: 2025-11-16 · **작성자**: Backend Platform Team

---

## 1. Wave Dependency Matrix

아래 표는 각 Wave에서 배포해야 하는 대표 리소스, 의존 관계, 그리고 예시 ArgoCD Application 파일을 정리한다. Wave 번호가 낮을수록 먼저 Sync 된다.

| Wave | 계층 | 대표 리소스 | 선행 의존성 | ArgoCD 예시 (`clusters/{env}/apps`) |
|------|------|-------------|-------------|-------------|
| -1 | CRD 번들 | Core CRDs (Prometheus, Postgres, ESO) | 없음 | `00-crds.yaml` |
| 0 | Namespace | `workloads/namespaces/overlays/{env}` | Wave -1 | `05-namespaces.yaml` |
| 0 | RBAC · Storage | ServiceAccount, IRSA, StorageClass | Wave 0 | `08-rbac-storage.yaml` |
| 5 | Network | Calico 기본 정책, Node taint/label | Wave 0 | `12-network.yaml` *(추가 예정)* |
| 10 | Platform | cert-manager, external-dns, ESO | Wave 5 | `10-platform.yaml` |
| 15 | LoadBalancer | AWS Load Balancer Controller + ClusterIssuer | Wave 10 | `15-alb-controller.yaml` |
| 20 | Monitoring Operator | kube-prometheus-stack (Controller) | Wave 15 | `20-monitoring-operator.yaml` |
| 25 | Data Operators | Postgres/Redis Operators (Helm) | Wave 20 | `25-data-operators.yaml` |
| 30 | Monitoring CR | Prometheus/Grafana CR, Rule/Alert | Wave 20 | `30-monitoring-cr.yaml` |
| 35 | Data CR | PostgresCluster, RedisCluster, PVC | Wave 25 | `35-data-cr.yaml` |
| 40 | Exporters | DB/Cache Exporter, ServiceMonitor | Wave 30 & 35 | `40-exporters.yaml` *(추가 예정)* |
| 50 | GitOps Tools | Atlantis, Workflow, Internal dashboards | Wave 35 | `50-tools-atlantis.yaml` |
| 58 | Secrets | ExternalSecret, SOPS Secret | Wave 50 | `58-secrets.yaml` |
| 60+ | Applications | API/Worker ApplicationSet | 모든 하위 계층 | `60-apis-appset.yaml` |
| 70+ | Application Ingress | 서비스 Ingress(Route) | Wave 60 | `70-application-ingress.yaml` |

### 참고
- Wave 번호는 5 단위로 확보해도 되지만, ArgoCD는 정수만 비교하므로 1 단위로도 표현 가능하다. 본 문서는 `sync-wave` 주석 또는 `argocd.argoproj.io/sync-wave` 어노테이션을 사용했을 때 직관적인 구간 배분을 목적으로 5 단위 간격을 권장한다.
- `Monitoring Instances`(Wave 30)는 Operator가 제공하는 CRD가 먼저 생성되어야 하므로 Wave 20에 완전히 종속된다. 동일하게 `Data Instances`도 Wave 25(Operators) 이후로만 선언한다.

---

## 2. 규칙

1. **CRD → Operator → Instance**  
   - CRD가 필요한 경우, Wave -1에서 설치하고, Operator Wave에서 컨트롤러를 배포한 뒤, Instance Wave에서 Custom Resource를 선언한다.
2. **Network와 TLS 선행**  
   - cert-manager, external-dns는 Network(AWS CNI/Calico, NetworkPolicy)가 준비된 후 배포한다. Ingress Controller는 TLS ClusterIssuer가 존재해야 하므로 Wave 15로 고정한다.
3. **모니터링 관점**  
   - Prometheus Operator가 Ingress보다 늦으면 Admission Webhook이 생성되지 못해 실패할 수 있으므로 Wave 20 ≥ Wave 15를 강제한다.
4. **데이터 계층 보호**  
   - `Data Operators`와 `Data Instances` 사이에 최소 한 Wave를 둬 Drift를 빠르게 감지할 수 있도록 한다. (예: Wave 25 vs Wave 35)
5. **Exporters는 데이터 이후**  
   - Exporter Pod는 DB/Queue Endpoint가 필요하므로 Wave 40 이상에서 배치한다. ServiceMonitor는 Wave 30에서 배포한 Prometheus CRD에 의존한다.
6. **애플리케이션은 최종**  
   - API/Worker는 Wave 60 이상으로 지정해 모든 인프라 계층이 Healthy일 때만 배포된다.

---

## 3. 적용 가이드

1. **ArgoCD Application 예시**

```yaml
# clusters/dev/apps/25-data-operators.yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: dev-data-operators
  annotations:
    argocd.argoproj.io/sync-wave: "25"
spec:
  project: dev
  source:
    repoURL: https://github.com/SeSACTHON/backend.git
    path: platform/helm/postgres-operator
    targetRevision: main
  destination:
    server: https://kubernetes.default.svc
    namespace: data-system
  syncPolicy:
    automated:
      prune: true
      selfHeal: true
```

2. **Nested Wave**  
   - ApplicationSet으로 다수 서비스가 배포될 경우, Template 내부에서 `argocd.argoproj.io/sync-wave`를 서비스별로 재정의하여 API 간 순서를 조정한다. (예: auth-api Wave 60, chat-api Wave 70)

3. **검증 체크리스트**
   - Root App Sync 후 `argocd app get dev-root-app` 출력에서 `Sync wave:` 값이 의도대로 표시되는지 확인한다.
   - Wave 간 의존성 위반이 감지되면, 먼저 lower wave 리소스가 Healthy인지 점검하고, 필요 시 `argocd app wait --sync --timeout`을 통해 순차 배포를 강제한다.

---

## 4. 향후 작업

1. `clusters/{env}/apps/*.yaml` 파일을 본 계획에 맞춰 재배치한다. (예: `15-alb-controller.yaml` → Wave 15)
2. Monitoring/Data Exporter에 해당하는 Helm/Kustomize 오버레이에 Wave 주석을 추가한다.
3. `docs/architecture/networking/NAMESPACE_NETWORKPOLICY_INGRESS.md` 등 관련 문서에서 Wave 번호를 본 계획과 일치하도록 수정한다.

---

> 본 문서는 ArgoCD Sync Wave 재구성의 기준이며, Wave 조정 시 먼저 본 문서를 업데이트한 뒤 관련 Kustomize/Helm 매니페스트와 GitOps 문서를 일괄 수정한다.

