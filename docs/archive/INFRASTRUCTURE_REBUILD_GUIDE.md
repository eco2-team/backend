# 🎯 인프라 재구축 가이드

**버전**: 13 Node Microservices Architecture  
**작성일**: 2025-11-06  
**대상 환경**: AWS ap-northeast-2 (Seoul)

---

## 📝 개요

이 문서는 13노드 마이크로서비스 아키텍처를 재구축하기 위한 단계별 가이드입니다.  
인프라 검증 결과를 바탕으로 필수 수정사항을 모두 반영했습니다.

---

## ✅ 완료된 수정 사항

### 1. Helm Charts
- ✅ 각 API Deployment에 **Health Probes** 추가 (`/health`, `/ready`)
- ✅ **NodeSelector** 수정 (개별 서비스별 노드 타겟팅)
- ✅ **Service 리소스** 확인 (이미 존재)
- ✅ **Namespace 리소스** 생성 (`api`, `workers`, `data`, `messaging`)

### 2. Terraform
- ✅ **IAM Role** 및 **Instance Profile** 정의 (`terraform/iam.tf`)
  - ALB Controller 권한
  - ECR 읽기 권한
  - S3 접근 권한
  - CloudWatch 로깅 권한

### 3. ArgoCD
- ✅ **repoURL** 수정 (`https://github.com/SeSACTHON/backend`)
- ✅ **targetRevision** 수정 (`develop`)
- ✅ **path** 수정 (`charts/ecoeco-backend`)

---

## 🚀 재구축 절차

### 사전 준비

**1. AWS 자격 증명 설정**
```bash
export AWS_PROFILE=sesacthon
export AWS_REGION=ap-northeast-2
aws sts get-caller-identity
```

**2. SSH 키 페어 준비**
```bash
# SSH 키가 없다면 생성
ssh-keygen -t rsa -b 4096 -f ~/.ssh/k8s-cluster-key -N ""

# 공개키 확인
cat ~/.ssh/k8s-cluster-key.pub
```

**3. ACM 인증서 생성 (HTTPS용)**
```bash
# AWS Console 또는 CLI로 ACM 인증서 요청
aws acm request-certificate \
  --domain-name "*.ecoeco.app" \
  --validation-method DNS \
  --region ap-northeast-2

# 인증서 ARN 기록 (나중에 사용)
export ACM_CERT_ARN="arn:aws:acm:ap-northeast-2:ACCOUNT_ID:certificate/CERT_ID"
```

---

### Step 1: Terraform 인프라 프로비저닝

**1.1 Terraform 초기화**
```bash
cd /Users/mango/workspace/SeSACTHON/backend/terraform

terraform init
```

**1.2 Terraform 변수 설정**

`terraform/terraform.tfvars` 생성:
```hcl
aws_region        = "ap-northeast-2"
environment       = "production"
vpc_cidr          = "10.0.0.0/16"
allowed_ssh_cidr  = "YOUR_IP/32"  # 본인 IP로 변경
public_key_path   = "~/.ssh/k8s-cluster-key.pub"
```

**1.3 Terraform Plan 검토**
```bash
terraform plan -out=tfplan

# 주요 확인 사항:
# - 13개 EC2 인스턴스 생성
# - VPC, Subnet, Security Groups
# - IAM Role & Instance Profile
```

**1.4 Terraform Apply**
```bash
terraform apply tfplan

# 완료 후 outputs 확인
terraform output
```

**1.5 생성된 인벤토리 파일 확인**
```bash
cat ../ansible/inventory.ini

# 노드 IP 주소 확인
terraform output -json | jq '.ssh_commands.value'
```

---

### Step 2: Ansible 클러스터 구성

**2.1 Ansible 연결 테스트**
```bash
cd /Users/mango/workspace/SeSACTHON/backend/ansible

ansible all -i inventory.ini -m ping
```

