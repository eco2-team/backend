# 프로젝트 구조

> **Terraform + Ansible 기반 Kubernetes 클러스터 자동화 프로젝트**

## 📂 전체 디렉토리 구조

```
SeSACTHON/backend/
│
├── terraform/                    # Infrastructure as Code (IaC)
│   ├── main.tf                   # 메인 설정 (모듈 호출)
│   ├── variables.tf               # 입력 변수
│   ├── outputs.tf                # 출력 값 (Ansible Inventory 자동 생성)
│   ├── backend.tf                # Terraform State 백엔드 (S3)
│   ├── acm.tf                    # ACM 인증서
│   ├── route53.tf                # Route53 DNS
│   ├── s3.tf                     # S3 버킷 (Terraform State, 이미지 저장)
│   ├── iam.tf                    # IAM 역할 및 정책
│   ├── alb-controller-iam.tf     # ALB Controller IAM
│   ├── terraform.tfvars          # 변수 값 설정
│   ├── modules/                  # 재사용 가능한 모듈
│   │   ├── vpc/                  # VPC 모듈
│   │   │   ├── main.tf           # VPC, Subnets, IGW, Route Tables
│   │   │   ├── variables.tf
│   │   │   └── outputs.tf
│   │   ├── ec2/                  # EC2 모듈
│   │   │   ├── main.tf           # Master, Workers, Storage 인스턴스
│   │   │   ├── variables.tf
│   │   │   └── outputs.tf
│   │   └── security-groups/       # 보안 그룹 모듈
│   │       ├── main.tf           # Master, Worker, ALB 보안 그룹
│   │       ├── variables.tf
│   │       └── outputs.tf
│   ├── templates/                # 템플릿 파일
│   │   └── hosts.tpl             # Ansible Inventory 템플릿
│   └── user-data/                # EC2 User Data
│       └── common.sh             # 공통 초기화 스크립트
│
├── ansible/                      # Configuration Management
│   ├── site.yml                  # 메인 플레이북 (17단계)
│   ├── ansible.cfg               # Ansible 설정
│   ├── inventory/                # 인벤토리 (Terraform에서 자동 생성)
│   │   └── group_vars/
│   │       └── all.yml           # 공통 변수 (K8s 버전, 도메인 등)
│   ├── playbooks/                # 단계별 플레이북
│   │   ├── 02-master-init.yml   # Master 초기화 (kubeadm init)
│   │   ├── 03-worker-join.yml   # Worker 조인 (kubeadm join)
│   │   ├── 04-cni-install.yml   # Calico CNI 설치
│   │   ├── 05-addons.yml        # Cert-manager, Metrics Server
│   │   ├── 05-1-ebs-csi-driver.yml # EBS CSI Driver
│   │   ├── 06-cert-manager-issuer.yml # Let's Encrypt Issuer
│   │   ├── 07-alb-controller.yml # AWS ALB Controller (Helm)
│   │   ├── 07-ingress-resources.yml # Ingress 리소스 (Path-based)
│   │   ├── 08-monitoring.yml    # Prometheus Stack (Helm)
│   │   └── 09-etcd-backup.yml   # etcd 백업 설정
│   └── roles/                    # 재사용 가능한 역할
│       ├── common/               # OS 설정 (Swap, 커널)
│       │   └── tasks/
│       │       └── main.yml
│       ├── docker/               # Docker 설치
│       │   └── tasks/
│       │       └── main.yml
│       ├── kubernetes/           # Kubernetes 패키지 설치
│       │   └── tasks/
│       │       └── main.yml
│       ├── argocd/               # ArgoCD 설치 (kubectl apply)
│       │   └── tasks/
│       │       └── main.yml
│       ├── rabbitmq/             # RabbitMQ Operator 설치
│       │   └── tasks/
│       │       └── main.yml
│       └── redis/                # Redis 설치 (kubectl apply)
│           └── tasks/
│               └── main.yml
│
├── scripts/                      # 자동화 스크립트
│   ├── auto-rebuild.sh          # 전체 자동화 (cleanup → build)
│   ├── cleanup.sh               # 리소스 삭제 (K8s → AWS → Terraform)
│   ├── build-cluster.sh         # 클러스터 구축 (Terraform → Ansible)
│   ├── check-cluster-health.sh  # 클러스터 상태 점검
│   ├── check-etcd-health.sh    # etcd 상태 확인
│   ├── check-monitoring-status.sh # 모니터링 상태 확인
│   ├── verify-cluster-status.sh # 상세 검증
│   ├── connect-ssh.sh          # SSH 접속 (Session Manager)
│   ├── get-instances.sh        # 인스턴스 정보 조회
│   └── ... (기타 유틸리티)
│
└── docs/                        # 문서
    ├── README.md                # 문서 메인 페이지
    ├── architecture/            # 아키텍처 설계
    │   ├── final-k8s-architecture.md # 최종 K8s 아키텍처
    │   ├── SERVICE_ARCHITECTURE.md # 서비스 아키텍처 (terraform/ansible 기반)
    │   ├── INFRASTRUCTURE_DEPLOYMENT_DIAGRAM.md # 배포 다이어그램
    │   └── task-queue-design.md # Task Queue 설계
    ├── infrastructure/          # 인프라 가이드
    │   ├── vpc-network-design.md
    │   ├── k8s-cluster-setup.md
    │   └── iac-terraform-ansible.md
    ├── guides/                  # 실용 가이드
    │   ├── SETUP_CHECKLIST.md
    │   ├── DEPLOYMENT_METHODS.md
    │   └── ...
    └── troubleshooting/         # 문제 해결
        └── TROUBLESHOOTING.md
```

