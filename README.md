# ♻️ AI Waste Coach Backend

> **AI가 쓰레기를 인식하고 분류하는 것을 넘어, '어떻게 버려야 하는지'까지 코칭하는 생활형 서비스**

## 📋 프로젝트 개요

사용자가 쓰레기를 찍으면 AI 비전(Vision) + LLM 기술을 결합하여 "이건 어디에 버려야 하지?"를 넘어서 "어떻게, 왜 그렇게 버려야 하는지"를 설명해주는 생활형 AI 환경 코치 서비스의 백엔드 API 서버입니다.

### 🎯 주요 기능

1. **AI 쓰레기 스캐너** (GPT-4o Vision)
   - 사용자가 카메라로 쓰레기를 찍으면 AI가 재질, 형태, 혼합 여부를 분석
   - 쓰레기 종류 및 분류 방법 제안

2. **위치 기반 재활용 수거함 제안** (Kakao Map)
   - 인식된 품목이 재활용 가능 자원일 경우, 가장 가까운 수거함 추천
   - 지도 기반 네비게이션 연동

3. **LLM 기반 피드백 코칭**
   - "이물질이 남아있네요. 미지근한 물에 30초 헹구면 깨끗하게 닦을 수 있어요." 등
   - 실제 세척법, 분리요령, 재질별 관리팁 제공

4. **소셜 로그인** (OAuth 2.0)
   - 카카오, 네이버, 구글 간편 로그인 지원

---

## 🚀 빠른 시작

### ⚡ 인프라 구축 (40-50분)

```bash
# Terraform + Ansible 완전 자동화
./scripts/auto-rebuild.sh

# 상세: DEPLOYMENT_GUIDE.md
```

---

## 🏗️ 4-Tier Layered Architecture

### Software Engineering 관점

```
Tier 1: Control Plane (Orchestration)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Master (t3.large, 8GB, $60/월)
├─ kube-apiserver, etcd, scheduler, controller
├─ Prometheus + Grafana (Monitoring)
└─ ArgoCD (GitOps)

관심사: "어떻게 워크로드를 배치하고 관리할 것인가?"

Tier 2: Data Plane (Business Logic)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Worker-1 + Worker-2 (t3.medium ×2, 4GB ×2, $60/월)

Worker-1 (Sync API):
├─ auth-service ×2 (OAuth, JWT)
├─ users-service ×1 (프로필, 이력)
└─ locations-service ×1 (수거함 검색)

Worker-2 (Async Processing):
├─ waste-service ×2 (이미지 분석 API)
├─ AI Workers ×3 (GPT-4o Vision)
└─ Batch Workers ×2 (배치 작업)

관심사: "비즈니스 로직을 어떻게 처리할 것인가?"
패턴: Reactor (Sync) + Task Queue (Async)

Tier 3: Message Queue (Middleware)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Storage 노드의 RabbitMQ HA ×3
├─ q.ai (AI Vision, Priority 10)
├─ q.batch (배치, Priority 1)
├─ q.api (외부 API, Priority 5)
├─ q.sched (예약, Priority 3)
└─ q.dlq (Dead Letter)

관심사: "메시지를 어떻게 안전하게 전달할 것인가?"

Tier 4: Persistence (Storage)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Storage 노드의 Database + Cache
├─ PostgreSQL (StatefulSet, 50GB)
├─ Redis (Result Backend + Cache)
└─ Celery Beat ×1 (스케줄러)

관심사: "데이터를 어떻게 영속적으로 저장할 것인가?"

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
노드: 4개, Tier: 4계층 (논리적 분리)
비용: $185/월 (EC2 $180 + S3 $5)
```

### 핵심 기술 스택

```
Infrastructure:
├─ Kubernetes (kubeadm) - Self-Managed
├─ Calico VXLAN - CNI
├─ AWS Load Balancer Controller - L7 Routing
├─ Terraform - IaC (AWS 리소스)
└─ Ansible - Configuration (75개 작업)

Tier 1 (Control Plane):
├─ Prometheus + Grafana - Monitoring
└─ ArgoCD - GitOps CD

Tier 2 (Data Plane):
├─ FastAPI - Reactor Pattern (Sync)
├─ Celery Workers - Task Queue (Async)
└─ S3 Pre-signed URL - Image Upload

Tier 3 (Message Queue):
└─ RabbitMQ HA (3-node) - Message Broker

Tier 4 (Persistence):
├─ PostgreSQL - RDBMS
├─ Redis - Cache + Result Backend
└─ Celery Beat - Scheduler

Networking:
├─ Route53 - DNS (growbin.app)
├─ ALB - L7 Load Balancing
├─ ACM - SSL/TLS (*.growbin.app)
└─ Path-based Routing (/api/v1/*)

External APIs:
├─ GPT-4o Vision - 이미지 분석
└─ Kakao Map - 위치 검색, OAuth
```

---

## 📚 문서

### ⭐ 필수 문서

