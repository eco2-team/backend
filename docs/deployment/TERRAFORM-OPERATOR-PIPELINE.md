# Terraform + Operator 기반 구축 파이프라인

## 🎯 목표

**Ansible 의존성 완전 제거**하고 **Terraform + User-Data + Operator + ArgoCD**로 완전 자동화된 클러스터 구축

---

## 📊 아키텍처 비교

### Before (Ansible 기반)
```
Terraform (Infrastructure)
    ↓
Ansible (클러스터 구축 + 설정)
    ├── OS 설정
    ├── Docker/K8s 설치
    ├── Master init / Worker join
    ├── Provider ID 설정
    ├── Labels/Taints 설정
    ├── CNI 설치
    ├── Add-ons 설치
    ├── ArgoCD 설치
    └── Apps 배포
```

### After (Terraform + Operator 기반)
```
Terraform Apply
    ├── EC2 user-data
    │   ├── OS 설정 ✅
    │   ├── Docker/K8s 설치 ✅
    │   ├── Master init (+ ArgoCD 설치) ✅
    │   └── Worker join (SSM Token) ✅
    │
    ├── SSM Parameters (Join Token 저장) ✅
    │
    └── null_resource (kubectl apply)
        ├── Node Lifecycle Operator CRD
        ├── Node Lifecycle Operator Deployment
        └── NodeConfig CR
            ↓
        [Operator 자동 실행]
            ├── Provider ID 설정 ✅
            ├── Labels 동기화 (EC2 Tags) ✅
            └── Taints 적용 ✅
            ↓
        [ArgoCD App of Apps]
            ├── Wave -1: Foundations (CRDs, Namespaces)
            ├── Wave 0: Infrastructure (CNI, Metrics, CSI, ALB)
            ├── Wave 1: Platform (Cert-Manager, Secrets)
            ├── Wave 2: Monitoring (Prometheus, Grafana)
            ├── Wave 3: Data Operators
            ├── Wave 4: Data Clusters (PostgreSQL, Redis, RabbitMQ)
            ├── Wave 5: GitOps Tools (Atlantis)
            └── Wave 10: Applications (API Services)
```

---

## 🔄 구축 절차 (완전 자동화)

### Phase 1: Terraform Apply (10-15분)

```bash
cd terraform
terraform apply
```

**Terraform이 수행하는 작업**:

#### 1. 인프라 프로비저닝
- VPC, Subnets, Security Groups
- EC2 Instances (14개)
- IAM Roles/Policies
- SSM Parameters (placeholder)
- ACM Certificate
- Route53 Records

#### 2. Master Node User-Data (자동 실행)
```bash
# k8s-node-common.sh
- OS 설정 (swap off, kernel modules, sysctl)
- Docker & containerd 설치
- Kubernetes 패키지 설치 (kubelet, kubeadm, kubectl)

# master-bootstrap.sh
- kubeadm init
- CNI 설치 (Calico)
- ArgoCD 설치 (Helm)
- Join Token → SSM 저장
- API Endpoint → SSM 저장
- CA Cert Hash → SSM 저장
```

#### 3. Worker Nodes User-Data (자동 실행)
```bash
# k8s-node-common.sh
- OS 설정
- Docker & containerd 설치
- Kubernetes 패키지 설치

# worker-bootstrap.sh
- SSM에서 Join Token 조회 (재시도 로직)
- kubeadm join 실행
- Provider ID 초기 설정 (AWS 메타데이터)
```

#### 4. Operator 배포 (null_resource)
```hcl
# terraform/operator.tf
resource "null_resource" "deploy_operator" {
  depends_on = [module.master]
  
  provisioner "local-exec" {
    command = <<EOT
      # kubeconfig 다운로드
      scp -i ${var.private_key_path} ubuntu@${module.master.public_ip}:/home/ubuntu/.kube/config /tmp/kubeconfig
      export KUBECONFIG=/tmp/kubeconfig
      
      # Operator CRD 배포
      kubectl apply -f ${path.module}/../k8s/operators/node-lifecycle/crd.yaml
      
      # Operator Deployment 배포
      kubectl apply -f ${path.module}/../k8s/operators/node-lifecycle/deployment.yaml
      
      # NodeConfig CR 배포
      kubectl apply -f ${path.module}/../k8s/operators/node-lifecycle/nodeconfig.yaml
      
      # ArgoCD Root App 배포
      kubectl apply -f ${path.module}/../argocd/root-app.yaml
    EOT
  }
}
```

---

### Phase 2: Operator 자동 실행 (1-2분)