**2.2 K8s 클러스터 설치**
```bash
ansible-playbook -i inventory.ini site.yml

# 예상 소요 시간: 30-40분
# 주요 작업:
# - Docker 설치
# - Kubernetes 설치 (kubeadm, kubelet, kubectl)
# - Master 노드 초기화
# - Worker 노드 조인
# - Calico CNI 설치
# - 노드 라벨링
```

**2.3 kubectl 설정**
```bash
# Master 노드에서 kubeconfig 복사
scp -i ~/.ssh/k8s-cluster-key ubuntu@MASTER_IP:~/.kube/config ~/.kube/k8s-cluster-config

# kubectl context 설정
export KUBECONFIG=~/.kube/k8s-cluster-config

# 노드 확인
kubectl get nodes -o wide
```

**2.4 노드 라벨 확인**
```bash
kubectl get nodes --show-labels | grep service=

# 예상 결과:
# k8s-api-waste         ... service=waste
# k8s-api-auth          ... service=auth
# k8s-api-userinfo      ... service=userinfo
# k8s-api-location      ... service=location
# k8s-api-recycle-info  ... service=recycle-info
# k8s-api-chat-llm      ... service=chat-llm
```

---

### Step 3: ALB Ingress Controller 설치

**3.1 AWS Load Balancer Controller 설치**
```bash
# Helm 리포지토리 추가
helm repo add eks https://aws.github.io/eks-charts
helm repo update

# 클러스터 이름 확인
export CLUSTER_NAME="k8s-cluster"

# AWS Load Balancer Controller 설치
helm install aws-load-balancer-controller eks/aws-load-balancer-controller \
  -n kube-system \
  --set clusterName=${CLUSTER_NAME} \
  --set serviceAccount.create=true \
  --set serviceAccount.name=aws-load-balancer-controller \
  --set region=ap-northeast-2 \
  --set vpcId=$(terraform output -raw vpc_id)

# 설치 확인
kubectl get deployment -n kube-system aws-load-balancer-controller
kubectl logs -n kube-system deployment/aws-load-balancer-controller
```

**3.2 IngressClass 확인**
```bash
kubectl get ingressclass

# 예상 결과:
# NAME   CONTROLLER            AGE
# alb    ingress.k8s.aws/alb   1m
```

---

### Step 4: ArgoCD 설치 및 설정

**4.1 ArgoCD 네임스페이스 생성**
```bash
kubectl create namespace argocd
```

**4.2 ArgoCD 설치**
```bash
kubectl apply -n argocd -f https://raw.githubusercontent.com/argoproj/argo-cd/stable/manifests/install.yaml

# 설치 확인
kubectl get pods -n argocd
```

**4.3 ArgoCD UI 접속**
```bash
# Admin 비밀번호 확인
kubectl -n argocd get secret argocd-initial-admin-secret -o jsonpath="{.data.password}" | base64 -d

# Port Forwarding
kubectl port-forward svc/argocd-server -n argocd 8080:443

# 브라우저에서 https://localhost:8080 접속
# ID: admin
# PW: (위에서 확인한 비밀번호)
```

**4.4 ArgoCD CLI 설치 (Optional)**
```bash
brew install argocd

# 로그인
argocd login localhost:8080 --username admin --password <PASSWORD>
```

---

### Step 5: GitHub 연동 및 Application 배포

**5.1 ArgoCD에 GitHub Repository 추가**
```bash
argocd repo add https://github.com/SeSACTHON/backend \
  --username YOUR_GITHUB_USERNAME \
  --password YOUR_GITHUB_TOKEN
```

**5.2 Application 배포**
```bash
cd /Users/mango/workspace/SeSACTHON/backend

kubectl apply -f argocd/application-13nodes.yaml

# 배포 상태 확인
argocd app get ecoeco-backend-13nodes

# Sync 강제 실행 (필요 시)
argocd app sync ecoeco-backend-13nodes
```

