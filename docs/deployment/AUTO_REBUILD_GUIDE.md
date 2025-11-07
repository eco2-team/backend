# 13-Node 클러스터 자동 재구축 가이드

## 📊 개요

`auto-rebuild.sh`는 13-Node Kubernetes 클러스터를 완전히 자동으로 재구축하고, v0.6.0 기능(모니터링 + WAL Workers)까지 배포하는 통합 스크립트입니다.

## 🎯 실행 순서

### 전체 프로세스 (자동)

1. **Terraform Destroy** - 기존 인프라 삭제
2. **Terraform Apply** - 13-Node 인프라 구축
3. **Ansible Playbook** - Kubernetes 설치
4. **Monitoring Stack** - Prometheus/Grafana 배포 (원격)
5. **Worker Images** - 이미지 빌드 & GHCR 푸시 (로컬)
6. **Worker Deployment** - WAL Workers 배포 (원격)

### 예상 소요 시간
- **전체**: 50-70분
  - Terraform destroy: 5-10분
  - Terraform apply: 10-15분
  - Ansible playbook: 15-20분
  - Monitoring 배포: 5분
  - Worker 빌드: 10분
  - Worker 배포: 5분

## 🚀 사용 방법

### 1. 사전 준비

```bash
# 필수 환경 변수 설정
export GITHUB_TOKEN=<your-github-token>
export GITHUB_USERNAME=<your-github-username>
export VERSION=v0.6.0  # 선택사항 (기본값: v0.6.0)

# AWS 자격증명 확인
aws sts get-caller-identity

# Terraform 변수 확인
cd terraform
cat terraform.tfvars
```

**필수 Terraform 변수**:
- `cluster_name`
- `environment`
- `domain_name`
- `key_name` (SSH 키)
- `aws_region`

### 2. 스크립트 실행

```bash
cd /Users/mango/workspace/SeSACTHON/backend
./scripts/cluster/auto-rebuild.sh
```

### 3. 실행 모드

**자동 모드** (기본):
- 모든 단계를 확인 없이 자동 실행
- 에러 발생 시에도 가능한 한 계속 진행
- `AUTO_MODE=true` 환경 변수 설정됨

**GitHub 인증 없이 실행**:
```bash
# Worker 빌드를 건너뛰고 실행
unset GITHUB_TOKEN
unset GITHUB_USERNAME
./scripts/cluster/auto-rebuild.sh
```

## 📦 배포되는 구성

### 13-Node 클러스터

| 노드 유형 | 개수 | 인스턴스 타입 | 역할 |
|----------|------|--------------|------|
| Master | 1 | t3a.large | Kubernetes Control Plane |
| API | 6 | t3a.medium | API Services (6개) |
| Worker | 2 | t3a.large | Celery Workers (2개) |
| Infrastructure | 4 | t3a.medium | RabbitMQ, PostgreSQL, Redis, Prometheus |

### 모니터링 스택

- **Prometheus**
  - ServiceMonitor (API 6개 + Worker 2개)
  - Alert Rules (20개)
  - 30일 메트릭 보관 (50GB PVC)

- **Grafana**
  - 13-Node 전용 대시보드 (12개 Panel)
  - 관리자 인증 (Secret)

- **Node Exporter**
  - DaemonSet (13개 노드 모니터링)

### Worker Services

- **Storage Worker**
  - S3 업로드 작업
  - Local SQLite WAL
  - PostgreSQL 비동기 동기화
  - 10GB PVC

- **AI Worker**
  - AI 추론 작업 (준비)
  - Local SQLite WAL
  - 10GB PVC

## 🔍 단계별 상세

### Step 1: Terraform Destroy

```bash
# 기존 리소스 확인
terraform state list

# 자동 삭제
terraform destroy -auto-approve

# 대기 시간: 30초 (AWS 리소스 완전 삭제)
```

**처리 방식**:
- 실패해도 계속 진행
- 리소스 개수 확인
- 상태 출력

### Step 2: Terraform Apply (13-Node)

```bash
# 13-Node 인프라 구축
terraform apply -auto-approve

# 생성되는 리소스:
# - 13 EC2 Instances
# - VPC, Subnets, Security Groups
# - S3 Bucket (images)
# - CloudFront Distribution
# - Route53 Records
# - ACM Certificates

# 대기 시간: 90초 (SSM Agent 등록)
```