**Node Lifecycle Operator**가 모든 노드를 자동 설정:

```yaml
# k8s/operators/node-lifecycle/nodeconfig.yaml
apiVersion: lifecycle.sesacthon.io/v1alpha1
kind: NodeConfig
metadata:
  name: worker-nodes
  namespace: kube-system
spec:
  selector:
    matchLabels:
      node-role.kubernetes.io/worker: ""
  
  # Provider ID 자동 설정
  providerID:
    enabled: true
    source: aws
  
  # EC2 Tags → Node Labels 동기화
  labels:
    fromTags:
      - tagKey: Workload
        labelKey: workload
      - tagKey: Domain
        labelKey: domain
      - tagKey: Phase
        labelKey: phase
  
  # 조건부 Taints 적용
  taints:
    - key: workload
      value: database
      effect: NoSchedule
      condition:
        labelSelector:
          matchLabels:
            workload: database
    - key: workload
      value: message-queue
      effect: NoSchedule
      condition:
        labelSelector:
          matchLabels:
            workload: message-queue
```

**Operator 동작**:
1. 모든 Worker 노드 감지
2. 각 노드별로:
   - Provider ID 설정 (없으면)
   - EC2 Tags 조회
   - Node Labels 동기화
   - 조건에 맞으면 Taints 적용
3. Status 업데이트

---

### Phase 3: ArgoCD App of Apps (5-10분)

**ArgoCD Root App**이 Wave 순서대로 자동 배포:

```yaml
# argocd/root-app.yaml (이미 kubectl apply 됨)
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: root-app
  namespace: argocd
spec:
  source:
    repoURL: https://github.com/SeSACTHON/backend
    targetRevision: refactor/operator-ansible-minimal
    path: argocd/components
```

**배포 Wave**:
```
Wave -2: root-app (최우선)
    ↓
Wave -1: foundations
    - Prometheus Operator CRDs
    - Cert-Manager CRDs
    - Namespaces (auth, my, scan, character, location, info, chat, data, monitoring, atlantis)
    - NetworkPolicies
    ↓
Wave 0: infrastructure  
    - Metrics Server
    - EBS CSI Driver + StorageClass
    - AWS Load Balancer Controller
    - Calico (이미 Master user-data에서 설치됨)
    ↓
Wave 1: platform
    - Cert-Manager
    - External Secrets Operator
    - Sealed Secrets
    ↓
Wave 2: monitoring
    - Prometheus Operator
    - Prometheus
    - Grafana
    - ServiceMonitors
    ↓
Wave 3: data-operators
    - PostgreSQL Operator (CloudNativePG)
    - Redis Operator
    - RabbitMQ Cluster Operator
    ↓
Wave 4: data-clusters
    - PostgreSQL Cluster (7 domains)
    - Redis Cluster
    - RabbitMQ Cluster
    ↓
Wave 5: gitops-tools
    - Atlantis
    ↓
Wave 10: applications
    - API Services (ApplicationSet)
    - Worker Services (Celery, Flower)
```

---

## 📁 디렉토리 구조

```
backend/
├── terraform/
│   ├── main.tf                    # EC2, VPC, etc.
│   ├── ssm.tf                     # SSM Parameters
│   ├── iam.tf                     # IAM (SSM 권한 포함)
│   ├── operator.tf                # 🆕 Operator 배포 (null_resource)
│   └── user-data/
│       ├── k8s-node-common.sh     # OS + Docker + K8s
│       ├── master-bootstrap.sh    # Master init + ArgoCD
│       ├── worker-bootstrap.sh    # Worker join (SSM)
│       ├── master-combined.sh     # Master orchestrator
│       └── worker-combined.sh     # Worker orchestrator
│
├── k8s/
│   ├── operators/
│   │   └── node-lifecycle/        # 🆕 Operator manifests
│   │       ├── crd.yaml           # NodeConfig CRD
│   │       ├── deployment.yaml    # Operator Deployment
│   │       ├── rbac.yaml          # ClusterRole, ServiceAccount
│   │       └── nodeconfig.yaml    # NodeConfig CR (instance)
│   │
│   ├── infrastructure/            # Kustomize
│   │   ├── kustomization.yaml
│   │   ├── namespaces/
│   │   ├── networkpolicies/
│   │   └── monitoring/
│   │
│   ├── platform/                  # Cert-Manager, Secrets
│   ├── data-operators/            # DB Operators
│   ├── databases/                 # DB Instances
│   └── overlays/                  # Per-service configs
│
└── argocd/
    ├── root-app.yaml              # App of Apps 진입점
    └── components/                # Wave-based Apps
        ├── 00-foundations.yaml    # Wave -1
        ├── 10-infrastructure.yaml # Wave 0
        ├── 20-platform.yaml       # Wave 1
        ├── 30-monitoring.yaml     # Wave 2
        ├── 40-data-operators.yaml # Wave 3
        ├── 50-data-clusters.yaml  # Wave 4
        ├── 60-gitops-tools.yaml   # Wave 5
        └── 70-appset.yaml         # Wave 10
```

