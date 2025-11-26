# Eco² Backend

> **Version**: v0.8.0 | [Changelog](CHANGELOG.md)

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

각 계층은 서로 독립적으로 기능하도록 설계되었으며, 모니터링 스택을 제외한 상위 계층의 의존성은 단일 하위 계층으로 제한됩니다.
프로덕션 환경을 전제로 한 Self-manged Kubernetes 기반 클러스터로 컨테이너화된 어플리케이션의 오케스트레이션을 지원합니다.
클러스터의 안정성과 성능을 보장하기 위해 모니터링 시스템을 도입, IaC(Infrastructure as Code) 및 GitOps 파이프라인을 구축해 모노레포 기반 코드베이스가 SSOT(Single Source Of Truth)로 기능하도록 제작되었습니다.
이에 따라 리소스 증설, 고가용성(HA) 도입 등 다양한 요구사항에 따라 클러스터가 유연하게 변경 및 확장이 가능합니다.

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

## AI Domain Progress

| 항목 | 진행 내용 (2025-11 기준) |
|------|-------------------------|
| Vision 인식 파이프라인 | `domains/chat/app/core/ImageRecognition.py`, `vision.py`에서 Azure Vision → OpenAI GPT-4o-mini 조합으로 폐기물 이미지를 분류. `item_class_list.yaml`, `situation_tags.yaml`에 카테고리/상황 태그 정의 후 Prompt에 자동 삽입. |
| Text/Intent 분류 | `text_classifier.py`, `prompts/text_classification_prompt.txt` 기반으로 사용자 질의를 intent/priority로 자동 분류하여 답변 라우팅. |
| RAG/지식 베이스 | `app/core/source/*.json`에 음식물/재활용 품목별 처리 지침을 다수의 JSON으로 축적하고, `rag.py`가 검색·요약해 답변에 인용. |
| 답변 생성 Prompt | `prompts/answer_generation_prompt.txt`, `vision_classification_prompt.txt`를 통해 다중 소스 결과를 하나의 친절한 응답으로 구성. multi-turn 컨텍스트와 tone을 prompt 레벨에서 제어. |
| API 구조 | `domains/chat/app` → FastAPI + `chat/app/core/*` 서비스 계층으로 분리. `/api/v1/chat` 엔드포인트는 text/vision 요청을 자동 판별하고 OpenAI 호출을 추상화. |
| 테스트/운영 | `tests/test_app.py`로 API 레벨 smoke test, `requirements.txt`에 OpenAI/Azure SDK 고정.|

다음 단계: 멀티모달 입력(텍스트+이미지) 동시 처리, 사용자별 히스토리 저장, ELK 기반 대화 로그 분석.

---

## Bootstrap Overview

```yaml
Cluster  : kubeadm Self-Managed (14 Nodes)
GitOps   :
  Layer0 - Terraform (AWS 인프라)
  Layer1 - Ansible (kubeadm, CNI)
  Layer2 - ArgoCD App-of-Apps Sync-wave + Kustomize/Helm
  Layer3 - GitHub Actions + Docker Hub
Domains  : auth, my, scan, character, location, info, chat
Data     : PostgreSQL, Redis, RabbitMQ (paused), Monitoring stack
Ingress  : Route53 + CloudFront + ALB → SG (AWS Nodes) -> Calico NetworkPolicy
```
1. Terraform으로 AWS 인프라를 구축합니다.
2. Ansible로 구축된 AWS 인프라를 엮어 K8s 클러스터를 구성하고, ArgoCD root-app을 설치합니다.
3. 모든 컴포넌트는 ArgoCD root-app과 sync된 상태이며, root-app은 develop 브랜치를 바라봅니다.
4. develop 브랜치에 push가 발생하면 CI 파이프라인을 거쳐 테스트, 도커 이미지 패키징, 허브 업로드까지 수행합니다.
5. ArgoCD root-app은 develop 브랜치의 변경사항이 감지되면 해당 파트를 업데이트해 코드 변경이 클러스터로 반영됩니다.

---

## Sync Wave Layout