**5.3 배포 진행 상황 확인**
```bash
# Pod 상태 확인
kubectl get pods -n api
kubectl get pods -n workers

# Ingress 확인
kubectl get ingress -n api

# ALB 주소 확인
kubectl get ingress api-ingress -n api -o jsonpath='{.status.loadBalancer.ingress[0].hostname}'
```

---

### Step 6: Ingress에 ACM 인증서 연결

**6.1 Ingress Annotation 추가**

`charts/ecoeco-backend/values-13nodes.yaml` 수정:
```yaml
api:
  ingress:
    enabled: true
    className: alb
    annotations:
      alb.ingress.kubernetes.io/scheme: internet-facing
      alb.ingress.kubernetes.io/target-type: instance
      alb.ingress.kubernetes.io/healthcheck-path: /health
      alb.ingress.kubernetes.io/listen-ports: '[{"HTTP": 80}, {"HTTPS": 443}]'
      alb.ingress.kubernetes.io/ssl-redirect: '443'
      alb.ingress.kubernetes.io/certificate-arn: <ACM_CERT_ARN>  # 추가
      alb.ingress.kubernetes.io/load-balancer-name: ecoeco-api-alb  # 추가
```

**6.2 Git Push 및 ArgoCD Sync**
```bash
git add .
git commit -m "feat: Add ACM certificate to Ingress"
git push origin feature/infrastructure-validation

# ArgoCD가 자동으로 Sync (30초 이내)
argocd app sync ecoeco-backend-13nodes
```

---

### Step 7: DNS 설정

**7.1 Route53에 레코드 추가**
```bash
# ALB 주소 확인
ALB_DNS=$(kubectl get ingress api-ingress -n api -o jsonpath='{.status.loadBalancer.ingress[0].hostname}')

echo "ALB DNS: ${ALB_DNS}"

# Route53에서 CNAME 레코드 생성
# api.ecoeco.app → ${ALB_DNS}
```

**7.2 DNS 전파 확인**
```bash
dig api.ecoeco.app
nslookup api.ecoeco.app
```

---

### Step 8: 배포 검증

**8.1 Health Check**
```bash
# 각 API Health Check
curl -k https://api.ecoeco.app/api/v1/waste/health
curl -k https://api.ecoeco.app/api/v1/auth/health
curl -k https://api.ecoeco.app/api/v1/users/health
curl -k https://api.ecoeco.app/api/v1/locations/health
curl -k https://api.ecoeco.app/api/v1/recycle/health
curl -k https://api.ecoeco.app/api/v1/chat/health
```

**8.2 Pod 상태 확인**
```bash
# API Pods
kubectl get pods -n api -o wide

# Worker Pods
kubectl get pods -n workers -o wide

# 각 Pod가 올바른 노드에 배치되었는지 확인
kubectl get pods -n api -o custom-columns=NAME:.metadata.name,NODE:.spec.nodeName
```

**8.3 리소스 사용량 확인**
```bash
# 노드별 리소스 사용량
kubectl top nodes

# Pod별 리소스 사용량
kubectl top pods -n api
kubectl top pods -n workers
```

**8.4 로그 확인**
```bash
# Waste API 로그
kubectl logs -n api -l app=waste-api --tail=50

# ALB Controller 로그
kubectl logs -n kube-system -l app.kubernetes.io/name=aws-load-balancer-controller --tail=100
```

---

## 🛠️ 트러블슈팅

### 문제 1: Pod가 Pending 상태
```bash
kubectl describe pod -n api <POD_NAME>

# 가능한 원인:
# 1. NodeSelector 불일치 → 노드 라벨 확인
# 2. 리소스 부족 → kubectl top nodes
# 3. Image Pull 실패 → 이미지 존재 확인
```

### 문제 2: ALB가 생성되지 않음
```bash
kubectl logs -n kube-system -l app.kubernetes.io/name=aws-load-balancer-controller

# 가능한 원인:
# 1. IAM 권한 부족 → iam.tf 확인
# 2. Subnet 태그 누락 → VPC Subnet 태그 확인
# 3. IngressClass 불일치 → ingressClassName: alb
```

