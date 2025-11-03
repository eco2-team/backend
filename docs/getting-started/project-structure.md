# 📁 프로젝트 구조

> **4-Tier Kubernetes 클러스터 구조**  
> **업데이트**: 2025-10-31

## 📂 전체 구조

```
SeSACTHON/backend/
├── README.md                          # 프로젝트 소개
├── DEPLOYMENT_GUIDE.md                # 배포 가이드 ⭐
│
├── 📁 terraform/ (Infrastructure as Code)
│   ├── main.tf                        # 메인 설정 (4-Tier)
│   ├── variables.tf                   # 변수 정의
│   ├── outputs.tf                     # Output 값
│   ├── backend.tf                     # S3 Backend
│   ├── terraform.tfvars               # 변수 값
│   │
│   ├── iam.tf                         # IAM (SSM)
│   ├── alb-controller-iam.tf          # ALB Controller IAM
│   ├── route53.tf                     # DNS (growbin.app)
│   ├── acm.tf                         # SSL Certificate
│   ├── s3.tf                          # S3 이미지 버킷 ⭐
│   │
│   ├── modules/
│   │   ├── vpc/                       # VPC (10.0.0.0/16)
│   │   ├── security-groups/           # Master SG, Worker SG
│   │   └── ec2/                       # EC2 인스턴스
│   │
│   ├── templates/
│   │   └── hosts.tpl                  # Ansible Inventory
│   │
│   └── user-data/
│       └── common.sh                  # EC2 초기화 스크립트
│
├── 📁 ansible/ (Configuration Management)
│   ├── ansible.cfg                    # Ansible 설정
│   ├── site.yml                       # 마스터 Playbook ⭐
│   │
│   ├── inventory/
│   │   └── group_vars/
│   │       └── all.yml                # 공통 변수
│   │
│   ├── roles/
│   │   ├── common/                    # OS 설정
│   │   ├── docker/                    # containerd
│   │   ├── kubernetes/                # kubeadm, kubelet
│   │   ├── argocd/                    # ArgoCD
│   │   └── rabbitmq/                  # RabbitMQ HA
│   │
│   └── playbooks/
│       ├── 02-master-init.yml         # Master 초기화
│       ├── 03-worker-join.yml         # Worker join
│       ├── 04-cni-install.yml         # Calico VXLAN
│       ├── 05-addons.yml              # Cert-manager
│       ├── 06-cert-manager-issuer.yml # ClusterIssuer
│       ├── 07-alb-controller.yml      # ALB Controller ⭐
│       ├── 07-ingress-resources.yml   # Ingress (Path) ⭐
│       ├── 08-monitoring.yml          # Prometheus
│       └── 09-etcd-backup.yml         # etcd 백업
│
├── 📁 scripts/ (자동화 스크립트)
│   ├── auto-rebuild.sh                # 완전 자동 재구축 ⭐
│   ├── rebuild-cluster.sh             # 대화형 재구축
│   ├── quick-rebuild.sh               # 빠른 재구축
│   ├── get-instances.sh               # 인스턴스 정보
│   ├── connect-ssh.sh                 # SSH 접속
│   ├── reset-node.sh                  # 노드 초기화
│   ├── reset-cluster.sh               # 클러스터 초기화
│   ├── remote-health-check.sh         # 원격 헬스체크
│   └── check-cluster-health.sh        # 클러스터 진단
│
├── 📁 docs/ (문서)
│   ├── README.md                      # 문서 메인 ⭐
│   │
│   ├── architecture/                  # 아키텍처 설계
│   │   ├── deployment-architecture-4node.md  # 최종 배포 아키텍처 ⭐
│   │   ├── final-k8s-architecture.md
│   │   ├── task-queue-design.md
│   │   ├── istio-service-mesh.md
│   │   └── decisions/                # 의사결정 과정
│   │
│   ├── infrastructure/                # 인프라 설계
│   │   ├── vpc-network-design.md      # VPC 네트워크 ⭐
│   │   ├── cni-comparison.md          # CNI 비교
│   │   └── k8s-cluster-setup.md
│   │
│   ├── guides/                        # 실용 가이드
│   │   ├── SETUP_CHECKLIST.md         # 구축 체크리스트 ⭐
│   │   ├── IaC_QUICK_START.md
│   │   ├── session-manager-guide.md
│   │   └── DEPLOYMENT_SETUP.md
│   │
│   ├── getting-started/               # 시작 가이드
│   │   ├── installation.md
│   │   ├── quickstart.md
│   │   └── project-structure.md (이 파일)
│   │
│   ├── development/                   # 개발 가이드
│   │   ├── conventions.md
│   │   └── pep8-guide.md
│   │
│   ├── deployment/                    # 배포 가이드
│   │   └── gitops-argocd-helm.md
│   │
│   └── contributing/
│       └── how-to-contribute.md
│
├── 📁 app/ (애플리케이션 - 미래)
│   ├── main.py
│   ├── core/
│   ├── domains/
│   │   ├── auth/
│   │   ├── users/
│   │   ├── waste/
│   │   ├── recycling/
│   │   └── locations/
│   └── external/
│
└── 📁 gitops/ (ArgoCD 설정 - 미래)
    └── applications/
```

