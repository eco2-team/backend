# 14-Node 클러스터 자동 재구축 가이드

## 📊 개요

`auto-rebuild.sh`는 14-Node Kubernetes 클러스터를 완전히 자동으로 재구축하고, GitOps 환경까지 배포하는 통합 스크립트입니다.

## 🎯 실행 순서

### 전체 프로세스 (자동)

1. **Terraform Destroy** - 기존 인프라 삭제
2. **Terraform Apply** - 14-Node 인프라 구축
3. **Ansible Playbook** - Kubernetes 설치
4. **Monitoring Stack** - Prometheus/Grafana 배포
5. **ArgoCD** - GitOps CD 도구 배포
6. **Atlantis** - Terraform PR Automation 배포

### 예상 소요 시간
- **전체**: 40-60분
  - Terraform destroy: 5-10분
  - Terraform apply: 10-15분
  - Ansible playbook: 15-20분
  - Monitoring 배포: 5분
  - ArgoCD 배포: 3분
  - Atlantis 배포: 2분

## 🚀 사용 방법

### 1. 사전 준비

```bash
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

## 📦 배포되는 구성

### 14-Node 클러스터

| 노드 유형 | 개수 | 인스턴스 타입 | 역할 |
|----------|------|--------------|------|
| Master | 1 | t3.large | Kubernetes Control Plane + ArgoCD + Atlantis |
| API | 7 | t3.micro~t3.small | API Services (auth, my, scan, character, location, info, chat) |
| Worker | 2 | t3.small | Storage Worker, AI Worker |
| Infrastructure | 4 | t3.micro~t3.small | PostgreSQL, Redis, RabbitMQ, Monitoring |

**총 비용**: ~$218/월

### 모니터링 스택

- **Prometheus**
  - ServiceMonitor (API 7개 + Worker 2개)
  - Alert Rules
  - 30일 메트릭 보관 (50GB PVC)

- **Grafana**
  - 14-Node 전용 대시보드
  - 관리자 인증 (Secret)

- **Node Exporter**
  - DaemonSet (14개 노드 모니터링)

### GitOps 도구

- **ArgoCD**
  - Helm Chart 기반 배포
  - Auto-Sync 활성화 (3분마다)
  - 애플리케이션 상태 모니터링

- **Atlantis**
  - Terraform PR 기반 인프라 변경
  - Plan/Apply 자동화
  - GitHub Webhook 연동

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

### Step 2: Terraform Apply (14-Node)

```bash
# 14-Node 인프라 구축
terraform apply -auto-approve

# 생성되는 리소스:
# - 14 EC2 Instances
# - VPC, Subnets, Security Groups
# - S3 Bucket (images)
# - CloudFront Distribution
# - Route53 Records
# - ACM Certificates
# - IAM Roles & Policies

# 대기 시간: 90초 (SSM Agent 등록)
```

### Step 3: Ansible Playbook

```bash
# Inventory 자동 생성
terraform output -raw ansible_inventory > ansible/inventory/hosts.ini

# Kubernetes 설치 (14 nodes)
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

### Step 4: Monitoring Stack 배포

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

### Step 5: ArgoCD 배포

```bash
# ArgoCD 설치
kubectl create namespace argocd
kubectl apply -n argocd -f https://raw.githubusercontent.com/argoproj/argo-cd/stable/manifests/install.yaml

# Ingress 설정
kubectl apply -f k8s/argocd/ingress.yaml

# 초기 비밀번호 확인
kubectl -n argocd get secret argocd-initial-admin-secret -o jsonpath="{.data.password}" | base64 -d
```

### Step 6: Atlantis 배포

```bash
# Atlantis 배포
kubectl apply -f k8s/atlantis/

# Webhook Secret 확인
kubectl get secret atlantis-webhook -o jsonpath="{.data.secret}" | base64 -d
```

## 📊 배포 확인

### 클러스터 접속

```bash
# Master 노드 접속
ssh ubuntu@$(cd terraform && terraform output -raw master_public_ip)

# 노드 확인 (14개)
kubectl get nodes -o wide

# Pod 확인
kubectl get pods -A
```

### 노드별 역할 확인

```bash
# 노드 레이블 확인
kubectl get nodes --show-labels

# 각 노드별 Pod 배치 확인
kubectl get pods -A -o wide | grep auth-node
kubectl get pods -A -o wide | grep scan-node
kubectl get pods -A -o wide | grep postgresql-node
```

### 모니터링 확인

