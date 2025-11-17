# Operator Source & Spec Catalog

> **목적**: Data / Monitoring / Messaging 계층에서 사용 예정인 Kubernetes Operator의 출처(공식 repo, Helm chart, CRD), 스펙 요약, 최소 요구사항을 한 문서에 정리해 App-of-Apps 구성 시 참조한다.  
> **작성 기준**: 2025-11-16, Backend Platform Team

---

## 1. Data Operators

| Operator | Source / Chart | 주요 Custom Resource | 특징 / 선택 이유 | 비고 |
|----------|----------------|----------------------|------------------|------|
| **Zalando Postgres Operator** | GitHub: `github.com/zalando/postgres-operator` (`charts/postgres-operator`, tag `v1.10.0`)<br>Local values: `platform/helm/postgres-operator/values/{dev,prod}.yaml` | `postgresql` (`acid.zalan.do/v1`) | - Battle-tested, 다중 샤드/팀 기반 관리<br>- AWS S3 WAL archiving, logical backup 지원<br>- Env별 nodeSelector/toleration/backup 값을 Helm values로 분리 | Wave 25 (Operator) / Wave 35 (PostgresCluster) |
| **Redis Operator (OT Container Kit)** | Helm Repo: `https://ot-container-kit.github.io/helm-charts`, chart `redis-operator`, version `0.22.2`<br>Local values: `platform/helm/redis-operator/values/{dev,prod}.yaml` | `Redis` / `RedisCluster` (`redis.redis.opstreelabs.in/v1beta1`) | - Sentinel/Failover 내장, metrics exporter 지원<br>- Helm valueFiles로 namespace/nodeSelector 등을 env별 관리 | Wave 25 (Operator) / Wave 35 (`Redis[Cluster].yaml`) |
| **RabbitMQ Cluster Operator** | GitHub: `github.com/rabbitmq/cluster-operator` (`config/default`, tag `v1.11.0`)<br>Kustomize manifest upstream 그대로 사용 (Helm chart 없음) | `RabbitmqCluster` (`rabbitmq.com/v1beta1`) | - Upstream Operator, TLS/Cert Manager 통합<br>- StatefulSet 기반 Scaling<br>- ArgoCD ApplicationSet에서 JSON Patch로 nodeSelector/toleration만 주입 | Wave 25 (Operator) + Wave 35 (`RabbitmqCluster`) |

### 최소 요구 사항
- Namespace
  - Operators: `data-system` (Postgres, Redis), `messaging-system` (RabbitMQ)
  - Instance CR 네임스페이스는 각 Workload manifest에서 정의 (`workloads/data/*`, `workloads/messaging/*`)
- Secrets (ExternalSecret → `/sesacthon/{env}/...`)
  - `postgresql-secret` (`/data/postgres-password`)
  - `redis-secret` (`/data/redis-password`)
  - `rabbitmq-default-user` (`/data/rabbitmq-password`)
- Storage: `StorageClass` EBS gp3, 기본 100Gi (Postgres), 50Gi (Redis), 20Gi (RabbitMQ)
- Backup: S3 bucket (`s3://sesacthon-pg-backup`) & IAM Role (`s3-backup-credentials`) – Postgres WAL/backup 용

### RabbitMQ Operator 배포 고려사항 (2025-11)
- **Helm Chart 부재**: 공식 repo(`rabbitmq/cluster-operator`)는 `config/default` Kustomize 매니페스트만 릴리스하며, Bitnami Helm chart는 2025-09 EOL. 서드파티 chart를 채택하면 보안/업데이트 책임이 커지므로 upstream 매니페스트를 그대로 쓰기로 결정.
- **GitOps 일관성 vs. 유지보수성**: Helm valueFiles를 통한 env 분리가 어렵다는 단점이 있지만, upstream 변경 추적이 단순하고 CRD/컨트롤러 버전 차이가 최소화된다. env 차이는 ApplicationSet JSON Patch(노드 스케줄링) 또는 향후 Kustomize overlay로 보완.
- **향후 선택지**: Helm 템플릿이 필요해질 경우
  1) upstream 매니페스트를 `helmify`로 자체 chart화하여 repo에 추가하거나  
  2) 커뮤니티 chart를 포크해 장기 유지한다.  
  현재는 “업스트림 준수 + 최소 패치” 전략을 유지한다.

