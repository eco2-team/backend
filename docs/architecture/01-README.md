# 🏗️ 아키텍처 문서

> **13-Node Kubernetes Cluster Architecture + Worker Local SQLite WAL**  
> **Self-Managed + Terraform + Ansible 완전 자동화**  
> **Eco² (이코에코) - v0.6.0**

## 🎯 핵심 문서

### 최종 아키텍처 ⭐

1. **[최종 K8s 아키텍처](final-k8s-architecture.md)** ⭐⭐⭐⭐⭐
   - 13-Node 클러스터 구조
   - Worker Local SQLite WAL 패턴
   - GitOps 파이프라인
   - 전체 시스템 설계
   
2. **[서비스 아키텍처](SERVICE_ARCHITECTURE.md)** ⭐⭐⭐⭐⭐
   - Terraform + Ansible 구조
   - 13-Node 배포 프로세스
   - 인프라 배포 다이어그램
   - Worker Local WAL 통합

3. **[CI/CD 파이프라인](CI_CD_PIPELINE.md)** ⭐⭐⭐⭐
   - GitHub Actions + ArgoCD
   - Rolling Update 전략
   - Canary 배포 분석
   - GHCR 컨테이너 레지스트리
   
4. **[Self-Managed Kubernetes 선택 배경](why-self-managed-k8s.md)** ⭐⭐⭐⭐
   - EKS vs kubeadm 비교
   - 비용 분석
   - 13-Node 진화 과정

### 네트워크 & 트래픽

5. **[네트워크 라우팅 구조](NETWORK_ROUTING_STRUCTURE.md)** ⭐⭐⭐⭐
   - ALB → Ingress → Service → Pod
   - Path-based routing
   - Calico CNI

6. **[Pod 배치 및 응답 흐름](POD_PLACEMENT_AND_RESPONSE_FLOW.md)** ⭐⭐⭐
   - NodeSelector 기반 배치
   - 요청/응답 플로우

7. **[모니터링 트래픽 흐름](MONITORING_TRAFFIC_FLOW.md)** ⭐⭐⭐
   - Prometheus 메트릭 수집
   - Grafana 시각화

### 기술 설계

8. [Task Queue 설계](task-queue-design.md)
   - RabbitMQ 5개 큐
   - Celery Worker 분리

9. [이미지 처리 아키텍처](image-processing-architecture.md)
   - S3 기반 저장소
   - Pre-signed URL

### 네트워크 & CNI

10. [Calico CNI 비교](../infrastructure/cni-comparison.md)
   - Flannel → Calico 전환
   - VXLAN vs BGP

11. [ALB & Calico 패턴](ALB_CALICO_PATTERNS_RESEARCH.md)
    - target-type: instance
    - NodePort 연동

### 추가 검토
   
12. [Polling vs WebSocket](polling-vs-websocket.md)
   - 실시간 통신 방식

---

## 📁 설계 검토 과정

**[design-reviews/](design-reviews/)** (이전: decisions/)

의사결정 과정을 담은 문서들:
- [배포 옵션 비교](design-reviews/deployment-options-comparison.md)
- [Self-Managed K8s 분석](design-reviews/self-managed-k8s-analysis.md)
- [EKS 비용 분석](design-reviews/eks-cost-breakdown.md)
- [GitOps 멀티 서비스](design-reviews/gitops-multi-service.md)
- [서비스 아키텍처](SERVICE_ARCHITECTURE.md) ⭐ (Terraform/Ansible 기반)
- [마이크로서비스 아키텍처](design-reviews/06-microservices-architecture.md) (의사결정 과정)

---

## 🏗️ 13-Node Architecture (v0.6.0)

### 노드 구성

