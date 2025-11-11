# 🏗️ 아키텍처 문서

> **14-Node Kubernetes Cluster Architecture + GitOps**  
> **Self-Managed + Terraform + Ansible 완전 자동화**  
> **Eco² (이코에코) - v0.7.0**

## 🎯 핵심 문서

### 최종 아키텍처 ⭐

1. **[최종 K8s 아키텍처](05-final-k8s-architecture.md)** ⭐⭐⭐⭐⭐
   - 14-Node 클러스터 구조
   - GitOps 파이프라인
   - 전체 시스템 설계
   
2. **[서비스 아키텍처](03-SERVICE_ARCHITECTURE.md)** ⭐⭐⭐⭐⭐
   - Terraform + Ansible 구조
   - 14-Node 배포 프로세스
   - 인프라 배포 다이어그램

3. **[CI/CD 파이프라인](04-CI_CD_PIPELINE.md)** ⭐⭐⭐⭐
   - GitHub Actions + ArgoCD
   - Rolling Update 전략
   - Canary 배포 분석
   - GHCR 컨테이너 레지스트리
   
4. **[Self-Managed Kubernetes 선택 배경](12-why-self-managed-k8s.md)** ⭐⭐⭐⭐
   - EKS vs kubeadm 비교
   - 비용 분석
   - 14-Node 진화 과정

### 네트워크 & 트래픽

5. **[네트워크 라우팅 구조](06-NETWORK_ROUTING_STRUCTURE.md)** ⭐⭐⭐⭐
   - ALB → Ingress → Service → Pod
   - Subdomain-based routing
   - Calico CNI

6. **[Pod 배치 및 응답 흐름](07-POD_PLACEMENT_AND_RESPONSE_FLOW.md)** ⭐⭐⭐
   - NodeSelector 기반 배치
   - 요청/응답 플로우

7. **[모니터링 트래픽 흐름](08-MONITORING_TRAFFIC_FLOW.md)** ⭐⭐⭐
   - Prometheus 메트릭 수집
   - Grafana 시각화

### 기술 설계

8. **[Task Queue 설계](09-task-queue-design.md)**
   - RabbitMQ 큐
   - Celery Worker 분리

9. **[이미지 처리 아키텍처](10-image-processing-architecture.md)**
   - S3 기반 저장소
   - Pre-signed URL

### 네트워크 & CNI

10. **[Calico CNI 비교](../infrastructure/cni-comparison.md)**
   - Flannel → Calico 전환
   - VXLAN vs BGP

11. **[ALB & Calico 패턴](11-ALB_CALICO_PATTERNS_RESEARCH.md)**
    - target-type: instance
    - NodePort 연동

### 추가 검토
   
12. **[Redis JWT Blacklist 설계](redis-jwt-blacklist-design.md)**
   - JWT 인증 전략
   - Redis 캐시 전략

---

## 📁 설계 검토 과정

**[design-reviews/](design-reviews/)** 

의사결정 과정을 담은 문서들:
- [배포 옵션 비교](design-reviews/01-deployment-options-comparison.md)
- [Self-Managed K8s 분석](design-reviews/02-self-managed-k8s-analysis.md)
- [EKS 비용 분석](design-reviews/04-eks-cost-breakdown.md)
- [GitOps 멀티 서비스](design-reviews/05-gitops-multi-service.md)
- [서비스 아키텍처](03-SERVICE_ARCHITECTURE.md) ⭐ (Terraform/Ansible 기반)
- [마이크로서비스 아키텍처](design-reviews/06-microservices-architecture.md) (의사결정 과정)

---

## 🏗️ 14-Node Architecture (v0.7.0)

### 노드 구성

