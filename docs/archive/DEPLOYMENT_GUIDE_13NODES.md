# Ecoeco Backend - 13 Node 배포 가이드

## 📋 사전 준비

### 필요한 도구
```bash
# Terraform
terraform --version  # >= 1.0

# Ansible
ansible --version    # >= 2.10

# kubectl
kubectl version      # >= 1.24

# Helm
helm version         # >= 3.0

# GitHub CLI (PR용)
gh --version
```

---

## 🚀 1단계: 인프라 생성 (Terraform)

### Terraform 초기화
```bash
cd /Users/mango/workspace/SeSACTHON/backend/terraform

# 초기화
terraform init

# 플랜 확인 (13개 노드 확인)
terraform plan

# 출력 예시:
# Plan: 13 to add, 0 to change, 0 to destroy.
# 
# Nodes to create:
#   - k8s-master (t3.large, 8GB)
#   - k8s-api-waste (t3.small, 2GB)
#   - k8s-api-auth (t3.micro, 1GB)
#   - k8s-api-userinfo (t3.micro, 1GB)
#   - k8s-api-location (t3.micro, 1GB)
#   - k8s-api-recycle-info (t3.micro, 1GB)
#   - k8s-api-chat-llm (t3.small, 2GB)
#   - k8s-worker-storage (t3.medium, 4GB)
#   - k8s-worker-ai (t3.medium, 4GB)
#   - k8s-rabbitmq (t3.small, 2GB)
#   - k8s-postgresql (t3.small, 2GB)
#   - k8s-redis (t3.small, 2GB)
#   - k8s-monitoring (t3.large, 8GB)
```

### 인프라 생성
```bash
# 실제 생성 (약 5-10분 소요)
terraform apply

# 완료 후 정보 확인
terraform output cluster_info

# 출력:
{
  total_nodes = 13
  total_vcpu = 18
  total_memory_gb = 26
  estimated_cost_usd = 270
}

# SSH 명령어 확인
terraform output ssh_commands
```

### Ansible Inventory 생성
```bash
# Terraform이 자동으로 inventory 생성
terraform output ansible_inventory > ../ansible/inventory/hosts.ini

# 확인
cat ../ansible/inventory/hosts.ini

# [api_nodes]
# k8s-api-waste ansible_host=54.180.xxx.1 service=waste ...
# k8s-api-auth ansible_host=54.180.xxx.2 service=auth ...
# ...
```

---

## 🔧 2단계: Kubernetes 설치 (Ansible)

### Ansible Playbook 실행
```bash
cd /Users/mango/workspace/SeSACTHON/backend/ansible

# SSH 키 확인
ls -la ~/.ssh/sesacthon.pem

# 권한 설정
chmod 400 ~/.ssh/sesacthon.pem

# 연결 테스트
ansible all -i inventory/hosts.ini -m ping

# 전체 클러스터 설치 (약 15-20분 소요)
ansible-playbook -i inventory/hosts.ini site.yml

# 단계별 진행:
# [✓] Master 노드 초기화
# [✓] Worker 노드 Join
# [✓] 노드 라벨링 (service, type 라벨)
# [✓] Helm 설치
# [✓] ArgoCD 설치
# [✓] Monitoring 설치 (Prometheus + Grafana)
# [✓] RabbitMQ 설치
# [✓] PostgreSQL 설치
# [✓] Redis 설치
```

