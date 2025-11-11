# Atlantis 배포 위치 및 설정 가이드 (14-Node)

## 🌊 Atlantis는 어디서 동작하는가?

### 답변: Kubernetes 클러스터 내부 Pod

```yaml
배포 위치: Kubernetes StatefulSet (Pod)
실행 노드: k8s-monitoring (14-Node 아키텍처)
Namespace: atlantis
외부 접근: ALB (Application Load Balancer)
```

---

## 📊 Atlantis 아키텍처

```
┌─────────────────────────────────────────────────────────────────────┐
│ GitHub (Pull Request)                                               │
└─────────────────┬───────────────────────────────────────────────────┘
                  │ Webhook
                  ↓
┌─────────────────────────────────────────────────────────────────────┐
│ AWS ALB (atlantis.sesacthon.com)                                    │
└─────────────────┬───────────────────────────────────────────────────┘
                  │ Port 80
                  ↓
┌─────────────────────────────────────────────────────────────────────┐
│ Kubernetes Service (LoadBalancer)                                   │
└─────────────────┬───────────────────────────────────────────────────┘
                  │ Port 4141
                  ↓
┌─────────────────────────────────────────────────────────────────────┐
│ k8s-monitoring 노드 (t3.medium, 2 vCPU, 4GB)                        │
│                                                                      │
│  ┌────────────────────────────────────────────────────────────┐    │
│  │ Atlantis Pod (StatefulSet)                                 │    │
│  │                                                             │    │
│  │  1. PR Event 수신 (GitHub Webhook)                         │    │
│  │  2. Git Clone (SeSACTHON/backend)                          │    │
│  │  3. Terraform Plan/Apply 실행                              │    │
│  │  4. ConfigMap 저장 (kubectl)                               │    │
│  │  5. ArgoCD Sync 트리거 (argocd CLI)                        │    │
│  │                                                             │    │
│  │  리소스:                                                    │    │
│  │    - CPU: 250m (request) / 1000m (limit)                   │    │
│  │    - Memory: 512Mi (request) / 2Gi (limit)                 │    │
│  │    - Storage: 20Gi EBS (PVC)                               │    │
│  └────────────────────────────────────────────────────────────┘    │
│                                                                      │
│  ┌────────────────────────────────────────────────────────────┐    │
│  │ Prometheus Pod (Monitoring)                                │    │
│  └────────────────────────────────────────────────────────────┘    │
│                                                                      │
│  ┌────────────────────────────────────────────────────────────┐    │
│  │ Grafana Pod (Monitoring)                                   │    │
│  └────────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────────┘
                  │
                  ↓
        ┌─────────────────────┐
        │ AWS Resources        │
        │ - EC2 (14 nodes)     │
        │ - VPC, Subnets       │
        │ - Security Groups    │
        └─────────────────────┘
```

---

## 🏗️ Atlantis Kubernetes 리소스

### 배포 구조

```yaml
atlantis Namespace:
  ├── StatefulSet: atlantis
  │   ├── Replicas: 1 (단일 인스턴스 권장)
  │   ├── Image: ghcr.io/runatlantis/atlantis:v0.27.0
  │   ├── Port: 4141
  │   └── Volume: atlantis-data (20Gi EBS gp3)
  │
  ├── Service: atlantis (LoadBalancer)
  │   ├── Type: LoadBalancer (ALB)
  │   ├── External Port: 80
  │   └── Target Port: 4141
  │
  ├── Ingress: atlantis (선택)
  │   ├── Host: atlantis.sesacthon.com
  │   └── Class: ALB
  │
  ├── Secret: atlantis-secrets
  │   ├── github-token: GitHub PAT
  │   ├── github-webhook-secret: Webhook Secret
  │   ├── aws-access-key-id: AWS Access Key
  │   └── aws-secret-access-key: AWS Secret Key
  │
  ├── ConfigMap: atlantis-config
  │   └── AWS_REGION: ap-northeast-2
  │
  └── ServiceAccount: atlantis
      ├── ClusterRole: configmap-creator
      └── ClusterRoleBinding: atlantis
```

---

## 📍 14-Node 아키텍처에서의 배치 전략

### 선택한 전략: k8s-monitoring 노드에 배포 ⭐

```yaml
노드: k8s-monitoring (t3.medium, 2 vCPU, 4GB)
NodeSelector: workload=monitoring
Toleration: node-role.kubernetes.io/infrastructure=true:NoSchedule

이유:
  ✅ Infrastructure 성격 (GitOps 도구)
  ✅ Monitoring 노드는 리소스 여유로움
  ✅ Prometheus/Grafana와 같은 노드 (관리 편의)
  ✅ 일반 API/Worker Pod과 격리
  ✅ CPU/Memory 충분 (Terraform 실행에 필요)
```

### 노드별 비교

