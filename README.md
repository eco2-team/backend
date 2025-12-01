# Eco² Backend

> **Version**: v0.9.0 | [Changelog](CHANGELOG.md)

<img width="3840" height="2160" alt="515829337-6a4f523a-fa37-49de-b8e1-0a5befe26605" src="https://github.com/user-attachments/assets/e6c7d948-aa06-4bbb-b2fc-237aa7f01223" />


- Self-managed Kubernetes, ArgoCD/Helm-charts/Kustomize 기반 GitOps Sync-wave로 운영하는 14-Nodes 마이크로서비스 플랫폼입니다.
- AI 폐기물 분류·근처 제로웨이스트샵 안내·챗봇 등 도메인 API와 데이터 계층, GitOps 파이프라인을 모노레포로 관리합니다.

---

## Service Architecture
![A18323CF-A487-42F9-A7FE-2317E8B5104D_1_105_c](https://github.com/user-attachments/assets/9206be51-429f-486e-aa02-45530b702927)


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
| my | 사용자 정보 | `docker.io/mng990/eco2:my-{env}-latest` |
| scan | Lite RAG + GPT 5.1 Vision 폐기물 분류 | `docker.io/mng990/eco2:scan-{env}-latest` |
| chat | Lite RAG + GPT 5.1 챗봇 | `docker.io/mng990/eco2:chat-{env}-latest` |
| character | 캐릭터 제공 | `docker.io/mng990/eco2:character-{env}-latest` |
| location | 지도/수거함 검색 | `docker.io/mng990/eco2:location-{env}-latest` |
| images | 이미지 업로드 | `docker.io/mng990/eco2:image-{env}-latest` |

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
## GitOps Architecture
![9093CE45-C239-4549-B1FA-10D2800BAD58_1_105_c](https://github.com/user-attachments/assets/9942e5f0-19d8-4777-9875-79623c53f30f)

Eco² 클러스터는 ArgoCD App-of-Apps 패턴을 중심으로 운영되며, 모든 인프라·데이터·애플리케이션이 Git 선언(Argo ApplicationSet) → Sync Wave → PostSync Hook 순으로 자동화되어 있습니다.

### App-of-Apps + Sync Wave
- 루트 앱이 여러 ApplicationSet을 생성하고, 각 AppSet 안의 실제 서비스/인프라가 argocd.argoproj.io/sync-wave 값으로 순서화된다.
- Wave 번호는 음수부터 양수까지 자유롭게 쓰며, 인프라(네임스페이스·CNI) → 시크릿/데이터 → API → Ingress 순으로 번호를 올려 의존성을 강제합니다.
- Reconcile 간 경합(CRD 없어 CrashLoop, Secret 없이 Ingress 먼저 올라오는 문제 등)을 제거했고, Git 상 wave 번호 자체가 런북 순서와 일치하도록 설계했습니다.

### Sync Hook 활용
- 일반 리소스는 Sync 단계에서 처리하고, DB 마이그레이션/점검은 PostSync Job으로 작성해 도메인 배포 직후 자동 실행합니다.
- Hook 종류별 사용처: PreSync(사전 검증/ConfigMap), Sync(리소스 기본 적용), PostSync(DB 주입·헬스체크·슬랙 알림), SyncFail(롤백/에러 리포트).
- 특히 도메인 API 배포 시 PostSync에서 스키마 주입/부트스트랩 잡을 실행해 “배포 → 마이그레이션” 순서를 보장합니다.

### Wave 설계 원칙
- 인프라 레이어: CNI, NetworkPolicy, ALB Controller, ExternalDNS, Observability 등 공통 컴포넌트는 낮은 Wave에 배치합니다.
- 데이터/시크릿 레이어: ExternalSecret → Secret → 데이터베이스/스토리지 → Operator/Instance 순으로 Wave를 띄워 “컨트롤러 → 인스턴스” 의존성을 명확히 했습니다.
- 애플리케이션 레이어: 60-apis-appset.yaml에서 도메인 API 전체를 Healthy 상태로 올린 뒤, 마지막 Wave 70에서 Ingress를 열어 외부 라우팅을 붙입니다. (Wave 설계 배경, 추가 사례)

### CI 파이프라인 연동
- 코드 변경 → GitHub Actions CI → Docker Image 빌드 & 푸시 → Helm/Kustomize 오버레이 업데이트 → ArgoCD Auto-Sync 순으로 이어집니다.
- CI 워크플로는 ci-services.yml, ci-infra.yml 등에서 정의되며, 도메인 서비스별로 테스트/빌드/이미지 푸시를 수행한 뒤 clusters/ 디렉터리의 ApplicationSet이 새 이미지 태그를 참조합니다.
- ArgoCD는 Auto-Sync + Wave 정책에 따라 배포 순서를 보장하고, PostSync Hook으로 DB 마이그레이션을 자동 실행합니다.

---

## Sync Wave Layout

![C4702A4B-B344-47EC-AB4A-7B2529496F44_1_105_c](https://github.com/user-attachments/assets/55c2b6bd-3324-4486-a146-1758cf86ea7c)

| Wave | 파일 (dev/prod 공통) | 설명 | Source Path / Repo |
|------|----------------------|------|--------------------|
| 0 | `00-crds.yaml` | ALB / External Secrets / Postgres / Redis / Prometheus 등 플랫폼 CRD 번들 | `platform/crds/{env}` |
| 2 | `02-namespaces.yaml` | 비즈니스·데이터·플랫폼 Namespace 정의 | `workloads/namespaces/{env}` |
| 3 | `03-rbac-storage.yaml` | ServiceAccount, RBAC, StorageClass, GHCR Pull Secret | `workloads/rbac-storage/{env}` |
| 6 | `06-network-policies.yaml` | Tier 기반 NetworkPolicy (default deny + DNS 허용) | `workloads/network-policies/{env}` |
| 10 | `10-secrets-operator.yaml` | External Secrets Operator Helm | Helm repo `charts.external-secrets.io` |
| 11 | `11-secrets-cr.yaml` | SSM Parameter → Kubernetes Secret ExternalSecret | `workloads/secrets/external-secrets/{env}` |
| 15 | `15-alb-controller.yaml` | AWS Load Balancer Controller Helm | Helm repo `aws/eks-charts` |
| 16 | `16-external-dns.yaml` | ExternalDNS Helm (Route53 자동화) | Helm repo `kubernetes-sigs/external-dns` |
| 20 | `20-monitoring-operator.yaml` | kube-prometheus-stack Helm | Helm repo `prometheus-community/kube-prometheus-stack` |
| 21 | `21-grafana.yaml` | Grafana Helm (독립 UI) | Helm repo `grafana/grafana` |
| 27 | `27-postgresql.yaml` | Bitnami PostgreSQL (standalone) | Helm repo `bitnami/postgresql` |
| 28 | `28-redis-operator.yaml` | Bitnami Redis Replication + Sentinel | Helm repo `bitnami/redis` |
| 60 | `60-apis-appset.yaml` | 도메인 API ApplicationSet (auth, my, scan, character, location, info, chat) | `workloads/domains/<service>/{env}` |
| 70 | `70-ingresses.yaml` | API·Argocd·Grafana Ingress ApplicationSet | `workloads/ingress/{service}/{env}` |

- Calico CNI는 Ansible(kubeadm bootstrap)에서 1회 설치하며, RabbitMQ Operator/CR은 안정화 완료 후 재도입합니다.
- ArgoCD Sync-wave로 의존성 순서를 보장하며, 패키지 의존성이 높은 플랫폼은 Helm-charts로 관리·배포합니다.
- AWS Load Balancer Controller·External Secrets·Postgres/Redis Operator는 upstream Helm chart를 `skipCrds: true`로 설치합니다.
- Operator에 의존하는 CRD와 CR은 `platform/{crds | cr}/{env}`에서 Kustomzie Overlay 방식으로 관리합니다.
- 모든 API는 공통 base(kustomize) 템플릿을 상속하고, 환경별 patch에서 이미지 태그·환경 변수·노드 셀렉터만 조정합니다.

---

### Namespace + Label Layout

![B13B764A-E597-4691-93F4-56F5C9FC0AB1](https://github.com/user-attachments/assets/1dc545ab-93db-4990-8a48-4df4dfb7adf0)

- “포지션(part-of) → 계층(tier) → 역할(role)” 순으로 라벨을 붙인 뒤 네임스페이스로 매핑합니다.
- Taint/Tolerance를 활용해 라벨과 매칭되는 노드로 파드의 배치가 제한되며, 계층별 network policy 격리가 적용됩니다.
- 이코에코(Eco²)에서 네임스페이스와 라벨은 컨트롤 포인트를 맡으며, 도메인/역할/책임/계층 추상화를 통해 개발 및 운영 복잡도를 낮춥니다.

### 상세 설명
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

---

### Network Topology

#### ALB가 Pod를 인지하는 경로
![CC86B4CB-7C2C-4602-BC10-B42B481948FD_4_5005_c](https://github.com/user-attachments/assets/ecbb091a-7310-4116-8d7a-f04d05e84aa4)

- Ingress는 `location-api` Service(NodePort 31666)를 통해 파드가 노출되고 있는 노드 IP와 포트 정보를 확인합니다.
- Endpoints 정보를 AWS Load Balancer Controller가 감지해 Target Group에 노드 IP + NodePort를 등록하고, ALB 리스너/규칙을 생성·업데이트합니다.

#### Cluster IP가 아닌 NodePort를 선택한 이유
- 이코에코의 클러스터는 Calico VXLAN으로 터널링된 **L2 오버레이 네트워크**를 사용합니다.
- Ingress가 어떤 노드/파드로 라우팅할지 알아야 하는데, ClusterIP Service를 사용하면 클러스터 외부에서 이를 인지할 수 없어 별도 프록시가 요구됩니다.
- NodePort로 파드를 노출하면 노드 IP:포트 조합만으로 ALB → Target Group → Ingress → Pod 통신이 가능해지며, 중간 레이어 및 hop을 최소화합니다.

#### Client <-> Pod 트래픽 경로

![17DBA027-2EDF-459E-9B4D-4A3A0AB10F0C](https://github.com/user-attachments/assets/26e8128b-8b7f-4b46-93d1-c85553f4c853)

- 얖서 구축한 TG와 Ingress를 바탕으로 Client → ALB → Target Group → Ingress → 각 노드 내부 파드 순서로 전달됩니다.
- Path by Route를 수행하며, RestFul한 트래픽 토폴로지를 제공합니다.

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
├── workloads/           # Kustomize (namespaces, rbac, network, apis, ingress 등 K8s 리소스)
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
- [Scan](https://api.dev.growbin.app/api/v1/scan/docs)
- [Chat](https://api.dev.growbin.app/api/v1/chat/docs)
- [Images](https://api.dev.growbin.app/api/v1/images/docs)
- [My](https://api.dev.growbin.app/api/v1/user/docs)
- [Character](https://api.dev.growbin.app/api/v1/character/docs#/)

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
- ✅ API 개발 완료, 연동 테스트 진행중