---

## 🏗️ Infrastructure (Terraform)

### 핵심 리소스

```
VPC:
- CIDR: 10.0.0.0/16
- Subnets: 3개 (Public)
- Internet Gateway
- Route Table

EC2 (4-Tier):
- Master: t3.large (8GB)
- Worker-1: t3.medium (4GB) - Application
- Worker-2: t3.medium (4GB) - Celery
- Storage: t3.large (8GB) - RabbitMQ, DB ⭐

Security Groups:
- Master SG (K8s API, Control Plane 포트)
- Worker SG (Pod 통신, VXLAN)

AWS Services:
- S3 (이미지 버킷) ⭐
- ACM (SSL Certificate)
- Route53 (DNS)
- IAM (SSM, ALB, S3)
```

---

## 🤖 Configuration (Ansible)

### Playbook 흐름

```
1. Prerequisites (OS 설정)
   - Swap 비활성화
   - Kernel 모듈
   - sysctl 네트워크

2. Docker/containerd
   - containerd 설치
   - pause:3.9 설정
   - CRI 소켓

3. Kubernetes 패키지
   - kubeadm, kubelet, kubectl
   - 버전 고정

4. Master 초기화
   - kubeadm init
   - control-plane-endpoint
   - kube-proxy (phase addon)

5. Workers 조인
   - kubeadm join (4개 노드)
   - Pre-flight 체크

6. Calico VXLAN ⭐
   - BGP 완전 비활성화
   - VXLAN Always
   - Probe 수정 (BIRD 제거)

7. ALB Controller ⭐
   - Helm 설치
   - IAM 연동

8. Ingress (Path-based) ⭐
   - 단일 도메인
   - 경로 라우팅

9. RabbitMQ ⭐
   - HA 3-node
   - Storage 노드 배치

10. Monitoring
    - Prometheus + Grafana
    - Master 노드 배치
```

---

## 📊 노드별 배치

```
Master (Control + Monitoring):
/var/lib/
├── etcd/                    # etcd 데이터
├── kubelet/                 # Kubelet 설정
└── prometheus/              # Prometheus TSDB

Worker-1 (Application):
/var/lib/
├── kubelet/
└── containerd/
    └── auth-pods/           # FastAPI Pods
        users-pods/
        locations-pods/

Worker-2 (Async):
/var/lib/
├── kubelet/
└── containerd/
    └── celery-workers/      # Celery Worker Pods

Storage (Stateful):
/var/lib/
├── kubelet/
└── containerd/
    ├── rabbitmq/            # RabbitMQ PVC
    ├── postgresql/          # PostgreSQL PVC
    └── redis/               # Redis 데이터
```

---

## 🌐 네트워킹

```
VPC CIDR: 10.0.0.0/16
Pod CIDR: 192.168.0.0/16 (Calico)
Service CIDR: 10.96.0.0/12

노드 IP:
- Master: 10.0.1.235
- Storage: 10.0.1.x
- Worker-1: 10.0.2.x
- Worker-2: 10.0.3.x

Pod IP:
- Master Pods: 192.168.0.0/24
- Storage Pods: 192.168.1.0/24
- Worker-1 Pods: 192.168.2.0/24
- Worker-2 Pods: 192.168.x.0/24

통신:
- VXLAN (UDP 4789)
- kube-proxy (iptables DNAT)
- Calico overlay
```

---

## 📚 관련 문서

- [VPC 네트워크 설계](../infrastructure/vpc-network-design.md)
- [배포 아키텍처](../architecture/deployment-architecture-4node.md)
- [구축 체크리스트](../guides/SETUP_CHECKLIST.md)

---

**작성일**: 2025-10-31  
**버전**: 2.0  
**구조**: 4-Tier Cluster

