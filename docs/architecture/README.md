# 🏗️ 아키텍처 문서

> **7-Node Kubernetes Cluster Architecture**  
> **Self-Managed + Terraform + Ansible 완전 자동화**

## 🎯 핵심 문서

### 최종 아키텍처 ⭐

1. **[최종 K8s 아키텍처](final-k8s-architecture.md)** ⭐⭐⭐⭐⭐
   - 7-Node 클러스터 구조
   - GitOps 파이프라인
   - 전체 시스템 설계
   
2. **[서비스 아키텍처](SERVICE_ARCHITECTURE.md)** ⭐⭐⭐⭐⭐
   - Terraform + Ansible 구조
   - 자동화 배포 프로세스
   - 인프라 배포 다이어그램

3. **[CI/CD 파이프라인](CI_CD_PIPELINE.md)** ⭐⭐⭐⭐
   - GitHub Actions + ArgoCD
   - Rolling Update 전략
   - Canary 배포 분석
   
4. **[Self-Managed Kubernetes 선택 배경](why-self-managed-k8s.md)** ⭐⭐⭐⭐
   - EKS vs kubeadm 비교
   - 비용: $180 vs $253 (29% 절감)
   - 7-node 진화 과정

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

## 🏗️ 4-Tier Architecture

```
Tier 1: Control + Monitoring (Master, t3.large, 8GB)
  ├─ kube-apiserver, scheduler, controller, etcd
  └─ Prometheus + Grafana

Tier 2: Sync API (Worker-1, t3.medium, 4GB)
  ├─ auth-service (FastAPI)
  ├─ users-service
  └─ locations-service

Tier 3: Async Workers (Worker-2, t3.medium, 4GB)
  ├─ celery-ai-worker (GPT-4o Vision)
  ├─ celery-batch-worker
  └─ celery-api-worker

Tier 4: Stateful Storage (Storage, t3.large, 8GB)
  ├─ RabbitMQ (HA 3-node cluster)
  ├─ PostgreSQL (StatefulSet)
  └─ Redis (Deployment)
```

---

## 📊 주요 결정사항

```
✅ kubeadm (Self-Managed) vs EKS
   → kubeadm 선택 (비용 -29%, 학습)

✅ Calico VXLAN vs Flannel
   → Calico VXLAN (안정성, 프로덕션 검증)

✅ ALB vs Nginx Ingress
   → AWS ALB + ACM (Cloud-native, SSL 자동)

✅ 3-node vs 4-node
   → 4-node (역할 분리, Instagram 패턴)

✅ Path-based vs Host-based routing
   → Path-based (단일 도메인, API Gateway)
```

---

## 📚 참고 문서

- [VPC 네트워크 설계](../infrastructure/vpc-network-design.md)
- [구축 체크리스트](../guides/SETUP_CHECKLIST.md)
- [배포 가이드](../../DEPLOYMENT_GUIDE.md)

---

**최종 업데이트**: 2025-10-31  
**아키텍처 버전**: 2.0 (4-Node Cluster)