| 노드 | vCPU | RAM | 기존 워크로드 | Atlantis 적합도 | 선택 |
|------|------|-----|---------------|----------------|------|
| **k8s-master** | 2 | 8GB | Control Plane | ⚠️ 보통 (리소스 공유) | ❌ |
| **k8s-monitoring** | 2 | 4GB | Prometheus, Grafana | ✅ 좋음 (Infrastructure) | ✅ 권장 |
| **k8s-rabbitmq** | 2 | 2GB | RabbitMQ | ⚠️ 낮음 (메모리 부족) | ❌ |
| **k8s-api-*** | 2 | 1-2GB | API Services | ❌ 부적합 (API 전용) | ❌ |
| **k8s-worker-*** | 2 | 2GB | Celery Workers | ❌ 부적합 (Worker 전용) | ❌ |

---

## 🔧 Atlantis 동작 방식

### 1. Pull Request 생성 시

```yaml
1. 개발자 → GitHub PR 생성 (terraform/ 수정)
2. GitHub → Webhook → ALB → Atlantis Pod
3. Atlantis Pod:
   a. Git Clone (SeSACTHON/backend)
   b. terraform init
   c. terraform plan
   d. GitHub PR에 Plan 결과 코멘트
```

### 2. "atlantis apply" 코멘트 시

```yaml
1. 팀원 PR 승인 → "atlantis apply" 코멘트
2. Atlantis Pod:
   a. terraform apply (EC2 생성 등)
   b. terraform output -json > /tmp/tf-outputs.json
   c. kubectl create configmap terraform-outputs \
        --from-file=/tmp/tf-outputs.json \
        --namespace=argocd
   d. argocd app sync sesacthon-infrastructure (선택)
   e. GitHub PR에 Apply 결과 코멘트
```

### 3. Pod 내부 디렉토리 구조

```bash
/atlantis-data/  # PersistentVolume (20Gi EBS)
├── repos/
│   └── github.com/
│       └── SeSACTHON/
│           └── backend/
│               ├── .git/
│               ├── terraform/
│               │   ├── .terraform/  # Terraform 플러그인
│               │   ├── main.tf
│               │   └── terraform.tfstate (S3에 실제 저장)
│               ├── ansible/
│               └── atlantis.yaml
└── locks/  # Terraform Lock 관리
```

---

## 🚀 Atlantis 배포 단계

### Step 1: Secret 생성

```bash
# GitHub Token 생성
# - Settings → Developer settings → Personal access tokens
# - 권한: repo, admin:repo_hook

# Webhook Secret 생성
WEBHOOK_SECRET=$(openssl rand -hex 20)

# Secret YAML 생성
cat <<EOF > atlantis-secrets.yaml
apiVersion: v1
kind: Secret
metadata:
  name: atlantis-secrets
  namespace: atlantis
type: Opaque
stringData:
  github-token: "ghp_xxxxxxxxxxxxxxxxxxxx"
  github-webhook-secret: "$WEBHOOK_SECRET"
  aws-access-key-id: "AKIAXXXXXXXXXXXXXXXX"
  aws-secret-access-key: "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
EOF

# Secret 생성
kubectl create namespace atlantis
kubectl apply -f atlantis-secrets.yaml
```

### Step 2: RBAC 설정 (ConfigMap 생성 권한)

```bash
# ClusterRole 생성
cat <<EOF | kubectl apply -f -
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: atlantis-configmap-creator
rules:
  - apiGroups: [""]
    resources: ["configmaps"]
    verbs: ["create", "update", "patch", "get", "list"]
  - apiGroups: [""]
    resources: ["namespaces"]
    verbs: ["get", "list"]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata:
  name: atlantis-configmap-creator
subjects:
  - kind: ServiceAccount
    name: atlantis
    namespace: atlantis
roleRef:
  kind: ClusterRole
  name: atlantis-configmap-creator
  apiGroup: rbac.authorization.k8s.io
EOF
```

### Step 3: Atlantis 배포

```bash
# Atlantis StatefulSet, Service, Ingress 배포
kubectl apply -f k8s/atlantis/atlantis-deployment.yaml

# 배포 확인
kubectl get pods -n atlantis
kubectl get svc -n atlantis
kubectl logs -n atlantis atlantis-0 -f
```

### Step 4: GitHub Webhook 설정

```bash
# ALB DNS 확인
ALB_DNS=$(kubectl get svc atlantis -n atlantis -o jsonpath='{.status.loadBalancer.ingress[0].hostname}')
echo "ALB DNS: $ALB_DNS"

# GitHub Repository → Settings → Webhooks → Add webhook
# Payload URL: http://$ALB_DNS/events
# Content type: application/json
# Secret: (위에서 생성한 WEBHOOK_SECRET)
# Events: Pull request reviews, Pull requests, Issue comments, Pushes
```

### Step 5: Route53 설정 (선택 - 도메인 사용 시)

