# Eco² Backend
> **Version**: v0.7.4 | [Changelog](CHANGELOG.md)

![0BE8497C-694D-4926-AEB8-E29AC23EBF94_4_5005_c](https://github.com/user-attachments/assets/460482ed-9bf6-4cfb-b454-d9db46a0a16f)


Self-managed Kubernetes 기반으로 Terraform · Ansible · ArgoCD · Atlantis를 결합해 운영하는 14-Node 마이크로서비스 플랫폼입니다.  
AI 폐기물 분류·지도·챗봇 등 도메인 API와 데이터 계층, GitOps 파이프라인을 모노레포로 관리합니다.

---

## Service Architecture

![E6A73249-BFDB-4CA9-A41B-4AF5A907C6D1](https://github.com/user-attachments/assets/fed94002-7bbd-49b0-bb2b-c2fc9ecd5b21)

```yaml
Tier 1 Representation : ALB, Route 53, CloudFront
Tier 2 Business Logic : auth, my, scan, character, location, info, chat
Tier 3 Data : PostgreSQL, Redis
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
Ingress  : Route53 + CloudFront + ALB → Calico NetworkPolicy
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

## Getting Started

### 1. Terraform (Layer 0)
```bash
cd terraform
terraform init
terraform plan
terraform apply -auto-approve
```

### 2. Ansible (Layer 1)
```bash
cd ansible
ansible-playbook site.yml
```

> 전체 과정을 자동화하려면 `scripts/deployment/bootstrap_cluster.sh`를 사용하세요.  
> 필요 시 `--skip-terraform`, `--skip-ansible`, `--skip-argocd` 옵션으로 단계를 건너뛸 수 있습니다.

### 3. ArgoCD Root App (Layer 2)
```bash
kubectl apply -n argocd -f clusters/dev/root-app.yaml
kubectl get applications -n argocd
```

### 4. GitHub Actions (Layer 3)
- `.github/workflows/ci-quality-gate.yml`가 서비스 코드 변경을 감지해 lint/test/build/push를 수행합니다.
- Docker Hub 이미지 태그(`docker.io/mng990/eco2:*`)가 갱신되면 ArgoCD가 자동 배포합니다.

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

## Troubleshooting Highlights

| 이슈 | 요약 | 문서 |
|------|------|------|
| ALB HTTPS→HTTP NAT | `backend-protocol: HTTP` + HTTPS-only listener + HTTP NodePort | `docs/troubleshooting/TROUBLESHOOTING.md#8-argocd-리디렉션-루프-문제` |
| Namespace 중복 정의 | `workloads/namespaces/{env}` 한 곳에서 단일 관리 | `workloads/namespaces/README.md` |
| Atlantis 배포 | PR 기반 Terraform plan/apply 자동화 (Atlantis) | `docs/architecture/gitops/ATLANTIS_TERRAFORM_FLOW.md` |
| GitOps/Cluster Health Check | `scripts/diagnostics/gitops_cluster_health.sh` 실행 · kubectl 기반 상태 요약 | README – Getting Started |

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

- ✅ Terraform · Atlantis · Ansible bootstrap · ArgoCD App-of-Apps
- ✅ GitOps Sync Wave 재정렬 (00~70) + upstream Helm/CRD 분리
- ✅ Docker Hub 단일 이미지 파이프라인 + External Secrets 운영 안정화
- ⚠️ RabbitMQ Operator/CR은 장애 원인 분석 완료 후 재도입 예정
- 🚧 서비스 비즈니스 로직/성능 테스트 고도화 진행 예정

최종 업데이트: 2025-11-19 (GitOps Sync Wave & 문서 보강)

