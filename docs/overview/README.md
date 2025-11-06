# 📊 프로젝트 개요

> **♻️ 이코에코(Eco²) Backend - 7-Node Self-Managed Kubernetes 클러스터**

## 🎯 프로젝트 요약

**♻️ 이코에코(Eco²) - AI 기반 쓰레기 분류 및 재활용 코칭 서비스**

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

## 🏗️ 아키텍처 개요

### 7-Node Kubernetes Cluster

```
Control Plane (1 Node)
├─ Master (t3.medium, 2 vCPU, 4GB) - $30/월
│  ├─ kube-apiserver, etcd, scheduler, controller
│  ├─ ArgoCD (GitOps)
│  └─ AWS Load Balancer Controller

Worker Nodes (6 Nodes)
├─ Worker-1 (t3.medium, 2 vCPU, 4GB) - $30/월
│  └─ Application Pods (auth, users, locations)
│
├─ Worker-2 (t3.medium, 2 vCPU, 4GB) - $30/월
│  └─ Async Workers (AI Workers, Batch Workers)
│
├─ Monitoring (t3.medium, 2 vCPU, 4GB) - $30/월
│  └─ Prometheus + Grafana
│
├─ PostgreSQL (t3.medium, 2 vCPU, 4GB) - $30/월
│  └─ Primary DB (StatefulSet, 50GB PVC)
│
├─ RabbitMQ (t3.medium, 2 vCPU, 4GB) - $30/월
│  └─ Message Broker (Cluster Operator, 20GB PVC)
│
└─ Redis (t3.small, 1 vCPU, 2GB) - $15/월
   └─ Cache + Result Backend

총 비용: $195/월 (EC2) + S3 $5/월 = $200/월
```

### 핵심 기술 스택

```
Infrastructure:
├─ Kubernetes (kubeadm) - Self-Managed, 7-Node
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
├─ OpenAI GPT-4o Vision
├─ Kakao Map API
└─ OAuth 2.0 (카카오, 네이버, 구글)
```

---

## 📊 프로젝트 상태

### Phase 완료 현황 (v0.4.1)

```
✅ Phase 1: 인프라 프로비저닝 (Terraform)
✅ Phase 2: Kubernetes 플랫폼 구축 (7-Node)
✅ Phase 3: 인프라 자동화 (Ansible 75개 작업)
✅ Phase 4: Monitoring (Prometheus + Grafana)
✅ Phase 5: CNI (Calico VXLAN)
✅ Phase 6: Storage (EBS CSI Driver, gp3)
✅ Phase 7: Networking (ALB Controller, Ingress)
✅ Phase 8: GitOps (ArgoCD + GitHub Actions)

🔄 Phase 9: Application Stack 배포 (진행 중)
⏳ Phase 10: 고급 배포 전략 (계획 중)
```

### 개발 현황

```
Infrastructure: ✅ 100% 완료
├─ Terraform (7 Nodes)
├─ Ansible (75 작업)
├─ AWS ALB Controller
├─ ArgoCD (GitOps)
└─ 자동화 스크립트

Documentation: ✅ 100% 완료
└─ 70+ 문서

Application: 🔄 진행 중
└─ FastAPI 서비스 개발
```

---

## 💡 핵심 의사결정

### Self-Managed Kubernetes 선택 이유

**배경: 9개월 엔터프라이즈 클라우드 플랫폼 개발 경험**

```
✅ 대규모 AWS 클라우드 플랫폼 개발
✅ Kubernetes 프로덕션 운영
✅ Multi-tenant 아키텍처 설계
✅ IaC (Terraform/Ansible) 전문성
✅ 엔터프라이즈급 트러블슈팅
```

**AI 도구 활용**

```
Cursor + Claude 4.5 Sonnet:
✅ Terraform 모듈 자동 생성
✅ Ansible Playbook 75개 작업
✅ 문서화 자동화 (70+ 문서)
✅ 복잡한 문제 20-40분 내 해결

생산성:
- 개발 시간: 80% 단축
- 문제 해결: 6배 빠름
```

**비용 효율**

```
Self-Managed: $200/월
EKS: $293/월 ($73 Control Plane + $220 Nodes)
절감: $93/월 (32%)
```

---

## 📚 주요 문서

### Architecture
- [Decision Summary](../architecture/decision-summary.md) ⭐⭐⭐⭐⭐
- [Why Self-Managed](../architecture/why-self-managed-k8s.md) ⭐⭐⭐⭐⭐
- [AI Worker Queue Design](../architecture/ai-worker-queue-design.md) ⭐⭐⭐⭐
- [Service Architecture](../architecture/SERVICE_ARCHITECTURE.md) ⭐⭐⭐⭐
- [CI/CD Pipeline](../architecture/CI_CD_PIPELINE.md) ⭐⭐⭐⭐

### Infrastructure
- [IaC Quick Start](../infrastructure/IaC_QUICK_START.md) ⭐⭐⭐⭐⭐
- [IaC Terraform Ansible](../infrastructure/iac-terraform-ansible.md) ⭐⭐⭐⭐⭐
- [VPC Network Design](../infrastructure/vpc-network-design.md) ⭐⭐⭐⭐
- [CNI Comparison](../infrastructure/cni-comparison.md) ⭐⭐⭐
- [Cluster Resources](../infrastructure/CLUSTER_RESOURCES.md) ⭐⭐⭐⭐

### Deployment
- [GitOps ArgoCD Helm](../deployment/gitops-argocd-helm.md) ⭐⭐⭐⭐⭐
- [Deployment Setup](../deployment/DEPLOYMENT_SETUP.md) ⭐⭐⭐⭐⭐
- [GHCR Setup](../deployment/ghcr-setup.md) ⭐⭐⭐⭐

### Guides
- [ArgoCD 운영 가이드](../guides/ARGOCD_GUIDE.md) ⭐⭐⭐⭐⭐
- [Setup Checklist](../guides/SETUP_CHECKLIST.md) ⭐⭐⭐⭐⭐
- [Etcd Health Check Guide](../guides/ETCD_HEALTH_CHECK_GUIDE.md) ⭐⭐⭐⭐
- [Helm Status Guide](../guides/HELM_STATUS_GUIDE.md) ⭐⭐⭐⭐
- [Rebuild Guide](../guides/REBUILD_GUIDE.md) ⭐⭐⭐⭐

### Troubleshooting
- **[Troubleshooting (통합 문서)](../troubleshooting/TROUBLESHOOTING.md)** ⭐⭐⭐⭐⭐

---

## 🚀 빠른 시작

```bash
# 1. 인프라 프로비저닝
./scripts/deployment/provision.sh

# 2. 상태 확인
kubectl get nodes
kubectl get pods -A

# 3. ArgoCD 접속
https://growbin.app/argocd

# 4. Grafana 접속
https://growbin.app/grafana
```

---

**최종 업데이트**: 2025-11-06  
**문서 버전**: v0.4.1  
**프로젝트 상태**: 🚧 초기 개발 단계 (Pre-Production)

**프로덕션 준비 로드맵**:
- v0.5.0: Application Stack 배포 완료
- v0.6.0: 모니터링 & 알림 강화
- v0.7.0: 고급 배포 전략 (Canary, Blue-Green)
- v0.8.0: 성능 최적화 & 보안 강화
- v0.9.0: 프로덕션 사전 검증
- **v1.0.0**: 🚀 프로덕션 릴리스 (서비스 정식 배포)
