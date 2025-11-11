# SeSACTHON Backend Infrastructure

> **Self-Managed Kubernetes 기반 마이크로서비스 플랫폼**  
> AI 분석 기반 쓰레기 분류 애플리케이션의 백엔드 인프라

[![Kubernetes](https://img.shields.io/badge/Kubernetes-326CE5?style=flat&logo=kubernetes&logoColor=white)](https://kubernetes.io/)
[![Terraform](https://img.shields.io/badge/Terraform-7B42BC?style=flat&logo=terraform&logoColor=white)](https://www.terraform.io/)
[![Ansible](https://img.shields.io/badge/Ansible-EE0000?style=flat&logo=ansible&logoColor=white)](https://www.ansible.com/)
[![ArgoCD](https://img.shields.io/badge/ArgoCD-EF7B4D?style=flat&logo=argo&logoColor=white)](https://argoproj.github.io/cd/)
[![AWS](https://img.shields.io/badge/AWS-232F3E?style=flat&logo=amazon-aws&logoColor=white)](https://aws.amazon.com/)

---

## 📋 목차

- [프로젝트 개요](#-프로젝트-개요)
- [아키텍처](#-아키텍처)
- [빠른 시작](#-빠른-시작)
- [문서 구조](#-문서-구조)
- [GitOps 아키텍처](#-gitops-아키텍처)
- [주요 기능](#-주요-기능)
- [기술 스택](#-기술-스택)

---

## 🎯 프로젝트 개요

### 핵심 특징

```yaml
클러스터 규모: 14 Nodes (Self-Managed Kubernetes)
API 서비스: 7개 (auth, my, scan, character, location, info, chat)
Worker 서비스: 2개 (storage, ai)
인프라: PostgreSQL, Redis, RabbitMQ, Monitoring
배포 방식: GitOps (Terraform + Ansible + ArgoCD + Atlantis)
```

### 왜 Self-Managed Kubernetes?

- ✅ **완전한 제어**: CNI, 네트워크 정책, 보안 설정 완전 제어
- ✅ **비용 절감**: EKS 대비 약 70% 비용 절감 (클러스터 시간당 $0.10)
- ✅ **학습 가치**: Kubernetes 내부 동작 원리 이해
- ✅ **확장성**: Phase별 단계적 확장 가능

→ 자세한 내용: [docs/architecture/12-why-self-managed-k8s.md](docs/architecture/12-why-self-managed-k8s.md)

---

## 🏗️ 아키텍처

### 클러스터 구성 (14-Node)

```mermaid
graph TB
    subgraph "14-Node Production Architecture"
        subgraph "Master Nodes (1)"
            M[k8s-master<br/>t3.large<br/>2 vCPU, 8GB]
        end
        
        subgraph "API Nodes (7)"
            A1[auth<br/>t3.micro<br/>2 vCPU, 1GB]
            A2[my<br/>t3.micro<br/>2 vCPU, 1GB]
            A3[scan<br/>t3.small<br/>2 vCPU, 2GB]
            A4[character<br/>t3.micro<br/>2 vCPU, 1GB]
            A5[location<br/>t3.micro<br/>2 vCPU, 1GB]
            A6[info<br/>t3.micro<br/>2 vCPU, 1GB]
            A7[chat<br/>t3.small<br/>2 vCPU, 2GB]
        end
        
        subgraph "Worker Nodes (2)"
            W1[storage<br/>t3.small<br/>2 vCPU, 2GB]
            W2[ai<br/>t3.small<br/>2 vCPU, 2GB]
        end
        
        subgraph "Infra Nodes (4)"
            I1[postgresql<br/>t3.small<br/>2 vCPU, 2GB]
            I2[redis<br/>t3.micro<br/>2 vCPU, 1GB]
            I3[rabbitmq<br/>t3.small<br/>2 vCPU, 2GB]
            I4[monitoring<br/>t3.small<br/>2 vCPU, 2GB]
        end
    end
    
    Total["📊 Total: 14 nodes, 30 vCPU, 22GB RAM"]
    
    style M fill:#ff6b6b
    style A1 fill:#4ecdc4
    style A2 fill:#4ecdc4
    style A3 fill:#4ecdc4
    style A4 fill:#4ecdc4
    style A5 fill:#4ecdc4
    style A6 fill:#4ecdc4
    style A7 fill:#4ecdc4
    style W1 fill:#95e1d3
    style W2 fill:#95e1d3
    style I1 fill:#f38181
    style I2 fill:#f38181
    style I3 fill:#f38181
    style I4 fill:#f38181
    style Total fill:#ffd93d
```

### 네트워크 구조

```mermaid
graph TD
    A[🌐 Internet] --> B[☁️ CloudFront CDN]
    B --> C[⚖️ ALB<br/>Application Load Balancer]
    C --> D[🔒 Calico CNI<br/>Network Policy]
    D --> E[🚀 API Pods<br/>NodePort 30000-30007]
    E --> F[⚙️ Worker Pods<br/>Internal]
    F --> G[💾 PostgreSQL / Redis / RabbitMQ]
    
    style A fill:#e1f5ff
    style B fill:#b3e5fc
    style C fill:#81d4fa
    style D fill:#4fc3f7
    style E fill:#29b6f6
    style F fill:#039be5
    style G fill:#0277bd,color:#fff
```

→ 자세한 내용: [docs/architecture/05-final-k8s-architecture.md](docs/architecture/05-final-k8s-architecture.md)

---

## 🚀 빠른 시작

### 1️⃣ 사전 요구사항

```yaml
필수:
  - AWS 계정 (vCPU 할당량 32개)
  - Terraform >= 1.5.0
  - Ansible >= 2.14
  - kubectl >= 1.27
  - SSH 키 (~/.ssh/sesacthon.pem)

선택:
  - ArgoCD CLI
  - Helm >= 3.12
```

### 2️⃣ 인프라 프로비저닝 (Terraform)

```bash
cd terraform

# 초기화
terraform init

# 계획 확인
terraform plan

# 14-Node 클러스터 생성
terraform apply -auto-approve

# 예상 소요 시간: 15-20분
```

### 3️⃣ Kubernetes 클러스터 구성 (Ansible)

```bash
cd ansible

# Bootstrap (Docker, Kubernetes 설치)
ansible-playbook playbooks/site.yml

# 노드 라벨링
ansible-playbook playbooks/label-nodes.yml

# 예상 소요 시간: 15-20분
```

### 4️⃣ 애플리케이션 배포 (ArgoCD)

```bash
# ArgoCD ApplicationSet 배포
kubectl apply -f argocd/applications/ecoeco-14nodes-appset.yaml

# 상태 확인
argocd app list

# 예상 소요 시간: 5-10분
```

### 5️⃣ 전체 자동화 (추천)

```bash
# 모든 단계를 한 번에 실행
./scripts/cluster/auto-rebuild.sh

# 예상 소요 시간: 40-60분
```

→ 자세한 내용: [docs/deployment/AUTO_REBUILD_GUIDE.md](docs/deployment/AUTO_REBUILD_GUIDE.md)

---

## 📚 문서 구조

```mermaid
graph TD
    D[docs/]
    
    D --> A[architecture/<br/>아키텍처 설계]
    D --> DE[deployment/<br/>배포 가이드]
    D --> I[infrastructure/<br/>인프라 설정]
    D --> G[guides/<br/>운영 가이드]
    D --> T[troubleshooting/<br/>트러블슈팅]
    D --> DEV[development/<br/>개발 가이드]
    D --> AR[archive/<br/>히스토리 보관]
    
    A --> A1[01-README.md<br/>아키텍처 개요]
    A --> A2[05-final-k8s-architecture.md]
    A --> A3[12-why-self-managed-k8s.md]
    A --> A4[13-nodes-architecture.md]
    A --> A5[redis-jwt-blacklist-design.md]
    
    DE --> DE1[README.md<br/>배포 개요]
    DE --> DE2[AUTO_REBUILD_GUIDE.md<br/>자동 배포]
    DE --> DE3[gitops-automation-design.md]
    DE --> DE4[14-node-completion-summary.md]
    
    I --> I1[01-README.md<br/>인프라 개요]
    I --> I2[04-IaC_QUICK_START.md]
    I --> I3[k8s-label-annotation-system.md]
    
    G --> G1[ARGOCD_GUIDE.md]
    G --> G2[HELM_STATUS_GUIDE.md]
    G --> G3[session-manager-guide.md]
    
    T --> T1[README.md]
    T --> T2[ANSIBLE_SSH_TIMEOUT.md]
    T --> T3[CLOUDFRONT_ACM_CERTIFICATE_STUCK.md]
    
    DEV --> DEV1[01-README.md]
    DEV --> DEV2[04-git-workflow.md]
    
    AR --> AR1[13NODES_COMPLETE_SUMMARY.md]
    
    style D fill:#ffd93d
    style A fill:#ff6b6b
    style DE fill:#4ecdc4
    style I fill:#95e1d3
    style G fill:#f38181
    style T fill:#fcbad3
    style DEV fill:#aa96da
    style AR fill:#ffffd2
```

### 주요 문서 빠른 링크

| 분류 | 문서 | 설명 |
|------|------|------|
| **시작하기** | [IaC Quick Start](docs/infrastructure/04-IaC_QUICK_START.md) | Terraform + Ansible 빠른 시작 |
| **아키텍처** | [14-Node Architecture](docs/architecture/13-nodes-architecture.md) | 전체 아키텍처 설계 |
| **배포** | [Auto Rebuild Guide](docs/deployment/AUTO_REBUILD_GUIDE.md) | 자동 배포 스크립트 가이드 |
| **GitOps** | [GitOps Architecture](docs/deployment/GITOPS_ARCHITECTURE.md) | GitOps 전체 구성 상세 설명 |
| **GitOps** | [GitOps Quick Reference](docs/deployment/GITOPS_QUICK_REFERENCE.md) | GitOps 빠른 참조 가이드 |
| **GitOps** | [ArgoCD Access](docs/deployment/ARGOCD_ACCESS.md) | ArgoCD 접속 정보 및 사용법 |
| **모니터링** | [Monitoring Setup](docs/deployment/MONITORING_SETUP.md) | Prometheus + Grafana 설정 |
| **트러블슈팅** | [Troubleshooting Index](docs/troubleshooting/README.md) | 주요 이슈 해결 방법 |

---

## 🔄 GitOps 아키텍처

### 개요

이 프로젝트는 **완전한 GitOps 워크플로우**를 구현하여 인프라, 클러스터 설정, 애플리케이션 배포를 모두 Git을 통해 관리합니다.

### 4-Layer GitOps 구조

```mermaid
graph TB
    subgraph Layer3["Layer 3: Application Code - Developer"]
        L3A["🎯 애플리케이션 개발"]
        L3B["🔧 GitHub Actions CI"]
    end
    
    Layer3 -->|Build & Push| Layer2
    
    subgraph Layer2["Layer 2: Kubernetes Resources - ArgoCD"]
        L2A["🚀 K8s 리소스 배포"]
        L2B["⏱️ Auto-Sync 3분마다"]
        L2C["📁 k8s/*.yaml"]
    end
    
    Layer2 -->|kubectl apply| Layer1
    
    subgraph Layer1["Layer 1: Kubernetes Cluster - Ansible"]
        L1A["⚙️ 클러스터 설정"]
        L1B["🔨 Ansible 수동 실행"]
        L1C["📁 ansible/playbooks/*.yml"]
    end
    
    Layer1 -->|SSH & kubeadm| Layer0
    
    subgraph Layer0["Layer 0: AWS Infrastructure - Atlantis"]
        L0A["☁️ 인프라 생성"]
        L0B["🏗️ Atlantis + Terraform"]
        L0C["📁 terraform/*.tf"]
    end
    
    style Layer3 fill:#e1f5fe
    style Layer2 fill:#b3e5fc
    style Layer1 fill:#81d4fa
    style Layer0 fill:#4fc3f7
    style L3A fill:#fff
    style L3B fill:#fff
    style L2A fill:#fff
    style L2B fill:#fff
    style L2C fill:#fff
    style L1A fill:#fff
    style L1B fill:#fff
    style L1C fill:#fff
    style L0A fill:#fff
    style L0B fill:#fff
    style L0C fill:#fff
```

### 도구별 역할 구분

| 도구 | 관리 대상 | 실행 방식 | 사용 시점 |
|------|-----------|-----------|----------|
| **Atlantis** | AWS 리소스 (EC2, VPC, IAM) | PR 코멘트 `atlantis apply` | 인프라 변경 시 |
| **Ansible** | K8s 클러스터 설정 (Kubeadm, CNI) | `ansible-playbook` 수동 실행 | 클러스터 설정 변경 시 |
| **ArgoCD** | K8s 리소스 (Deployment, Service) | Git Auto-Sync (3분마다) | 애플리케이션 배포 시 |
| **GitHub Actions** | CI/CD (빌드, 테스트, 이미지) | Git Push 이벤트 | 코드 변경 시 |

### 변경 시나리오별 워크플로우

#### 시나리오 1: EC2 인스턴스 추가

```bash
# 1. terraform/variables.tf 수정
variable "scan_worker_count" {
  default = 3  # 2에서 변경
}

# 2. Pull Request 생성
# 3. Atlantis가 자동으로 terraform plan 실행
# 4. PR 코멘트: "atlantis apply"
# 5. AWS에 EC2 인스턴스 생성됨 ✅
```

#### 시나리오 2: Kubernetes CNI 업그레이드

```bash
# 1. ansible/playbooks/04-cni-install.yml 수정
# 2. Git Push
# 3. 수동 실행:
ansible-playbook -i ansible/inventory/hosts.ini \
  ansible/playbooks/04-cni-install.yml
# 4. CNI 업그레이드 완료 ✅
```

#### 시나리오 3: Auth API 버전 업데이트

```bash
# 1. src/auth/*.ts 코드 수정
# 2. Git Push
# 3. GitHub Actions 자동 실행:
#    - 테스트
#    - Docker 이미지 빌드 (v1.2.3)
#    - 이미지 푸시
#    - k8s/auth/auth-deployment.yaml 이미지 태그 업데이트
# 4. ArgoCD 자동 감지 및 배포 (3분 이내) ✅
```

#### 시나리오 4: PostgreSQL 리소스 증가

```bash
# 1. k8s/database/postgres-deployment.yaml 수정
resources:
  requests:
    memory: "2Gi"  # 1Gi에서 변경

# 2. Git Push
# 3. ArgoCD 자동 배포 ✅
```

### GitOps 접속 정보

#### Atlantis (Terraform GitOps)

| 항목 | 내용 |
|------|------|
| **URL** | https://atlantis.growbin.app |
| **Role** | AWS 인프라 관리 |
| **Workflow** | PR 기반 terraform plan/apply |

#### ArgoCD (Kubernetes GitOps)

| 항목 | 내용 |
|------|------|
| **URL** | https://argocd.growbin.app |
| **Username** | admin |
| **Password** | TLybIfgEpRr7rC8G |
| **Role** | K8s 애플리케이션 배포 |

> **보안**: 초기 비밀번호는 접속 후 즉시 변경하세요!

### Git 저장소 구조

```mermaid
graph LR
    subgraph "backend/"
        T[terraform/<br/>← Atlantis가 관리]
        A[ansible/<br/>← Ansible이 관리]
        K[k8s/<br/>← ArgoCD가 관리]
        S[src/<br/>← GitHub Actions가 빌드]
    end
    
    T --> T1[main.tf]
    T --> T2[vpc.tf]
    T --> T3[ec2.tf]
    
    A --> A1[playbooks/]
    A1 --> A2[site.yml]
    
    K --> K1[auth/]
    K --> K2[scan/]
    K --> K3[database/]
    
    S --> S1[auth/]
    S --> S2[scan/]
    
    style T fill:#ff6b6b
    style A fill:#4ecdc4
    style K fill:#95e1d3
    style S fill:#f38181
```

### 상세 문서

- [GitOps Architecture](docs/deployment/GITOPS_ARCHITECTURE.md) - 전체 구성 상세 설명
- [GitOps Quick Reference](docs/deployment/GITOPS_QUICK_REFERENCE.md) - 빠른 참조 가이드
- [ArgoCD Access](docs/deployment/ARGOCD_ACCESS.md) - ArgoCD 접속 및 사용법

---

## 🎯 주요 기능

### 1. GitOps 완전 자동화

```yaml
Terraform (IaC):
  - AWS 리소스 프로비저닝
  - Atlantis를 통한 PR 기반 인프라 변경

Ansible (Configuration):
  - Kubernetes 클러스터 구성
  - 수동 또는 자동화 도구 실행

ArgoCD (CD):
  - Kubernetes 리소스 자동 배포
  - ApplicationSet으로 멀티 서비스 관리
  - Auto-Sync (3분마다)
```

### 2. 마이크로서비스 아키텍처

```yaml
API Services (7):
  - auth: JWT 인증 (Redis Blacklist)
  - my: 사용자 정보 관리
  - scan: AI 이미지 분석 (비동기)
  - character: 캐릭터 시스템
  - location: 위치 기반 서비스
  - info: 정보 제공
  - chat: AI 챗봇 (WebSocket)

Worker Services (2):
  - storage: S3 이미지 처리
  - ai: AI 모델 추론 (SQLite WAL + MQ)

Infrastructure (4):
  - postgresql: 메인 DB
  - redis: JWT Blacklist + Cache-Aside
  - rabbitmq: 비동기 작업 큐
  - monitoring: Prometheus + Grafana
```

### 3. 고급 네트워킹

```yaml
CNI: Calico (Network Policy)
Ingress: AWS ALB Controller
Service Mesh: Native Kubernetes (향후 Istio 고려)
DNS: CoreDNS + External DNS (Route53)
CDN: CloudFront (이미지 최적화)
```

### 4. 모니터링 & 로깅

```yaml
Metrics:
  - Prometheus (메트릭 수집)
  - Grafana (시각화)
  - ServiceMonitor (자동 발견)

Logging:
  - CloudWatch Logs (중앙 집중)
  - Fluent Bit (로그 수집기)

Alerting:
  - Prometheus Alertmanager
  - 26+ Alert Rules
```

### 5. 보안

```yaml
네트워크:
  - Calico Network Policy
  - Security Group (Terraform)
  - Private Subnet (Worker, DB)

인증:
  - JWT with Redis Blacklist
  - Refresh Token Rotation
  - HTTPS/TLS (ALB, CloudFront)

시크릿:
  - Kubernetes Secrets
  - AWS Secrets Manager (계획 중)
```

---

## 🛠️ 기술 스택

### Infrastructure as Code

| 도구 | 역할 | 버전 |
|------|------|------|
| **Terraform** | AWS 리소스 프로비저닝 | 1.5.0+ |
| **Ansible** | Kubernetes 클러스터 구성 | 2.14+ |
| **Atlantis** | Terraform GitOps 자동화 | Latest |

### Kubernetes

| 컴포넌트 | 구현 | 비고 |
|----------|------|------|
| **Control Plane** | kubeadm | Self-Managed |
| **CNI** | Calico | Network Policy 지원 |
| **Ingress** | AWS ALB Controller | ALB 자동 생성 |
| **Storage** | AWS EBS CSI Driver | GP3, 동적 프로비저닝 |
| **DNS** | CoreDNS | 내장 |

### CI/CD

| 도구 | 역할 | 통합 |
|------|------|------|
| **GitHub Actions** | CI Pipeline | PR 기반 Workflow |
| **ArgoCD** | Kubernetes CD | GitOps |
| **Helm** | Package Manager | Chart 관리 |
| **GHCR** | Container Registry | GitHub 통합 |

### Monitoring

| 도구 | 역할 | 메트릭 |
|------|------|--------|
| **Prometheus** | 메트릭 수집 | 18+ ServiceMonitors |
| **Grafana** | 시각화 | 대시보드 |
| **Alertmanager** | 알림 | 26+ Rules |

### Database & Cache

| 서비스 | 용도 | 설정 |
|--------|------|------|
| **PostgreSQL** | 메인 DB | 단일 인스턴스 |
| **Redis** | JWT Blacklist + Cache | Standalone |
| **RabbitMQ** | 작업 큐 | Cluster |

---

## 📊 현재 상태

### ✅ 완료된 작업

```yaml
Infrastructure:
  ✅ 14-Node Terraform 모듈 작성
  ✅ Ansible Playbook (Bootstrap, Label)
  ✅ VPC, Subnets, Security Groups
  ✅ CloudFront + ACM Certificate
  ✅ S3 Bucket (이미지 스토리지)

Kubernetes:
  ✅ kubeadm 클러스터 초기화
  ✅ Calico CNI 설치
  ✅ AWS ALB Controller
  ✅ EBS CSI Driver
  ✅ Label & Annotation 시스템

GitOps:
  ✅ Terraform + Atlantis 통합 (https://atlantis.growbin.app)
  ✅ ArgoCD + ApplicationSet (https://argocd.growbin.app)
  ✅ 4-Layer GitOps 아키텍처 구현
  ✅ 각 도구의 역할 명확히 분리
  ✅ GitHub Actions (간소화)

Monitoring:
  ✅ Prometheus + Grafana
  ✅ ServiceMonitor (18개)
  ✅ Alert Rules (26개)
  ✅ Grafana Dashboard

Documentation:
  ✅ 아키텍처 문서
  ✅ 배포 가이드
  ✅ 트러블슈팅 가이드
  ✅ GitOps 설계 문서
```

### 🚧 진행 중 / 계획

```yaml
진행 중:
  🔄 14-Node 클러스터 최초 배포
  🔄 Ansible playbook 실행
  🔄 ArgoCD ApplicationSet 배포

계획:
  📝 API 애플리케이션 개발
  📝 Worker 애플리케이션 개발
  📝 Service Mesh (Istio) 도입
  📝 EKS 전환 검토
```

---

## 🤝 기여

이 프로젝트는 **SeSACTHON 2025**의 일환으로 개발되었습니다.

### 팀

- **Infrastructure**: Kubernetes, Terraform, Ansible, GitOps
- **Backend**: FastAPI, PostgreSQL, Redis, RabbitMQ
- **Frontend**: React Native
- **AI**: TensorFlow, Computer Vision

---

## 📝 라이센스

이 프로젝트는 교육 목적으로 제작되었습니다.

---

## 🔗 관련 링크

- [Kubernetes 공식 문서](https://kubernetes.io/docs/)
- [Terraform AWS Provider](https://registry.terraform.io/providers/hashicorp/aws/latest/docs)
- [Ansible Kubernetes Collection](https://docs.ansible.com/ansible/latest/collections/kubernetes/core/index.html)
- [ArgoCD 문서](https://argo-cd.readthedocs.io/)
- [Calico 문서](https://docs.tigera.io/calico/latest/about/)

---

**Last Updated**: 2025-11-11  
**Version**: 14-Node Production Architecture + Full GitOps  
**Status**: ✅ Atlantis & ArgoCD Running