---

## 🔧 Terraform 구조

### 모듈 기반 설계

```
terraform/
├── main.tf              # 모듈 호출 및 리소스 정의
│   ├── module.vpc
│   ├── module.ec2 (Master, Workers, Storage)
│   └── module.security-groups
│
├── modules/
│   ├── vpc/             # 네트워크 인프라
│   │   └── VPC, 3개 Public Subnets, IGW, Route Tables
│   │
│   ├── ec2/             # 컴퓨팅 인프라
│   │   ├── Master (t3.large)
│   │   ├── Worker-1 (t3.medium) - workload=application
│   │   ├── Worker-2 (t3.medium) - workload=async-workers
│   │   └── Storage (t3.large) - workload=storage
│   │
│   └── security-groups/ # 보안 그룹
│       ├── Master SG (6443, 2379, 10250, 10259, 10257)
│       ├── Worker SG (10250, 30000-32767)
│       └── ALB SG (80, 443)
│
└── outputs.tf           # Ansible Inventory 자동 생성
    └── ansible_inventory (hosts.tpl 기반)
```

### Terraform 출력

```hcl
output "ansible_inventory" {
  description = "Ansible inventory"
  value = templatefile("${path.module}/templates/hosts.tpl", {
    master_ip = aws_instance.master.private_ip
    worker1_ip = aws_instance.worker1.private_ip
    worker2_ip = aws_instance.worker2.private_ip
    storage_ip = aws_instance.storage.private_ip
    # ...
  })
}
```

---

## 🎭 Ansible 구조

### Playbook 실행 순서 (site.yml)

