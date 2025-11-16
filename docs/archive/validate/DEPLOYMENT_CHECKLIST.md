# 클러스터 재배포 체크리스트
**작성일:** 2025-11-15  
**목적:** GitOps 기반 클린 배포

---

## ✅ 사전 점검 완료

### 1. 코드베이스 확인 ✅
- [x] Terraform 설정: 14대 노드 (main.tf)
- [x] Ansible site.yml: 완전한 부트스트랩 프로세스
- [x] ArgoCD role: root-app.yaml 자동 배포 포함
- [x] k8s/namespaces: 존재 (네임스페이스 정의)
- [x] charts/data/databases: Helm umbrella chart 존재
- [x] argocd/apps: App-of-Apps 구조 완성

### 2. 브랜치 전략 확인 ⚠️
- **현재 브랜치:** main
- **ArgoCD 타겟:** develop
- **필요 조치:** develop 브랜치 확인 및 동기화

### 3. 환경 변수 (ansible/inventory/group_vars/all.yml)
```yaml
# 필수 환경 변수 설정
POSTGRES_PASSWORD=<strong-password>
RABBITMQ_PASSWORD=<strong-password>
GRAFANA_PASSWORD=<admin-password>
```

### 4. Terraform 변수 (terraform.tfvars)
```hcl
enable_cloudfront = true
domain_name = "growbin.app"
```

---

## 📋 배포 절차

### Phase 0: 준비 작업

#### 0-1. 브랜치 동기화
```bash
# Option A: develop 브랜치로 전환
git checkout develop
git pull origin develop
git merge main  # main의 최신 변경사항 통합

# Option B: main 브랜치 사용하도록 ArgoCD 설정 변경
# root-app.yaml 및 모든 Application의 targetRevision을 'main'으로 변경
```

#### 0-2. Helm Dependencies 준비
```bash
cd charts/data/databases
helm dependency update
cd ../../..
```

#### 0-3. 환경 변수 설정
```bash
# 비밀번호 생성
export POSTGRES_PASSWORD=$(openssl rand -base64 32)
export RABBITMQ_PASSWORD=$(openssl rand -base64 32)
export GRAFANA_PASSWORD=$(openssl rand -base64 20)

# 저장 (선택사항)
echo "POSTGRES_PASSWORD=${POSTGRES_PASSWORD}" >> ~/.env.sesacthon
echo "RABBITMQ_PASSWORD=${RABBITMQ_PASSWORD}" >> ~/.env.sesacthon
echo "GRAFANA_PASSWORD=${GRAFANA_PASSWORD}" >> ~/.env.sesacthon
```

#### 0-4. SSH 키 확인
```bash
ls -la ~/.ssh/sesacthon.pem
ls -la ~/.ssh/sesacthon.pub
```

### Phase 1: 현재 클러스터 파괴

```bash
cd terraform
terraform destroy -auto-approve
```

**예상 시간:** 5-10분

**확인 사항:**
- [ ] EC2 인스턴스 모두 삭제
- [ ] EBS 볼륨 삭제
- [ ] Security Groups 삭제
- [ ] ELB/ALB 삭제
- [ ] VPC 삭제

### Phase 2: 인프라 생성 (Terraform)

```bash
cd terraform
terraform init
terraform plan
terraform apply -auto-approve
```

**예상 시간:** 5-7분

**확인 사항:**
- [ ] EC2 14대 생성 완료
- [ ] VPC, Subnet, IGW 생성
- [ ] Security Groups 설정
- [ ] ACM Certificate 생성/검증
- [ ] Route53 호스트존 존재
- [ ] IAM Role/Instance Profile 생성

**생성된 리소스:**
```
Master: 1대 (t3.large)
API Nodes: 7대
  - api-auth: t3.micro
  - api-my: t3.micro  
  - api-scan: t3.small
  - api-character: t3.micro
  - api-location: t3.micro
  - api-info: t3.micro
  - api-chat: t3.small
Workers: 2대
  - worker-storage: t3.small
  - worker-ai: t3.small
Infrastructure: 4대
  - postgresql: t3.medium
  - redis: t3.small
  - rabbitmq: t3.small
  - monitoring: t3.medium
```