### 노드 라벨 확인
```bash
# Master 노드 접속
ssh -i ~/.ssh/sesacthon.pem ubuntu@<master-ip>

# 노드 확인
kubectl get nodes -o wide

# NAME                    STATUS   ROLES           AGE   VERSION
# k8s-master              Ready    control-plane   10m   v1.28.0
# k8s-api-waste           Ready    <none>          8m    v1.28.0
# k8s-api-auth            Ready    <none>          8m    v1.28.0
# k8s-api-userinfo        Ready    <none>          8m    v1.28.0
# k8s-api-location        Ready    <none>          8m    v1.28.0
# k8s-api-recycle-info    Ready    <none>          8m    v1.28.0
# k8s-api-chat-llm        Ready    <none>          8m    v1.28.0
# k8s-worker-storage      Ready    <none>          8m    v1.28.0
# k8s-worker-ai           Ready    <none>          8m    v1.28.0
# k8s-rabbitmq            Ready    <none>          8m    v1.28.0
# k8s-postgresql          Ready    <none>          8m    v1.28.0
# k8s-redis               Ready    <none>          8m    v1.28.0
# k8s-monitoring          Ready    <none>          8m    v1.28.0

# 라벨 확인
kubectl get nodes --show-labels | grep service

# k8s-api-waste ... service=waste
# k8s-api-auth ... service=auth
# k8s-api-userinfo ... service=userinfo
# k8s-api-location ... service=location
# k8s-api-recycle-info ... service=recycle-info
# k8s-api-chat-llm ... service=chat-llm
```

---

## 📦 3단계: Helm Chart 배포

### Helm Chart 검증
```bash
# 차트 문법 검증
cd /Users/mango/workspace/SeSACTHON/backend/charts/ecoeco-backend

helm lint .

# values 파일 확인
cat values-13nodes.yaml | grep nodeSelector -A 2

# 출력:
# waste:
#   nodeSelector:
#     service: waste  # ← k8s-api-waste 노드만 지정
```

### 수동 배포 (테스트)
```bash
# Dry-run (실제 배포 없이 확인)
helm install ecoeco-backend . \
  -f values-13nodes.yaml \
  --dry-run --debug

# 실제 배포
helm install ecoeco-backend . \
  -f values-13nodes.yaml \
  --namespace api \
  --create-namespace

# 배포 상태 확인
helm list -n api
helm get values ecoeco-backend -n api

# Pod 배치 확인
kubectl get pods -n api -o wide

# NAME                      READY   NODE
# waste-api-xxx-1           1/1     k8s-api-waste
# waste-api-xxx-2           1/1     k8s-api-waste
# waste-api-xxx-3           1/1     k8s-api-waste
# auth-api-xxx-1            1/1     k8s-api-auth
# auth-api-xxx-2            1/1     k8s-api-auth
# userinfo-api-xxx-1        1/1     k8s-api-userinfo
# ...

# ✅ 각 API가 자신의 전용 노드에서 실행 중!
```

---

## 🔄 4단계: ArgoCD 자동 배포 설정

### ArgoCD 접속
```bash
# ArgoCD 비밀번호 확인
kubectl -n argocd get secret argocd-initial-admin-secret \
  -o jsonpath="{.data.password}" | base64 -d; echo

# Port Forward
kubectl port-forward svc/argocd-server -n argocd 8080:443

# 브라우저에서 접속
# https://localhost:8080
# ID: admin
# PW: <위에서 확인한 비밀번호>
```

### ArgoCD Application 배포
```bash
# Application 생성
kubectl apply -f /Users/mango/workspace/SeSACTHON/backend/argocd/application-13nodes.yaml

# 상태 확인
kubectl get applications -n argocd

# NAME                        SYNC STATUS   HEALTH STATUS
# ecoeco-backend-13nodes     Synced        Healthy

# ArgoCD CLI 설치 (선택)
brew install argocd

# 로그인
argocd login localhost:8080

# 앱 확인
argocd app list
argocd app get ecoeco-backend-13nodes

# 동기화 (수동)
argocd app sync ecoeco-backend-13nodes
```

---

## ✅ 5단계: 배포 검증

### 1. 노드별 Pod 배치 확인
```bash
# API 노드별 Pod 확인
for node in waste auth userinfo location recycle-info chat-llm; do
  echo "=== k8s-api-$node ==="
  kubectl get pods -n api -o wide | grep "k8s-api-$node"
  echo ""
done

# Worker 노드별 Pod 확인
echo "=== k8s-worker-storage ==="
kubectl get pods -n workers -o wide | grep storage

echo "=== k8s-worker-ai ==="
kubectl get pods -n workers -o wide | grep ai
```

