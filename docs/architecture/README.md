# 🏗️ 아키텍처 문서

> **4-Node Kubernetes Cluster Architecture**  
> **Self-Managed + Instagram + Robin Storage 패턴**

## 🎯 핵심 문서

### 최종 아키텍처 ⭐

1. **[4-Node 배포 아키텍처](deployment-architecture-4node.md)** ⭐⭐⭐⭐⭐
   - 완전한 시스템 구조
   - Mermaid 다이어그램 6개
   - Path-based routing (ALB)
   - End-to-end 데이터 흐름
   
2. **[Self-Managed Kubernetes 선택 배경](why-self-managed-k8s.md)** ⭐⭐⭐⭐
   - EKS vs kubeadm 비교
   - 비용: $180 vs $253 (29% 절감)
   - 4-tier 진화 과정
   - Instagram + Robin 패턴 적용

### 기술 설계

3. [Task Queue 설계](task-queue-design.md)
   - RabbitMQ 5개 큐
   - Celery Worker 분리
   - Instagram 패턴

4. [최종 K8s 아키텍처](final-k8s-architecture.md)
   - GitOps 파이프라인
   - 마이크로서비스 배치

### 네트워크 & CNI

5. [Calico CNI 비교](../infrastructure/cni-comparison.md)
   - Flannel → Calico 전환
   - VXLAN vs BGP

### 추가 기술 검토

6. [Istio Service Mesh](istio-service-mesh.md)
   - MVP 후 검토
   
7. [Polling vs WebSocket](polling-vs-websocket.md)
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
