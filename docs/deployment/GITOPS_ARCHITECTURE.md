# GitOps 아키텍처 - 전체 구성

> 14-Node Microservices Architecture의 GitOps 워크플로우 및 도구 역할 정리

## 📋 목차

1. [GitOps 개요](#gitops-개요)
2. [도구별 역할 구분](#도구별-역할-구분)
3. [전체 워크플로우](#전체-워크플로우)
4. [각 도구의 관리 범위](#각-도구의-관리-범위)
5. [Git 저장소 구조](#git-저장소-구조)
6. [변경 시나리오별 워크플로우](#변경-시나리오별-워크플로우)

---

## GitOps 개요

### GitOps란?

**Git을 Single Source of Truth로 사용하여 인프라와 애플리케이션을 선언적으로 관리**

```
Git Repository (Source of Truth)
    ↓
Automation Tools (Atlantis, ArgoCD, Ansible)
    ↓
Infrastructure & Applications (AWS, Kubernetes)
```

---

## 도구별 역할 구분

### 1. Atlantis (Terraform GitOps)

**역할**: AWS 인프라 관리 (Infrastructure as Code)

**관리 대상**:
- ✅ VPC, Subnet, Security Group
- ✅ EC2 Instances (Master, Workers, Monitoring, DB, Storage 노드)
- ✅ IAM Roles, Policies
- ✅ Route53 DNS
- ✅ CloudFront CDN
- ✅ S3 Buckets
- ✅ AWS Load Balancer

**워크플로우**:
```
1. Terraform 코드 수정 (terraform/*.tf)
2. Pull Request 생성
3. Atlantis가 자동으로 `terraform plan` 실행 → PR에 결과 코멘트
4. 리뷰 후 승인
5. PR 코멘트: `atlantis apply`
6. Atlantis가 `terraform apply` 실행 → AWS 인프라 변경
```

**Atlantis가 관리하지 않는 것**:
- ❌ Kubernetes 클러스터 설정 (Kubeadm, CNI, 노드 초기화)
- ❌ Kubernetes 리소스 (Deployment, Service, ConfigMap)
- ❌ 애플리케이션 배포

---

### 2. Ansible (Cluster Configuration Management)

**역할**: Kubernetes 클러스터 설정 및 초기화

**관리 대상**:
- ✅ Kubernetes 클러스터 초기화 (Kubeadm)
- ✅ CNI 설치 (Calico)
- ✅ 노드 레이블링 (node-role, feature labels)
- ✅ 시스템 패키지 설치 (kubectl, helm, docker)
- ✅ Kubernetes 인프라 컴포넌트 배포:
  - Cert-Manager
  - AWS Load Balancer Controller
  - Metrics Server
  - Ingress 리소스
  - Prometheus, Grafana
  - Atlantis
  - ArgoCD

**워크플로우**:
```
1. Ansible Playbook 수정 (ansible/playbooks/*.yml)
2. Git Push
3. ArgoCD Hooks가 감지하여 Ansible 실행 (자동)
   또는
   수동 실행: ansible-playbook -i ansible/inventory/hosts.ini ansible/playbooks/site.yml
4. Kubernetes 클러스터 설정 변경
```

**Ansible이 관리하지 않는 것**:
- ❌ AWS 인프라 생성/삭제 (EC2, VPC 등)
- ❌ 애플리케이션 배포 (API 서버들)
- ❌ 애플리케이션 빌드/테스트

---

### 3. ArgoCD (Application Deployment GitOps)

**역할**: Kubernetes 애플리케이션 배포 및 동기화

**관리 대상**:
- ✅ Microservices API Deployments:
  - Auth API
  - Scan API
  - Chat API
  - Community API
  - User API
  - Reward API
- ✅ Database Deployments:
  - PostgreSQL
  - Redis
  - RabbitMQ
- ✅ Kubernetes 리소스:
  - Deployments
  - Services
  - ConfigMaps
  - Secrets
  - PersistentVolumeClaims

**워크플로우**:
```
1. Kubernetes Manifest 수정 (k8s/*.yaml)
   또는
   애플리케이션 이미지 업데이트
2. Git Push
3. ArgoCD가 변경 사항 자동 감지
4. ArgoCD가 클러스터에 자동 배포 (Auto-Sync)
```

**ArgoCD Hooks** (Phase 3):
```
PreSync Hook → Ansible 실행 → 클러스터 설정 변경
    ↓
ArgoCD Sync → 애플리케이션 배포
    ↓
PostSync Hook → Health Check, Smoke Test
```

**ArgoCD가 관리하지 않는 것**:
- ❌ AWS 인프라 (Atlantis 담당)
- ❌ Kubernetes 클러스터 초기화 (Ansible 담당)
- ❌ CI/CD 빌드/테스트 (GitHub Actions 담당)

---

### 4. GitHub Actions (CI/CD)

**역할**: 애플리케이션 빌드, 테스트, 이미지 생성

**관리 대상**:
- ✅ 코드 빌드
- ✅ 단위 테스트, 통합 테스트
- ✅ Docker 이미지 빌드
- ✅ Docker 이미지 푸시 (ECR, Docker Hub)
- ✅ 이미지 태그 업데이트 (k8s/*.yaml)

**워크플로우**:
```
1. 애플리케이션 코드 수정 (src/*)
2. Git Push
3. GitHub Actions 실행:
   - 테스트
   - Docker 이미지 빌드
   - 이미지 푸시
   - Manifest 파일의 이미지 태그 업데이트
4. ArgoCD가 감지하여 자동 배포
```

---

## 전체 워크플로우

### Phase 1: 인프라 생성 (Atlantis + Terraform)

```mermaid
graph LR
    A[terraform/*.tf 수정] --> B[Pull Request]
    B --> C[Atlantis: terraform plan]
    C --> D[PR 리뷰]
    D --> E[atlantis apply 코멘트]
    E --> F[AWS 인프라 생성]
    F --> G[EC2 Instances Running]
```

### Phase 2: 클러스터 설정 (Ansible)

```mermaid
graph LR
    A[ansible/playbooks/*.yml 수정] --> B[Git Push]
    B --> C[ArgoCD Hook 트리거]
    C --> D[Ansible Playbook 실행]
    D --> E[Kubernetes 클러스터 초기화]
    E --> F[인프라 컴포넌트 설치]
    F --> G[클러스터 Ready]
```

### Phase 3: 애플리케이션 배포 (ArgoCD + GitHub Actions)

```mermaid
graph LR
    A[src/* 코드 수정] --> B[Git Push]
    B --> C[GitHub Actions: Build & Test]
    C --> D[Docker Image Push]
    D --> E[k8s/*.yaml 이미지 태그 업데이트]
    E --> F[Git Push]
    F --> G[ArgoCD 감지]
    G --> H[자동 배포]
```

---

## 각 도구의 관리 범위

### Layer별 구분

```
┌─────────────────────────────────────────────────────────┐
│  Layer 4: Application Code (개발자)                      │
│  - 애플리케이션 소스 코드                                  │
│  - 단위 테스트                                            │
└─────────────────────────────────────────────────────────┘
                    ↓ GitHub Actions
┌─────────────────────────────────────────────────────────┐
│  Layer 3: Container Images (GitHub Actions)              │
│  - Docker 이미지 빌드                                      │
│  - 이미지 레지스트리 (ECR, Docker Hub)                      │
└─────────────────────────────────────────────────────────┘
                    ↓ Image Tag Update
┌─────────────────────────────────────────────────────────┐
│  Layer 2: Kubernetes Resources (ArgoCD)                  │
│  - Deployments, Services                                  │
│  - ConfigMaps, Secrets                                    │
│  - 애플리케이션 배포                                        │
└─────────────────────────────────────────────────────────┘
                    ↓ kubectl apply
┌─────────────────────────────────────────────────────────┐
│  Layer 1: Kubernetes Cluster (Ansible)                   │
│  - Kubeadm init/join                                      │
│  - CNI (Calico)                                           │
│  - 노드 레이블링                                           │
│  - 인프라 컴포넌트 (Cert-Manager, ALB Controller)          │
└─────────────────────────────────────────────────────────┘
                    ↓ SSH & kubectl
┌─────────────────────────────────────────────────────────┐
│  Layer 0: Infrastructure (Atlantis + Terraform)          │
│  - AWS EC2, VPC, Security Groups                         │
│  - IAM Roles                                              │
│  - Route53, CloudFront                                    │
└─────────────────────────────────────────────────────────┘
```

---

## Git 저장소 구조

```
SeSACTHON/backend/
│
├── terraform/                    # Atlantis가 관리
│   ├── main.tf
│   ├── variables.tf
│   ├── vpc.tf
│   ├── ec2.tf
│   ├── iam.tf
│   └── ...
│
├── ansible/                      # Ansible이 관리
│   ├── inventory/
│   │   └── hosts.ini
│   └── playbooks/
│       ├── site.yml
│       ├── 01-prerequisites.yml
│       ├── 02-init-master.yml
│       ├── 03-join-workers.yml
│       ├── 04-cni-install.yml
│       ├── 05-label-nodes.yml
│       ├── 06-infrastructure-components.yml
│       ├── 07-ingress-resources.yml
│       ├── 08-monitoring.yml
│       └── 09-atlantis.yml
│
├── k8s/                          # ArgoCD가 관리
│   ├── auth/
│   │   └── auth-deployment.yaml
│   ├── scan/
│   │   └── scan-deployment.yaml
│   ├── chat/
│   │   └── chat-deployment.yaml
│   ├── community/
│   │   └── community-deployment.yaml
│   ├── database/
│   │   ├── postgres-deployment.yaml
│   │   ├── redis-deployment.yaml
│   │   └── rabbitmq-deployment.yaml
│   ├── ingress/
│   │   └── 14-nodes-ingress.yaml
│   └── argocd/
│       └── applications/
│
├── src/                          # GitHub Actions가 빌드
│   ├── auth/
│   ├── scan/
│   ├── chat/
│   └── ...
│
└── .github/
    └── workflows/
        ├── build-auth.yml
        ├── build-scan.yml
        └── ...
```

---

## 변경 시나리오별 워크플로우

### 시나리오 1: EC2 인스턴스 타입 변경

**도구**: Atlantis (Terraform)

```bash
1. terraform/variables.tf 수정
   variable "master_instance_type" {
     default = "t3.large"  # t3.medium에서 변경
   }

2. Pull Request 생성

3. Atlantis가 자동으로 plan 실행
   PR에 변경 사항 코멘트

4. 리뷰 후 PR에 코멘트: "atlantis apply"

5. Atlantis가 terraform apply 실행
   → EC2 인스턴스 타입 변경
```

### 시나리오 2: Kubernetes CNI 업그레이드

**도구**: Ansible

```bash
1. ansible/playbooks/04-cni-install.yml 수정
   - name: "Calico 설치"
     shell: |
       kubectl apply -f https://docs.projectcalico.org/v3.28/manifests/calico.yaml
       # 버전 변경: v3.26 → v3.28

2. Git Push

3. ArgoCD PreSync Hook 트리거
   → Ansible Playbook 실행
   → CNI 업그레이드

4. 또는 수동 실행:
   ansible-playbook -i ansible/inventory/hosts.ini \
     ansible/playbooks/04-cni-install.yml
```

### 시나리오 3: Auth API 버전 업데이트

**도구**: GitHub Actions → ArgoCD

```bash
1. src/auth/*.ts 코드 수정

2. Git Push

3. GitHub Actions 실행:
   - 테스트
   - Docker 이미지 빌드 (태그: v1.2.3)
   - 이미지 푸시

4. GitHub Actions가 k8s/auth/auth-deployment.yaml 수정:
   image: your-registry/auth-api:v1.2.3

5. Git Push

6. ArgoCD가 변경 감지
   → 자동 배포
```

### 시나리오 4: PostgreSQL 리소스 증가

**도구**: ArgoCD

```bash
1. k8s/database/postgres-deployment.yaml 수정
   resources:
     requests:
       memory: "2Gi"   # 1Gi에서 변경
       cpu: "1"        # 500m에서 변경

2. Git Push

3. ArgoCD가 자동으로 감지하여 배포
   → PostgreSQL Pod 재시작 (새로운 리소스 할당)
```

### 시나리오 5: 새로운 Worker 노드 추가

**도구**: Atlantis → Ansible

```bash
# Phase 1: 인프라 생성 (Atlantis)
1. terraform/variables.tf 수정
   variable "scan_worker_count" {
     default = 3  # 2에서 변경
   }

2. Pull Request 생성

3. atlantis apply
   → EC2 인스턴스 생성

# Phase 2: 클러스터 조인 (Ansible)
4. Ansible inventory 자동 업데이트

5. ansible-playbook -i ansible/inventory/hosts.ini \
     ansible/playbooks/03-join-workers.yml
   → 새 Worker 노드가 클러스터에 조인

6. ansible-playbook -i ansible/inventory/hosts.ini \
     ansible/playbooks/05-label-nodes.yml
   → 노드 레이블링
```

---

## 각 도구의 장단점

### Atlantis (Terraform)

**장점**:
- ✅ PR 기반 리뷰 프로세스
- ✅ Plan 결과를 PR에 자동 코멘트
- ✅ 인프라 변경 이력이 Git에 기록
- ✅ 롤백이 용이 (Git revert)

**단점**:
- ❌ Kubernetes 리소스 관리 불가
- ❌ 애플리케이션 배포 불가

**사용 케이스**:
- AWS 리소스 생성/수정/삭제
- 인프라 변경 사항 리뷰

---

### Ansible

**장점**:
- ✅ SSH 기반으로 모든 노드 제어 가능
- ✅ 시스템 레벨 설정 관리
- ✅ 멱등성 (Idempotency)
- ✅ Playbook으로 복잡한 워크플로우 구현

**단점**:
- ❌ AWS 인프라 관리에는 적합하지 않음
- ❌ 애플리케이션 배포에는 ArgoCD가 더 적합

**사용 케이스**:
- Kubernetes 클러스터 초기화
- 시스템 패키지 설치
- 인프라 컴포넌트 배포

---

### ArgoCD

**장점**:
- ✅ Git을 Single Source of Truth로 사용
- ✅ 자동 동기화
- ✅ 실시간 상태 모니터링
- ✅ 롤백이 매우 쉬움
- ✅ UI/CLI로 쉬운 관리

**단점**:
- ❌ Kubernetes 외부 리소스 관리 불가
- ❌ 클러스터 초기화 불가

**사용 케이스**:
- Kubernetes 애플리케이션 배포
- 애플리케이션 상태 모니터링
- GitOps 워크플로우

---

### GitHub Actions

**장점**:
- ✅ GitHub와 완벽한 통합
- ✅ 병렬 실행
- ✅ 다양한 Action 마켓플레이스
- ✅ Secret 관리

**단점**:
- ❌ 인프라 관리 불가
- ❌ 배포 상태 추적 어려움

**사용 케이스**:
- 애플리케이션 빌드
- 테스트 실행
- Docker 이미지 생성

---

## GitOps 흐름도 (전체)

```
┌──────────────────────────────────────────────────────────────────────┐
│                        Developer Workflow                              │
└──────────────────────────────────────────────────────────────────────┘
    │
    ├── 인프라 변경? ─────────────────────────────────────────────────┐
    │                                                                   │
    │   terraform/*.tf 수정                                             │
    │        ↓                                                          │
    │   Pull Request                                                    │
    │        ↓                                                          │
    │   Atlantis: terraform plan                                        │
    │        ↓                                                          │
    │   리뷰 & 승인                                                     │
    │        ↓                                                          │
    │   atlantis apply 코멘트                                           │
    │        ↓                                                          │
    │   AWS 인프라 변경                                                 │
    │        ↓                                                          │
    └────────┼───────────────────────────────────────────────────────┘
             │
    ├── 클러스터 설정 변경? ───────────────────────────────────────────┐
    │                                                                   │
    │   ansible/playbooks/*.yml 수정                                    │
    │        ↓                                                          │
    │   Git Push                                                        │
    │        ↓                                                          │
    │   ArgoCD PreSync Hook                                             │
    │        ↓                                                          │
    │   Ansible Playbook 실행                                           │
    │        ↓                                                          │
    │   Kubernetes 클러스터 설정 변경                                   │
    │        ↓                                                          │
    └────────┼───────────────────────────────────────────────────────┘
             │
    └── 애플리케이션 배포? ───────────────────────────────────────────┐
                                                                       │
        src/* 코드 수정                                                │
             ↓                                                         │
        Git Push                                                       │
             ↓                                                         │
        GitHub Actions: Build & Test                                   │
             ↓                                                         │
        Docker Image Push                                              │
             ↓                                                         │
        k8s/*.yaml 이미지 태그 업데이트                                │
             ↓                                                         │
        Git Push                                                       │
             ↓                                                         │
        ArgoCD 감지                                                    │
             ↓                                                         │
        자동 배포                                                      │
             ↓                                                         │
        ────────┼───────────────────────────────────────────────────┘
```

---

## 결론

### Atlantis vs Ansible vs ArgoCD

| 구분 | Atlantis | Ansible | ArgoCD |
|------|----------|---------|--------|
| **목적** | AWS 인프라 관리 | 클러스터 설정 | 애플리케이션 배포 |
| **관리 대상** | EC2, VPC, IAM 등 | Kubeadm, CNI, 노드 설정 | Deployment, Service 등 |
| **실행 방식** | PR 코멘트 | SSH | Git Sync |
| **실행 주기** | 수동 (PR) | 수동/Hook | 자동 (3분마다) |
| **롤백** | Git revert → apply | Playbook 재실행 | Git revert → Auto-sync |

### 각 도구는 서로를 대체하지 않습니다!

- **Atlantis**: Infrastructure Layer (AWS)
- **Ansible**: Configuration Layer (Kubernetes Cluster)
- **ArgoCD**: Application Layer (Kubernetes Apps)

**모두 필요하며, 각자의 역할이 명확합니다.**

---

## 참고 문서

- [Atlantis 공식 문서](https://www.runatlantis.io/docs/)
- [Ansible 공식 문서](https://docs.ansible.com/)
- [ArgoCD 공식 문서](https://argo-cd.readthedocs.io/)
- [GitOps 원칙](https://www.gitops.tech/)

---

**작성일**: 2025-11-11  
**버전**: v1.0.0  
**아키텍처**: 14-Node Microservices with Full GitOps

