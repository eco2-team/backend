# 📋 프로젝트 요약

> **AI Waste Coach Backend**  
> **4-Node Kubernetes 클러스터 기반 프로덕션급 인프라**

## 🎯 프로젝트 개요

**AI 기반 쓰레기 분류 및 재활용 코칭 서비스 - 백엔드 API 서버**

사용자가 쓰레기를 촬영하면 GPT-4o Vision이 분석하고, 분류 방법과 재활용 팁을 제공하는 생활형 AI 환경 코치 서비스

### 주요 기능

1. **AI 쓰레기 스캐너** (GPT-4o Vision)
   - 이미지 기반 쓰레기 분석
   - 재질, 형태, 혼합 여부 인식
   - 분류 방법 제안

2. **위치 기반 재활용 수거함 제안** (Kakao Map API)
   - 가장 가까운 수거함 검색
   - 지도 기반 네비게이션

3. **LLM 기반 피드백 코칭**
   - 실용적 세척 방법
   - 분리 요령
   - 재질별 관리 팁

4. **소셜 로그인** (OAuth 2.0)
   - 카카오, 네이버, 구글

---

## 🏗️ 최종 아키텍처

### 4-Node Kubernetes Cluster

```
Tier 1: Control + Monitoring
├─ Master (t3.large, 8GB) - $60/월
│  ├─ kube-apiserver, etcd, scheduler, controller
│  ├─ Prometheus + Grafana
│  └─ ArgoCD

Tier 2: Sync API (Application)
├─ Worker-1 (t3.medium, 4GB) - $30/월
│  ├─ auth-service ×2
│  ├─ users-service ×1
│  └─ locations-service ×1

Tier 3: Async Workers
├─ Worker-2 (t3.medium, 4GB) - $30/월
│  ├─ AI Workers ×3 (GPT-4o Vision)
│  ├─ Batch Workers ×2
│  └─ waste-service ×2

Tier 4: Stateful Storage
└─ Storage (t3.large, 8GB) - $60/월
   ├─ RabbitMQ ×3 (HA Cluster)
   ├─ PostgreSQL (StatefulSet)
   ├─ Redis (Deployment)
   └─ Celery Beat ×1

총 비용: $185/월 (EC2 $180 + S3 $5)
```

### 핵심 기술 스택

```
Infrastructure:
├─ Kubernetes (kubeadm) - Self-Managed, 4-Node
├─ Calico VXLAN - CNI
├─ AWS ALB Controller - L7 Routing
├─ Terraform - IaC (AWS 리소스)
└─ Ansible - Configuration (75개 작업)

GitOps:
├─ GitHub Actions - CI
├─ ArgoCD - CD
├─ Helm - Charts
└─ GHCR - Registry (무료)

Backend:
├─ FastAPI - Reactor Pattern (Sync API)
├─ Celery + RabbitMQ - Async Processing
├─ PostgreSQL - Primary DB
├─ Redis - Cache + Result Backend
└─ S3 - Pre-signed URL (이미지)

Networking:
├─ Route53 - DNS (growbin.app)
├─ ALB - L7 Load Balancing
├─ ACM - SSL/TLS (*.growbin.app)
└─ Path-based Routing

Monitoring:
├─ Prometheus - Metrics
├─ Grafana - Visualization
└─ Metrics Server - HPA

External APIs:
├─ GPT-4o Vision - 이미지 분석
└─ Kakao Map - 위치 검색
```

---

## 📊 개발 현황

### 완료된 작업 ✅

```
Infrastructure (100%):
✅ Terraform 모듈 (VPC, EC2, S3, ACM, Route53)
✅ Ansible Playbook 75개 작업
✅ 4-Node 클러스터 구성
✅ AWS ALB Controller 설정
✅ Calico VXLAN CNI
✅ RabbitMQ HA (3-node)
✅ PostgreSQL StatefulSet
✅ Redis Deployment
✅ 자동화 스크립트 12개

Documentation (100%):
✅ 아키텍처 설계 문서 10개
✅ 인프라 구성 문서 5개
✅ 가이드 문서 7개
✅ 의사결정 문서 8개 (design-reviews)
✅ Overview 문서 3개
✅ 총 70+ 문서

Automation (100%):
✅ auto-rebuild.sh (40-50분 자동 배포)
✅ connect-ssh.sh (SSH 접속)
✅ remote-health-check.sh (헬스체크)
✅ reset-node.sh (노드 초기화)
```