### 2. 서비스 Health Check
```bash
# Master 노드 내부에서
kubectl run curl --image=curlimages/curl -i --rm --restart=Never -- \
  curl -s http://waste-api.api.svc.cluster.local:8000/health

# {"status":"healthy","service":"waste-api"}

# 모든 API 확인
for api in waste auth userinfo location recycle-info chat-llm; do
  echo "Checking $api-api..."
  kubectl run curl --image=curlimages/curl -i --rm --restart=Never -- \
    curl -s http://$api-api.api.svc.cluster.local:8000/health
done
```

### 3. Ingress 확인
```bash
# ALB 생성 확인
kubectl get ingress -n api

# NAME          CLASS   HOSTS              ADDRESS
# api-ingress   alb     api.ecoeco.app    xxx.elb.amazonaws.com

# 외부 접속 테스트
curl https://api.ecoeco.app/api/v1/waste/health
curl https://api.ecoeco.app/api/v1/auth/health
curl https://api.ecoeco.app/api/v1/users/health
```

### 4. Worker 동작 확인
```bash
# RabbitMQ 큐 확인
kubectl exec -n messaging rabbitmq-0 -- rabbitmqctl list_queues

# Celery Worker 로그
kubectl logs -n workers -l app=image-uploader --tail=50
kubectl logs -n workers -l app=gpt5-analyzer --tail=50
```

---

## 🔧 6단계: CI/CD 파이프라인 연결

### GitHub Actions 설정
```bash
# GitHub Secrets 등록
gh secret set GHCR_TOKEN --body "<your-token>"
gh secret set KUBE_CONFIG --body "$(cat ~/.kube/config | base64)"

# Workflow 확인
cat .github/workflows/api-deploy.yml

# 테스트 Push
git add services/waste-api/
git commit -m "feat: Update waste-api"
git push origin main

# GitHub Actions 실행 확인
# → Docker Build → GHCR Push → Helm Values Update → ArgoCD Auto Sync
```

---

## 📊 7단계: 모니터링 설정

### Grafana 접속
```bash
# Port Forward
kubectl port-forward -n monitoring svc/grafana 3000:80

# 브라우저: http://localhost:3000
# ID: admin
# PW: (ConfigMap에서 확인)

# 대시보드 import
# - Kubernetes Cluster Monitoring
# - API Performance by Node
# - Celery Worker Metrics
```

### Prometheus Targets 확인
```bash
# Port Forward
kubectl port-forward -n monitoring svc/prometheus 9090:9090

# 브라우저: http://localhost:9090
# Status > Targets
# ✅ 모든 API Pod가 /metrics 노출 확인
```

---

## 🎯 완료 체크리스트

```yaml
Infrastructure:
  ✅ Terraform으로 13개 노드 생성
  ✅ Ansible로 Kubernetes 설치
  ✅ 노드 라벨링 완료

Application:
  ✅ Helm Chart 배포
  ✅ 각 API가 독립 노드에서 실행
  ✅ Worker가 전용 노드에서 실행
  ✅ Ingress 생성 (ALB)

Automation:
  ✅ ArgoCD 자동 배포 설정
  ✅ GitHub Actions CI/CD 연결
  ✅ Git Push → 자동 배포 확인

Monitoring:
  ✅ Prometheus 메트릭 수집
  ✅ Grafana 대시보드
  ✅ Alert 설정

Verification:
  ✅ Health Check 통과
  ✅ API 외부 접속 가능
  ✅ Worker 정상 동작
```

---

## 🚨 트러블슈팅

### Pod이 특정 노드에 배치되지 않을 때
```bash
# 1. 노드 라벨 확인
kubectl get nodes --show-labels | grep k8s-api-waste

# 2. 없으면 수동 라벨링
kubectl label node k8s-api-waste service=waste --overwrite

# 3. Pod 재시작
kubectl rollout restart deployment/waste-api -n api
```

### ArgoCD Sync 실패 시
```bash
# 상태 확인
argocd app get ecoeco-backend-13nodes

# 로그 확인
kubectl logs -n argocd -l app.kubernetes.io/name=argocd-application-controller

# 수동 Sync
argocd app sync ecoeco-backend-13nodes --prune
```

---

**🎉 배포 완료! 13 노드 마이크로서비스 아키텍처가 실행 중입니다!**