---

## 2. Monitoring Operators

| Operator | Source / Chart | 주요 CRD | 특징 |
|----------|----------------|----------|------|
| **kube-prometheus-stack** (Prometheus Operator) | Helm: `https://prometheus-community.github.io/helm-charts`, chart `kube-prometheus-stack`, version `56.21.1` | `Prometheus`, `Alertmanager`, `ServiceMonitor`, `PodMonitor`, `PrometheusRule` | - Prometheus/Alertmanager 번들<br>- CNCF 관리 Repo, CRD `monitoring.coreos.com/v1` |
| **Grafana** | Helm: `https://grafana.github.io/helm-charts`, chart `grafana`, version `8.5.9` | (Helm-managed) | - 독립 Grafana 배포, admin Secret/Ingress 분리<br>- Datasource: Prometheus ClusterIP |

### 요구사항
- Namespace: `prometheus` (kube-prometheus-stack), `grafana` (grafana chart)
- Wave: 20 (Prometheus Operator) → 21 (Grafana) → 40 (Exporters)
- Secrets:
  - `alertmanager-config` (Slack webhook 등)
  - `grafana-admin` (ExternalSecret → `/sesacthon/{env}/platform/grafana-admin-password`)
- ConfigMap: `prometheus-rules`

### Grafana 분리 운영 배경
- **릴리스/롤백 반경 축소**: Prometheus Operator 업데이트와 Grafana UI 배포를 별도 Helm 릴리스로 관리해 서로의 장애 범위를 줄인다.
- **구성·비밀 격리**: `grafana.ini`, Datasource, ExternalSecret(관리자 패스워드) 등 민감 설정을 `grafana` 네임스페이스에서 독립적으로 다루고, `prometheus` values는 CRD/알람 규칙 중심으로 단순화한다.
- **네임스페이스·정책 명확화**: Tier/Role 기반 NetworkPolicy·RBAC를 네임스페이스 단위로 설계해 관측 계층 구조를 문서화/자동화하기 쉽다.
- **미래 교체 용이성**: SaaS Grafana나 다른 시각화 도구로 전환할 때 kube-prometheus-stack 구성을 건드리지 않고 Release만 교체할 수 있다.
- 필요 시 `grafana.enabled: true`로 번들형 배포도 즉시 복귀 가능하므로, GitOps Sync Wave 20/21 구분은 운영 상의 선택지를 늘리기 위한 구조다.

---

## 3. Network (CNI)

| 컴포넌트 | Source / Chart | 주요 리소스 | 설정 | Wave |
|---------|----------------|------------|------|------|
| **Calico (tigera-operator)** | Helm: `https://docs.tigera.io/calico/charts`, chart `tigera-operator`, version `v3.27.0` | `Installation` (`operator.tigera.io/v1`), `IPPool`, `NetworkPolicy` | - VXLAN Always, BGP disabled<br>- `spec.calicoNetwork.ipPools[].encapsulation: VXLAN`<br>- `spec.calicoNetwork.bgp: Disabled`<br>- `natOutgoing: Enabled` | Wave 5 (Network) |

### 요구사항
- Namespace: `tigera-operator` (Operator), `calico-system` (Data plane)
- Wave: 5 (CNI 먼저), 이후 NetworkPolicy (동일 Wave 또는 바로 뒤)
- 선행 조건: Kubernetes v1.24+ (kube-proxy IPVS/iptables 호환)
- 참고: Tigera Operator는 Installation CR로 Calico 설정을 선언적으로 관리하며, VXLAN 모드에서 BGP를 비활성화하면 간단한 overlay network 구성 가능

---

## 4. Messaging / Event Operators