### 진행 중 작업 🔄

```
Application Development (20%):
🔄 5개 마이크로서비스 스켈레톤
🔄 Helm Charts (기본 템플릿)
⏳ FastAPI 코드
⏳ Celery Task 구현
⏳ Database Schema
⏳ API 엔드포인트

GitOps Pipeline (50%):
✅ ArgoCD 설정 완료
✅ Helm 기본 구조
⏳ GitHub Actions Workflows
⏳ GHCR 이미지 빌드
⏳ 자동 배포 테스트
```

---

## 🎯 핵심 의사결정

### 결정 #1: Self-Managed Kubernetes

```
선택: kubeadm (Self-Managed)
기각: AWS EKS

이유:
✅ 9개월 엔터프라이즈 클라우드 플랫폼 개발 경험
✅ Cursor + Claude 4.5로 생산성 6배
✅ 비용 27% 절감 ($253 → $185)
✅ 완전한 제어 (Control Plane 접근)
✅ IaC 자동화 (Terraform + Ansible)
```

### 결정 #2: 4-Node Architecture

```
선택: 1M + 3W (역할 분리)
기각: 3-Node 혼재

이유:
✅ Instagram 패턴 (Worker 분리)
✅ Robin Storage 패턴 (Stateful 격리)
✅ 독립 스케일링
✅ 리소스 최적화
```

### 결정 #3: AWS ALB Controller

```
선택: AWS ALB + ACM
기각: Nginx Ingress + Let's Encrypt

이유:
✅ Cloud-native (AWS 네이티브)
✅ ACM SSL 자동 갱신
✅ Path-based routing (/api/v1/*)
✅ target-type: ip (Pod 직접)
```

### 결정 #4: RabbitMQ HA

```
선택: RabbitMQ 3-node HA
기각: Redis Queue, AWS SQS

이유:
✅ 메시지 보장 (Durable Queues)
✅ 5개 큐 분리 (장애 격리)
✅ DLX (Dead Letter Exchange)
✅ HA Cluster (3-node)
```

---

## 📈 비용 분석

### 월 비용: $185

```
EC2 Instances: $180/월
├─ Master (t3.large, 8GB): $60
├─ Worker-1 (t3.medium, 4GB): $30
├─ Worker-2 (t3.medium, 4GB): $30
└─ Storage (t3.large, 8GB): $60

S3 (이미지 저장): $5/월
├─ 저장: $0.023/GB
├─ 요청: $0.005/1K
└─ 예상: 1,000장/월

기타:
├─ Route53: $0.5/월
├─ ACM: $0 (무료)
└─ Data Transfer: ~$2/월

━━━━━━━━━━━━━━━━━━━━━━━━━━━━
총: $185/월

vs EKS: $253/월
절감: $68/월 (-27%)
```

### 개발 시간: 8일

```
엔터프라이즈 경험 + AI 도구 활용:

Phase 1: 의사결정 (3일)
├─ EKS vs Self-Managed 검토
├─ 비용 분석
└─ 아키텍처 설계

Phase 2: 구현 (3일)
├─ Terraform 작성 (4시간)
├─ Ansible 작성 (1일)
├─ 문서화 (4시간)
└─ 스크립트 자동화 (4시간)

Phase 3: 테스트 (2일)
├─ 배포 테스트
├─ 안정성 검증
└─ 문서 정리

━━━━━━━━━━━━━━━━━━━━━━━━━━━━
총: 8일 (AI 도구 활용)
전통적 방식: 3주 → 85% 단축
```

---

## 📚 문서 구조

### Core Documents (필수)

1. **[배포 가이드](../../DEPLOYMENT_GUIDE.md)** ⭐⭐⭐⭐⭐
   - 40-50분 자동 배포
   - 전체 프로세스

2. **[구축 체크리스트](../guides/SETUP_CHECKLIST.md)** ⭐⭐⭐⭐⭐
   - 단계별 작업
   - 우선순위 관리

3. **[4-Node 배포 아키텍처](../architecture/deployment-architecture-4node.md)** ⭐⭐⭐⭐⭐
   - 전체 시스템 다이어그램
   - End-to-end 흐름

