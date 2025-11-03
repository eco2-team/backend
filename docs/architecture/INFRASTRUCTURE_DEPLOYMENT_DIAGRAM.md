# 인프라 배포 프로세스 다이어그램

> **Terraform + Ansible 기반 자동 배포 프로세스**  
> **전체 구축 시간: 40-50분**

## 현재 배포 프로세스 흐름

### 전체 배포 플로우

```mermaid
sequenceDiagram
    participant User
    participant AutoRebuild as auto-rebuild.sh
    participant Cleanup as cleanup.sh
    participant K8s as Kubernetes API
    participant AWS as AWS API
    participant Build as build-cluster.sh
    participant TF as Terraform
    participant Ansible as Ansible
    
    Note over User,Ansible: Phase 1: 인프라 및 구성요소 삭제
    User->>AutoRebuild: 실행
    AutoRebuild->>Cleanup: 호출
    Cleanup->>K8s: Ingress 삭제
    Cleanup->>K8s: PVC 삭제
    Cleanup->>K8s: RabbitMQ CR 삭제
    Cleanup->>K8s: Helm Release 삭제
    Cleanup->>AWS: EBS 볼륨 삭제
    Cleanup->>AWS: 보안 그룹 삭제
    Cleanup->>AWS: Load Balancer 삭제
    Cleanup->>TF: terraform destroy
    
    Note over User,Ansible: Phase 2: 인프라 구축 (Terraform)
    AutoRebuild->>Build: 호출
    Build->>TF: terraform init
    Build->>TF: terraform apply
    TF->>AWS: EC2 인스턴스 생성<br/>(Master, Workers, Storage)
    TF->>AWS: VPC/서브넷 생성
    TF->>AWS: S3 버킷 생성
    TF->>AWS: IAM 역할 생성
    TF->>AWS: ACM 인증서
    TF->>AWS: Elastic IP 할당
    TF->>Build: Inventory 생성 (hosts.tpl)
    
    Note over User,Ansible: Phase 3: Kubernetes 클러스터 구축 (Ansible)
    Build->>Ansible: ansible-playbook site.yml
    Ansible->>AWS: OS 설정 (Swap, 커널)
    Ansible->>AWS: Container Runtime 설치
    Ansible->>AWS: Kubernetes 패키지 설치
    Ansible->>AWS: Master 초기화 (kubeadm init)
    Ansible->>AWS: Worker 조인 (kubeadm join)
    Ansible->>K8s: CNI 설치 (Calico)
    Ansible->>K8s: 노드 레이블 지정
    
    Note over User,Ansible: Phase 4: Add-ons 설치
    Ansible->>K8s: Cert-manager 설치 (kubectl apply)
    Ansible->>K8s: EBS CSI Driver 설치
    Ansible->>K8s: ALB Controller 설치 (Helm)
    
    Note over User,Ansible: Phase 5: 애플리케이션 Stack
    Ansible->>K8s: ArgoCD 설치 (kubectl apply)
    Ansible->>K8s: Prometheus 설치 (Helm)
    Ansible->>K8s: RabbitMQ Operator 설치
    Ansible->>K8s: RabbitmqCluster CR 생성
    K8s->>AWS: RabbitMQ Pod 생성 (Operator)
    Ansible->>K8s: Redis 설치 (kubectl apply)
    Ansible->>K8s: Ingress 리소스 생성
    Ansible->>AWS: etcd 백업 설정
    
    Note over User,Ansible: ✅ 배포 완료
```

## 상세 배포 단계

### Phase 1: 인프라 및 구성요소 삭제 (cleanup.sh)

```mermaid
sequenceDiagram
    participant User
    participant Cleanup as cleanup.sh
    participant K8s as Kubernetes API
    participant AWS as AWS API
    participant TF as Terraform
    
    User->>Cleanup: 실행
    Cleanup->>K8s: kubectl delete ingress --all
    Cleanup->>K8s: kubectl delete pvc --all
    Cleanup->>K8s: kubectl delete rabbitmqcluster
    Cleanup->>K8s: helm uninstall (Prometheus, ArgoCD)
    Cleanup->>AWS: EBS 볼륨 삭제
    Cleanup->>AWS: 보안 그룹 삭제
    Cleanup->>AWS: Load Balancer 삭제
    Cleanup->>TF: terraform destroy
```