```
Tier 1: Control Plane (1 노드)
  └─ Master Node (t3a.large, 8GB)
     ├─ kube-apiserver, scheduler, controller, etcd
     └─ Cluster 관리

Tier 2: API Services (6 노드)
  ├─ API-Auth (t3a.medium, 4GB) - 인증/인가
  ├─ API-Userinfo (t3a.medium, 4GB) - 사용자 정보
  ├─ API-Location (t3a.medium, 4GB) - 위치 서비스
  ├─ API-Waste (t3a.medium, 4GB) - 쓰레기 분석
  ├─ API-Recycle-Info (t3a.medium, 4GB) - 재활용 정보
  └─ API-Chat-LLM (t3a.medium, 4GB) - LLM 챗봇

Tier 3: Worker Services (2 노드)
  ├─ Worker-Storage (t3a.large, 8GB)
  │  ├─ S3 Upload Worker
  │  ├─ Worker Local SQLite WAL
  │  └─ PostgreSQL 동기화
  └─ Worker-AI (t3a.large, 8GB)
     ├─ AI Analysis Worker
     ├─ Worker Local SQLite WAL
     └─ PostgreSQL 동기화

Tier 4: Infrastructure (4 노드)
  ├─ RabbitMQ (t3a.medium, 4GB) - 메시지 브로커
  ├─ PostgreSQL (t3a.medium, 4GB) - 중앙 DB
  ├─ Redis (t3a.medium, 4GB) - 캐시
  └─ Monitoring (t3a.medium, 4GB) - Prometheus + Grafana
```

### 주요 특징

#### Worker Local SQLite WAL
- **패턴**: Robin (Local Write + Async Sync)
- **로컬 저장소**: SQLite WAL
- **중앙 DB**: PostgreSQL
- **동기화**: 배치 동기화 (5분 주기)
- **복구**: WAL 기반 자동 복구

#### CDN + S3 이미지 캐싱
- **CDN**: CloudFront
- **저장소**: S3 버킷 (prod-sesacthon-images)
- **도메인**: images.ecoeco.app (예정)
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

✅ 4-node vs 7-node vs 13-node
   → 13-node (마이크로서비스 분리, 확장성, 고가용성)

✅ Path-based vs Host-based routing
   → Path-based (단일 도메인, API Gateway 패턴, 비용 절감)

✅ RabbitMQ WAL vs Worker Local WAL
   → Worker Local SQLite WAL (네트워크 부하 감소, 성능 향상, 로컬 복구)

✅ Redis 이미지 캐싱 vs CDN
   → CloudFront + S3 (글로벌 캐싱, 낮은 레이턴시, 비용 효율)

✅ Helm vs ArgoCD
   → 둘 다 사용 (Helm Charts + ArgoCD GitOps)
```

---

## 💾 총 리소스

### vCPU 및 메모리
- **총 vCPU**: 26 vCPU
  - Master: 2 vCPU
  - API (6개): 12 vCPU (2 × 6)
  - Worker (2개): 4 vCPU (2 × 2)
  - Infra (4개): 8 vCPU (2 × 4)
  
- **총 메모리**: 60 GB
  - Master: 8 GB
  - API (6개): 24 GB (4 × 6)
  - Worker (2개): 16 GB (8 × 2)
  - Infra (4개): 12 GB (3 × 4, Monitoring 제외 모두 t3a.medium에서 4GB로 조정)

### AWS 인스턴스 타입
- **t3a.large** (2 vCPU, 8GB): Master, Worker-Storage, Worker-AI (총 3개)
- **t3a.medium** (2 vCPU, 4GB): API 6개 + Infra 4개 (총 10개)

---

## 📚 참고 문서

- [VPC 네트워크 설계](../infrastructure/vpc-network-design.md)
- [Worker WAL 구현 가이드](../guides/WORKER_WAL_IMPLEMENTATION.md)
- [모니터링 설정](../deployment/MONITORING_SETUP.md)
- [자동 재구축 가이드](../deployment/AUTO_REBUILD_GUIDE.md)
- [버전 가이드](../development/VERSION_GUIDE.md)

---

**최종 업데이트**: 2025-11-07  
**아키텍처 버전**: 3.0 (13-Node + Worker Local SQLite WAL)  
**앱 이름**: Eco² (이코에코)