### Architecture Documents

- [Why Self-Managed K8s](../architecture/why-self-managed-k8s.md)
- [Decision Summary](../architecture/decision-summary.md)
- [Final K8s Architecture](../architecture/final-k8s-architecture.md)
- [Task Queue Design](../architecture/task-queue-design.md)
- [Design Reviews](../architecture/design-reviews/) (01-07)

### Infrastructure Documents

- [VPC 네트워크 설계](../infrastructure/vpc-network-design.md)
- [K8s 클러스터 구축](../infrastructure/k8s-cluster-setup.md)
- [IaC 구성](../infrastructure/iac-terraform-ansible.md)
- [CNI 비교](../infrastructure/cni-comparison.md)

---

## 🚀 빠른 시작

### 인프라 자동 구축 (40-50분)

```bash
cd /Users/mango/workspace/SeSACTHON/backend

# 완전 자동 배포
./scripts/auto-rebuild.sh

# 또는 단계별
./scripts/rebuild-cluster.sh
```

### 서비스 개발

```bash
# 각 서비스 코드 작성
# Helm Charts 업데이트
# Git Push → ArgoCD 자동 배포!
```

---

## 🎯 현재 상태

```
Infrastructure: ✅ 100% 완료
├─ Terraform 모듈
├─ Ansible Playbook
├─ 자동화 스크립트
└─ 4-Node 클러스터 준비

Documentation: ✅ 100% 완료
├─ 70+ 문서
├─ Mermaid 다이어그램
└─ 의사결정 과정

Application: 🔄 20% 진행
├─ 서비스 스켈레톤
├─ Helm Chart 기본
└─ 코드 작성 대기

GitOps: 🔄 50% 진행
├─ ArgoCD 설정 완료
├─ Helm 기본 구조
└─ CI/CD 구성 중
```

---

## 📊 기술 하이라이트

### 9개월 엔터프라이즈 경험 적용

```
✅ 대규모 AWS 인프라 설계
✅ Kubernetes 프로덕션 운영
✅ Multi-AZ 고가용성
✅ IaC 전문성
✅ 엔터프라이즈급 트러블슈팅
```

### AI 도구 활용 (Cursor + Claude 4.5)

```
생산성:
- Terraform: 3시간 → 30분
- Ansible: 1주일 → 1일
- 문서화: 2일 → 4시간
→ 80% 시간 단축

품질:
- 모범 사례 자동 적용
- 복잡한 문제 20-40분 해결
- 일관된 코드 스타일
```

### 프로덕션급 인프라

```
✅ Self-Managed Kubernetes (kubeadm)
✅ 4-Tier Architecture (Instagram + Robin)
✅ Calico VXLAN CNI
✅ AWS ALB Controller (L7)
✅ RabbitMQ HA (3-node)
✅ StatefulSet (PostgreSQL)
✅ Auto Scaling (HPA)
✅ Monitoring (Prometheus + Grafana)
```

---

## 📁 프로젝트 구조

```
SeSACTHON/backend/
├── 📄 루트 문서
│   ├── README.md                       # 프로젝트 소개
│   ├── DEPLOYMENT_GUIDE.md            # 배포 가이드 ⭐⭐⭐⭐⭐
│   └── GIT_FLOW_COMPLETED.md          # Git 브랜치 전략
│
├── 🏗️ terraform/                      # Infrastructure as Code
│   ├── main.tf                        # 4-Node 정의
│   ├── vpc.tf, s3.tf, acm.tf
│   ├── alb-controller-iam.tf
│   └── modules/ (VPC, Security Groups, EC2)
│
├── 🤖 ansible/                         # Configuration Management
│   ├── site.yml                       # Master Playbook
│   ├── playbooks/ (9개)
│   │   ├── 02-master-init.yml
│   │   ├── 03-worker-join.yml
│   │   ├── 04-cni-install.yml (Calico VXLAN)
│   │   ├── 05-addons.yml
│   │   ├── 06-cert-manager-issuer.yml
│   │   ├── 07-alb-controller.yml
│   │   ├── 07-ingress-resources.yml
│   │   ├── 08-monitoring.yml
│   │   └── 09-etcd-backup.yml
│   └── roles/ (Common, Docker, Kubernetes, RabbitMQ)
│
├── ⚙️ scripts/                        # Automation
│   ├── auto-rebuild.sh                # 완전 자동 (40-50분)
│   ├── rebuild-cluster.sh             # 대화형
│   ├── connect-ssh.sh                 # SSH 접속
│   ├── remote-health-check.sh         # 헬스체크
│   ├── reset-node.sh                  # 노드 초기화
│   └── get-instances.sh               # 인스턴스 조회
│
├── 📚 docs/                            # 70+ 문서
│   ├── overview/ (3개)                # 프로젝트 요약
│   ├── guides/ (5개)                  # 실용 가이드
│   ├── architecture/ (10개)           # 아키텍처 설계
│   │   └── design-reviews/ (01-07)    # 의사결정 과정
│   └── infrastructure/ (4개)          # 인프라 구성
│
└── ⚙️ 설정 파일
    ├── .github/workflows/ (CI/CD 계획)
    └── IaC 설정 (Terraform, Ansible)
```