### Step 3: Ansible Playbook

```bash
# Inventory 자동 생성
terraform output -raw ansible_inventory > ansible/inventory/hosts.ini

# Kubernetes 설치 (13 nodes)
ansible-playbook -i inventory/hosts.ini site.yml \
    -e "vpc_id=$VPC_ID" \
    -e "acm_certificate_arn=$ACM_ARN"

# 설치되는 컴포넌트:
# - Docker
# - Kubernetes (kubeadm)
# - Calico CNI
# - AWS EBS CSI Driver
# - AWS ALB Ingress Controller
# - Cert-Manager

# 대기 시간: 60초 (클러스터 초기화)
```

### Step 4: Monitoring Stack 배포 (원격)

```bash
# Master 노드로 파일 복사
scp -r k8s/monitoring ubuntu@$MASTER_IP:~/
scp scripts/deploy-monitoring.sh ubuntu@$MASTER_IP:~/

# 원격 실행 (SSH)
ssh ubuntu@$MASTER_IP
  kubectl apply -f ~/monitoring/node-exporter.yaml
  kubectl create configmap prometheus-rules --from-file=...
  kubectl apply -f ~/monitoring/prometheus-deployment.yaml
  kubectl create configmap grafana-dashboards --from-file=...
  kubectl apply -f ~/monitoring/grafana-deployment.yaml
```

### Step 5: Worker 이미지 빌드 (로컬)

```bash
# GHCR 로그인
echo $GITHUB_TOKEN | docker login ghcr.io -u $GITHUB_USERNAME --password-stdin

# 이미지 빌드 및 푸시
export VERSION=v0.6.0
./scripts/build-workers.sh

# 빌드되는 이미지:
# - ghcr.io/$GITHUB_USERNAME/ecoeco-storage-worker:v0.6.0
# - ghcr.io/$GITHUB_USERNAME/ecoeco-ai-worker:v0.6.0
```

**건너뛰는 경우**:
- `GITHUB_TOKEN` 또는 `GITHUB_USERNAME`이 없으면 자동으로 건너뜀
- 수동으로 나중에 실행 가능

### Step 6: Worker 배포 (원격)

```bash
# Master 노드로 파일 복사
scp -r k8s/workers ubuntu@$MASTER_IP:~/

# 원격 실행 (SSH)
ssh ubuntu@$MASTER_IP
  kubectl apply -f ~/workers/worker-wal-deployments.yaml
  kubectl get pods -l component=worker
  kubectl get pvc -l component=wal
```

## 📊 배포 확인

### 클러스터 접속

```bash
# Master 노드 접속
ssh ubuntu@$(cd terraform && terraform output -raw master_public_ip)

# 노드 확인 (13개)
kubectl get nodes -o wide

# Pod 확인
kubectl get pods -A
```

### 모니터링 확인

```bash
# Prometheus 접속
kubectl port-forward svc/prometheus 9090:9090
# http://localhost:9090

# Grafana 접속
kubectl port-forward svc/grafana 3000:3000
# http://localhost:3000

# Grafana 비밀번호 확인
kubectl get secret grafana-admin -o jsonpath='{.data.password}' | base64 -d
```

### Worker 확인

```bash
# Worker Pod 상태
kubectl get pods -l component=worker

# WAL PVC 확인
kubectl get pvc -l component=wal

# Worker 로그
kubectl logs -l app.kubernetes.io/name=storage-worker --tail=100
kubectl logs -l app.kubernetes.io/name=ai-worker --tail=100
```

## 🐛 트러블슈팅

### 1. Terraform Destroy 실패

**증상**: VPC 삭제 시 장시간 대기

**원인**: ENI, Security Group 등이 남아있음

**해결**:
```bash
# VPC ID 확인
cd terraform
VPC_ID=$(terraform output -raw vpc_id)

# 남은 리소스 확인 및 삭제
aws ec2 describe-network-interfaces --filters Name=vpc-id,Values=$VPC_ID
aws ec2 describe-security-groups --filters Name=vpc-id,Values=$VPC_ID

# 재시도
terraform destroy -auto-approve
```

