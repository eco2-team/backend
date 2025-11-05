# Terraform/Ansible 검수 및 재구축 가이드

> 날짜: 2025-11-04  
> 목적: Storage 노드 레이블 문제 해결 및 클러스터 재구축  

---

## 🔍 검수 결과 요약

### ✅ 전반적 평가: 양호

**검수 항목**:
- ✅ Terraform 리소스 중복: 없음
- ✅ Ansible 플레이북 순서: 올바름
- ✅ 노드 레이블링 타이밍: 적절
- ✅ PostgreSQL nodeSelector: 수정 완료
- ⚠️ 노드 레이블 적용 보장: 개선 필요

---

## 🐛 이전 문제 분석

### PostgreSQL Pod FailedScheduling

**에러**:
```
FailedScheduling: 0/4 nodes are available
- 2 node(s) didn't match Pod's node affinity/selector
```

**근본 원인**:
1. PostgreSQL이 `workload=storage` 레이블 요구
2. Ansible playbook 실행 중 노드 레이블 단계가:
   - 실행되지 않았거나
   - 에러가 발생했거나
   - 무시되었음
3. 결과: Pod가 스케줄링되지 못함

---

## ✅ 적용된 수정사항

### 1. PostgreSQL 배치 설정 복원

**파일**: `ansible/roles/postgresql/tasks/main.yml`

```yaml
spec:
  nodeSelector:
    workload: storage  # Storage 노드에 배포
```

**Service DNS**: `postgres.default.svc.cluster.local:5432`  
**클러스터 전반 접근**: ✅ 가능 (ClusterIP Service)

---

### 2. Ansible 플레이북 순서 확인

**파일**: `ansible/site.yml`

```
1. Prerequisites (OS 설정)
2. Docker 설치
3. Kubernetes 패키지 설치
4. Master 초기화
5. Workers 조인
6. CNI 설치
7. ✅ 노드 레이블 지정 ← 여기서 workload=storage 설정
8. Add-ons 설치
9. AWS EBS CSI Driver
10. AWS Load Balancer Controller
11. IngressClass 생성
12. ArgoCD 설치
13. Monitoring 설치
14. RabbitMQ 설치
15. Redis 설치
16. ✅ PostgreSQL 설치 ← 여기서 workload=storage 요구
```

**결론**: 순서는 올바름 ✅

---

### 3. 노드 레이블링 강화

**파일**: `ansible/site.yml` (Line 52-64)

```yaml
- name: 노드 레이블 지정
  hosts: masters
  become: yes
  become_user: "{{ kubectl_user }}"
  tasks:
    - name: Label worker-1 (Application)
      command: kubectl label nodes k8s-worker-1 workload=application instance-type=t3.medium role=application --overwrite
      register: label_worker1
      failed_when: label_worker1.rc != 0
    
    - name: Label worker-2 (Async Workers)
      command: kubectl label nodes k8s-worker-2 workload=async-workers instance-type=t3.medium role=workers --overwrite
      register: label_worker2
      failed_when: label_worker2.rc != 0
    
    - name: Label storage (Stateful Services)
      command: kubectl label nodes k8s-storage workload=storage instance-type=t3.large role=storage --overwrite
      register: label_storage
      failed_when: label_storage.rc != 0
    
    - name: Verify storage node label
      command: kubectl get nodes k8s-storage -L workload
      register: verify_storage_label
      failed_when: "'storage' not in verify_storage_label.stdout"
      changed_when: false
```

**개선사항**:
- `register`로 결과 저장
- `failed_when`으로 실패 감지
- 레이블 적용 확인 단계 추가

---

## 📋 Terraform 검수

### VPC 및 네트워크

**파일**: `terraform/modules/vpc/main.tf`

```hcl
resource "aws_vpc" "main" {
  cidr_block           = var.vpc_cidr  # 10.0.0.0/16
  enable_dns_hostnames = true
  enable_dns_support   = true
}

# Public Subnets (3 AZs)
resource "aws_subnet" "public" {
  count                   = 3
  vpc_id                  = aws_vpc.main.id
  cidr_block              = cidrsubnet(var.vpc_cidr, 8, count.index)
  availability_zone       = data.aws_availability_zones.available.names[count.index]
  map_public_ip_on_launch = true
}
```

