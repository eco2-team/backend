# ♻️ AI Waste Coach Backend

> **AI가 쓰레기를 인식하고 분류하는 것을 넘어, '어떻게 버려야 하는지'까지 코칭하는 생활형 서비스**

## 📋 프로젝트 개요

사용자가 쓰레기를 찍으면 AI 비전(Vision) + LLM 기술을 결합하여 "이건 어디에 버려야 하지?"를 넘어서 "어떻게, 왜 그렇게 버려야 하는지"를 설명해주는 생활형 AI 환경 코치 서비스의 백엔드 API 서버입니다.

### 🎯 주요 기능

1. **AI 쓰레기 스캐너**
   - 사용자가 카메라로 쓰레기를 찍으면 AI 비전 모델이 재질, 형태, 혼합 여부를 분석
   - 쓰레기 종류 및 분류 방법 제안

2. **위치 기반 재활용 수거함 제안**
   - 인식된 품목이 재활용 가능 자원일 경우, 가장 가까운 재활용 수거함/제로웨이스트샵 위치 추천
   - 지도 기반 네비게이션 연동

3. **LLM 기반 피드백 코칭**
   - "이물질이 남아있네요. 미지근한 물에 30초 헹구면 깨끗하게 닦을 수 있어요." 등 실용적 피드백
   - 실제 세척법, 분리요령, 재질별 관리팁 제공

4. **소셜 로그인 (OAuth 2.0)**
   - 카카오, 네이버, 구글 간편 로그인 지원

---

## 🚀 빠른 시작

### ⚡ 인프라 구축 (40-50분)

```bash
# Terraform + Ansible 완전 자동화
./scripts/auto-rebuild.sh

# 상세: DEPLOYMENT_GUIDE.md
```

### 📖 단계별 구축

**[배포 가이드](DEPLOYMENT_GUIDE.md)** ← 여기서 시작! ⭐⭐⭐⭐⭐

---

## 🏗️ 아키텍처

### 최종 구성 (4-Node Cluster)

**[4-Node 배포 아키텍처](docs/architecture/deployment-architecture-4node.md)** ⭐⭐⭐⭐⭐

```
Kubernetes (kubeadm, 1M + 3W, Self-Managed)
├─ Master: t3.large, 8GB ($60/월)
│  ├─ Control Plane (kube-apiserver, etcd, scheduler, controller)
│  └─ Monitoring (Prometheus, Grafana)
│
├─ Worker-1: t3.medium, 4GB ($30/월) - Application
│  └─ FastAPI Pods (auth, users, locations)
│
├─ Worker-2: t3.medium, 4GB ($30/월) - Async Workers
│  └─ Celery Workers (GPT-4o Vision)
│
└─ Storage: t3.large, 8GB ($60/월) - Stateful Services
   ├─ RabbitMQ (HA 3-node cluster)
   ├─ PostgreSQL
   └─ Redis

총 비용: $185/월 (EC2 $180 + S3 $5)
구축 시간: 40-50분 (자동화)
```

### 핵심 기술 스택

```
Infrastructure:
├─ Terraform (AWS VPC, EC2, S3, ACM, Route53)
├─ Ansible (Kubernetes 자동 설치)
├─ AWS Load Balancer Controller (L7 Routing)
├─ Calico VXLAN (CNI)
└─ cert-manager → ACM (SSL/TLS)

Kubernetes:
├─ kubeadm (Self-Managed)
├─ 4 nodes (8 vCPU, 24GB RAM)
├─ Path-based routing (/api/v1/*)
└─ Session Manager (SSH-less)

Backend:
├─ FastAPI (Reactor Pattern)
├─ Celery + RabbitMQ (Async)
├─ PostgreSQL + Redis
├─ S3 Pre-signed URL
└─ GPT-4o Vision

GitOps:
├─ ArgoCD (CD)
├─ GitHub Actions (CI)
├─ Helm Charts
└─ GHCR (무료 레지스트리)

Monitoring:
├─ Prometheus
├─ Grafana
└─ Metrics Server
```

### 네트워킹

```
Route53 (growbin.app)
   ↓
AWS ALB (Application Load Balancer)
├─ ACM SSL/TLS 자동 갱신
├─ HTTP → HTTPS 리다이렉트
└─ Path-based routing:
    ├─ /argocd       → ArgoCD Server
    ├─ /grafana      → Grafana Dashboard
    ├─ /api/v1/auth  → auth-service
    ├─ /api/v1/users → users-service
    ├─ /api/v1/waste → waste-service
    └─ /              → default-backend
```

---

## 🛠️ 기술 스택

### Infrastructure & DevOps
- **Kubernetes (kubeadm)** - Self-Managed K8s (4-Node)
- **Terraform** - AWS 인프라 프로비저닝
- **Ansible** - K8s 클러스터 자동 설정 (75개 커밋)
- **AWS Load Balancer Controller** - L7 Routing
- **Calico VXLAN** - CNI (Container Network Interface)
- **ArgoCD** - GitOps CD 엔진
- **Helm** - K8s 패키지 관리
- **GitHub Actions** - CI 파이프라인
- **GHCR** - 컨테이너 레지스트리 (무료)
- **cert-manager + ACM** - SSL 자동화

