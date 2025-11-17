# ArgoCD Sync Wave Plan

> **목적**: ArgoCD App-of-Apps에서 Sync Wave를 이용해 인프라 → 데이터 → 애플리케이션 순으로 안전하게 배포하기 위한 기준 순서를 정의한다.  
> **작성일**: 2025-11-16 · **작성자**: Backend Platform Team

---

## 1. Wave Dependency Matrix

아래 표는 각 Wave에서 배포해야 하는 대표 리소스, 의존 관계, 그리고 예시 ArgoCD Application 파일을 정리한다. Wave 번호가 낮을수록 먼저 Sync 된다.

| Wave | 계층 | 대표 리소스 | 선행 의존성 | ArgoCD 파일 (clusters/{env}/apps) |
|------|------|-------------|-------------|-------------------------------|
| 0 | CRD Seed | ALB, Prometheus, Postgres, ESO CRDs | 없음 | `00-crds.yaml` |
| 2 | Namespaces | 13개 Namespace (tier, domain 레이블) | Wave 0 | `02-namespaces.yaml` |
| 3 | RBAC · Storage | ServiceAccount, ClusterRole, Role, StorageClass | Wave 2 | `03-rbac-storage.yaml` |
| 5 | CNI | Calico (VXLAN, BGP disabled) | Wave 3 | `05-calico.yaml` |
| 6 | NetworkPolicy | default-deny, tier 기반 격리 (L3/L4) | Wave 5 | `06-network-policies.yaml` |
| 10 | Secrets Operator | ExternalSecrets Operator (Helm) | Wave 6 | `10-secrets-operator.yaml` |
| 11 | Secrets CR | ExternalSecret CR (SSM → K8s Secret) | Wave 10 | `11-secrets-cr.yaml` |
| 15 | Ingress Controller | AWS Load Balancer Controller (ACM via Terraform) | Wave 11 | `15-alb-controller.yaml` |
| 16 | DNS Automation | ExternalDNS (Route53 관리) | Wave 11, 15 | `16-external-dns.yaml` |
| 20 | Monitoring Operator | kube-prometheus-stack (Prometheus Operator) | Wave 15 | `20-monitoring-operator.yaml` |
| 21 | Observability UI | Grafana (Helm, 독립 배포) | Wave 20 | `21-grafana.yaml` |
| 25 | Data Operators | Postgres/Redis/RabbitMQ Operators | Wave 20 | `25-data-operators.yaml` |
| 35 | Data Instances | PostgresCluster, RedisFailover CR | Wave 25 | `35-data-cr.yaml` |
| 60 | Applications | API Deployments (7개 도메인) | Wave 35 | `60-apis-appset.yaml` |
| 70 | Application Ingress | ALB Path routing (api/argocd/grafana) | Wave 60 | `70-ingress.yaml` |

### 참고
- **파일명 = Wave 번호**: 직관성을 위해 파일명 prefix와 Wave를 일치 (`02-namespaces.yaml` → Wave 2)
- **같은 Wave 내 순서**: 파일명 알파벳 순서로 적용 (예: `05-calico` → `06-network-policies`)
- **ExternalSecrets 특이사항**: Operator(Wave 10) 직후 CR(Wave 11)을 배치해 Secret이 소비자(ALB, Wave 15)보다 먼저 준비되도록 함

---

## 2. 규칙

1. **CRD → Operator → Instance**  
   - CRD가 필요한 경우, Wave -1에서 설치하고, Operator Wave에서 컨트롤러를 배포한 뒤, Instance Wave에서 Custom Resource를 선언한다.
2. **Network와 TLS 선행**  
   - ExternalSecrets는 Network(Calico, NetworkPolicy) 준비 후 배포한다. ALB Controller는 ACM Certificate ARN(Terraform 생성)이 필요하므로 Wave 15로 고정한다.
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
# argocd/apps/40-data-operators.yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: data-operators
  annotations:
    argocd.argoproj.io/sync-wave: "25"
spec:
  project: infrastructure
  source:
    repoURL: https://github.com/SeSACTHON/backend.git
    path: k8s/operators
    targetRevision: main
  destination:
    server: https://kubernetes.default.svc
    namespace: data-operators
  syncPolicy:
    automated:
      prune: true
      selfHeal: true
```

2. **Nested Wave**  
   - ApplicationSet으로 다수 서비스가 배포될 경우, Template 내부에서 `argocd.argoproj.io/sync-wave`를 서비스별로 재정의하여 API 간 순서를 조정한다. (예: auth-api Wave 60, chat-api Wave 70)

3. **검증 체크리스트**
   - Root App Sync 후 `argocd app get <app>` 출력에서 `Sync wave:` 값이 의도대로 표시되는지 확인한다.
   - Wave 간 의존성 위반이 감지되면, 먼저 lower wave 리소스가 Healthy인지 점검하고, 필요 시 `argocd app wait --sync --timeout`을 통해 순차 배포를 강제한다.

---

## 4. 향후 작업

1. `argocd/apps/*.yaml` 파일을 본 계획에 맞춰 재배치한다. (예: `20-alb-controller.yaml` → Wave 15)
2. Monitoring/Data Exporter에 해당하는 Helm/Kustomize 오버레이에 Wave 주석을 추가한다.
3. `docs/architecture/networking/NAMESPACE_NETWORKPOLICY_INGRESS.md` 등 관련 문서에서 Wave 번호를 본 계획과 일치하도록 수정한다.

---

> 본 문서는 ArgoCD Sync Wave 재구성의 기준이며, Wave 조정 시 먼저 본 문서를 업데이트한 뒤 관련 Kustomize/Helm 매니페스트와 GitOps 문서를 일괄 수정한다.