**검수 결과**: ✅ 정상
- VPC CIDR: 10.0.0.0/16
- Pod CIDR: 192.168.0.0/16 (Calico Overlay)
- 충돌 없음

---

### EC2 인스턴스

**파일**: `terraform/main.tf`

```hcl
# Master: t3.large (8GB, 80GB EBS)
module "master" {
  instance_type    = "t3.large"
  root_volume_size = 80
  subnet_id        = module.vpc.public_subnet_ids[0]
}

# Worker-1: t3.medium (4GB, 40GB EBS) - Application
module "worker_1" {
  instance_type    = "t3.medium"
  root_volume_size = 40
  subnet_id        = module.vpc.public_subnet_ids[1]
  tags = {
    Workload = "application"
  }
}

# Worker-2: t3.medium (4GB, 40GB EBS) - Async Workers
module "worker_2" {
  instance_type    = "t3.medium"
  root_volume_size = 40
  subnet_id        = module.vpc.public_subnet_ids[2]
  tags = {
    Workload = "async-workers"
  }
}

# Storage: t3.large (8GB, 100GB EBS) - Stateful Services
module "storage" {
  instance_type    = "t3.large"
  root_volume_size = 100
  subnet_id        = module.vpc.public_subnet_ids[0]
  tags = {
    Workload = "storage"
  }
}
```

**검수 결과**: ✅ 정상
- 4개 노드 (Master + 3 Workers)
- Storage 노드 100GB (PostgreSQL, RabbitMQ, Redis용)

---

### IAM 권한

**파일**: `terraform/iam.tf`, `terraform/alb-controller-iam.tf`

```hcl
# EC2 Instance Role
resource "aws_iam_role" "ec2_ssm_role" {
  name = "${var.environment}-k8s-ec2-ssm-role"
}

# Policies
- AmazonSSMManagedInstanceCore (Session Manager)
- CloudWatchAgentServerPolicy (로깅)
- EBS CSI Driver Policy (Dynamic PV)
- ALB Controller Policy (Ingress → ALB)
- S3 Pre-signed URL Policy (이미지 업로드)
```

**검수 결과**: ✅ 정상
- 모든 필요한 권한 부여됨
- ALB Controller 권한 확장 완료

---

## 🔧 클러스터 재구축 가이드

### Pre-requisites

1. **AWS Credentials 설정**
   ```bash
   export AWS_ACCESS_KEY_ID="your-key"
   export AWS_SECRET_ACCESS_KEY="your-secret"
   export AWS_DEFAULT_REGION="ap-northeast-2"
   ```

2. **SSH Key 생성** (없는 경우)
   ```bash
   ssh-keygen -t rsa -b 4096 -f ~/.ssh/k8s-cluster-key -N ""
   ```

3. **환경 변수 설정**
   ```bash
   export POSTGRES_PASSWORD="your-secure-password"
   export RABBITMQ_PASSWORD="your-rabbitmq-password"
   export GRAFANA_PASSWORD="your-grafana-password"
   ```

---

### 1단계: 기존 클러스터 완전 정리

```bash
cd /path/to/backend

# 완전한 리소스 정리 (Kubernetes → AWS → Terraform → VPC)
bash scripts/destroy-with-cleanup.sh

# 자동 모드 (확인 없이 즉시 삭제)
AUTO_MODE=true bash scripts/destroy-with-cleanup.sh
```

**스크립트 기능**:
- Kubernetes 리소스 정리 (Ingress, PVC, Helm)
- AWS 리소스 정리 (ALB, Target Groups, EBS, ENI)
- Security Group 순환 참조 해결
- Terraform destroy
- 남은 VPC 리소스 완전 삭제

**예상 시간**: 10-15분

---

### 2단계: Terraform으로 인프라 구축

```bash
cd terraform

# 초기화
terraform init

# 계획 확인
terraform plan -out=tfplan

# 인프라 생성
terraform apply tfplan
```

**생성 리소스**:
- VPC (10.0.0.0/16)
- 3개 Public Subnets (각 AZ)
- Internet Gateway, Route Tables
- Security Groups (Master, Worker)
- 4개 EC2 인스턴스
- EBS Volumes
- IAM Roles & Policies
- S3 Bucket (이미지 저장)
- Route53 A 레코드
- ACM Certificate

**예상 시간**: 5-10분