```bash
# Route53에 A Record 생성
# atlantis.sesacthon.com → ALB DNS (Alias)

# 또는 Terraform으로 자동화
resource "aws_route53_record" "atlantis" {
  zone_id = data.aws_route53_zone.main.zone_id
  name    = "atlantis.sesacthon.com"
  type    = "A"
  
  alias {
    name                   = data.kubernetes_service.atlantis.status[0].load_balancer[0].ingress[0].hostname
    zone_id                = data.aws_elb_hosted_zone_id.main.id
    evaluate_target_health = true
  }
}
```

---

## 🔍 Atlantis 동작 확인

### 테스트 PR 생성

```bash
# Feature 브랜치 생성
git checkout -b test/atlantis-setup
echo "# Test" >> terraform/test.txt
git add terraform/
git commit -m "test: Atlantis setup verification"
git push origin test/atlantis-setup

# GitHub에서 PR 생성
# → Atlantis가 자동으로 terraform plan 실행
# → PR에 코멘트로 Plan 결과 표시

# PR 승인 후 코멘트
# "atlantis apply"
# → Atlantis가 terraform apply 실행
# → ConfigMap 저장
# → ArgoCD Sync 트리거
```

### 로그 확인

```bash
# Atlantis Pod 로그
kubectl logs -n atlantis atlantis-0 -f

# 예상 로그:
# {"level":"info","msg":"Received event from VCS","event":"pull_request"}
# {"level":"info","msg":"Running terraform plan"}
# {"level":"info","msg":"Plan success","duration":"15.2s"}
# {"level":"info","msg":"Commenting plan result on PR"}
```

---

## 📊 리소스 사용량

### Atlantis Pod 리소스

```yaml
Resources:
  Requests:
    CPU: 250m (25% of 1 core)
    Memory: 512Mi
  Limits:
    CPU: 1000m (1 core)
    Memory: 2Gi

Storage:
  Type: EBS gp3
  Size: 20Gi
  Usage: ~5-10Gi (Git repos + Terraform state cache)
```

### k8s-monitoring 노드 리소스 분배

```yaml
노드: t3.medium (2 vCPU, 4GB RAM)

배분:
  Prometheus:
    - CPU: 500m / Memory: 2Gi
  Grafana:
    - CPU: 200m / Memory: 512Mi
  Atlantis:
    - CPU: 250m / Memory: 512Mi
  System Reserved:
    - CPU: ~500m / Memory: ~1Gi

총 사용:
  - CPU: 1450m / 2000m (72%)
  - Memory: 3Gi / 4Gi (75%)
  
여유:
  - CPU: 550m (Atlantis Limit 1000m 사용 가능)
  - Memory: 1Gi (Atlantis Limit 2Gi 사용 가능)
```

---

## 🎯 Atlantis vs 기존 방식 비교

### Before: 수동 Terraform 실행

```bash
# 로컬 개발 환경
terraform init
terraform plan
terraform apply  # 위험! 로컬 → 프로덕션 직접 적용

문제점:
  ❌ 팀원 검토 없음
  ❌ Lock 관리 어려움
  ❌ State 충돌 가능
  ❌ 변경 히스토리 추적 어려움
```

### After: Atlantis (GitOps)

```bash
# GitHub Pull Request
PR 생성 → Atlantis Plan (자동) → 팀원 검토 → "atlantis apply"

장점:
  ✅ PR 기반 검토 (Code Review)
  ✅ 자동 Lock 관리
  ✅ Git 히스토리와 연동
  ✅ Terraform State 안전 관리
  ✅ ConfigMap 자동 저장
  ✅ ArgoCD 자동 연동
```

---

## 📝 요약

### Atlantis 배포 위치

```yaml
서버: Kubernetes 클러스터 내부
노드: k8s-monitoring (14-Node 아키텍처)
Namespace: atlantis
접근: ALB (atlantis.sesacthon.com)
```

### 왜 k8s-monitoring 노드인가?

```yaml
이유:
  1. Infrastructure 성격 (GitOps 도구)
  2. 리소스 여유 (t3.medium, 4GB RAM)
  3. Prometheus/Grafana와 동일 노드 (관리 편의)
  4. API/Worker Pod과 격리
  5. Taint 설정으로 일반 Pod 격리
```

### 다음 단계

```bash
1. ✅ Atlantis 배포 YAML 업데이트 (완료)
   - NodeSelector: workload=monitoring
   - Toleration: infrastructure taint

2. 🔲 Secret 생성 (대기)
   - GitHub Token
   - Webhook Secret
   - AWS Credentials

3. 🔲 Atlantis 배포 (대기)
   - kubectl apply -f k8s/atlantis/atlantis-deployment.yaml

4. 🔲 GitHub Webhook 설정 (대기)
   - Repository Settings

5. 🔲 테스트 PR 생성 (대기)
   - terraform/ 수정 → PR → "atlantis apply"
```

---

**작성일**: 2025-11-08  
**상태**: Atlantis 배포 YAML 업데이트 완료  
**다음**: Secret 생성 → Atlantis 배포 → GitHub Webhook 설정

