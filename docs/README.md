# 📚 AI Waste Coach Backend - 문서

> **4-Node Kubernetes 클러스터 배포 문서**  
> **Instagram + Robin Storage 패턴 적용**

---

## 🚀 빠른 시작

### 처음이신가요?

**→ [DEPLOYMENT_GUIDE.md](../DEPLOYMENT_GUIDE.md)** - 배포 가이드부터 시작!

### 자동 배포

```bash
cd /Users/mango/workspace/SeSACTHON/backend

# 완전 자동 (확인 없음)
./scripts/auto-rebuild.sh

# 소요 시간: 40-50분
```

---

## 📖 문서 카테고리

### 🎯 [배포 가이드](guides/)

빠른 시작 및 실용 가이드

- **[구축 체크리스트](guides/SETUP_CHECKLIST.md)** ⭐⭐⭐⭐⭐
  - 단계별 구축 순서
  - 우선순위별 작업
  - 예상 시간
  
- [IaC 빠른 시작](guides/IaC_QUICK_START.md)
  - Terraform + Ansible 자동화
  
- [Session Manager 가이드](guides/session-manager-guide.md)
  - SSH 키 없이 EC2 접속
  
- [배포 환경 구축](guides/DEPLOYMENT_SETUP.md)
  - GitOps 파이프라인

### 🏗️ [인프라](infrastructure/)

네트워크 및 인프라 설계

- **[VPC 네트워크 설계](infrastructure/vpc-network-design.md)** ⭐⭐⭐
  - VPC (10.0.0.0/16)
  - 3 Public Subnets
  - Security Groups 상세
  - 포트 목록

---

## 🏗️ 최종 아키텍처

### 4-Node Cluster

```
Master (t3.large, 8GB) - $60/월
├─ Control Plane
└─ Prometheus + Grafana

Worker-1 (t3.medium, 4GB) - $30/월
└─ Application Pods (FastAPI)

Worker-2 (t3.medium, 4GB) - $30/월
└─ Celery Workers (Async)

Storage (t3.large, 8GB) - $60/월
├─ RabbitMQ (HA 3-node)
├─ PostgreSQL
└─ Redis

총: $185/월 (EC2 $180 + S3 $5)
```

### 네트워킹

```
Route53 (DNS)
   ↓
ALB (L7 Routing + ACM TLS)
   ↓
Path-based:
   /argocd → ArgoCD
   /grafana → Grafana
   /api/v1/auth → auth-service
   /api/v1/users → users-service
   /api/v1/waste → waste-service
   ...
```

---

## 🔧 유틸리티 스크립트

```bash
# 인스턴스 조회
./scripts/get-instances.sh

# SSH 접속
./scripts/connect-ssh.sh master
./scripts/connect-ssh.sh storage

# 노드 초기화
./scripts/reset-node.sh master
./scripts/reset-node.sh all

# 재구축
./scripts/auto-rebuild.sh

# 헬스체크
./scripts/remote-health-check.sh master
```

---

## 📊 주요 기술

```
Infrastructure:
- Terraform (IaC)
- Ansible (Configuration)
- AWS (VPC, EC2, S3, ALB, ACM, Route53)

Kubernetes:
- kubeadm (1M + 3W)
- Calico VXLAN (CNI)
- AWS Load Balancer Controller
- cert-manager

Application:
- FastAPI (Reactor Pattern)
- Celery + RabbitMQ (Async)
- PostgreSQL + Redis
- S3 (Pre-signed URL)
- GPT-4o Vision

Monitoring:
- Prometheus + Grafana
- Metrics Server

GitOps:
- ArgoCD
- GitHub Actions
- GHCR
```

---

## 🗺️ 문서 네비게이션

```
SeSACTHON/backend/
├── README.md (프로젝트 메인)
├── DEPLOYMENT_GUIDE.md (배포 가이드) ⭐
│
├── docs/
│   ├── README.md (이 파일)
│   │
│   ├── guides/ (실용 가이드)
│   │   ├── SETUP_CHECKLIST.md ⭐⭐⭐⭐⭐
│   │   ├── IaC_QUICK_START.md
│   │   └── session-manager-guide.md
│   │
│   └── infrastructure/ (인프라 설계)
│       └── vpc-network-design.md ⭐⭐⭐
│
├── terraform/ (Infrastructure as Code)
└── ansible/ (Configuration Management)
```

---

## 🎯 다음 단계

```
Phase 1: Infrastructure ✅ (완료)
- Terraform
- 4-node cluster
- VPC, Security Groups

Phase 2: Platform ✅ (완료)
- Kubernetes
- Calico VXLAN
- ALB Controller
- RabbitMQ

Phase 3: Application 🔄 (진행 중)
- 5개 마이크로서비스 (FastAPI)
- Celery Workers
- PostgreSQL, Redis

Phase 4: GitOps ⏳ (대기)
- ArgoCD 설정
- GitHub Actions
- 자동 배포
```

---

**문서 버전**: 2.0  
**최종 업데이트**: 2025-10-31  
**아키텍처**: 4-Node Instagram-style

