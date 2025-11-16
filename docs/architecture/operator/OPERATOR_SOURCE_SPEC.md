# Operator Source & Spec Catalog

> **목적**: Data / Monitoring / Messaging 계층에서 사용 예정인 Kubernetes Operator의 출처(공식 repo, Helm chart, CRD), 스펙 요약, 최소 요구사항을 한 문서에 정리해 App-of-Apps 구성 시 참조한다.  
> **작성 기준**: 2025-11-16, Backend Platform Team

---

## 1. Data Operators

| Operator | Source / Chart | 주요 Custom Resource | 특징 / 선택 이유 | 비고 |
|----------|----------------|----------------------|------------------|------|
| **Zalando Postgres Operator** | GitHub: `github.com/zalando/postgres-operator`<br>Helm: `https://opensource.zalando.com/postgres-operator/charts/postgres-operator` | `postgresql` (`acid.zalan.do/v1`) | - battle-tested, 다중 샤드/팀 기반 관리<br>- AWS S3 WAL archiving, logical backup 지원 | Wave 25(Operator) / Wave 35(PostgresCluster) |
| **CloudNativePG (대체안)** | GitHub: `github.com/cloudnative-pg/cloudnative-pg`<br>Installer: `kubectl apply -f https://raw.githubusercontent.com/cloudnative-pg/cloudnative-pg/release-1.27/releases/cnpg-1.27.1.yaml` | `Cluster` (`postgresql.cnpg.io`) | - Sidecar 없는 네이티브 PG operator<br>- pgBackRest 내장 | 후보 (SPOF 감축 필요 시) |
| **Redis Operator (Spotahome)** | GitHub: `github.com/spotahome/redis-operator`<br>Manifest: `https://raw.githubusercontent.com/spotahome/redis-operator/v1.0.0/deploy/operator.yaml` | `RedisFailover` (`databases.spotahome.com/v1`) | - Master/Replica 자동 Failover<br>- Sentinel 내장 | Wave 25 / Wave 35에서 `Redis[Cluster].yaml` |
| **Redis Operator (Opstree) - 후보** | Helm Repo: `https://ot-container-kit.github.io/helm-charts/` (`redis-operator`) | `RedisCluster`, `RedisReplication` | - Percona 기반 Enterprise 기능<br>- TLS/ACL 내장 | SLA 요구 시 검토 |
| **RabbitMQ Cluster Operator** | GitHub: `github.com/rabbitmq/cluster-operator`<br>YAML: `https://github.com/rabbitmq/cluster-operator/releases/download/v1.11.0/cluster-operator.yml` | `RabbitmqCluster` (`rabbitmq.com/v1beta1`) | - K8s Service 기반 클러스터/고가용성<br>- TLS/Cert Manager 통합 | Wave 25 (Operator) + Wave 35 (`RabbitmqCluster`) |

### 최소 요구 사항
- Namespace: `data-system` (Operators) / `data`, `messaging` (Instance)
- Secrets / ConfigMap: `postgresql-secret`, `redis-secret`, `rabbitmq-default-user`
- Storage: `StorageClass` (EBS gp3) + Volume size 100Gi (Postgres), 50Gi (Redis)
- Backup: S3 bucket (`s3://sesacthon-pg-backup`) & IAM Role (`s3-backup-credentials`)

---

## 2. Monitoring Operators

| Operator | Source / Chart | 주요 CRD | 특징 |
|----------|----------------|----------|------|
| **kube-prometheus-stack** (Prometheus Operator) | Helm: `https://prometheus-community.github.io/helm-charts` (`kube-prometheus-stack`) | `Prometheus`, `Alertmanager`, `ServiceMonitor`, `PodMonitor`, `PrometheusRule` | - Operator + 기본 Prom/Grafana/Alertmanager 번들<br>- CRD 버전 `monitoring.coreos.com/v1` |
| **Grafana Operator (Optional)** | Helm: `https://grafana.github.io/helm-charts` (`grafana-operator`) | `Grafana`, `GrafanaDashboard`, `GrafanaDatasource` | - 대규모 Dashboard 관리 필요 시 도입 |

### 요구사항
- Namespace: `monitoring`
- Wave: 20 (Operator) → 30 (Prometheus/Grafana CR) → 40 (Exporters)
- Secrets: `alertmanager-config` (Slack webhook 등), `grafana-datasource`
- ConfigMap: `prometheus-rules`, `grafana-dashboards`

---

## 3. Messaging / Event Operators

| Operator | Source / Chart | CRD | 특징 |
|----------|----------------|-----|------|
| **RabbitMQ Cluster Operator** | GitHub Release YAML | `RabbitmqCluster` | - PodDisruptionBudget 포함<br>- TLS Secret, User Secret 자동 생성 |
| **RabbitMQ Messaging Topology Operator** *(Optional)* | GitHub: `github.com/rabbitmq/messaging-topology-operator` | `RabbitmqCluster`, `Exchange`, `Queue`, `Binding` | - Infra-as-Code 방식으로 exchange/queue 정의 |

### 요구사항
- Namespace: `messaging`
- Secret: `rabbitmq-default-user` (for management UI)
- Storage: StatefulSet PVC 20Gi, `ReadWriteOnce`
- NetworkPolicy: 허용 대상 `tier=business-logic`, `tier=integration`

---

## 4. 소스 명시 & 버전 관리

1. **Helm Chart 버전**  
   - `platform/helm/<operator>/Chart.yaml`에 `version`, `appVersion` 명시  
   - `values/{env}.yaml`에서 CRD install 옵션 (`prometheusOperator.createCustomResource`) 비활성화하고 CRD는 Wave -1에서 관리

2. **Git Tag / Release**  
   - RabbitMQ Operator: `v1.11.0` (2025-08 LTS)  
   - Zalando Postgres Operator: `1.10.x` (Helm chart 기준)  
   - Spotahome Redis Operator: `v1.0.0`

3. **검증 플로우**  
   - Helm chart upgrade 시 `helm template` + `kubeconform`으로 CRD 호환성 검사  
   - Operator Pod 변경 시 `kubectl describe deploy`에서 `image:` SHA 기록  
   - App-of-Apps에 `sesacthon.io/operator-version` 라벨 추가하여 추적

---

## 5. 참고 문서
- Zalando Postgres Operator Docs: <https://postgres-operator.readthedocs.io/>
- CloudNativePG Docs: <https://cloudnative-pg.io/documentation/>
- Spotahome Redis Operator: <https://github.com/spotahome/redis-operator>
- RabbitMQ Cluster Operator: <https://www.rabbitmq.com/kubernetes/operator/cluster-operator/index.html>
- Prometheus Operator: <https://github.com/prometheus-operator/kube-prometheus/tree/main>

> 이 문서는 운영 중인 Operator의 소스와 스펙을 추적하기 위한 기준 정보이며, 새 Operator를 도입할 경우 동일한 테이블 포맷으로 항목을 추가하고 Helm/Kustomize 경로를 문서에 반영한다.