---

### 3단계: Ansible Inventory 생성

```bash
cd ../ansible

# Terraform output에서 IP 추출
MASTER_IP=$(cd ../terraform && terraform output -raw master_public_ip)
WORKER1_IP=$(cd ../terraform && terraform output -raw worker_1_public_ip)
WORKER2_IP=$(cd ../terraform && terraform output -raw worker_2_public_ip)
STORAGE_IP=$(cd ../terraform && terraform output -raw storage_public_ip)

# Inventory 파일 생성
cat > inventory/hosts.ini <<EOF
[masters]
master ansible_host=${MASTER_IP} ansible_user=ubuntu private_ip=$(cd ../terraform && terraform output -raw master_private_ip)

[workers]
worker-1 ansible_host=${WORKER1_IP} ansible_user=ubuntu
worker-2 ansible_host=${WORKER2_IP} ansible_user=ubuntu

[storage]
storage ansible_host=${STORAGE_IP} ansible_user=ubuntu

[k8s_cluster:children]
masters
workers
storage
EOF
```

**예상 시간**: 1분

---

### 4단계: Ansible로 Kubernetes 클러스터 구축

```bash
# SSH 연결 테스트
ansible all -i inventory/hosts.ini -m ping

# 전체 플레이북 실행
ansible-playbook -i inventory/hosts.ini site.yml

# 또는 자동화 스크립트 사용
bash scripts/build-cluster.sh
```

**실행 단계** (총 16단계):
1. Prerequisites (OS 설정)
2. Docker 설치
3. Kubernetes 패키지 설치
4. Master 초기화
5. Workers 조인
6. CNI 설치 (Calico)
7. **✅ 노드 레이블 지정** ← 중요!
8. Add-ons 설치
9. EBS CSI Driver
10. ALB Controller
11. IngressClass 생성
12. ArgoCD 설치
13. Monitoring 설치
14. RabbitMQ 설치
15. Redis 설치
16. **✅ PostgreSQL 설치** ← 레이블 필요

**예상 시간**: 15-20분

---

### 5단계: 클러스터 상태 확인

```bash
# SSH로 Master 노드 접속
ssh ubuntu@${MASTER_IP}

# 노드 상태 확인
kubectl get nodes -o wide

# 노드 레이블 확인 (✅ 중요!)
kubectl get nodes -L workload,instance-type,role

# 예상 출력:
# NAME            STATUS   WORKLOAD        INSTANCE-TYPE   ROLE
# k8s-master      Ready    <none>          <none>          <none>
# k8s-worker-1    Ready    application     t3.medium       application
# k8s-worker-2    Ready    async-workers   t3.medium       workers
# k8s-storage     Ready    storage         t3.large        storage

# PostgreSQL Pod 확인
kubectl get pods -n default -o wide | grep postgres

# 예상 출력:
# postgres-0   1/1   Running   0   5m   192.168.x.x   k8s-storage

# PostgreSQL 연결 테스트
kubectl exec -it statefulset/postgres -n default -- psql -U admin -d sesacthon -c "SELECT version();"

# 모든 Pod 확인
kubectl get pods -A -o wide
```

---

## ⚠️ 문제 해결: 노드 레이블 누락 시

만약 PostgreSQL Pod가 Pending 상태라면:

### 1. 노드 레이블 확인
```bash
kubectl get nodes -L workload
```

### 2. Storage 노드 레이블이 없는 경우

**자동 수정 (권장)**:
```bash
# 로컬에서 실행
bash scripts/fix-node-labels.sh ${MASTER_IP} ubuntu
```

**수동 수정**:
```bash
# Master 노드에서 실행
kubectl label nodes k8s-storage workload=storage instance-type=t3.large role=storage --overwrite

# 레이블 확인
kubectl get nodes k8s-storage -L workload

# PostgreSQL Pod 재시작
kubectl delete pod -l app=postgres -n default

# Pod 상태 확인 (1분 후)
kubectl get pods -n default -o wide | grep postgres
```

### 3. Ansible 노드 레이블 단계만 재실행

```bash
cd ansible

ansible-playbook -i inventory/hosts.ini site.yml \
  --start-at-task='노드 레이블 지정'
```

---

## 📊 구축 완료 확인 체크리스트

