# 🏗️ 최종 확정 아키텍처

## ✅ 기술 스택

### 인프라
- **Kubernetes (kubeadm)** - 1 Master + 2 Worker (non-HA)
- **Terraform** - AWS 인프라 프로비저닝
- **Ansible** - K8s 클러스터 자동 구성

### GitOps & 배포
- **ArgoCD** - GitOps CD 엔진
- **Helm** - Kubernetes 패키지 관리
- **GitHub Actions** - CI 파이프라인 (서비스별 5개)
- **GHCR** - 컨테이너 레지스트리 (무료)

### 마이크로서비스 (5개)
- **auth-service** - OAuth, JWT (Namespace: auth)
- **users-service** - 사용자 관리 (Namespace: users)
- **waste-service** - 이미지 분석 (Namespace: waste)
- **recycling-service** - LLM 피드백 (Namespace: recycling)
- **locations-service** - 수거함 검색 (Namespace: locations)

### 비동기 처리
- **RabbitMQ** - Message Broker (5개 큐: fast, bulk, external, sched, dlq)
- **Celery Workers** - 4가지 타입, 12개 Pods
  - Fast Workers ×5 (q.fast, CPU 집약)
  - External-AI Workers ×3 (q.external, AI API)
  - External-LLM Workers ×2 (q.external, LLM API)
  - Bulk Workers ×2 (q.bulk, 배치)

### API Gateway & 통신
- **Nginx Ingress Controller** - Path-based routing
- **Short Polling** - 0.5초 간격 (Stateless)
- **Cert-manager** - Let's Encrypt SSL 자동화

### 데이터
- **PostgreSQL** - K8s Pod, Schema 분리 (auth, users, waste, recycling, locations)
- **Redis** - Result Backend, 캐싱

## 💰 비용

**$105/월**
- Master (t3.medium): $30/월
- Worker 1 (t3.medium): $30/월
- Worker 2 (t3.medium): $30/월
- Worker 3 (t3.small): $15/월
- 부가 서비스: $0 (모든 컴포넌트 Pod로 실행)

## 📊 구축 시간

- **수동**: 7시간 (kubeadm 단계별 설치)
- **IaC 자동화**: 35분 (Terraform 5분 + Ansible 30분)

## 📚 상세 문서

- [최종 K8s 아키텍처](docs/architecture/final-k8s-architecture.md)
- [K8s 클러스터 구축](docs/infrastructure/k8s-cluster-setup.md)
- [IaC 구성](docs/infrastructure/iac-terraform-ansible.md)
- [Task Queue 설계](docs/architecture/task-queue-design.md)
- [GitOps 배포](docs/deployment/gitops-argocd-helm.md)
- [구축 체크리스트](SETUP_CHECKLIST.md)

---

**작성일**: 2025-10-30  
**상태**: ✅ 최종 확정

