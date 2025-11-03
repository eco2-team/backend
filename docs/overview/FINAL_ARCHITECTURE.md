# 🏗️ 최종 확정 아키텍처

> **4-Node Kubernetes Cluster (Self-Managed)**  
> **엔터프라이즈 경험 + AI 도구 = 프로덕션급 인프라**

## ✅ 기술 스택

### 인프라 (Instagram + Robin 패턴)
- **Kubernetes (kubeadm)** - 1 Master + 3 Workers (4-Node)
- **Terraform** - AWS 인프라 프로비저닝
- **Ansible** - K8s 클러스터 자동 구성 (75개 작업)
- **Calico VXLAN** - Container Network Interface

### GitOps & 배포
- **ArgoCD** - GitOps CD 엔진
- **Helm** - Kubernetes 패키지 관리
- **GitHub Actions** - CI 파이프라인
- **GHCR** - 컨테이너 레지스트리 (무료)

### 네트워킹
- **AWS ALB Controller** - L7 Load Balancing
- **ACM** - SSL/TLS 자동 관리
- **Route53** - DNS 관리
- **Path-based Routing** - 단일 도메인, 여러 서비스

### 마이크로서비스 (6개)
- **auth-service** - OAuth, JWT (Worker-1)
- **users-service** - 사용자 관리 (Worker-1)
- **locations-service** - 수거함 검색 (Worker-1)
- **waste-service** - 이미지 분석 (Worker-2)
- **recycling-service** - LLM 피드백 (계획)
- **default-backend** - 404 처리

### 비동기 처리 (Worker-2)
- **RabbitMQ** - Message Broker (Operator 관리, 단일 Pod, Storage)
- **Celery Workers** - 7개 Pods
  - AI Workers ×3 (q.ai, GPT-4o Vision)
  - Batch Workers ×2 (q.batch, 배치 작업)
  - API Workers ×2 (q.api, 외부 API)
- **Celery Beat** ×1 (Storage, 스케줄러)

### 데이터 (Storage Node)
- **PostgreSQL** - StatefulSet, 50GB PVC
- **Redis** - Deployment, Result Backend + Cache
- **S3** - 이미지 저장 (Pre-signed URL)

## 🎯 4-Tier Architecture

```
Tier 1: Control + Monitoring (Master, t3.large, 8GB)
├─ kube-apiserver, etcd, scheduler, controller
├─ Prometheus + Grafana
└─ ArgoCD

Tier 2: Sync API (Worker-1, t3.medium, 4GB)
├─ auth-service ×2
├─ users-service ×1
└─ locations-service ×1

Tier 3: Async Workers (Worker-2, t3.medium, 4GB)
├─ AI Workers ×3 (GPT-4o Vision)
├─ Batch Workers ×2
└─ waste-service ×2

Tier 4: Stateful Storage (Storage, t3.large, 8GB)
├─ RabbitMQ ×1 (Operator 관리, 단일 Pod)
├─ PostgreSQL (StatefulSet, 향후)
├─ Redis (Deployment)
└─ Celery Beat ×1
```

## 💰 비용

**$185/월**
- Master (t3.large, 8GB): $60/월
- Worker-1 (t3.medium, 4GB): $30/월
- Worker-2 (t3.medium, 4GB): $30/월
- Storage (t3.large, 8GB): $60/월
- S3 (이미지 저장): $5/월

**vs EKS: $253/월 → $68/월 절감 (27%)**

## 📊 구축 시간

- **수동**: 7시간 (kubeadm 단계별 설치)
- **IaC 자동화**: 40-50분 (Terraform + Ansible)
  - Terraform: 5-10분
  - Ansible: 35-40분

## 💪 핵심 강점

### 9개월 엔터프라이즈 경험

```
✅ AWS 클라우드 플랫폼 개발
✅ Kubernetes 프로덕션 운영
✅ Multi-AZ 고가용성 설계
✅ IaC 전문성 (Terraform/Ansible)
✅ 엔터프라이즈급 트러블슈팅
```

### AI 도구 시너지

```
경험 + AI 도구 = 최적 조합

Cursor + Claude 4.5:
- 개발 시간: 80% 단축
- 문제 해결: 6배 빠름
- 문서화 자동화: 70+ 문서
```

## 📚 상세 문서

### Architecture
- [Why Self-Managed K8s](../architecture/why-self-managed-k8s.md) ⭐⭐⭐⭐⭐
- [4-Node 배포 아키텍처](../architecture/deployment-architecture-4node.md)
- [최종 K8s 아키텍처](../architecture/final-k8s-architecture.md)
- [Task Queue 설계](../architecture/task-queue-design.md)

### Infrastructure
- [VPC 네트워크 설계](../infrastructure/vpc-network-design.md)
- [K8s 클러스터 구축](../infrastructure/k8s-cluster-setup.md)
- [IaC 구성](../infrastructure/iac-terraform-ansible.md)

### Deployment
- [배포 가이드](../../DEPLOYMENT_GUIDE.md)
- [구축 체크리스트](../guides/SETUP_CHECKLIST.md)

---

**작성일**: 2025-10-31  
**상태**: ✅ 프로덕션 준비 완료  
**총 비용**: $185/월  
**배경**: 9개월 엔터프라이즈 경험 + AI 도구