### Phase 2: 인프라 구축 (build-cluster.sh - Terraform)

```mermaid
graph LR
    A[Terraform Init] --> B[Terraform Apply<br/>인프라 생성]
    B --> C[EC2 인스턴스<br/>Master, Workers, Storage]
    B --> D[VPC/Subnet/IGW]
    B --> E[S3 버킷]
    B --> F[IAM 역할]
    B --> G[ACM 인증서]
    B --> H[Elastic IP]
    
    C --> I[Ansible Inventory 생성<br/>hosts.tpl 템플릿]
    D --> I
    E --> I
    F --> I
    G --> I
    H --> I
    
    I --> J[Ansible Playbook 실행]
    J --> K[Kubernetes 클러스터 구축]
```

**Terraform 모듈 구조**:
```
terraform/
├── modules/
│   ├── vpc/          # VPC, 3개 Public Subnets, IGW
│   ├── ec2/          # EC2 인스턴스 (Master, Worker-1, Worker-2, Storage)
│   └── security-groups/ # 보안 그룹 (Master, Worker, ALB)
├── main.tf           # 모듈 호출
├── outputs.tf       # Inventory 자동 생성 (hosts.tpl)
└── templates/
    └── hosts.tpl     # Ansible Inventory 템플릿
```

### Phase 3: Kubernetes 클러스터 구축 (Ansible - site.yml)

```mermaid
sequenceDiagram
    participant Ansible
    participant Master as Master Node
    participant Workers as Worker Nodes
    participant K8s as Kubernetes API
    participant Helm as Helm
    participant Operator as RabbitMQ Operator
    participant AWS as AWS API
    
    Note over Ansible,AWS: 1. 기반 설정 (Roles)
    Ansible->>Master: OS 설정 (Role: common)
    Ansible->>Workers: OS 설정 (Role: common)
    Ansible->>Master: Docker 설치 (Role: docker)
    Ansible->>Workers: Docker 설치 (Role: docker)
    Ansible->>Master: Kubernetes 패키지 (Role: kubernetes)
    Ansible->>Workers: Kubernetes 패키지 (Role: kubernetes)
    
    Note over Ansible,AWS: 2. 클러스터 구성 (Playbooks)
    Ansible->>Master: kubeadm init (02-master-init.yml)
    Master->>K8s: API Server 시작
    Ansible->>Workers: kubeadm join (03-worker-join.yml)
    Workers->>K8s: 노드 등록
    Ansible->>K8s: CNI 설치 (04-cni-install.yml)
    K8s->>Master: Calico Pod 배포
    K8s->>Workers: Calico Pod 배포
    Ansible->>K8s: 노드 레이블 지정 (workload=storage 등)
    
    Note over Ansible,AWS: 3. 인프라 Add-ons (Playbooks)
    Ansible->>K8s: Cert-manager 설치 (05-addons.yml)
    Ansible->>K8s: EBS CSI Driver (05-1-ebs-csi-driver.yml)
    Ansible->>AWS: StorageClass 생성 (gp3)
    Ansible->>K8s: Cert-manager Issuer (06-cert-manager-issuer.yml)
    Ansible->>Helm: ALB Controller 설치 (07-alb-controller.yml)
    Helm->>K8s: ALB Controller 배포
    
    Note over Ansible,AWS: 4. 애플리케이션 Stack (Roles + Playbooks)
    Ansible->>K8s: ArgoCD 설치 (Role: argocd, kubectl apply)
    K8s->>K8s: ArgoCD Pod 배포
    Ansible->>Helm: Prometheus 설치 (08-monitoring.yml)
    Helm->>K8s: Prometheus Stack 배포
    Ansible->>K8s: RabbitMQ Operator 설치 (Role: rabbitmq)
    K8s->>Operator: Operator Pod 실행
    Ansible->>K8s: RabbitmqCluster CR 생성
    Operator->>K8s: StatefulSet/Service 생성
    K8s->>AWS: RabbitMQ Pod 생성 (EBS 볼륨 연결)
    Ansible->>K8s: Redis 설치 (Role: redis, kubectl apply)
    K8s->>Workers: Redis Pod 배포
    Ansible->>K8s: Ingress 리소스 생성 (07-ingress-resources.yml)
    K8s->>AWS: ALB 자동 생성
    Ansible->>Master: etcd 백업 설정 (09-etcd-backup.yml)
```