---

## 🎯 다음 단계

### Phase 1: Application Development

```
⏳ 마이크로서비스 코드 작성
   ├─ auth-service (FastAPI)
   ├─ users-service
   ├─ waste-service
   ├─ recycling-service
   └─ locations-service

⏳ Celery Task 구현
   ├─ AI Vision 분석
   ├─ LLM 피드백 생성
   └─ 배치 작업

⏳ Database Schema
   ├─ Alembic Migration
   └─ 초기 데이터
```

### Phase 2: GitOps Pipeline

```
⏳ GitHub Actions
   ├─ CI Workflows (5개)
   ├─ Lint, Test, Build
   └─ GHCR Push

⏳ ArgoCD Applications
   ├─ 5개 서비스 등록
   └─ Auto Sync 설정

⏳ Helm Values
   ├─ Production 환경 설정
   └─ Secrets 관리
```

### Phase 3: Monitoring & Operations

```
⏳ Grafana Dashboard
   ├─ Cluster Overview
   ├─ Node Resources
   ├─ Pod Status
   └─ RabbitMQ Queues

⏳ Alerts
   ├─ Slack 통합
   ├─ DLQ 모니터링
   └─ Resource 경고
```

---

## 📚 주요 문서 링크

### 필수 문서 (시작 여기서!)

| 문서 | 설명 | 중요도 |
|------|------|--------|
| [배포 가이드](../../DEPLOYMENT_GUIDE.md) | 40-50분 자동 배포 | ⭐⭐⭐⭐⭐ |
| [4-Node 아키텍처](../architecture/deployment-architecture-4node.md) | 전체 시스템 다이어그램 | ⭐⭐⭐⭐⭐ |
| [VPC 네트워크](../infrastructure/vpc-network-design.md) | 보안 그룹 상세 | ⭐⭐⭐⭐ |
| [Self-Managed K8s 배경](../architecture/why-self-managed-k8s.md) | 의사결정 근거 | ⭐⭐⭐⭐ |

### 상세 문서

- **Architecture**: [../architecture/](../architecture/) - 10개 문서
- **Infrastructure**: [../infrastructure/](../infrastructure/) - 4개 문서  
- **Guides**: [../guides/](../guides/) - 5개 문서
- **Design Reviews**: [../architecture/design-reviews/](../architecture/design-reviews/) - 01-07

---

## 🎉 달성한 것

```
✅ 프로덕션급 4-Node Kubernetes 클러스터
✅ 완전 자동화된 배포 (40-50분)
✅ 70+ 포괄적 문서
✅ Instagram + Robin Storage 패턴 적용
✅ AWS ALB Controller (Cloud-native)
✅ RabbitMQ HA (3-node)
✅ Calico VXLAN CNI
✅ 9개월 엔터프라이즈 경험 적용
✅ AI 도구로 생산성 6배 향상
✅ EKS 대비 27% 비용 절감

기술 스택:
- 8 vCPU, 24GB RAM
- Terraform + Ansible
- 75개 자동화 작업
- 12개 유틸리티 스크립트
- GitOps 준비
```

---

**작성일**: 2025-10-31  
**문서 버전**: 3.0 (4-Node Architecture)  
**상태**: ✅ Infrastructure 완료, Application 개발 중  
**총 비용**: $185/월  
**배경**: 9개월 엔터프라이즈 경험 + AI 도구