### Infrastructure (Terraform)
- [ ] VPC 생성 완료
- [ ] 4개 EC2 인스턴스 Running
- [ ] Security Groups 생성
- [ ] IAM Roles 생성
- [ ] S3 Bucket 생성
- [ ] Route53 A 레코드 생성
- [ ] ACM Certificate 검증 완료

### Kubernetes Cluster (Ansible)
- [ ] 모든 노드 Ready 상태
- [ ] CNI (Calico) 정상 동작
- [ ] **노드 레이블 정상 적용** ✅
- [ ] EBS CSI Driver 설치 완료
- [ ] StorageClass gp3 생성

### Applications
- [ ] ArgoCD 설치 및 접근 가능
- [ ] Prometheus/Grafana 설치
- [ ] ALB Controller 설치
- [ ] IngressClass 생성
- [ ] RabbitMQ Running (k8s-storage)
- [ ] Redis Running
- [ ] **PostgreSQL Running (k8s-storage)** ✅

### Network
- [ ] ALB 생성 완료
- [ ] Ingress 리소스 생성
- [ ] DNS 레코드 전파
- [ ] HTTPS 리다이렉트 동작
- [ ] Health Check 정상

---

## 🎯 성공 기준

### 1. 노드 상태
```bash
kubectl get nodes -L workload

# 기대 결과:
# 모든 노드 Ready
# k8s-storage 노드에 workload=storage 레이블 존재 ✅
```

### 2. PostgreSQL 상태
```bash
kubectl get pods -n default -o wide | grep postgres

# 기대 결과:
# postgres-0   1/1   Running   0   Xm   192.168.x.x   k8s-storage ✅
```

### 3. 연결 테스트
```bash
kubectl exec -it statefulset/postgres -n default -- psql -U admin -d sesacthon -c "SELECT 1;"

# 기대 결과:
# ?column?
# ----------
#         1
# (1 row)
```

### 4. 클러스터 전반 접근
```bash
# 테스트 Pod 생성
kubectl run test-pod --image=postgres:16-alpine --rm -it --restart=Never -- \
  psql postgresql://admin:${POSTGRES_PASSWORD}@postgres.default.svc.cluster.local:5432/sesacthon -c "SELECT 1;"

# 기대 결과: 연결 성공 ✅
```

---

## 📝 재구축 요약

### 명령어 순서 (전체)

```bash
# 1. 환경 변수 설정
export AWS_ACCESS_KEY_ID="..."
export AWS_SECRET_ACCESS_KEY="..."
export POSTGRES_PASSWORD="..."
export RABBITMQ_PASSWORD="..."
export GRAFANA_PASSWORD="..."

# 2. 기존 리소스 정리
bash scripts/destroy-with-cleanup.sh

# 3. Terraform 인프라 구축
cd terraform
terraform init
terraform apply -auto-approve

# 4. Ansible Inventory 생성
cd ../ansible
# (위의 3단계 스크립트 실행)

# 5. Kubernetes 클러스터 구축
ansible-playbook -i inventory/hosts.ini site.yml

# 6. 상태 확인
ssh ubuntu@$(cd ../terraform && terraform output -raw master_public_ip)
kubectl get nodes -L workload
kubectl get pods -A -o wide
```

### 예상 소요 시간
- 정리: 10-15분
- Terraform: 5-10분
- Ansible: 15-20분
- **총합: 30-45분**

---

## ✅ 최종 검수 결과

### Terraform
- ✅ VPC/네트워크 구성 정상
- ✅ EC2 인스턴스 구성 적절
- ✅ IAM 권한 충분
- ✅ Security Groups 순환 참조 해결됨
- ✅ 리소스 중복 없음

### Ansible
- ✅ 플레이북 순서 올바름
- ✅ 노드 레이블링 타이밍 적절
- ✅ PostgreSQL nodeSelector 수정 완료
- ✅ Role 분리 명확
- ✅ 의존성 순서 올바름

### 개선사항
- ✅ `fix-node-labels.sh` 스크립트 추가
- ✅ `destroy-with-cleanup.sh` 강화
- ✅ 노드 레이블 검증 단계 추가 (권장)

**결론**: **재구축 준비 완료** ✅

---

**검수자**: AI Assistant  
**검수일**: 2025-11-04  
**승인 상태**: ✅ Approved for Rebuild