![C4702A4B-B344-47EC-AB4A-7B2529496F44_1_105_c](https://github.com/user-attachments/assets/55c2b6bd-3324-4486-a146-1758cf86ea7c)

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
| 24 | PostgreSQL | `clusters/{env}/apps/24-postgres-operator.yaml` · `zalando/postgres-operator` Helm |
| 28 | Redis | `clusters/{env}/apps/28-redis-operator.yaml` · OT-Container-Kit Helm (`skipCrds`) |
| 35 | Data Custom Resources | `platform/cr/{env}` · PostgresCluster / RedisReplication / RedisSentinel (RabbitMQ 일시 중단) |
| 60 | Domain APIs | `clusters/{env}/apps/60-apis-appset.yaml` → `workloads/apis/<domain>/{env}` |
| 70 | Ingress | `workloads/ingress/{env}` · API / Grafana / API, ArgoCD, Grafana Ingress + ExternalDNS annotation |

- ArgoCD Sync-wave로 의존성 순서를 보장하며, 패키지 의존성이 높은 플랫폼은 Helm-charts로 관리·배포합니다.
- AWS Load Balancer Controller·External Secrets·Postgres/Redis Operator는 upstream Helm chart를 `skipCrds: true`로 설치합니다.
- Operator에 의존하는 CRD와 CR은 `platform/{crds | cr}/{env}`에서 Kustomzie Overlay 방식으로 관리합니다.
- 모든 API는 공통 base(kustomize) 템플릿을 상속하고, 환경별 patch에서 이미지 태그·환경 변수·노드 셀렉터만 조정합니다.
- 상세 구조는 `clusters/README.md`, `platform/cr/README.md`, `platform/crds/README.md`, `workloads/README.md`를 참고하세요.

---

### Namespace + Label Layout

![B13B764A-E597-4691-93F4-56F5C9FC0AB1](https://github.com/user-attachments/assets/1dc545ab-93db-4990-8a48-4df4dfb7adf0)

“포지션(part-of) → 계층(tier) → 역할(role)” 순으로 라벨을 붙인 뒤 네임스페이스로 매핑합니다.
Taint/Tolerance를 활용해 라벨과 매칭되는 노드로 파드의 배치가 제한되며, 계층별 network policy 격리가 적용됩니다. (Monitoring 제외, 상위 계층은 단일 하위 계층만 의존)
이코에코(Eco²)에서 라벨이 컨트롤 포인트를 맡으며, 도메인/역할/책임/계층 추상화를 통해 개발 및 운영 복잡도를 낮춥니다.

### 관계 설명
1. **app.kubernetes.io/part-of**  
   - `ecoeco-backend`: 업무 도메인(API)와 그에 붙은 데이터/관측 리소스.  
   - `ecoeco-platform`: 플랫폼 자체를 관리하는 인프라/오퍼레이터 네임스페이스.

2. **tier**  
   - 백엔드 전용 네임스페이스는 대부분 `business-logic`.  
   - 데이터 계층(`data`)과 관측(`observability`)도 같은 제품군(`ecoeco-backend`) 안에 포함.  
   - 플랫폼 계층은 `infrastructure`.

3. **role**  
   - 비즈니스 로직 네임스페이스는 공통적으로 `role: api`.  
   - 데이터 계층 내에서도 `database`, `cache`, `messaging`처럼 분리.  
   - 관측 계층은 `metrics`, `dashboards`.  
   - 플랫폼 계층은 `platform-core` 혹은 `operators`.

4. **domain / data-type**  
   - `domain` 라벨로 실제 서비스(예: `auth`, `location`)를 식별.  
   - 데이터 계층은 `data-type`으로 DB 종류까지 표기(`postgres`, `redis`).  

이 구조 덕분에 `kubectl`이나 ArgoCD 필터링 시 “제품군→계층→역할→도메인”으로 세분화된 셀렉터를 바로 사용할 수 있습니다.

---

### Network Topology

#### ALB가 Pod를 인지하는 경로
![CC86B4CB-7C2C-4602-BC10-B42B481948FD_4_5005_c](https://github.com/user-attachments/assets/ecbb091a-7310-4116-8d7a-f04d05e84aa4)

Ingress는 `location-api` Service(NodePort 31666)를 통해 파드가 노출되고 있는 노드 IP와 포트 정보를 확인합니다.
이 Endpoints 정보를 AWS Load Balancer Controller가 감지해 Target Group에 노드 IP + NodePort를 등록하고, ALB 리스너/규칙을 생성·업데이트합니다.

#### 왜 NodePort를 택했나?
- 이코에코의 클러스터는 Calico VXLAN으로 구성된 **오버레이 네트워크**를 사용합니다.
- Ingress가 어떤 노드/파드로 라우팅할지 알아야 하는데, ClusterIP Service만 쓰면 클러스터 외부에서 이 정보를 얻기 어려워서 별도 프록시가 요구됩니다.
- NodePort로 파드를 노출하면 노드 IP:포트 조합만으로 ALB → Target Group → Ingress → Pod 통신이 가능해지며, 중간 레이어 및 hop을 최소화합니다.

#### Client <-> Pod 트래픽 경로

![17DBA027-2EDF-459E-9B4D-4A3A0AB10F0C](https://github.com/user-attachments/assets/26e8128b-8b7f-4b46-93d1-c85553f4c853)

얖서 구축한 TG와 Ingress를 바탕으로 Client → ALB → Target Group → Ingress → 각 노드 내부 파드 순서로 전달됩니다.
Path by Route를 수행하며, RestFul한 트래픽 토폴로지를 제공합니다. 

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

## Release Highlights (v0.8.0)

- **OAuth 플로우 안정화 (2025-11-20 ~ 2025-11-23)**
  Google/Kakao/Naver 콜백에 상세 로깅을 추가하고 RedirectResponse를 재사용해 리다이렉트 이후에도 `Set-Cookie`가 유지되도록 수정했습니다.
  쿠키 `domain`을 `.growbin.app`으로 확장해 `api.dev.growbin.app`, `frontend.dev.growbin.app` 등 growbin 서브도메인 간 세션을 공유할 수 있습니다.

- **네트워크 & 보안 보강**
  `allow-external-https` NetworkPolicy를 추가해 Auth 파드가 OAuth Provider(HTTPS)와 안정적으로 통신하도록 했으며, ArgoCD GitHub webhook secret을 ExternalSecret + SSM 구조로 재작성했습니다.
  Pre-commit(Black, Ruff, 기본 hooks)을 도입해 lint/format 파이프라인을 커밋 단계에서 자동화했습니다.

- **DNS & 쿠키 도메인 전략 정비**
  Route53에 `frontend.growbin.app`, `frontend.dev.growbin.app` CNAME(Vercel) 레코드를 추가해 프런트 커스텀 도메인을 growbin 계층으로 편입했습니다.

- **AI 도메인 기능 고도화**
  Vision 인식(`ImageRecognition.py`, `vision.py`)과 Text/Intent 분류(`text_classifier.py`) 파이프라인을 정리하고, RAG 지식 베이스(`app/core/source/*.json`)를 확장했습니다.
  프롬프트(`answer_generation_prompt.txt`, `vision_classification_prompt.txt`, `text_classification_prompt.txt`)를 분리해 멀티모달 응답 품질을 높였고, FastAPI 챗봇 엔드포인트 `/api/v1/chat`이 이 흐름을 통합 처리합니다.

- **플랫폼 토대 (v0.7.4) 유지**
  GitOps Sync-wave(00~70) 재정렬, `platform/crds`/`platform/cr` 단일화, Docker Hub 단일 이미지 파이프라인, RBAC/Storage 안정화 등 v0.7.4 기반 구성은 그대로 유지되며 이번 버전에서 Auth/OAuth 영역만 추가됐습니다.

---

## API Docs
- [Auth](https://api.dev.growbin.app/api/v1/auth/docs)
- [Locations](https://api.dev.growbin.app/api/v1/locations/docs)

---

## Article

- [이코에코 인프라 구축기 #1 클러스터 부트스트랩](https://rooftopsnow.tistory.com/8)
- [이코에코 인프라 구축기 #2 GitOps: Ansible 의존성 줄이기](https://rooftopsnow.tistory.com/10)
- [이코에코 인프라 구축기 #3 GitOps: 네트워크 트러블슈팅](https://rooftopsnow.tistory.com/11)
- [이코에코 인프라 구축기 #4 GitOps: Operator vs Helm-charts](https://rooftopsnow.tistory.com/12)
- [이코에코 인프라 구축기 #5 GitOps: Sync-wave](https://rooftopsnow.tistory.com/13)
- [이코에코 인프라 구축기 #6 Namespace/RBAC/NeworkPolicy](https://rooftopsnow.tistory.com/14)

---

## Status

- ✅ Terraform · Ansible bootstrap · ArgoCD Sync-wave
- ✅ GitOps Sync-Wave 재정렬 (00~70) + upstream Helm/CRD 분리
- ✅ Docker Hub 단일 이미지 파이프라인 + External Secrets 운영 안정화
- ⚠️ RabbitMQ Operator/CR 장애로 Pending, MVP API 개발 이후 재도입 예정
- 🚧 API 개발 중