```
Tier 1: Control Plane (1 노드)
  └─ Master Node (t3.large, 8GB)
     ├─ kube-apiserver, scheduler, controller, etcd
     └─ Cluster 관리

Tier 2: API Services (7 노드)
  ├─ API-Auth (t3.micro, 1GB) - 인증/인가
  ├─ API-My (t3.micro, 1GB) - 사용자 정보
  ├─ API-Scan (t3.small, 2GB) - AI 이미지 분석
  ├─ API-Character (t3.micro, 1GB) - 캐릭터 시스템
  ├─ API-Location (t3.micro, 1GB) - 위치 서비스
  ├─ API-Info (t3.micro, 1GB) - 정보 제공
  └─ API-Chat (t3.small, 2GB) - AI 챗봇

Tier 3: Worker Services (2 노드)
  ├─ Worker-Storage (t3.small, 2GB)
  │  └─ S3 이미지 처리
  └─ Worker-AI (t3.small, 2GB)
     └─ AI 모델 추론

Tier 4: Infrastructure (4 노드)
  ├─ PostgreSQL (t3.small, 2GB) - 메인 DB
  ├─ Redis (t3.micro, 1GB) - JWT Blacklist + Cache
  ├─ RabbitMQ (t3.small, 2GB) - 작업 큐
  └─ Monitoring (t3.small, 2GB) - Prometheus + Grafana
```

### 주요 특징

#### GitOps 완전 자동화
- **Layer 0**: Terraform + Atlantis (AWS 인프라)
- **Layer 1**: Ansible (K8s 클러스터 설정)
- **Layer 2**: ArgoCD (K8s 리소스 배포)
- **Layer 3**: GitHub Actions (CI/CD)

#### CDN + S3 이미지 캐싱
- **CDN**: CloudFront
- **저장소**: S3 버킷
- **도메인**: images.growbin.app
- **캐싱**: CloudFront Edge 캐싱

---

## 📊 주요 결정사항

```
✅ kubeadm (Self-Managed) vs EKS
   → kubeadm 선택 (비용 절감, 학습 목적, 완전한 제어)

✅ Calico VXLAN vs Flannel
   → Calico VXLAN (안정성, 프로덕션 검증, NetworkPolicy)

✅ ALB vs Nginx Ingress
   → AWS ALB + ACM (Cloud-native, SSL 자동 관리, Route53 통합)

✅ 4-node vs 7-node vs 14-node
   → 14-node (마이크로서비스 분리, 확장성, 고가용성)

✅ Path-based vs Host-based routing
   → Subdomain-based (도메인별 분리, 명확한 API 구조)

✅ Helm vs ArgoCD
   → 둘 다 사용 (Helm Charts + ArgoCD GitOps)
```

---

## 💾 총 리소스

### vCPU 및 메모리
- **총 vCPU**: 30 vCPU
  - Master: 2 vCPU
  - API (7개): 14 vCPU
  - Worker (2개): 4 vCPU
  - Infra (4개): 10 vCPU
  
- **총 메모리**: 22 GB
  - Master: 8 GB
  - API (7개): 8 GB
  - Worker (2개): 4 GB
  - Infra (4개): 7 GB

### AWS 인스턴스 타입
- **t3.large** (2 vCPU, 8GB): Master (총 1개)
- **t3.small** (2 vCPU, 2GB): Scan, Chat, Workers, PostgreSQL, RabbitMQ, Monitoring (총 6개)
- **t3.micro** (2 vCPU, 1GB): Auth, My, Character, Location, Info, Redis (총 6개)

---

## 📚 참고 문서

- [VPC 네트워크 설계](../infrastructure/vpc-network-design.md)
- [모니터링 설정](../deployment/MONITORING_SETUP.md)
- [자동 재구축 가이드](../deployment/AUTO_REBUILD_GUIDE.md)
- [버전 가이드](../development/02-VERSION_GUIDE.md)
- [GitOps 아키텍처](../deployment/GITOPS_ARCHITECTURE.md)

---

**최종 업데이트**: 2025-11-11  
**아키텍처 버전**: v0.7.0 (14-Node + GitOps)  
**앱 이름**: Eco² (이코에코)