### Backend
- **Python 3.11+**
- **FastAPI** - 고성능 비동기 웹 프레임워크
- **Uvicorn** - ASGI 서버
- **Pydantic** - 데이터 검증

### Database
- **SQLAlchemy** - ORM
- **Alembic** - DB 마이그레이션
- **PostgreSQL** - 메인 데이터베이스
- **Redis** - Caching, Celery Result Backend

### Async Processing
- **Celery** - 비동기 Task Queue
- **RabbitMQ** - Message Broker (HA 3-node)

### Authentication
- **python-jose** - JWT 토큰
- **passlib** - 비밀번호 해싱
- **OAuth 2.0** - 소셜 로그인 (Kakao, Naver, Google)

### Code Quality
- **Black** - 코드 포맷터
- **Flake8** - 린터 (PEP 8)
- **isort** - Import 정렬
- **pycodestyle** - PEP 8 검사
- **pre-commit** - Git hooks

### Testing
- **pytest** - 테스트 프레임워크
- **pytest-asyncio** - 비동기 테스트

---

## 📚 문서

### ⭐ 필수 문서

| 문서 | 설명 | 중요도 |
|------|------|--------|
| [**배포 가이드**](DEPLOYMENT_GUIDE.md) | 4-Node 클러스터 배포 | ⭐⭐⭐⭐⭐ |
| [**4-Node 아키텍처**](docs/architecture/deployment-architecture-4node.md) | 전체 시스템 시각화 | ⭐⭐⭐⭐⭐ |
| [**VPC 네트워크**](docs/infrastructure/vpc-network-design.md) | 네트워크 설계 상세 | ⭐⭐⭐⭐ |
| [**Self-Managed K8s 선택 배경**](docs/architecture/why-self-managed-k8s.md) | EKS vs kubeadm | ⭐⭐⭐⭐ |

### 📖 카테고리별 문서

#### 🏗️ [아키텍처](docs/architecture/)
- [4-Node 배포 아키텍처](docs/architecture/deployment-architecture-4node.md) - 전체 시스템 ⭐⭐⭐⭐⭐
- [Self-Managed K8s 선택 배경](docs/architecture/why-self-managed-k8s.md) - 의사결정 과정
- [Task Queue 설계](docs/architecture/task-queue-design.md) - RabbitMQ + Celery
- [최종 K8s 아키텍처](docs/architecture/final-k8s-architecture.md) - GitOps 파이프라인
- [설계 검토 과정](docs/architecture/design-reviews/) - 의사결정 문서

#### 🏗️ [인프라](docs/infrastructure/)
- [VPC 네트워크 설계](docs/infrastructure/vpc-network-design.md) - 보안 그룹, 포트
- [K8s 클러스터 구축](docs/infrastructure/k8s-cluster-setup.md) - 수동 설치 (4-Node)
- [IaC 구성](docs/infrastructure/iac-terraform-ansible.md) - Terraform + Ansible
- [CNI 비교](docs/infrastructure/cni-comparison.md) - Calico vs Flannel

#### 🎯 [가이드](docs/guides/)
- [구축 체크리스트](docs/guides/SETUP_CHECKLIST.md) - 단계별 구축
- [IaC 빠른 시작](docs/guides/IaC_QUICK_START.md) - 자동화
- [Session Manager](docs/guides/session-manager-guide.md) - SSH-less 접속

---

## 🗺️ 프로젝트 구조

```
SeSACTHON/backend/
├── README.md (이 파일)
├── DEPLOYMENT_GUIDE.md (배포 가이드) ⭐
│
├── docs/ (문서)
│   ├── architecture/ (아키텍처 설계)
│   ├── infrastructure/ (인프라 구성)
│   └── guides/ (실용 가이드)
│
├── terraform/ (Infrastructure as Code)
│   ├── main.tf (4-node EC2)
│   ├── vpc.tf, s3.tf, acm.tf
│   └── modules/ (VPC, Security Groups, EC2)
│
├── ansible/ (Configuration Management)
│   ├── site.yml (Master playbook)
│   ├── playbooks/ (9개 playbook)
│   └── roles/ (Common, Docker, Kubernetes, RabbitMQ)
│
└── scripts/ (Automation)
    ├── auto-rebuild.sh (완전 자동)
    ├── connect-ssh.sh
    └── remote-health-check.sh
```

---

## 🔗 외부 링크

- [GitHub Repository](https://github.com/your-org/sesacthon-backend)
- [ArgoCD Dashboard](https://growbin.app/argocd)
- [Grafana Dashboard](https://growbin.app/grafana)

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
**Version**: 2.0 (4-Node Architecture)  
**Team**: SeSACTHON Backend