### Phase 3: 클러스터 부트스트랩 (Ansible)

#### 3-1. Inventory 생성
```bash
cd ansible
terraform output -raw hosts > inventory/hosts.ini
```

#### 3-2. Ansible 실행
```bash
ansible-playbook -i inventory/hosts.ini site.yml \
  -e "postgres_password=${POSTGRES_PASSWORD}" \
  -e "rabbitmq_password=${RABBITMQ_PASSWORD}" \
  -e "grafana_admin_password=${GRAFANA_PASSWORD}"
```

**예상 시간:** 30-45분

**Ansible 실행 순서:**
1. Common setup (모든 노드)
2. Docker 설치
3. Kubernetes 설치
4. Master 초기화
5. Workers join
6. Provider ID 설정 (ALB 필수)
7. CNI 설치 (Calico)
8. Node 라벨링
9. Addons 설치 (cert-manager, metrics-server)
10. EBS CSI Driver
11. ALB Controller
12. IngressClass
13. **ArgoCD 설치 + root-app 자동 배포** ← 핵심!
14. Namespaces 생성
15. Monitoring 설치 (Prometheus Operator)
16. RabbitMQ, Redis, PostgreSQL (Ansible Roles)
17. Atlantis
18. Ingress 리소스
19. Route53 업데이트

**확인 사항:**
- [ ] 모든 노드 Ready
- [ ] ArgoCD Pod Running
- [ ] root-app Application 생성됨
- [ ] Monitoring 스택 Running

### Phase 4: ArgoCD 자동 배포 확인

#### 4-1. SSH로 Master 접속
```bash
ssh -i ~/.ssh/sesacthon.pem ubuntu@$(cd terraform && terraform output -raw master_public_ip)
```

#### 4-2. ArgoCD Applications 확인
```bash
# Applications 목록
kubectl get applications -n argocd

# ApplicationSets 확인
kubectl get applicationsets -n argocd

# Sync 상태 확인
kubectl get applications -n argocd -o json | jq -r '.items[] | "\(.metadata.name): \(.status.sync.status)"'
```

**예상 Applications (Wave 순서):**
```
Wave -1:  namespaces
Wave 10:  infrastructure (reserved)
Wave 20:  alb-controller, platform
Wave 30:  platform
Wave 40:  monitoring
Wave 50:  data-operators
Wave 60:  data-clusters (PostgreSQL/Redis/RabbitMQ via Helm)
Wave 70:  gitops-tools (Atlantis)
Wave 80:  api-services (ApplicationSet → 7개 API)
          workers (Celery + Flower)
```

#### 4-3. API Services 배포 확인
```bash
# ApplicationSet이 7개 API Application 생성했는지 확인
kubectl get applications -n argocd | grep api-

# 각 네임스페이스에 Pod 배포 확인
kubectl get pods -n auth
kubectl get pods -n character
kubectl get pods -n chat
kubectl get pods -n info
kubectl get pods -n location
kubectl get pods -n my
kubectl get pods -n scan
```

#### 4-4. Workers 배포 확인
```bash
kubectl get pods -n workers
```

---

## 🔍 배포 후 검증

### 1. 클러스터 헬스 체크

```bash
# 노드 상태
kubectl get nodes

# 전체 Pod 상태
kubectl get pods -A

# Persistent Volumes
kubectl get pv
kubectl get pvc -A
```

### 2. 데이터 계층 확인

```bash
# PostgreSQL
kubectl get pods -n data -l app.kubernetes.io/name=postgresql

# Redis
kubectl get pods -n data -l app.kubernetes.io/name=redis

# RabbitMQ
kubectl get rabbitmqcluster -A
kubectl get pods -n messaging
```

### 3. API Services 확인

```bash
# 모든 API 서비스 Pod
kubectl get pods -l tier=business-logic -A

# Ingress 확인
kubectl get ingress -A
```

### 4. ArgoCD WebUI 접속

```bash
# 포트 포워딩 (로컬)
kubectl port-forward svc/argocd-server -n argocd 8080:443

# 또는 Ingress URL
echo "https://argocd.growbin.app"

# 초기 비밀번호
kubectl -n argocd get secret argocd-initial-admin-secret -o jsonpath="{.data.password}" | base64 -d
```