| 문서 | 설명 | 중요도 |
|------|------|--------|
| [**배포 가이드**](DEPLOYMENT_GUIDE.md) | 4-Tier 클러스터 배포 | ⭐⭐⭐⭐⭐ |
| [**4-Tier 아키텍처**](docs/deployment/deployment-architecture-4node.md) | Layered Architecture | ⭐⭐⭐⭐⭐ |
| [**VPC 네트워크**](docs/infrastructure/vpc-network-design.md) | 네트워크 설계 | ⭐⭐⭐⭐ |
| [**Self-Managed K8s 배경**](docs/architecture/why-self-managed-k8s.md) | 의사결정 | ⭐⭐⭐⭐ |

### 📖 카테고리별 문서

#### 🏗️ [아키텍처](docs/architecture/)
- [Self-Managed K8s 선택 배경](docs/architecture/why-self-managed-k8s.md) - 의사결정 ⭐⭐⭐⭐⭐
- [Final K8s Architecture](docs/architecture/final-k8s-architecture.md) - 전체 시스템
- [Task Queue 설계](docs/architecture/task-queue-design.md) - Tier 3 Message Queue
- [Image Processing](docs/architecture/image-processing-architecture.md) - 이미지 분석 파이프라인
- [설계 검토 과정](docs/architecture/design-reviews/) - 01-07

#### 🚢 [배포](docs/deployment/)
- [4-Tier 배포 아키텍처](docs/deployment/deployment-architecture-4node.md) - 전체 다이어그램 ⭐⭐⭐⭐⭐
- [GitOps 배포](docs/deployment/gitops-argocd-helm.md) - ArgoCD + Helm
- [GHCR 설정](docs/deployment/ghcr-setup.md) - Container Registry

#### 🏗️ [인프라](docs/infrastructure/)
- [VPC 네트워크 설계](docs/infrastructure/vpc-network-design.md) - Security Groups, Subnets
- [K8s 클러스터 구축](docs/infrastructure/k8s-cluster-setup.md) - kubeadm 설치
- [IaC 구성](docs/infrastructure/iac-terraform-ansible.md) - Terraform + Ansible
- [CNI 비교](docs/infrastructure/cni-comparison.md) - Calico vs Flannel
- [Redis 구성](docs/infrastructure/redis-configuration.md) - Tier 4, Cache & State ⭐
- [RabbitMQ HA](docs/infrastructure/rabbitmq-ha-setup.md) - Tier 3, Message Queue ⭐

#### 🎯 [가이드](docs/guides/)
- [구축 체크리스트](docs/guides/SETUP_CHECKLIST.md) - 단계별 가이드
- [IaC 빠른 시작](docs/infrastructure/IaC_QUICK_START.md) - Terraform + Ansible
- [Session Manager](docs/guides/session-manager-guide.md) - SSH-less 접속

---

## 🗺️ 프로젝트 구조

```
SeSACTHON/backend/
├── README.md (이 파일)
├── DEPLOYMENT_GUIDE.md (배포 가이드) ⭐
│
├── docs/ (70+ 문서)
│   ├── overview/ (프로젝트 요약)
│   ├── architecture/ (4-Tier 설계)
│   ├── infrastructure/ (인프라 구성)
│   ├── deployment/ (배포 가이드)
│   ├── guides/ (실용 가이드)
│   └── getting-started/ (시작 가이드)
│
├── terraform/ (Infrastructure as Code)
│   ├── main.tf (4개 노드)
│   ├── vpc.tf, s3.tf, acm.tf
│   └── modules/
│
├── ansible/ (Configuration Management)
│   ├── site.yml (Master playbook)
│   ├── playbooks/ (9개)
│   └── roles/ (RabbitMQ, etc)
│
└── scripts/ (Automation, 12개)
    ├── auto-rebuild.sh (40-50분 자동 배포)
    ├── connect-ssh.sh
    └── remote-health-check.sh
```

---

## 🎯 4-Tier 설계 원칙

```
✅ Layered Architecture
   - 각 계층은 명확한 책임
   - 상위 → 하위만 의존

✅ Separation of Concerns
   - Control (Tier 1)
   - Processing (Tier 2)
   - Messaging (Tier 3)
   - Persistence (Tier 4)

✅ Single Responsibility
   - RabbitMQ: 메시지 전달만 (Tier 3)
   - PostgreSQL: 데이터 저장만 (Tier 4)
   
✅ Kubernetes Standard
   - Control Plane (표준 용어)
   - Data Plane (표준 용어)
```

---

## 👥 팀 구성

- **Backend**: 1명
- **Frontend**: 2명
- **AI**: 1명
- **Design**: 1명

## 📅 일정

- **해커톤**: 2025년 12월 1일 ~ 12월 2일 (무박 2일)
- **사전 개발**: 11월 중 완료 예정
- **배포**: 해커톤 당일

---

**Last Updated**: 2025-10-31  
**Version**: 3.0 (4-Tier Layered Architecture)  
**Team**: SeSACTHON Backend
