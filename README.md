# Eco² Backend

> **Version**: v0.7.4 | [Changelog](CHANGELOG.md)

![0BE8497C-694D-4926-AEB8-E29AC23EBF94_4_5005_c](https://github.com/user-attachments/assets/460482ed-9bf6-4cfb-b454-d9db46a0a16f)


Self-managed Kubernetes, ArgoCD를 기반으로 GitOps Sync-wave로 운영하는 14-Node 마이크로서비스 플랫폼입니다.  
AI 폐기물 분류·근처 제로웨이스트샵 안내·챗봇 등 도메인 API와 데이터 계층, GitOps 파이프라인을 모노레포로 관리합니다.

---

## Service Architecture

![E6A73249-BFDB-4CA9-A41B-4AF5A907C6D1](https://github.com/user-attachments/assets/fed94002-7bbd-49b0-bb2b-c2fc9ecd5b21)

```yaml
Tier 1 Presentation : ALB, Route 53, CloudFront
Tier 2 Business Logic : auth, my, scan, character, location, info, chat
Tier 3 Data : PostgreSQL, Redis, RabbitMQ(Pending), Celery(Pending)
Tier 0 Monitoring  : Prometheus, Grafana, Alerter Manager, ArgoCD
```

본 서비스는 4-Tier Layered Architecture로 구성되었습니다. 

각 계층은 서로 독립적으로 기능하도록 설계되었으며, 모니터링 스택을 제외한 상위 계층의 의존성은 하위 단일 계층으로 제한됩니다. 
프로덕션 환경을 전제로 한 Self-manged Kubernetes 기반 클러스터로 컨테이너화된 어플리케이션의 오케스트레이션을 지원합니다. 
클러스터의 안정성과 성능을 보장하기 위해 모니터링 시스템을 도입, IaC(Infrastructure as Code) 및 GitOps 파이프라인을 구축해 단일 레포지토리가 SSOT(Single Source Of Truth)로 기능 하도록 제작되었습니다. 
이에 따라 리소스 증설, 고가용성(HA) 도입 등 다양한 요구 사항에 따라 클러스터가 유연하게 변경 및 확장이 가능합니다.

---

## Bootstrap Overview

```yaml
Cluster  : kubeadm Self-Managed (14 Nodes)
GitOps   :
  Layer0 - Terraform (AWS 인프라)
  Layer1 - Ansible (kubeadm, CNI, Add-ons)
  Layer2 - ArgoCD App-of-Apps + Kustomize/Helm
  Layer3 - GitHub Actions + Docker Hub
Domains  : auth, my, scan, character, location, info, chat
Data     : PostgreSQL, Redis, RabbitMQ (paused), Monitoring stack
Ingress  : Route53 + CloudFront + ALB → SG (AWS Nodes) -> Calico NetworkPolicy
```

## Release Highlights (v0.7.4)

- **GitOps Sync Wave 재정렬**  
  `clusters/{env}/apps` 전반을 Wave 00~70으로 재배치하고, 모든 플랫폼 컴포넌트를 upstream Helm/Kustomize 소스로 직접 가져오도록 정리했습니다. Calico·ALB Controller·ExternalDNS·Prometheus Stack·Grafana·Postgres/Redis Operator가 각각 전용 Wave에서 동기화되며, GitOps Root App만으로 전체 클러스터를 재생성할 수 있습니다.

- **데이터 계층 이중화 & CRD 단일화**  
  `platform/crds/`에 AWS Load Balancer, External Secrets, Redis, Postgres, Prometheus CRD를 모으고, `platform/cr/`에서는 Postgres/Redis CR만 관리합니다. RabbitMQ는 장애 분석이 끝날 때까지 CR 생성이 일시 중단된 상태이며, 관련 문서는 `docs/troubleshooting/2025-11-19-rabbitmq-redis.md`에 기록했습니다.

- **Docker Hub 기반 단일 이미지 파이프라인**  
  모든 도메인 API가 `docker.io/mng990/eco2` 이미지를 공유하도록 CI를 단순화했습니다. GitHub Actions는 서비스별 테스트 후 공통 이미지를 태그로 분리하고, `workloads/apis/*` Kustomize 오버레이는 태그와 환경 변수를 patch 합니다.

- **RBAC/Storage 안정화**  
  `workloads/rbac-storage/*`가 AWS LB Controller·ExternalDNS·External Secrets·Operator용 ServiceAccount와 `gp3` StorageClass(EBS CSI)를 제공하며, External Secret → Secret → Helm Chart 흐름이 README로 문서화되었습니다.

- **문서 보강**  
  `README.md`, `clusters/README.md`, `platform/cr/README.md`, `platform/crds/README.md`, `workloads/README.md`, `workloads/rbac-storage/README.md`, `services/README.md` 등 작업 스코프별 README를 v0.7.4 기준으로 업데이트했습니다.

---

## Quick Links

| 카테고리 | 문서 |
|----------|------|
| 아키텍처 허브 | `docs/architecture/README.md`, `docs/architecture/CLUSTER_METADATA_REFERENCE.md` |
| GitOps & Sync Waves | `clusters/README.md`, `docs/gitops/ARGOCD_HELM_KUSTOMIZE_STRUCTURE.md` |
| Kustomize Workloads | `workloads/README.md`, `workloads/rbac-storage/README.md` |
| 데이터 계층 (CRD/CR) | `platform/crds/README.md`, `platform/cr/README.md`, `docs/troubleshooting/2025-11-19-rabbitmq-redis.md` |
| 서비스 & CI | `services/README.md`, `docs/ci/04-CI_CD_PIPELINE.md` |
| 배포/운영 가이드 | `docs/deployment/README.md`, `docs/troubleshooting/TROUBLESHOOTING.md` |

---

## Sync Wave Layout

![C4702A4B-B344-47EC-AB4A-7B2529496F44_1_105_c](https://github.com/user-attachments/assets/55c2b6bd-3324-4486-a146-1758cf86ea7c)

상세 구조는 `clusters/README.md`, `platform/cr/README.md`, `platform/crds/README.md`, `workloads/README.md`를 참고하세요.

| Wave | 구성 | Source / 설명 |
|------|------|----------------|
| 00 | CRD 번들 | `platform/crds/{env}` · AWS LB / External Secrets / Redis / Postgres / Prometheus CRD + webhook patch |
| 02 | Namespaces | `workloads/namespaces/{env}` · 13개 도메인/데이터/플랫폼 Namespace |
| 03 | RBAC & Storage | `workloads/rbac-storage/{env}` · ServiceAccount, ClusterRole, `gp3` StorageClass, dockerhub-secret |
| 06 | NetworkPolicy | `workloads/network-policies/{env}` · Tier 기반 기본 차단 + 허용 규칙 |
| 10 | External Secrets Operator | `clusters/{env}/apps/10-secrets-operator.yaml` · `charts.external-secrets.io` Helm (skip CRD) |
| 11 | ExternalSecret CR | `workloads/secrets/external-secrets/{env}` · SSM Parameter / Secrets Manager ←→ K8s Secret |
| 15 | AWS Load Balancer Controller | `clusters/{env}/apps/15-alb-controller.yaml` · `aws/eks-charts` Helm |
| 16 | ExternalDNS | `clusters/{env}/apps/16-external-dns.yaml` · `kubernetes-sigs/external-dns` Helm |
| 20 | kube-prometheus-stack | `clusters/{env}/apps/20-monitoring-operator.yaml` · `prometheus-community` Helm (skip CRD) |
| 21 | Grafana | `clusters/{env}/apps/21-grafana.yaml` · `grafana/grafana` Helm (NodePort + Secret) |
| 24 | Postgres Operator | `clusters/{env}/apps/24-postgres-operator.yaml` · `zalando/postgres-operator` Helm |
| 28 | Redis Operator | `clusters/{env}/apps/28-redis-operator.yaml` · OT-Container-Kit Helm (`skipCrds`) |
| 35 | Data Custom Resources | `platform/cr/{env}` · PostgresCluster / RedisReplication / RedisSentinel (RabbitMQ 일시 중단) |
| 60 | Domain APIs | `clusters/{env}/apps/60-apis-appset.yaml` → `workloads/apis/<domain>/{env}` |
| 70 | Ingress | `workloads/ingress/{env}` · API / Grafana / ArgoCD Ingress + ExternalDNS annotation |

모든 API는 공통 base(kustomize) 템플릿을 상속하고, 환경별 patch에서 이미지 태그·환경 변수·노드 셀렉터만 조정합니다.

---

## Services Snapshot

| 서비스 | 설명 | 이미지/태그 |
|--------|------|-------------|
| auth | JWT 인증/인가 | `docker.io/mng990/eco2:auth-{env}-latest` |
| my | 사용자 정보·포인트 | `docker.io/mng990/eco2:my-{env}-latest` |
| scan | AI 폐기물 분류 | `docker.io/mng990/eco2:scan-{env}-latest` |
| character | 캐릭터 분석 | `docker.io/mng990/eco2:character-{env}-latest` |
| location | 지도/수거함 검색 | `docker.io/mng990/eco2:location-{env}-latest` |
| info | 재활용 정보/FAQ | `docker.io/mng990/eco2:info-{env}-latest` |
| chat | GPT-4o-mini 챗봇 | `docker.io/mng990/eco2:chat-{env}-latest` |

각 도메인은 공통 FastAPI 템플릿·Dockerfile·테스트를 공유하고, Kustomize overlay에서 이미지 태그와 ConfigMap/Secret만 분기합니다.

---

### Troubleshooting Highlight

| 이슈 | 증상 & 해결 | 문서 |
|------|------------|------|
| ALB HTTPS→HTTP NAT | `backend-protocol: HTTP` + HTTPS-only listener + HTTP NodePort | `docs/troubleshooting/TROUBLESHOOTING.md#8-argocd-리디렉션-루프-문제` |
| **Calico Typha 포트 차단** | Master ↔ Worker 노드 간 5473/TCP 연결 실패 → Security Group에 Calico Typha 포트 규칙 추가 | `docs/troubleshooting/CALICO_TYPHA_PORT_5473_ISSUE.md` |
| **Redis PVC Pending** | EBS CSI Driver 미설치로 PVC 생성 실패 → `ebs.csi.aws.com` Provisioner + `gp3` StorageClass 설정 | `docs/troubleshooting/2025-11-19-rabbitmq-redis.md#2` |
| **CRD 이중 적용** | Helm Chart 내장 CRD와 충돌 → `skipCrds: true` + `platform/crds/{env}` 단일 관리 | `docs/troubleshooting/2025-11-19-rabbitmq-redis.md#4` |
| **Taint/Toleration 이슈** | 노드 라벨/taint 불일치로 Pod Pending → `fix-node-labels.yml` 실행 + kubeadm 재설정 | `docs/troubleshooting/ansible-label-sync.md` |

---

## Repository Layout

```text
backend/
├── terraform/           # Terraform (Atlantis) IaC
├── ansible/             # kubeadm, Calico, bootstrap playbooks
├── scripts/deployment/  # bootstrap_cluster.sh / destroy_cluster.sh
├── clusters/            # Argo CD Root Apps + Wave별 Application 목록
├── workloads/           # Kustomize (namespaces, rbac, network, apis, ingress 등)
├── platform/            # Upstream CRD & CR bundles (AWS LB, External Secrets, Redis, Postgres, Prometheus)
├── services/            # FastAPI 도메인 코드
└── docs/                # Architecture / Deployment / Troubleshooting
```

---

## Status

- ✅ Terraform · Ansible bootstrap · ArgoCD Sync-wave
- ✅ GitOps Sync-Wave 재정렬 (00~70) + upstream Helm/CRD 분리
- ✅ Docker Hub 단일 이미지 파이프라인 + External Secrets 운영 안정화
- ⚠️ RabbitMQ Operator/CR 장애로 Pending, MVP API 개발 이후 재도입 예정
- 🚧 API 개발 중