### 5. 모니터링 확인

```bash
# Prometheus
echo "https://prometheus.growbin.app"

# Grafana
echo "https://grafana.growbin.app"
# Username: admin
# Password: ${GRAFANA_PASSWORD}
```

### 6. API Endpoints 테스트

```bash
# Health check
curl https://api.growbin.app/auth/health
curl https://api.growbin.app/my/health
curl https://api.growbin.app/scan/health
# ... (각 서비스별)
```

---

## ⚠️ 알려진 이슈 & 해결

### Issue 1: PostgreSQL Secret 이름 불일치

**문제:**
- Helm chart가 생성한 Secret 이름과 기존 참조가 다를 수 있음

**해결:**
- ArgoCD가 Helm chart로 PostgreSQL 배포 시 자동 처리됨
- 또는 values.yaml에서 Secret 이름 명시

### Issue 2: Helm Chart Dependencies

**문제:**
- charts/data/databases의 dependencies가 pull 안되어 있음

**해결:**
```bash
cd charts/data/databases
helm dependency update
cd ../../..
git add charts/data/databases/Chart.lock charts/data/databases/charts
git commit -m "chore: update helm dependencies"
git push origin develop  # 또는 main
```

### Issue 3: ArgoCD가 develop 브랜치 참조

**문제:**
- main과 develop 브랜치 불일치 가능성

**해결 Option A (권장):**
```bash
git checkout develop
git merge main
git push origin develop
```

**해결 Option B:**
```bash
# root-app.yaml 및 모든 Application의 targetRevision을 'main'으로 변경
find argocd/apps -name "*.yaml" -exec sed -i '' 's/targetRevision: develop/targetRevision: main/g' {} \;
sed -i '' 's/targetRevision: develop/targetRevision: main/g' argocd/root-app.yaml
git commit -am "chore: switch argocd to main branch"
```

---

## 📊 배포 시간 예상

| Phase | 작업 | 예상 시간 |
|-------|------|----------|
| 0 | 준비 작업 | 5분 |
| 1 | Terraform Destroy | 5-10분 |
| 2 | Terraform Apply | 5-7분 |
| 3 | Ansible Playbook | 30-45분 |
| 4 | ArgoCD 자동 배포 | 10-15분 |
| 5 | 검증 | 5-10분 |
| **합계** | | **60-92분** |

---

## 🎯 성공 기준

### 필수 (Critical)
- [ ] 14개 노드 모두 Ready
- [ ] ArgoCD 설치 완료
- [ ] root-app Application 생성
- [ ] Foundations Application Synced
- [ ] Data Clusters Synced (PostgreSQL/Redis/RabbitMQ)
- [ ] API ApplicationSet이 7개 Application 생성
- [ ] 모든 API Service Pod Running
- [ ] Ingress로 API 접근 가능

### 선택 (Optional)
- [ ] Monitoring 대시보드 접근 가능
- [ ] Atlantis 동작 확인
- [ ] CloudFront 설정 (enable_cloudfront=true인 경우)
- [ ] Route53 DNS 전파 완료

---

## 🔧 문제 해결

### Ansible 실패 시
```bash
# 특정 단계부터 재실행
ansible-playbook -i inventory/hosts.ini site.yml --start-at-task="<task-name>"

# 특정 playbook만 재실행
ansible-playbook -i inventory/hosts.ini playbooks/07-alb-controller.yml
```

### ArgoCD Application 수동 트리거
```bash
# Application Sync 강제 실행
kubectl patch application <app-name> -n argocd --type merge -p '{"operation":{"initiatedBy":{"username":"admin"},"sync":{"revision":"develop"}}}'

# 또는 ArgoCD CLI 사용
argocd app sync <app-name>
```

### 로그 확인
```bash
# ArgoCD controller 로그
kubectl logs -n argocd deployment/argocd-application-controller

# ApplicationSet controller 로그
kubectl logs -n argocd deployment/argocd-applicationset-controller

# 특정 Application 상태
kubectl describe application <app-name> -n argocd
```

---

**준비 완료!** 체크리스트를 따라 진행하세요.

