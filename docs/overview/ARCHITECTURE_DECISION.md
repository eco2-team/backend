# 🎯 최종 아키텍처 결정

## ✅ 확정된 구성

### 인프라

**Kubernetes (kubeadm) - 1 Master + 2 Worker (non-HA)**

```
Master Node:
├─ Instance: t3.medium (2 vCPU, 4GB)
├─ 역할: Control Plane + 경량 Pod
└─ 비용: $30/월

Worker Node 1:
├─ Instance: t3.medium (2 vCPU, 4GB)
├─ 역할: Heavy Workload (waste, recycling, workers)
└─ 비용: $30/월

Worker Node 2:
├─ Instance: t3.small (2 vCPU, 2GB)
├─ 역할: Light Workload (auth, users, locations)
└─ 비용: $15/월

총 비용: $75/월 + 부가 서비스 $16 = $91/월
```

### 주요 기술 스택

- ✅ **Kubernetes (kubeadm)** - 컨테이너 오케스트레이션
- ✅ **ArgoCD** - GitOps CD
- ✅ **Helm** - 패키지 관리
- ✅ **Nginx Ingress** - API Gateway
- ✅ **Cert-manager** - SSL 자동화
- ✅ **Prometheus + Grafana** - 모니터링
- ✅ **RabbitMQ** - Message Broker

### 마이크로서비스 구조

```
5개 독립 서비스 (Namespace 분리):
├─ auth-service (2 replicas)
├─ users-service (1 replica)
├─ waste-service (2 replicas)
├─ recycling-service (2 replicas)
└─ locations-service (1 replica)

+ Celery Workers:
├─ waste-worker (3 replicas)
└─ recycling-worker (2 replicas)
```

## 📚 상세 문서

- [K8s 클러스터 구축 가이드](docs/architecture/k8s-cluster-setup.md)
- [아키텍처 결정 요약](docs/architecture/decision-summary.md)
- [전체 문서](docs/README.md)

## 🚀 다음 단계

1. EC2 인스턴스 3대 생성
2. Kubernetes 클러스터 구축 (1.5시간)
3. ArgoCD 설치 (20분)
4. Helm Charts 작성 (3시간)
5. RabbitMQ 설치 (30분)
6. 서비스 배포 (1시간)

---

**최종 확정일**: 2025-10-30  
**총 비용**: $105/월 (3노드 + RabbitMQ)  
**구축 시간**: 7시간