**Ansible 구조**:
```
ansible/
├── site.yml              # 메인 플레이북 (17단계)
├── playbooks/            # 단계별 플레이북
│   ├── 02-master-init.yml
│   ├── 03-worker-join.yml
│   ├── 04-cni-install.yml
│   ├── 05-addons.yml
│   ├── 05-1-ebs-csi-driver.yml
│   ├── 06-cert-manager-issuer.yml
│   ├── 07-alb-controller.yml
│   ├── 07-ingress-resources.yml
│   ├── 08-monitoring.yml
│   └── 09-etcd-backup.yml
└── roles/                # 재사용 가능한 역할
    ├── common/           # OS 설정
    ├── docker/           # Docker 설치
    ├── kubernetes/       # Kubernetes 패키지
    ├── argocd/           # ArgoCD 설치
    ├── rabbitmq/         # RabbitMQ Operator
    └── redis/            # Redis 설치
```

## RabbitMQ 배포 상세 (순수 Operator 방식)

```mermaid
sequenceDiagram
    participant Ansible
    participant K8s as Kubernetes API
    participant Operator as RabbitMQ Operator
    participant Pod as RabbitMQ Pod
    
    Ansible->>K8s: kubectl apply (Operator YAML)
    Note over K8s: CRD 자동 생성<br/>rabbitmqclusters.rabbitmq.com
    
    K8s->>Operator: Operator Deployment 생성
    Operator->>Operator: Operator Pod 실행
    
    Ansible->>K8s: kubectl apply (RabbitmqCluster CR)
    Note over K8s: Operator가 감지
    
    Operator->>K8s: StatefulSet 생성
    Operator->>K8s: Service 생성
    Operator->>K8s: ConfigMap 생성
    Operator->>K8s: Secret 참조
    
    K8s->>Pod: Pod 생성 및 스케줄링 (Storage Node)
    Pod->>Pod: RabbitMQ 서버 시작
    Pod->>Operator: 상태 업데이트
    Operator->>K8s: RabbitmqCluster.status 업데이트
    
    Note over Ansible,Pod: Day-2 운영 (확장, 업그레이드 등)은<br/>Operator가 자동 관리
```

## 인프라 구성 요소

### Terraform 관리 리소스

```mermaid
graph TB
    A[Terraform] --> B[Compute]
    A --> C[Network]
    A --> D[Storage]
    A --> E[Security]
    A --> F[DNS]
    
    B --> B1[EC2: Master t3.large]
    B --> B2[EC2: Worker-1 t3.medium]
    B --> B3[EC2: Worker-2 t3.medium]
    B --> B4[EC2: Storage t3.large]
    
    C --> C1[VPC 10.0.0.0/16]
    C --> C2[Public Subnets 3개]
    C --> C3[Internet Gateway]
    C --> C4[Route Tables]
    
    D --> D1[S3 Bucket]
    
    E --> E1[Security Groups]
    E --> E2[IAM Roles]
    E --> E3[IAM Policies]
    
    F --> F1[Route53]
    F --> F2[ACM Certificate]
```

### Kubernetes 관리 리소스 (Ansible)