### 2. Ansible Playbook 실패

**증상**: SSH 연결 실패

**원인**: SSM Agent 미등록 또는 SSH 키 문제

**해결**:
```bash
# SSH 테스트
ansible all -i ansible/inventory/hosts.ini -m ping

# 수동 SSH 접속
ssh -i ~/.ssh/your-key.pem ubuntu@<master-ip>

# SSM Session Manager 사용
aws ssm start-session --target <instance-id>
```

### 3. Monitoring 배포 실패

**증상**: Pod가 Pending 상태

**원인**: PVC 바인딩 실패 또는 리소스 부족

**해결**:
```bash
# PVC 상태 확인
kubectl get pvc

# StorageClass 확인
kubectl get storageclass

# Pod 상세 정보
kubectl describe pod <pod-name>

# EBS CSI Driver 확인
kubectl get pods -n kube-system -l app.kubernetes.io/name=aws-ebs-csi-driver
```

### 4. Worker 이미지 빌드 실패

**증상**: Docker 빌드 에러

**원인**: Dockerfile 문제 또는 의존성 누락

**해결**:
```bash
# 로그 확인
docker build -f workers/Dockerfile.storage -t test .

# 개별 빌드 테스트
cd workers
docker build -f Dockerfile.storage -t storage-worker-test .
docker build -f Dockerfile.ai -t ai-worker-test .
```

### 5. Worker Pod 시작 실패

**증상**: CrashLoopBackOff

**원인**: 환경 변수 누락 또는 WAL 디렉토리 권한

**해결**:
```bash
# Pod 로그 확인
kubectl logs <worker-pod-name>

# 환경 변수 확인
kubectl get pod <worker-pod-name> -o yaml | grep -A 20 env:

# Secret 확인
kubectl get secret postgresql-secret -o yaml
kubectl get secret aws-credentials -o yaml
```

## 💡 베스트 프랙티스

### 실행 전

1. **백업**
   - Terraform state 백업
   - 중요 데이터 백업 (DB, S3)

2. **변수 확인**
   - `terraform.tfvars` 검증
   - 환경 변수 설정 확인

3. **리소스 확인**
   - AWS 할당량 확인 (EC2 인스턴스, Elastic IP)
   - 도메인 설정 확인

### 실행 중

1. **모니터링**
   - 터미널 출력 주시
   - AWS Console에서 리소스 생성 확인

2. **에러 대응**
   - 에러 발생 시 로그 저장
   - 가능한 단계는 계속 진행

### 실행 후

1. **검증**
   - 13개 노드 모두 Ready 상태
   - 모든 Pod Running 상태
   - 모니터링 대시보드 정상 작동

2. **보안**
   - Grafana admin 비밀번호 변경
   - Security Group 규칙 검토

## 📝 수동 실행 옵션

### Worker 빌드만 별도 실행

```bash
export GITHUB_TOKEN=<token>
export GITHUB_USERNAME=<username>
export VERSION=v0.6.0
./scripts/build-workers.sh
```

### Worker 배포만 별도 실행

```bash
# Master 노드에서
kubectl apply -f k8s/workers/worker-wal-deployments.yaml
```

### 모니터링만 별도 실행

```bash
# Master 노드에서
./scripts/deploy-monitoring.sh
```

## 🎯 다음 단계

배포 완료 후:

1. **도메인 확인**
   ```
   https://ecoeco.app
   https://api.ecoeco.app
   ```

2. **ArgoCD 배포** (GitOps)
   ```bash
   kubectl apply -f argocd/
   ```

3. **애플리케이션 배포** (Helm)
   ```bash
   kubectl apply -f charts/ecoeco-backend/
   ```

## 🔗 관련 문서

- [Terraform 13-Node 설정](../../terraform/README.md)
- [Ansible Playbook 가이드](../../ansible/README.md)
- [모니터링 설정 가이드](../../docs/deployment/MONITORING_SETUP.md)
- [WAL 구현 가이드](../../docs/guides/WORKER_WAL_IMPLEMENTATION.md)
- [v0.6.0 완료 가이드](../../docs/development/V0.6.0_COMPLETION_GUIDE.md)