### 문제 3: Health Check 실패
```bash
# Pod 내부에서 Health Check
kubectl exec -n api -it <POD_NAME> -- curl localhost:8000/health

# 가능한 원인:
# 1. /health 엔드포인트 미구현
# 2. 포트 불일치
# 3. 서비스 시작 실패 → 로그 확인
```

### 문제 4: ArgoCD Sync 실패
```bash
argocd app get ecoeco-backend-13nodes

# 가능한 원인:
# 1. Helm Template 오류 → helm template 로컬 테스트
# 2. Repository 접근 실패 → argocd repo list
# 3. Namespace 미생성 → kubectl get ns
```

---

## 📊 모니터링 설정

### Prometheus & Grafana 배포

**1. Helm으로 Prometheus Stack 설치**
```bash
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm repo update

helm install prometheus prometheus-community/kube-prometheus-stack \
  -n monitoring --create-namespace \
  --set prometheus.prometheusSpec.serviceMonitorSelectorNilUsesHelmValues=false \
  --set prometheus.prometheusSpec.podMonitorSelectorNilUsesHelmValues=false
```

**2. Grafana 접속**
```bash
kubectl port-forward -n monitoring svc/prometheus-grafana 3000:80

# 브라우저에서 http://localhost:3000
# ID: admin
# PW: prom-operator
```

**3. 대시보드 Import**
- Kubernetes Cluster (ID: 7249)
- Node Exporter (ID: 1860)
- Pod Metrics (ID: 6417)

---

## 🔐 보안 강화

### 1. Network Policies
```yaml
# network-policy.yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: api-network-policy
  namespace: api
spec:
  podSelector: {}
  policyTypes:
    - Ingress
  ingress:
    - from:
        - namespaceSelector:
            matchLabels:
              name: kube-system
      ports:
        - protocol: TCP
          port: 8000
```

### 2. Pod Security Policy
```yaml
apiVersion: policy/v1beta1
kind: PodSecurityPolicy
metadata:
  name: restricted
spec:
  privileged: false
  allowPrivilegeEscalation: false
  requiredDropCapabilities:
    - ALL
  runAsUser:
    rule: MustRunAsNonRoot
```

### 3. Resource Quotas
```yaml
apiVersion: v1
kind: ResourceQuota
metadata:
  name: api-quota
  namespace: api
spec:
  hard:
    requests.cpu: "10"
    requests.memory: 20Gi
    limits.cpu: "20"
    limits.memory: 40Gi
```

---

## ✅ 최종 체크리스트

- [ ] Terraform Apply 완료 (13 nodes)
- [ ] Ansible Playbook 실행 완료
- [ ] kubectl get nodes → 13 nodes Ready
- [ ] 노드 라벨 확인 (service=waste, auth, ...)
- [ ] ALB Ingress Controller 설치
- [ ] ArgoCD 설치 및 설정
- [ ] GitHub Repository 연동
- [ ] Application Sync 성공
- [ ] 모든 Pod가 Running 상태
- [ ] ALB가 생성되고 Target이 Healthy
- [ ] ACM 인증서 연결
- [ ] Route53 DNS 설정
- [ ] HTTPS Health Check 성공 (6개 API)
- [ ] Prometheus & Grafana 설치
- [ ] 보안 정책 적용 (Network Policy, PSP, Quotas)

---

## 📞 문의 및 지원

**문제 발생 시**:
1. 로그 확인 (`kubectl logs`)
2. 이벤트 확인 (`kubectl get events`)
3. ArgoCD UI 확인
4. 이 문서의 트러블슈팅 섹션 참고

**다음 단계**:
- CI/CD 파이프라인 테스트
- 부하 테스트 (Locust, k6)
- Canary 배포 전략 적용 (Argo Rollouts)
- Monitoring 대시보드 커스터마이징

---

**작성자**: AI Assistant  
**최종 업데이트**: 2025-11-06  
**버전**: 1.0.0