```mermaid
graph TB
    A[Kubernetes Cluster] --> B[Control Plane]
    A --> C[Data Plane]
    A --> D[Storage]
    A --> E[Add-ons]
    
    B --> B1[Master Node<br/>kube-apiserver, etcd]
    
    C --> C1[Worker-1<br/>FastAPI Pods]
    C --> C2[Worker-2<br/>Celery Workers]
    C --> C3[Storage Node<br/>RabbitMQ, Redis, PostgreSQL]
    
    D --> D1[EBS CSI Driver]
    D --> D2[StorageClass: gp3]
    D --> D3[PVCs]
    
    E --> E1[ArgoCD<br/>kubectl apply]
    E --> E2[Prometheus Stack<br/>Helm]
    E --> E3[RabbitMQ Operator<br/>kubectl apply]
    E --> E4[Cert-manager<br/>kubectl apply]
    E --> E5[ALB Controller<br/>Helm]
```

## 배포 스크립트 계층 구조

```mermaid
graph TD
    A[auto-rebuild.sh<br/>최상위 자동화] --> B[cleanup.sh<br/>인프라 및 구성요소 삭제]
    A --> C[build-cluster.sh<br/>인프라 구축]
    
    B --> B1[kubectl 명령어들]
    B --> B2[helm uninstall]
    B --> B3[aws cli]
    B --> B4[terraform destroy]
    
    C --> C1[terraform init/apply]
    C --> C2[ansible inventory 생성]
    C --> C3[ansible-playbook site.yml]
    
    C3 --> D[Ansible Playbooks]
    D --> D1[OS 설정 (Role: common)]
    D --> D2[Kubernetes 설치 (Role: kubernetes)]
    D --> D3[CNI 설치 (04-cni-install.yml)]
    D --> D4[Add-ons 설치 (05-addons.yml)]
    D --> D5[RabbitMQ Role<br/>Operator 방식]
    D --> D6[Redis Role<br/>kubectl apply]
```

## 배포 시간 분석

```
전체 배포 시간: 40-50분

Phase 1: cleanup.sh
├─ Kubernetes 리소스 삭제: 2-3분
├─ AWS 리소스 삭제: 3-5분
└─ terraform destroy: 5-8분
─────────────────────
총: 10-16분

Phase 2: Terraform Apply
├─ terraform init: 1-2분
├─ EC2 인스턴스 생성: 3-5분
├─ VPC/네트워크 구성: 2-3분
└─ 기타 리소스 (IAM, S3, ACM): 2-3분
─────────────────────
총: 8-13분

Phase 3: Ansible site.yml
├─ OS 설정: 2-3분
├─ Docker 설치: 3-5분
├─ Kubernetes 설치: 2-3분
├─ Master 초기화: 3-5분
├─ Worker 조인: 2-3분
├─ CNI 설치: 2-3분
├─ Add-ons 설치: 5-8분
├─ 애플리케이션 Stack: 5-8분
└─ Ingress 생성: 2-3분
─────────────────────
총: 25-37분
```

## CI/CD 로드맵

### 현재 상태
- ✅ 인프라 자동화 (Terraform + Ansible)
- ✅ 스크립트 기반 배포 (auto-rebuild.sh)
- ✅ GitOps 준비 (ArgoCD 설치됨)
- ⚠️ CI/CD 파이프라인 미구현

### Phase 1: 기본 CI/CD 설정 (우선순위: 높음)

#### 1.1 GitHub Actions 워크플로우
```yaml
# 필요 작업:
- [ ] .github/workflows/infrastructure.yml
  - Terraform Plan/Apply 자동화
  - Ansible 실행 자동화
  - 환경별 분리 (dev/staging/prod)
  
- [ ] .github/workflows/validate.yml
  - Terraform validate
  - Ansible syntax check
  - YAML linting
```

#### 1.2 Secret 관리
```yaml
# GitHub Secrets 필요:
- [ ] AWS_ACCESS_KEY_ID
- [ ] AWS_SECRET_ACCESS_KEY
- [ ] SSH_PRIVATE_KEY (또는 AWS Systems Manager)
- [ ] RABBITMQ_PASSWORD
- [ ] GRAFANA_PASSWORD
```