```bash
# Prometheus 접속
kubectl port-forward -n monitoring svc/prometheus 9090:9090
# http://localhost:9090

# Grafana 접속
kubectl port-forward -n monitoring svc/grafana 3000:3000
# http://localhost:3000

# Grafana 비밀번호 확인
kubectl get secret -n monitoring grafana-admin -o jsonpath='{.data.password}' | base64 -d
```

### GitOps 도구 확인

```bash
# ArgoCD 접속
kubectl port-forward -n argocd svc/argocd-server 8080:443
# https://localhost:8080

# Atlantis 상태 확인
kubectl get pods -n atlantis
kubectl logs -n atlantis deployment/atlantis
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
kubectl get pvc -n monitoring

# StorageClass 확인
kubectl get storageclass

# Pod 상세 정보
kubectl describe pod -n monitoring <pod-name>

# EBS CSI Driver 확인
kubectl get pods -n kube-system -l app.kubernetes.io/name=aws-ebs-csi-driver
```

### 4. ArgoCD 접속 실패

**증상**: ArgoCD UI 접속 불가

**원인**: Ingress 설정 문제 또는 ALB Controller 미작동

**해결**:
```bash
# ArgoCD Pod 상태 확인
kubectl get pods -n argocd

# Ingress 상태 확인
kubectl get ingress -n argocd

# ALB Controller 로그 확인
kubectl logs -n kube-system deployment/aws-load-balancer-controller
```

### 5. Atlantis Webhook 실패

**증상**: GitHub PR에서 Atlantis 반응 없음

**원인**: Webhook Secret 불일치 또는 네트워크 문제

**해결**:
```bash
# Atlantis 로그 확인
kubectl logs -n atlantis deployment/atlantis

# Webhook Secret 재확인
kubectl get secret -n atlantis atlantis-webhook -o jsonpath="{.data.secret}" | base64 -d

# GitHub Webhook 설정 확인
# Settings → Webhooks → Recent Deliveries
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
   - AWS 할당량 확인 (EC2 인스턴스 32개, Elastic IP)
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
   - 14개 노드 모두 Ready 상태
   - 모든 Pod Running 상태
   - 모니터링 대시보드 정상 작동
   - ArgoCD/Atlantis 접속 가능

2. **보안**
   - Grafana admin 비밀번호 변경
   - ArgoCD admin 비밀번호 변경
   - Security Group 규칙 검토
   - Atlantis Webhook Secret 확인

## 📝 수동 실행 옵션

### 모니터링만 별도 실행

```bash
# Master 노드에서
./scripts/deploy-monitoring.sh
```

### ArgoCD만 별도 실행

```bash
# ArgoCD 설치
kubectl create namespace argocd
kubectl apply -n argocd -f https://raw.githubusercontent.com/argoproj/argo-cd/stable/manifests/install.yaml

# Application 등록
kubectl apply -f argocd/application-14nodes.yaml
```

### Atlantis만 별도 실행

```bash
# Atlantis 배포
kubectl apply -f k8s/atlantis/

# GitHub Webhook 설정 (수동)
# Repository Settings → Webhooks → Add webhook
```

## 🎯 다음 단계

배포 완료 후:

1. **도메인 확인**
   ```
   https://growbin.app
   https://api.growbin.app
   https://argocd.growbin.app
   https://atlantis.growbin.app
   https://grafana.growbin.app
   ```

2. **ArgoCD Application 등록**
   ```bash
   kubectl apply -f argocd/application-14nodes.yaml
   ```

3. **Helm Chart 배포** (ArgoCD가 자동으로 처리)
   ```bash
   # Git에 푸시하면 ArgoCD가 자동 배포
   git add charts/ecoeco-backend/values-14nodes.yaml
   git commit -m "feat: Update 14-node configuration"
   git push origin develop
   ```

4. **Atlantis PR 테스트**
   ```bash
   # terraform/*.tf 파일 수정 후 PR 생성
   # PR 코멘트에 "atlantis plan" 입력
   # 결과 확인 후 "atlantis apply" 입력
   ```

## 🔗 관련 문서

- [Terraform 14-Node 설정](../../terraform/README.md)
- [Ansible Playbook 가이드](../../ansible/README.md)
- [모니터링 설정 가이드](MONITORING_SETUP.md)
- [ArgoCD 가이드](../guides/ARGOCD_GUIDE.md)
- [Atlantis 설정 가이드](ATLANTIS_SETUP.md)
- [GitOps 아키텍처](GITOPS_ARCHITECTURE.md)
- [v0.7.0 완료 가이드](../development/03-V0.7.0_COMPLETION_GUIDE.md)

---

**문서 버전**: v0.7.0  
**최종 업데이트**: 2025-11-11  
**아키텍처**: 14-Node Microservices with Full GitOps