---

## 🚀 실행 방법

### 1. 사전 준비
```bash
# Terraform 변수 설정
cd terraform
cat > terraform.tfvars << EOF
environment = "dev"
aws_region = "ap-northeast-2"
vpc_cidr = "10.0.0.0/16"
public_key_path = "~/.ssh/sesacthon.pub"
private_key_path = "~/.ssh/sesacthon"
allowed_ssh_cidr = "0.0.0.0/0"  # 운영에서는 제한 필요
domain_name = ""  # 선택사항
EOF
```

### 2. 클러스터 구축 (완전 자동)
```bash
# Terraform Apply 한 번만 실행
terraform apply

# 예상 소요 시간:
# - Terraform: 10-15분
# - Master user-data: 5분
# - Worker user-data: 3분
# - Operator: 1-2분
# - ArgoCD Apps: 5-10분
# 총: 약 25-35분
```

### 3. 검증
```bash
# kubeconfig 다운로드
MASTER_IP=$(terraform output -raw master_public_ip)
scp -i ~/.ssh/sesacthon ubuntu@${MASTER_IP}:/home/ubuntu/.kube/config ~/.kube/config-sesacthon
export KUBECONFIG=~/.kube/config-sesacthon

# 노드 확인
kubectl get nodes -o wide

# 예상 결과:
# NAME               STATUS   ROLES           PROVIDER-ID                   LABELS
# k8s-master         Ready    control-plane   aws:///ap-northeast-2a/i-xxx   ...
# k8s-api-auth       Ready    <none>          aws:///ap-northeast-2a/i-xxx   workload=api-auth,domain=auth,phase=1
# k8s-api-my         Ready    <none>          aws:///ap-northeast-2b/i-xxx   workload=api-my,domain=my,phase=1
# ... (14 nodes total)

# Operator 확인
kubectl get pods -n kube-system | grep node-lifecycle

# NodeConfig 확인
kubectl get nodeconfig -n kube-system

# ArgoCD Apps 확인
kubectl get applications -n argocd

# 모든 Pod 확인
kubectl get pods -A
```

---

## ✅ Ansible 대비 장점

| 항목 | Ansible | Terraform + Operator |
|------|---------|----------------------|
| **구축 시간** | 40-50분 | 25-35분 |
| **수동 개입** | SSH 연결, inventory 관리 | 0 (완전 자동) |
| **실패 복구** | Playbook 재실행 | 자동 재시도 (Operator) |
| **Node 추가** | Ansible 재실행 | Terraform apply (자동 Join) |
| **설정 Drift** | 감지 불가 | Operator가 자동 복구 |
| **GitOps** | 부분 지원 | 완전 지원 (ArgoCD) |
| **유지보수** | Ansible 코드 관리 필요 | Operator + CRD로 선언적 |

---

## 🎯 다음 단계

### 즉시 필요한 작업:
1. ✅ Kustomize 중복 제거 (완료)
2. 🔄 Operator K8s 매니페스트 작성
   - `k8s/operators/node-lifecycle/crd.yaml`
   - `k8s/operators/node-lifecycle/deployment.yaml`
   - `k8s/operators/node-lifecycle/rbac.yaml`
   - `k8s/operators/node-lifecycle/nodeconfig.yaml`
3. 🔄 Terraform `operator.tf` 작성
   - null_resource로 Operator 배포
   - ArgoCD root-app 배포
4. 🔄 ArgoCD root-app targetRevision 업데이트
   - `develop` → `refactor/operator-ansible-minimal`

### 이후 작업:
5. Operator 구현 (Go + Kubebuilder)
6. Docker 이미지 빌드 & 푸시
7. 파이프라인 전체 테스트
8. 문서 업데이트

---

**문서 버전**: 1.0  
**최종 수정**: 2025-11-14  
**관련 문서**:
- [OPERATOR-DESIGN-SPEC.md](../architecture/OPERATOR-DESIGN-SPEC.md)
- [ANSIBLE-TASK-CLASSIFICATION.md](../architecture/ANSIBLE-TASK-CLASSIFICATION.md)