```yaml
1. Prerequisites - OS 설정
   Role: common
   
2. Docker 설치
   Role: docker
   
3. Kubernetes 패키지 설치
   Role: kubernetes
   
4. Master 초기화
   Playbook: 02-master-init.yml
   ├─ kubeadm init
   ├─ kubeconfig 설정
   └─ Join 토큰 생성
   
5. Workers 조인
   Playbook: 03-worker-join.yml
   ├─ Worker-1 조인
   ├─ Worker-2 조인
   └─ Storage 조인
   
6. CNI 플러그인 설치
   Playbook: 04-cni-install.yml
   └─ Calico VXLAN
   
7. 노드 레이블 지정
   ├─ worker-1: workload=application
   ├─ worker-2: workload=async-workers
   └─ storage: workload=storage
   
8. Add-ons 설치
   Playbook: 05-addons.yml
   ├─ Cert-manager
   └─ Metrics Server
   
9. EBS CSI Driver
   Playbook: 05-1-ebs-csi-driver.yml
   └─ StorageClass (gp3)
   
10. Cert-manager Issuer
    Playbook: 06-cert-manager-issuer.yml
    └─ Let's Encrypt ClusterIssuer
    
11. ALB Controller
    Playbook: 07-alb-controller.yml
    └─ Helm 설치
    
12. ArgoCD 설치
    Role: argocd
    └─ kubectl apply
    
13. Monitoring 설치
    Playbook: 08-monitoring.yml
    └─ Prometheus Stack (Helm)
    
14. RabbitMQ 설치
    Role: rabbitmq
    ├─ Operator 설치
    └─ RabbitmqCluster CR 생성
    
15. Redis 설치
    Role: redis
    └─ kubectl apply
    
16. Ingress 리소스 생성
    Playbook: 07-ingress-resources.yml
    └─ Path-based Routing
    
17. etcd 백업 설정
    Playbook: 09-etcd-backup.yml
```

### Role 구조

```
ansible/roles/
├── common/              # OS 레벨 설정
│   └── tasks/main.yml
│       ├─ Swap 비활성화
│       ├─ 커널 파라미터
│       └─ 호스트네임 설정
│
├── docker/              # Container Runtime
│   └── tasks/main.yml
│       └─ Docker 설치 및 설정
│
├── kubernetes/          # Kubernetes 패키지
│   └── tasks/main.yml
│       ├─ kubeadm 설치
│       ├─ kubelet 설치
│       └─ kubectl 설치
│
├── argocd/              # GitOps CD
│   └── tasks/main.yml
│       └─ kubectl apply (공식 매니페스트)
│
├── rabbitmq/            # Message Queue
│   └── tasks/main.yml
│       ├─ Operator 설치
│       └─ RabbitmqCluster CR 생성
│
└── redis/               # Cache & Result Backend
    └── tasks/main.yml
        └─ kubectl apply (Deployment + Service)
```

---

## 🚀 스크립트 구조

### 자동화 스크립트

```
scripts/
├── auto-rebuild.sh      # 전체 자동화
│   ├── cleanup.sh 호출
│   └── build-cluster.sh 호출
│
├── cleanup.sh          # 리소스 삭제
│   ├── K8s 리소스 삭제 (Ingress, PVC, CR, Helm Release)
│   ├── AWS 리소스 삭제 (EBS, Security Groups, ALB)
│   └── terraform destroy
│
├── build-cluster.sh    # 클러스터 구축
│   ├── terraform init
│   ├── terraform apply
│   ├── Inventory 생성
│   └── ansible-playbook site.yml
│
└── check-*.sh          # 상태 확인
    ├── check-cluster-health.sh
    ├── check-etcd-health.sh
    └── check-monitoring-status.sh
```

---

## 📊 배포 흐름

### 전체 프로세스

```
1. Terraform (AWS 인프라)
   └─> EC2, VPC, IAM, ACM, Route53, S3

2. Ansible (Kubernetes 클러스터)
   └─> OS 설정 → Docker → Kubernetes → 클러스터 초기화

3. Ansible (Add-ons)
   └─> Cert-manager, EBS CSI, ALB Controller

4. Ansible (애플리케이션 인프라)
   └─> ArgoCD, Prometheus, RabbitMQ, Redis

5. 향후: GitOps (애플리케이션 서비스)
   └─> GitHub Actions → GHCR → ArgoCD → Kubernetes
```

---

## 🎯 핵심 파일

### 설정 파일

- `terraform/terraform.tfvars` - Terraform 변수 값
- `terraform/variables.tf` - Terraform 변수 정의
- `ansible/inventory/group_vars/all.yml` - Ansible 변수
- `ansible/ansible.cfg` - Ansible 설정

### 메인 실행 파일

- `scripts/auto-rebuild.sh` - 전체 자동화 진입점
- `terraform/main.tf` - Terraform 진입점
- `ansible/site.yml` - Ansible 진입점

---

**작성일**: 2025-11-03  
**기준**: Terraform + Ansible 기반 구조