### Phase 2: 애플리케이션 CI/CD (우선순위: 중간)

#### 2.1 애플리케이션 빌드 파이프라인
```yaml
# 필요 작업:
- [ ] .github/workflows/application-build.yml
  - Docker 이미지 빌드
  - 이미지 스캔 (보안)
  - GHCR 푸시
  
- [ ] .github/workflows/application-deploy.yml
  - ArgoCD Application 업데이트
  - 또는 kubectl 직접 배포
```

#### 2.2 GitOps 구성
```yaml
# 필요 작업:
- [ ] ArgoCD Application 정의
  - Application YAML 생성
  - Kustomize 또는 Helm Chart 준비
  
- [ ] Git 저장소 구조
  - apps/ 디렉토리
  - envs/ 디렉토리 (dev/staging/prod)
```

### Phase 3: 고급 CI/CD 기능 (우선순위: 낮음)

#### 3.1 자동 테스트
```yaml
# 필요 작업:
- [ ] 통합 테스트
  - 클러스터 헬스 체크
  - RabbitMQ 연결 테스트
  - API 엔드포인트 테스트
  
- [ ] E2E 테스트
  - 전체 워크플로우 테스트
```

#### 3.2 롤백 자동화
```yaml
# 필요 작업:
- [ ] 자동 롤백 스크립트
- [ ] 헬스 체크 기반 롤백
- [ ] 이전 버전 자동 복구
```

#### 3.3 모니터링 통합
```yaml
# 필요 작업:
- [ ] 배포 알림 (Slack/Discord)
- [ ] 메트릭 수집 (Prometheus)
- [ ] 로그 집계 (ELK/Fluentd)
```

### Phase 4: 멀티 환경 관리 (우선순위: 낮음)

#### 4.1 환경 분리
```yaml
# 필요 작업:
- [ ] 환경별 Terraform Workspace
- [ ] 환경별 Ansible Inventory
- [ ] 환경별 Kubernetes Namespace
```

#### 4.2 Blue-Green 배포
```yaml
# 필요 작업:
- [ ] ArgoCD Rollout 설정
- [ ] 트래픽 분할 구성
```

## 구현 우선순위 요약

### 즉시 구현 (1-2주)
1. ✅ GitHub Actions 기본 워크플로우
2. ✅ Secret 관리 설정
3. ✅ Terraform/Ansible 자동화

### 단기 구현 (1개월)
1. ✅ 애플리케이션 빌드 파이프라인
2. ✅ ArgoCD GitOps 구성
3. ✅ 기본 테스트 자동화

### 중기 구현 (2-3개월)
1. ⚠️ 고급 테스트 (통합/E2E)
2. ⚠️ 자동 롤백
3. ⚠️ 모니터링 통합

### 장기 구현 (3개월+)
1. ⚠️ 멀티 환경 관리
2. ⚠️ Blue-Green 배포
3. ⚠️ 카나리 배포

## 참고 파일

### 스크립트
- `scripts/auto-rebuild.sh` - 최상위 자동화 스크립트 (cleanup.sh → build-cluster.sh)
- `scripts/cleanup.sh` - 인프라 및 구성요소 삭제 (K8s → AWS → Terraform)
- `scripts/build-cluster.sh` - 인프라 구축 (Terraform apply → Ansible)

### Ansible
- `ansible/site.yml` - Ansible 메인 플레이북 (17단계)
- `ansible/roles/rabbitmq/tasks/main.yml` - RabbitMQ Operator 배포
- `ansible/roles/redis/tasks/main.yml` - Redis 배포

### Terraform
- `terraform/main.tf` - Terraform 메인 설정 (모듈 호출)
- `terraform/outputs.tf` - Ansible Inventory 자동 생성
- `terraform/modules/` - 재사용 가능한 모듈 (VPC, EC2, Security Groups)

---

**작성일**: 2025-11-03  
**기준**: Terraform + Ansible 기반 구조  
**배포 시간**: 40-50분
