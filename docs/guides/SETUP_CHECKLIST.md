# ✅ 구축 체크리스트

> **전체 구축 순서 및 우선순위**  
> **예상 소요 시간**: 약 8-10시간 (1-2일)  
> **날짜**: 2025-10-30

## 📋 목차

1. [사전 준비 (필수)](#사전-준비-필수)
2. [로컬 환경 설정](#로컬-환경-설정)
3. [AWS 인프라 구축](#aws-인프라-구축)
4. [Kubernetes 클러스터 구축](#kubernetes-클러스터-구축)
5. [ArgoCD & GitOps 설정](#argocd--gitops-설정)
6. [Helm Charts 작성](#helm-charts-작성)
7. [GitHub Actions 설정](#github-actions-설정)
8. [서비스 배포](#서비스-배포)
9. [검증 및 테스트](#검증-및-테스트)

---

## 🎯 전체 흐름 요약

```mermaid
graph TD
    A[1. 사전 준비<br/>30분] --> B[2. 로컬 환경<br/>30분]
    B --> C[3. AWS 인프라<br/>Terraform<br/>10분]
    C --> D[4. K8s 클러스터<br/>Ansible<br/>40분]
    D --> E[5. ArgoCD<br/>20분]
    E --> F[6. Helm Charts<br/>3시간]
    F --> G[7. GitHub Actions<br/>1시간]
    G --> H[8. 서비스 배포<br/>1시간]
    H --> I[9. 검증<br/>1시간]
    I --> J[✅ 완료!<br/>총 8시간]
    
    style A fill:#cce5ff,stroke:#007bff,stroke-width:3px,color:#000
    style B fill:#cce5ff,stroke:#007bff,stroke-width:2px,color:#000
    style C fill:#e6d5ff,stroke:#8844ff,stroke-width:3px,color:#000
    style D fill:#ffd1d1,stroke:#dc3545,stroke-width:4px,color:#000
    style E fill:#e6d5ff,stroke:#8844ff,stroke-width:3px,color:#000
    style F fill:#ffe0b3,stroke:#fd7e14,stroke-width:3px,color:#000
    style G fill:#ffd1d1,stroke:#dc3545,stroke-width:2px,color:#000
    style H fill:#d1f2eb,stroke:#28a745,stroke-width:3px,color:#000
    style I fill:#d1f2eb,stroke:#28a745,stroke-width:2px,color:#000
    style J fill:#d1f2eb,stroke:#28a745,stroke-width:4px,color:#000
```

---

## 📌 우선순위 범례

```
🔴 P0 - 필수, 막히면 진행 불가
🟡 P1 - 중요, 권장
🟢 P2 - 선택, 나중에 추가 가능
```

---

## 1️⃣ 사전 준비 (필수) - 30분

### 🔴 P0: AWS 계정 및 권한

```bash
# 확인 사항
- [ ] AWS 계정 존재
- [ ] IAM 사용자 생성 (AdministratorAccess 또는 EC2FullAccess)
- [ ] AWS CLI 설치
- [ ] AWS 자격증명 설정

# AWS CLI 설치
curl "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o "awscliv2.zip"
unzip awscliv2.zip
sudo ./aws/install

# 자격증명 설정
aws configure
# AWS Access Key ID: YOUR_ACCESS_KEY
# AWS Secret Access Key: YOUR_SECRET_KEY
# Default region: ap-northeast-2
# Default output format: json

# 확인
aws sts get-caller-identity
```

### 🔴 P0: SSH 키 생성 (백업용, 선택)

```bash
# SSH 키 생성 (선택적, 백업 접속용)
- [ ] SSH 키 페어 생성 (선택)

ssh-keygen -t rsa -b 4096 -f ~/.ssh/sesacthon -C "sesacthon-k8s"

# 결과:
# ~/.ssh/sesacthon (private key)
# ~/.ssh/sesacthon.pub (public key)

# terraform.tfvars 수정 (Session Manager 사용 시 선택)
# public_key_path = "~/.ssh/sesacthon.pub"

# ⭐ Session Manager 사용 시 SSH 키 없어도 됨!
```

### 🔴 P0: AWS Session Manager Plugin 설치

```bash
# Session Manager Plugin 설치 (SSH 키 대체)
- [ ] Session Manager Plugin 설치

# macOS
brew install --cask session-manager-plugin

# Linux
curl "https://s3.amazonaws.com/session-manager-downloads/plugin/latest/ubuntu_64bit/session-manager-plugin.deb" -o "session-manager-plugin.deb"
sudo dpkg -i session-manager-plugin.deb

# Windows
# https://docs.aws.amazon.com/systems-manager/latest/userguide/session-manager-working-with-install-plugin.html

# 확인
session-manager-plugin

# ✅ 이제 SSH 키 없이 EC2 접속 가능!
```

### 🔴 P0: GitHub Repository 준비

```bash
- [ ] GitHub Repository 생성 (sesacthon-backend)
- [ ] Git Clone
- [ ] GitHub Token 생성 (GHCR 권한)

# GitHub Personal Access Token
https://github.com/settings/tokens/new

Scopes 선택:
✅ repo (전체)
✅ write:packages
✅ read:packages
✅ delete:packages
✅ workflow

# Token 저장 (나중에 사용)
```

### 🟡 P1: Slack Webhook (선택)

```bash
- [ ] Slack Workspace 생성
- [ ] Incoming Webhooks 앱 추가
- [ ] Webhook URL 복사

https://api.slack.com/messaging/webhooks

# 나중에 GitHub Secrets에 저장
```

---

## 2️⃣ 로컬 환경 설정 - 30분

### 🔴 P0: 필수 도구 설치

```bash
# Terraform 설치
- [ ] Terraform 설치 (v1.0+)

# macOS
brew install terraform

# Linux
wget https://releases.hashicorp.com/terraform/1.6.0/terraform_1.6.0_linux_amd64.zip
unzip terraform_1.6.0_linux_amd64.zip
sudo mv terraform /usr/local/bin/

# 확인
terraform version
```

```bash
# Ansible 설치
- [ ] Ansible 설치 (v2.10+)

# macOS
brew install ansible

# Linux
sudo apt update
sudo apt install -y ansible

# 확인
ansible --version
```

```bash
# kubectl 설치
- [ ] kubectl 설치

# macOS
brew install kubectl

# Linux
curl -LO "https://dl.k8s.io/release/$(curl -L -s https://dl.k8s.io/release/stable.txt)/bin/linux/amd64/kubectl"
sudo install -o root -g root -m 0755 kubectl /usr/local/bin/kubectl

# 확인
kubectl version --client
```

```bash
# Helm 설치
- [ ] Helm 설치 (v3.0+)

# macOS
brew install helm

# Linux
curl https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3 | bash

# 확인
helm version
```

```bash
# ArgoCD CLI 설치 (선택)
- [ ] ArgoCD CLI 설치

# macOS
brew install argocd

# Linux
curl -sSL -o argocd https://github.com/argoproj/argo-cd/releases/latest/download/argocd-linux-amd64
sudo install -m 555 argocd /usr/local/bin/argocd

# 확인
argocd version --client
```

### 🔴 P0: Python 환경 (로컬 개발용)

```bash
- [ ] Python 3.11 설치
- [ ] 가상환경 생성
- [ ] 의존성 설치

python3.11 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

---

## 3️⃣ AWS 인프라 구축 (Terraform) - 10분

### 🔴 P0: S3 Backend 준비

```bash
- [ ] S3 버킷 생성 (Terraform State 저장)
- [ ] DynamoDB 테이블 생성 (State Lock - 동시 실행 방지)

# S3 버킷 (terraform.tfstate 저장용)
aws s3api create-bucket \
  --bucket sesacthon-terraform-state \
  --region ap-northeast-2 \
  --create-bucket-configuration LocationConstraint=ap-northeast-2

# Versioning 활성화 (중요!)
aws s3api put-bucket-versioning \
  --bucket sesacthon-terraform-state \
  --versioning-configuration Status=Enabled

# DynamoDB 테이블 (Terraform Lock용)
# 용도: 동시 terraform apply 방지
# 비용: ~$0 (월 수백 건)
aws dynamodb create-table \
  --table-name terraform-state-lock \
  --attribute-definitions AttributeName=LockID,AttributeType=S \
  --key-schema AttributeName=LockID,KeyType=HASH \
  --billing-mode PAY_PER_REQUEST \
  --region ap-northeast-2

# 확인
aws s3 ls | grep terraform-state
aws dynamodb list-tables | grep terraform-state-lock

# ✅ DynamoDB 덕분에 팀원과 동시 작업 가능!
```

### 🔴 P0: terraform.tfvars 설정

```bash
- [ ] terraform.tfvars 수정

cd terraform
vim terraform.tfvars

# 필수 수정 항목:
aws_region = "ap-northeast-2"
allowed_ssh_cidr = "YOUR_IP/32"  # ⚠️ 본인 IP로 변경 (또는 0.0.0.0/0)
public_key_path = "~/.ssh/sesacthon.pub"  # (선택, 백업용)

# ⭐ Session Manager 사용 시:
# - allowed_ssh_cidr은 보안상 특정 IP 권장
# - public_key_path는 비상 접속용으로 설정
```

### 🔴 P0: Terraform 실행

```bash
- [ ] terraform init
- [ ] terraform plan 검토
- [ ] terraform apply

cd terraform

# 초기화
terraform init

# 계획 확인
terraform plan -out=tfplan

# 리뷰 후 적용
terraform apply tfplan

# 출력 확인
terraform output

# ✅ 예상 결과:
# master_public_ip = "3.34.xxx.xxx"
# worker_1_public_ip = "3.35.xxx.xxx"
# worker_2_public_ip = "3.36.xxx.xxx"
```

### 🔴 P0: Ansible Inventory 생성

```bash
- [ ] Terraform output으로 Inventory 생성

terraform output -raw ansible_inventory > ../ansible/inventory/hosts.ini

# 확인
cat ../ansible/inventory/hosts.ini

# ✅ Master, Worker IP가 올바른지 확인
```

---

## 4️⃣ Kubernetes 클러스터 구축 (Ansible) - 40분

### 🔴 P0: 연결 테스트

```bash
- [ ] EC2 부팅 및 SSM Agent 등록 대기 (3-5분)
- [ ] Session Manager 또는 SSH 연결 테스트

sleep 300  # 5분 대기 (SSM Agent 등록 시간 포함)

# Session Manager로 접속 테스트 (권장)
MASTER_ID=$(aws ec2 describe-instances \
  --filters "Name=tag:Name,Values=k8s-master" "Name=instance-state-name,Values=running" \
  --query "Reservations[].Instances[].InstanceId" \
  --output text \
  --region ap-northeast-2)

aws ssm start-session --target $MASTER_ID --region ap-northeast-2

# 접속 성공 후 종료: exit

# 또는 SSH로 접속 (백업)
# ssh -i ~/.ssh/sesacthon ubuntu@$(terraform output -raw master_public_ip)

cd ../ansible

# Ansible Ping 테스트
ansible all -i inventory/hosts.ini -m ping

# ✅ 모든 노드 SUCCESS 확인
```

### 🔴 P0: Ansible Playbook 실행

```bash
- [ ] site.yml 실행 (전체 설치)

ansible-playbook -i inventory/hosts.ini site.yml

# 실행 내용:
# 1. OS 설정 (5분)
# 2. Docker 설치 (3분)
# 3. Kubernetes 설치 (5분)
# 4. Master 초기화 (3분)
# 5. CNI 설치 (2분)
# 6. Worker 조인 (2분)
# 7. Add-ons 설치 (5분)
# 8. ArgoCD 설치 (3분)
# 9. RabbitMQ 설치 (2분)
# 10. Monitoring 설치 (5분)

# 총 35분 소요

# ✅ 출력에서 ArgoCD 비밀번호 저장!
```

### 🔴 P0: 클러스터 확인

```bash
- [ ] Master 접속
- [ ] kubectl get nodes 확인

# Session Manager로 Master 접속 (권장)
MASTER_ID=$(aws ec2 describe-instances \
  --filters "Name=tag:Name,Values=k8s-master" \
  --query "Reservations[].Instances[].InstanceId" \
  --output text \
  --region ap-northeast-2)

aws ssm start-session --target $MASTER_ID --region ap-northeast-2

# 또는 SSH (백업)
# ssh -i ~/.ssh/sesacthon ubuntu@$(cd ../terraform && terraform output -raw master_public_ip)

# 노드 확인
kubectl get nodes -o wide

# ✅ 예상 결과:
# NAME           STATUS   ROLES           AGE   VERSION
# k8s-master     Ready    control-plane   10m   v1.28.4
# k8s-worker-1   Ready    <none>          5m    v1.28.4
# k8s-worker-2   Ready    <none>          5m    v1.28.4

# Pod 확인
kubectl get pods -A

# ✅ 모든 Pod Running 확인

# Session Manager 종료
exit
```

---

## 5️⃣ ArgoCD & GitOps 설정 - 20분

### 🔴 P0: ArgoCD 접근

```bash
- [ ] ArgoCD 초기 비밀번호 확인
- [ ] Port Forward 설정
- [ ] UI 로그인

# Master 노드에서
kubectl -n argocd get secret argocd-initial-admin-secret \
  -o jsonpath="{.data.password}" | base64 -d && echo

# Port Forward (로컬 PC에서)
kubectl port-forward svc/argocd-server -n argocd 8080:443

# 브라우저에서 접속
# https://localhost:8080
# Username: admin
# Password: (위에서 확인한 비밀번호)
```

### 🔴 P0: ArgoCD GitHub 연동

```bash
- [ ] GitHub Repository 등록

# ArgoCD CLI 로그인
argocd login localhost:8080 \
  --username admin \
  --password <PASSWORD> \
  --insecure

# GitHub Repository 추가
argocd repo add https://github.com/YOUR_ORG/sesacthon-backend.git \
  --username YOUR_GITHUB_USERNAME \
  --password YOUR_GITHUB_TOKEN

# 확인
argocd repo list
```

### 🟡 P1: ArgoCD Ingress 설정 (선택)

```bash
- [ ] 도메인 준비
- [ ] Ingress 적용

# argocd/ingress.yaml 수정
vim argocd/ingress.yaml
# host: argocd.yourdomain.com

# 적용
kubectl apply -f argocd/ingress.yaml

# DNS 설정 (Route53 등)
# argocd.yourdomain.com → Master Public IP
```

---

## 6️⃣ Helm Charts 작성 - 3시간

### 🔴 P0: Helm Charts 생성 (5개 서비스)

```bash
- [ ] auth Chart
- [ ] users Chart
- [ ] waste Chart
- [ ] recycling Chart
- [ ] locations Chart

mkdir -p charts

# 각 서비스별 Chart 생성
for svc in auth users waste recycling locations; do
  helm create charts/$svc
done

# ✅ 생성 확인
ls -la charts/
```

### 🔴 P0: values-prod.yaml 커스터마이징

각 서비스별로 `charts/{service}/values-prod.yaml` 생성:

```yaml
# charts/auth/values-prod.yaml
replicaCount: 2

image:
  repository: ghcr.io/YOUR_ORG/sesacthon-backend/auth-service
  tag: latest  # ⚠️ 나중에 GitHub Actions가 자동 업데이트
  pullPolicy: Always

service:
  type: ClusterIP
  port: 80
  targetPort: 8000

ingress:
  enabled: true
  annotations:
    kubernetes.io/ingress.class: alb
    alb.ingress.kubernetes.io/scheme: internet-facing
    alb.ingress.kubernetes.io/target-type: ip
    alb.ingress.kubernetes.io/certificate-arn: arn:aws:acm:ap-northeast-2:xxxxx:certificate/xxxxx
    alb.ingress.kubernetes.io/group.name: ecoeco-alb
  hosts:
    - host: api.yourdomain.com
      paths:
        - path: /api/v1/auth
          pathType: Prefix
  tls:
    - secretName: api-tls
      hosts:
        - api.yourdomain.com

resources:
  requests:
    cpu: 100m
    memory: 128Mi
  limits:
    cpu: 500m
    memory: 256Mi

nodeSelector:
  workload: network  # Worker 3

env:
  - name: DATABASE_URL
    valueFrom:
      secretKeyRef:
        name: auth-secrets
        key: database-url
  - name: REDIS_URL
    value: "redis://redis.default.svc.cluster.local:6379/0"
```

**체크리스트:**
```bash
- [ ] charts/auth/values-prod.yaml
- [ ] charts/users/values-prod.yaml
- [ ] charts/waste/values-prod.yaml
- [ ] charts/recycling/values-prod.yaml
- [ ] charts/locations/values-prod.yaml

# 각 파일에서 수정할 항목:
# 1. image.repository (GHCR 경로)
# 2. nodeSelector (workload 레이블)
# 3. resources (CPU, Memory)
# 4. env (환경변수)
```

### 🔴 P0: Secrets 생성

```bash
- [ ] auth-secrets
- [ ] waste-secrets
- [ ] recycling-secrets

# auth-secrets
kubectl create namespace auth
kubectl create secret generic auth-secrets \
  --from-literal=database-url='postgresql://user:pass@postgres.default:5432/sesacthon' \
  --from-literal=jwt-secret='YOUR_JWT_SECRET' \
  --from-literal=kakao-client-id='YOUR_KAKAO_ID' \
  --from-literal=kakao-client-secret='YOUR_KAKAO_SECRET' \
  -n auth

# waste-secrets
kubectl create namespace waste
kubectl create secret generic waste-secrets \
  --from-literal=ai-api-url='https://api.roboflow.com/...' \
  --from-literal=ai-api-key='YOUR_ROBOFLOW_KEY' \
  -n waste

# recycling-secrets
kubectl create namespace recycling
kubectl create secret generic recycling-secrets \
  --from-literal=openai-api-key='sk-YOUR_OPENAI_KEY' \
  -n recycling
```

### 🔴 P0: PostgreSQL & Redis 배포

```bash
- [ ] PostgreSQL Helm Chart
- [ ] Redis Helm Chart

# PostgreSQL
helm install postgresql bitnami/postgresql \
  --namespace default \
  --set auth.username=sesacthon \
  --set auth.password=YOUR_DB_PASSWORD \
  --set auth.database=sesacthon \
  --set primary.persistence.size=10Gi

# Redis
helm install redis bitnami/redis \
  --namespace default \
  --set auth.enabled=false \
  --set master.persistence.size=5Gi

# 확인
kubectl get pods -n default
```

---

## 7️⃣ GitHub Actions 설정 - 1시간

### 🔴 P0: GitHub Secrets 설정

```bash
- [ ] Repository Settings → Secrets and variables → Actions

필수 Secrets:
└─ SLACK_WEBHOOK_URL (선택)

# GITHUB_TOKEN은 자동 제공됨 (설정 불필요)
```

### 🔴 P0: Workflow 파일 복제

```bash
- [ ] ci-build-{service}.yml 생성 (5개)

# auth는 이미 생성됨
# 나머지 복제
for svc in users waste recycling locations; do
  cp .github/workflows/ci-build-auth.yml \
     .github/workflows/ci-build-$svc.yml
  
  # SERVICE_NAME 변경
  sed -i "s/SERVICE_NAME: auth/SERVICE_NAME: $svc/g" \
    .github/workflows/ci-build-$svc.yml
  
  # IMAGE_NAME 변경
  sed -i "s|/auth-service|/$svc-service|g" \
    .github/workflows/ci-build-$svc.yml
done

# 확인
ls -la .github/workflows/ci-build-*.yml
```

### 🔴 P0: Workflow 파일 수정

각 Workflow의 `IMAGE_NAME` 확인:

```yaml
# .github/workflows/ci-build-waste.yml
env:
  SERVICE_NAME: waste
  REGISTRY: ghcr.io
  IMAGE_NAME: ${{ github.repository }}/waste-service  # ✅ 확인
```

---

## 8️⃣ 서비스 배포 - 1시간

### 🔴 P0: ArgoCD Applications 등록

```bash
- [ ] argocd/applications/all-services.yaml 수정
- [ ] kubectl apply

# Repository URL 수정
vim argocd/applications/all-services.yaml
# repoURL: https://github.com/YOUR_ORG/sesacthon-backend.git

# 적용
kubectl apply -f argocd/applications/all-services.yaml

# 확인
kubectl get applications -n argocd
argocd app list

# ✅ 5개 Application 생성 확인
```

### 🔴 P0: 서비스 디렉토리 구조 생성

```bash
- [ ] services/ 폴더 구조
- [ ] 각 서비스 Dockerfile
- [ ] requirements.txt

mkdir -p services/{auth,users,waste,recycling,locations}/{app,tests}

# 각 서비스에:
# ├─ app/
# │   ├─ __init__.py
# │   ├─ main.py
# │   ├─ routes.py
# │   └─ ...
# ├─ tests/
# ├─ Dockerfile
# └─ requirements.txt
```

### 🔴 P0: 첫 서비스 구현 (Auth)

```bash
- [ ] services/auth/app/main.py 작성
- [ ] services/auth/Dockerfile 작성
- [ ] services/auth/requirements.txt 작성

# 최소한의 Health Check 엔드포인트
# app/main.py:
# @app.get("/health")
# def health():
#     return {"status": "healthy"}
```

### 🔴 P0: 첫 배포 테스트

```bash
- [ ] Git Push
- [ ] GitHub Actions 확인
- [ ] ArgoCD Sync 확인

git add services/auth
git commit -m "feat: Add auth service skeleton"
git push origin main

# GitHub Actions 확인
# https://github.com/YOUR_ORG/sesacthon-backend/actions

# ArgoCD 확인
argocd app get auth-service

# Pod 확인
kubectl get pods -n auth

# ✅ auth-service Pod Running 확인
```

---

## 9️⃣ 검증 및 테스트 - 1시간

### 🔴 P0: 클러스터 상태 검증

```bash
- [ ] 모든 노드 Ready
- [ ] 모든 시스템 Pod Running
- [ ] ArgoCD Applications Synced

kubectl get nodes
# ✅ 3개 노드 모두 Ready

kubectl get pods -A
# ✅ 모든 Pod Running 또는 Completed

argocd app list
# ✅ 5개 Application 모두 Synced, Healthy
```

### 🔴 P0: Ingress 테스트

```bash
- [ ] ALB Controller 정상
- [ ] 도메인 연결 (Route53)

kubectl get ingress -A

# ALB DNS 확인
kubectl get ingress main-ingress -o jsonpath='{.status.loadBalancer.ingress[0].hostname}'

# Route53에서 Alias 레코드:
# ecoeco.app → ALB DNS

# 테스트
curl http://MASTER_PUBLIC_IP
# 또는
curl https://api.yourdomain.com
```

### 🔴 P0: RabbitMQ 확인

```bash
- [ ] RabbitMQ Pod Running
- [ ] Queue 생성 확인

kubectl get pods -n messaging

# Management UI 접근
kubectl port-forward -n messaging svc/rabbitmq 15672:15672

# 브라우저: http://localhost:15672
# Username: admin
# Password: (ansible/inventory/group_vars/all.yml 확인)

# ✅ Queues 탭에서 q.fast, q.bulk, q.external, q.sched, q.dlq 확인
```

### 🟡 P1: 모니터링 확인

```bash
- [ ] Prometheus 정상
- [ ] Grafana 접속

kubectl get pods -n monitoring

# Grafana 접근
kubectl port-forward -n monitoring svc/prometheus-grafana 3000:80

# 브라우저: http://localhost:3000
# Username: admin
# Password: (ansible에서 설정한 비밀번호)
```

### 🔴 P0: 로그 확인

```bash
- [ ] 에러 로그 없는지 확인

# ArgoCD 로그
kubectl logs -n argocd -l app.kubernetes.io/name=argocd-server

# RabbitMQ 로그
kubectl logs -n messaging -l app.kubernetes.io/name=rabbitmq

# 서비스 로그
kubectl logs -n auth -l app=auth-service

# ✅ ERROR 없는지 확인
```

---

## 🎯 최종 검증 체크리스트

### 인프라

```bash
✅ Terraform
- [ ] S3 Backend 정상
- [ ] EC2 3대 Running
- [ ] Security Groups 설정 완료
- [ ] Elastic IP 할당 완료

✅ Kubernetes
- [ ] 3개 노드 모두 Ready
- [ ] Flannel CNI 정상 (Pod network)
- [ ] Ingress Controller Running
- [ ] Cert-manager Running
- [ ] Metrics Server Running
```

### GitOps

```bash
✅ ArgoCD
- [ ] ArgoCD UI 접속 가능
- [ ] GitHub Repo 연동 완료
- [ ] 5개 Applications 등록
- [ ] 모두 Synced & Healthy

✅ GitHub Actions
- [ ] 5개 워크플로우 파일 존재
- [ ] GHCR 권한 설정 완료
- [ ] 첫 Push 성공
- [ ] 이미지 빌드 & Push 성공
```

### 서비스

```bash
✅ 데이터베이스
- [ ] PostgreSQL Pod Running
- [ ] Redis Pod Running
- [ ] 접속 테스트 완료

✅ RabbitMQ
- [ ] RabbitMQ Pod Running
- [ ] Management UI 접속 가능
- [ ] 5개 Queue 자동 생성 확인

✅ 마이크로서비스
- [ ] auth-service Pod Running
- [ ] users-service Pod Running
- [ ] waste-service Pod Running
- [ ] recycling-service Pod Running
- [ ] locations-service Pod Running

✅ Celery Workers
- [ ] Fast Workers Running
- [ ] External-AI Workers Running
- [ ] External-LLM Workers Running
- [ ] Bulk Workers Running
- [ ] Celery Beat Running
```

---

## 📊 진행 상황 트래킹

### Day 1 (4시간)

```
오전 (2시간):
✅ 1. 사전 준비
✅ 2. 로컬 환경 설정
✅ 3. AWS 인프라 구축 (Terraform)
✅ 4. K8s 클러스터 구축 (Ansible)

오후 (2시간):
✅ 5. ArgoCD 설정
□ 6. Helm Charts 작성 (시작)
```

### Day 2 (4-6시간)

```
오전 (3시간):
□ 6. Helm Charts 작성 (완료)

오후 (3시간):
□ 7. GitHub Actions 설정
□ 8. 서비스 배포
□ 9. 검증
```

---

## 🚨 주의사항

### 순서 지키기 (의존성)

```
⚠️ 반드시 순서대로 진행!

잘못된 순서:
❌ Helm Charts 없이 ArgoCD Applications 등록
❌ Secrets 없이 서비스 배포
❌ PostgreSQL 없이 서비스 실행

올바른 순서:
✅ Terraform → Ansible → ArgoCD → Helm Charts → Secrets → Services
```

### 확인 후 다음 단계

```
각 단계마다 반드시 확인:
1. Terraform apply 후 → output 확인
2. Ansible 실행 후 → kubectl get nodes
3. ArgoCD 설정 후 → UI 로그인
4. Helm Charts 작성 후 → helm lint
5. 배포 후 → kubectl get pods
```

### 문제 발생 시

```
문제 발생 지점에 따라:

Terraform 실패 → terraform destroy 후 재시도
Ansible 실패 → 해당 Playbook만 재실행
ArgoCD Sync 실패 → kubectl logs 확인
Pod CrashLoopBackOff → kubectl describe pod
```

---

## 🔧 유용한 명령어

### Session Manager 빠른 접속

```bash
# scripts/connect.sh 생성
cat <<'EOF' > scripts/connect.sh
#!/bin/bash

NODE_NAME=${1:-master}

echo "🔍 $NODE_NAME 인스턴스 검색 중..."
INSTANCE_ID=$(aws ec2 describe-instances \
  --filters "Name=tag:Name,Values=k8s-$NODE_NAME" "Name=instance-state-name,Values=running" \
  --query "Reservations[].Instances[].InstanceId" \
  --output text \
  --region ap-northeast-2)

if [ -z "$INSTANCE_ID" ]; then
  echo "❌ $NODE_NAME 인스턴스를 찾을 수 없습니다."
  exit 1
fi

echo "🔗 $NODE_NAME ($INSTANCE_ID) 접속 중..."
aws ssm start-session --target $INSTANCE_ID --region ap-northeast-2
EOF

chmod +x scripts/connect.sh

# 사용법:
# ./scripts/connect.sh master    # Master 접속
# ./scripts/connect.sh worker-1  # Worker 1 접속
# ./scripts/connect.sh worker-2  # Worker 2 접속
```

### 전체 상태 확인

```bash
# 한 번에 모든 상태 확인
cat <<'EOF' > check-status.sh
#!/bin/bash
echo "=== Nodes ==="
kubectl get nodes

echo -e "\n=== Pods (All Namespaces) ==="
kubectl get pods -A

echo -e "\n=== ArgoCD Applications ==="
kubectl get applications -n argocd

echo -e "\n=== Ingress ==="
kubectl get ingress -A

echo -e "\n=== Services ==="
kubectl get svc -A | grep -v ClusterIP

echo -e "\n=== HPA ==="
kubectl get hpa -A

echo -e "\n=== PVC ==="
kubectl get pvc -A
EOF

chmod +x check-status.sh

# Master에서 실행
# Session Manager로 접속 후:
./check-status.sh
```

---

## 📚 문서 참조

- [최종 K8s 아키텍처](docs/architecture/final-k8s-architecture.md)
- [IaC 설계](docs/architecture/iac-terraform-ansible.md)
- [GitOps 배포](docs/deployment/gitops-argocd-helm.md)
- [Task Queue 설계](docs/architecture/task-queue-design.md)

---

## 🎉 완료 후

```bash
축하합니다! 🎉

구축 완료된 인프라:
✅ Kubernetes Cluster (1M + 2W)
✅ ArgoCD GitOps
✅ RabbitMQ Message Broker
✅ Prometheus + Grafana
✅ 5개 마이크로서비스 (준비)
✅ AWS Session Manager (SSH 키 불필요!)

접속 방법:
# 어떤 PC에서든 (AWS 자격증명만 있으면)
./scripts/connect.sh master

다음 단계:
→ 각 서비스 코드 작성
→ Git Push하면 자동 배포!

비용: $105/월
```

---

## 📚 참고 문서

### Session Manager 상세

**[Session Manager 가이드](session-manager-guide.md)** - SSH 키 없이 접속

**핵심:**
- ✅ SSH 키 관리 불필요
- ✅ 어떤 PC에서든 접속 가능
- ✅ IAM으로 팀원 관리
- ✅ 접속 로그 자동 기록
- ✅ 비용 $0

---

**작성일**: 2025-10-30  
**예상 시간**: 8-10시간 (1-2일)  
**난이도**: ⭐⭐⭐⭐ (높음, K8s 경험자 권장)