| Operator | Source / Chart | CRD | 특징 |
|----------|----------------|-----|------|
| **RabbitMQ Cluster Operator** | GitHub: `github.com/rabbitmq/cluster-operator` (`config/default`, tag `v1.11.0`) | `RabbitmqCluster` | - PodDisruptionBudget 포함<br>- TLS Secret, User Secret 자동 생성 |
| **RabbitMQ Messaging Topology Operator** *(Optional)* | GitHub: `github.com/rabbitmq/messaging-topology-operator` | `RabbitmqCluster`, `Exchange`, `Queue`, `Binding` | - Infra-as-Code 방식으로 exchange/queue 정의 |

### 요구사항
- Namespace: `messaging-system`
- Secret: `rabbitmq-default-user` (for management UI)
- Storage: StatefulSet PVC 20Gi, `ReadWriteOnce`
- NetworkPolicy: 허용 대상 `tier=business-logic`, `tier=integration`

---

## 5. 소스 명시 & 버전 관리

1. **Helm Chart 버전**  
   - `platform/helm/<operator>/Chart.yaml`에 `version`, `appVersion` 명시  
   - `values/{env}.yaml`에서 CRD install 옵션 (`prometheusOperator.createCustomResource`) 비활성화하고 CRD는 Wave -1에서 관리

2. **Git Tag / Release**  
   - RabbitMQ Operator: `v1.11.0` (`config/default` Kustomize)  
   - Zalando Postgres Operator: `v1.10.0` (Helm chart)  
   - OT Container Kit Redis Operator: `0.22.2` (Helm chart)

3. **검증 플로우**  
   - Helm chart upgrade 시 `helm template` + `kubeconform`으로 CRD 호환성 검사  
   - Operator Pod 변경 시 `kubectl describe deploy`에서 `image:` SHA 기록  
   - App-of-Apps에 `sesacthon.io/operator-version` 라벨 추가하여 추적

---

## 5. Ingress / Load Balancer Controller

| Controller | Source / Chart | 주요 CRD/리소스 | 특징 | 비고 |
|------------|----------------|-----------------|------|------|
| **AWS Load Balancer Controller (ALB Controller)** | Helm: `https://aws.github.io/eks-charts`, chart `aws-load-balancer-controller`, version `1.8.3` (ArtifactHub 안정 릴리스) | `TargetGroupBinding` (`elbv2.k8s.aws/v1beta1`) | - AWS 공식 Controller, NLB/ALB 지원<br>- IRSA 필수 (IAM policy: `AWSLoadBalancerControllerIAMPolicy`) | Wave 15 (`argocd/apps/15-ingress.yaml`), `platform/crds/alb-controller`에서 CRD 관리 |

### 요구사항
- Namespace: `kube-system`
- Secret/Config: `alb-controller-values` (VPC ID, Subnet IDs, SG ID 등 Terraform output 연동)
- IAM: IRSA Role에 `AWSLoadBalancerControllerIAMPolicy` 부여 (`alb-controller-iam.tf`)
- 서비스: NodePort 또는 `alb.ingress.kubernetes.io/target-type: ip` 선택 (현재 Instance 모드)

---

## 6. 참고 문서
- Zalando Postgres Operator Docs: <https://postgres-operator.readthedocs.io/>
- CloudNativePG Docs: <https://cloudnative-pg.io/documentation/>
- Spotahome Redis Operator: <https://github.com/spotahome/redis-operator>
- RabbitMQ Cluster Operator: <https://www.rabbitmq.com/kubernetes/operator/cluster-operator/index.html>
- Prometheus Operator: <https://github.com/prometheus-operator/kube-prometheus/tree/main>
- AWS Load Balancer Controller Helm Chart: <https://artifacthub.io/packages/helm/aws/aws-load-balancer-controller>

> 이 문서는 운영 중인 Operator의 소스와 스펙을 추적하기 위한 기준 정보이며, 새 Operator를 도입할 경우 동일한 테이블 포맷으로 항목을 추가하고 Helm/Kustomize 경로를 문서에 반영한다.

