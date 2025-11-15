# Ansible 작업 완전 분류 (대안 여부 기준)

**작성일**: 2025-11-14  
**브랜치**: `refactor/operator-ansible-minimal`  
**목적**: Ansible 의존성 최소화를 위한 작업별 대안 식별

---

## 📋 분류 기준

- **✅ 대안 있음**: Terraform, ArgoCD, Helm 등으로 대체 가능
- **❌ 대안 없음**: Operator 또는 Ansible 유지 필요
- **🗑️ 제거 가능**: 실제로 사용하지 않는 작업
- **⚡ 우선순위**: 높음(필수), 중간, 낮음(선택)

---

## 📊 전체 요약

| 카테고리 | 대안 있음 | 대안 없음 | 제거 가능 | 합계 |
|---------|-----------|-----------|-----------|------|
| OS 레벨 설정 | 3 | 0 | 0 | 3 |
| 클러스터 초기화 | 2 | 1 | 0 | 3 |
| CNI/네트워크 | 1 | 0 | 0 | 1 |
| K8s Add-ons | 3 | 0 | 1 | 4 |
| GitOps 도구 | 2 | 0 | 0 | 2 |
| 데이터베이스 | 4 | 0 | 0 | 4 |
| K8s 리소스 | 3 | 0 | 0 | 3 |
| 노드 관리 | 0 | 3 | 0 | 3 |
| 기타 | 2 | 0 | 0 | 2 |
| **합계** | **20** | **4** | **1** | **25** |

---

## 🎯 핵심 결론

### Operator가 필요한 작업 (3가지만)

1. **Node Labels** - EC2 태그 → K8s Label 자동 매핑
2. **Node Taints** - Workload별 자동 Taint 설정  
3. **Provider ID 패치** - ALB Controller를 위한 kubectl patch

### 제거 가능 (1가지)

1. **Cert-Manager** - 설치만 되고 실제 사용 안함 (ACM 사용 중)

---

## 📋 Category 1: OS 레벨 설정

### 1.1 Prerequisites - OS 설정 (common role)

**작업 내용**:
- 시스템 업데이트 (`apt update && apt upgrade`)
- Swap 비활성화
- 커널 모듈 로드 (overlay, br_netfilter)
- sysctl 네트워크 설정
- CNI 디렉토리 생성

**현재 코드 위치**: `ansible/roles/common/tasks/main.yml` (108줄)

**대안**: ✅ **Terraform user-data**

```bash
#!/bin/bash
# terraform/user-data/os-setup.sh

# 시스템 업데이트
apt-get update && apt-get upgrade -y

# Swap 비활성화
swapoff -a
sed -i '/ swap / s/^/#/' /etc/fstab

# 커널 모듈
cat <<EOF > /etc/modules-load.d/k8s.conf
overlay
br_netfilter
EOF
modprobe overlay
modprobe br_netfilter

# sysctl 설정
cat <<EOF > /etc/sysctl.d/99-kubernetes.conf
net.bridge.bridge-nf-call-iptables = 1
net.ipv4.ip_forward = 1
EOF
sysctl --system

# CNI 디렉토리
mkdir -p /etc/cni/net.d /var/lib/cni /opt/cni/bin
```

**구현 방법**:
```hcl
# terraform/modules/ec2/main.tf
resource "aws_instance" "node" {
  user_data = file("${path.module}/../../user-data/os-setup.sh")
  # ...
}
```

**결론**: ✅ **Terraform user-data로 이관**  
**우선순위**: 높음 (필수)  
**예상 작업 시간**: 1시간

---

### 1.2 Docker/containerd 설치 (docker role)

**작업 내용**:
- Docker GPG 키 추가
- Docker repository 추가
- Docker, containerd 설치
- containerd 설정 (SystemdCgroup, CRI 활성화)

**현재 코드 위치**: `ansible/roles/docker/tasks/main.yml` (102줄)

**대안**: ✅ **Terraform user-data**

```bash
#!/bin/bash
# Docker 설치 (공식 스크립트)
curl -fsSL https://get.docker.com | sh

# containerd 설정
mkdir -p /etc/containerd
containerd config default > /etc/containerd/config.toml

# SystemdCgroup 활성화 (Kubernetes 필수)
sed -i 's/SystemdCgroup = false/SystemdCgroup = true/g' /etc/containerd/config.toml

# CRI 활성화
sed -i 's/^disabled_plugins = \["cri"\]/#disabled_plugins = ["cri"]/g' /etc/containerd/config.toml

# pause 이미지 버전 설정
sed -i 's|sandbox_image = .*|sandbox_image = "registry.k8s.io/pause:3.9"|g' /etc/containerd/config.toml

# containerd 재시작
systemctl restart containerd
systemctl enable containerd

# crictl 설정
cat <<EOF > /etc/crictl.yaml
runtime-endpoint: unix:///run/containerd/containerd.sock
image-endpoint: unix:///run/containerd/containerd.sock
timeout: 10
EOF
```

**결론**: ✅ **Terraform user-data로 이관**  
**우선순위**: 높음 (필수)  
**예상 작업 시간**: 1시간

---

### 1.3 Kubernetes 패키지 설치 (kubernetes role)

**작업 내용**:
- K8s APT 키 추가
- K8s repository 추가
- kubelet, kubeadm, kubectl 설치 (v1.28.*)
- 패키지 hold (자동 업그레이드 방지)

**현재 코드 위치**: `ansible/roles/kubernetes/tasks/main.yml` (60줄)

**대안**: ✅ **Terraform user-data**

```bash
#!/bin/bash
# Kubernetes APT 키
mkdir -p /etc/apt/keyrings
curl -fsSL https://pkgs.k8s.io/core:/stable:/v1.28/deb/Release.key | \
  gpg --dearmor -o /etc/apt/keyrings/kubernetes-apt-keyring.gpg

# Kubernetes repository
echo "deb [signed-by=/etc/apt/keyrings/kubernetes-apt-keyring.gpg] https://pkgs.k8s.io/core:/stable:/v1.28/deb/ /" | \
  tee /etc/apt/sources.list.d/kubernetes.list

# 패키지 설치
apt-get update
apt-get install -y kubelet=1.28.* kubeadm=1.28.* kubectl=1.28.*

# 자동 업그레이드 방지
apt-mark hold kubelet kubeadm kubectl

# kubelet 활성화
systemctl enable kubelet
```

**결론**: ✅ **Terraform user-data로 이관**  
**우선순위**: 높음 (필수)  
**예상 작업 시간**: 30분

---

## 📋 Category 2: 클러스터 초기화 (핵심)

### 2.1 Master 초기화 (kubeadm init)

**작업 내용**:
```bash
kubeadm init \
  --apiserver-advertise-address=<PRIVATE_IP> \
  --pod-network-cidr=10.244.0.0/16 \
  --cri-socket=unix:///run/containerd/containerd.sock
```

**현재 코드 위치**: `ansible/playbooks/02-master-init.yml`

**대안 검토**:
- ❌ Operator: 클러스터 외부 작업이라 불가능
- ⚠️ Terraform user-data: 가능하지만 kubeconfig 추출 문제
- ✅ **Terraform null_resource + remote-exec**: SSH로 실행 후 kubeconfig 가져오기

**추천 방법**: ✅ **Terraform null_resource + SSM**

```hcl
# terraform/master-init.tf
resource "null_resource" "master_init" {
  depends_on = [aws_instance.master]
  
  connection {
    type        = "ssh"
    user        = "ubuntu"
    private_key = file("~/.ssh/sesacthon.pem")
    host        = aws_eip.master.public_ip
  }
  
  provisioner "remote-exec" {
    inline = [
      # OS 준비 완료 대기
      "while [ ! -f /var/lib/cloud/instance/boot-finished ]; do sleep 5; done",
      
      # kubeadm init
      "sudo kubeadm init --apiserver-advertise-address=${aws_instance.master.private_ip} --pod-network-cidr=10.244.0.0/16",
      
      # kubeconfig 설정
      "mkdir -p $HOME/.kube",
      "sudo cp /etc/kubernetes/admin.conf $HOME/.kube/config",
      "sudo chown $(id -u):$(id -g) $HOME/.kube/config",
      
      # Join token을 SSM에 저장
      "JOIN_CMD=$(kubeadm token create --print-join-command)",
      "aws ssm put-parameter --name '/k8s/cluster/sesacthon/join-command' --value \"$JOIN_CMD\" --type SecureString --overwrite --region ap-northeast-2"
    ]
  }
}
```

**대안**: ⚠️ **Terraform user-data도 가능** (SSM 활용)

```bash
#!/bin/bash
# Master node만 실행
if [ "$(hostname)" == "k8s-master" ]; then
  # kubeadm init
  kubeadm init --apiserver-advertise-address=$(hostname -I | awk '{print $1}') --pod-network-cidr=10.244.0.0/16
  
  # kubeconfig
  mkdir -p /home/ubuntu/.kube
  cp /etc/kubernetes/admin.conf /home/ubuntu/.kube/config
  chown ubuntu:ubuntu /home/ubuntu/.kube/config
  
  # Join token → SSM
  JOIN_CMD=$(kubeadm token create --print-join-command)
  aws ssm put-parameter \
    --name "/k8s/cluster/sesacthon/join-command" \
    --value "$JOIN_CMD" \
    --type "SecureString" \
    --overwrite \
    --region ap-northeast-2
fi
```

**결론**: ✅ **Terraform null_resource (안정적) 또는 user-data (단순)**  
**우선순위**: 높음 (필수)  
**예상 작업 시간**: 2시간

---

### 2.2 Worker 노드 Join (kubeadm join)

**작업 내용**:
```bash
# Master에서 생성한 join 명령 실행
kubeadm join <master-ip>:6443 --token <token> --discovery-token-ca-cert-hash sha256:<hash>
```

**현재 코드 위치**: `ansible/playbooks/03-worker-join.yml`

**대안**: ✅ **Terraform user-data + SSM Parameter Store**

```bash
#!/bin/bash
# Worker nodes만 실행

# SSM에서 join 명령 가져오기 (Master가 저장한 것)
JOIN_CMD=$(aws ssm get-parameter \
  --name "/k8s/cluster/sesacthon/join-command" \
  --region ap-northeast-2 \
  --with-decryption \
  --query 'Parameter.Value' \
  --output text)

# Join 실행 (최대 5회 재시도)
for i in 1 2 3 4 5; do
  if eval "$JOIN_CMD --cri-socket unix:///run/containerd/containerd.sock"; then
    echo "Successfully joined cluster"
    
    # Join 완료 신호 (선택사항)
    aws ssm put-parameter \
      --name "/k8s/nodes/$(hostname)/status" \
      --value "joined:$(date -Iseconds)" \
      --type "String" \
      --region ap-northeast-2 \
      --overwrite
    
    exit 0
  fi
  
  echo "Join attempt $i failed, retrying in 30s..."
  sleep 30
done

echo "Failed to join cluster after 5 attempts"
exit 1
```

**결론**: ✅ **Terraform user-data + SSM**  
**우선순위**: 높음 (필수)  
**예상 작업 시간**: 2시간

---

### 2.3 Provider ID 설정 (kubectl patch)

**작업 내용**:
```bash
# Worker 노드 자체 설정
INSTANCE_ID=$(ec2-metadata --instance-id | cut -d ' ' -f 2)
AZ=$(ec2-metadata --availability-zone | cut -d ' ' -f 2)
# kubelet extra args에 --provider-id 설정

# Master에서 kubectl patch (더 안정적)
kubectl patch node <node-name> \
  -p '{"spec":{"providerID":"aws:///<AZ>/<INSTANCE_ID>"}}'
```

**현재 코드 위치**: 
- `ansible/playbooks/03-worker-join.yml` (Worker 노드 자체 설정)
- `ansible/playbooks/03-1-set-provider-id.yml` (Master에서 patch)

**대안 분석**:
1. **Worker 노드 자체 설정**: ✅ user-data 가능
2. **kubectl patch**: ❌ **Operator 필요** (RBAC 제한)

**결론**: ⚠️ **user-data (기본) + Operator (패치)**

```bash
# user-data에서 기본 설정 (Worker 노드)
INSTANCE_ID=$(ec2-metadata --instance-id | cut -d ' ' -f 2)
AZ=$(ec2-metadata --availability-zone | cut -d ' ' -f 2)

# kubelet에 미리 설정
cat <<EOF > /etc/default/kubelet
KUBELET_EXTRA_ARGS="--cloud-provider=external --provider-id=aws:///$AZ/$INSTANCE_ID"
EOF

systemctl restart kubelet
```

```python
# Operator가 검증 및 수정
@kopf.on.create('v1', 'nodes')
def verify_provider_id(spec, name, **kwargs):
    provider_id = spec.get('providerID')
    
    # Provider ID 없으면 수정
    if not provider_id or not provider_id.startswith('aws:///'):
        ec2_info = get_ec2_instance_info(name)
        correct_provider_id = f"aws:///{ec2_info['az']}/{ec2_info['instance_id']}"
        
        patch_node_provider_id(name, correct_provider_id)
```

**우선순위**: 높음 (ALB Controller 필수)  
**예상 작업 시간**: 
- user-data: 30분
- Operator: 1시간

---

## 📋 Category 3: CNI 및 네트워크

### 3.1 CNI 설치 (Calico/VPC-CNI)

**작업 내용**:
```bash
kubectl apply -f https://raw.githubusercontent.com/projectcalico/calico/v3.26.1/manifests/calico.yaml
# 또는
kubectl apply -f https://raw.githubusercontent.com/aws/amazon-vpc-cni-k8s/release-1.12/config/master/aws-k8s-cni.yaml
```

**현재 코드 위치**: 
- `ansible/playbooks/04-cni-install.yml` (Calico)
- `ansible/playbooks/04-cni-install-vpc.yml` (VPC-CNI)

**대안**: ✅ **ArgoCD + Helm**

```yaml
# argocd/apps/cni.yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: aws-vpc-cni
  namespace: argocd
spec:
  project: default
  source:
    repoURL: https://aws.github.io/eks-charts
    chart: aws-vpc-cni
    targetRevision: v1.12.0
    helm:
      values: |
        env:
          AWS_VPC_K8S_CNI_EXTERNALSNAT: true
  destination:
    server: https://kubernetes.default.svc
    namespace: kube-system
  syncPolicy:
    automated:
      prune: true
      selfHeal: true
```

**Calico 대안**:
```yaml
# argocd/apps/calico.yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: calico
  namespace: argocd
spec:
  source:
    repoURL: https://docs.tigera.io/calico/charts
    chart: tigera-operator
    targetRevision: v3.26.1
```

**결론**: ✅ **ArgoCD + Helm로 이관**  
**우선순위**: 높음 (CNI 없으면 Pod 통신 불가)  
**예상 작업 시간**: 1시간

---

## 📋 Category 4: Kubernetes Add-ons

### 4.1 ~~Cert-Manager~~ (제거)

**작업 내용**:
```bash
kubectl apply -f https://github.com/cert-manager/cert-manager/releases/download/v1.13.0/cert-manager.yaml
```

**현재 코드 위치**: 
- `ansible/playbooks/05-addons.yml` (설치)
- `ansible/playbooks/06-cert-manager-issuer.yml` (설정 - 실제로 비어있음)

**현재 상태**: 🗑️ **설치만 되고 실제 사용 안함**

```yaml
# ansible/playbooks/06-cert-manager-issuer.yml (63-72줄)
# ⚠️ Let's Encrypt ClusterIssuer 제거
# 이유: ALB에서 AWS ACM 인증서를 사용하므로 불필요
# Cert-manager는 Kubernetes 내부 인증서 관리용으로만 유지
```

**ACM 사용 확인**: ✅ Terraform에서 완전 관리

```hcl
# terraform/acm.tf
resource "aws_acm_certificate" "main" {
  domain_name               = var.domain_name
  subject_alternative_names = ["*.${var.domain_name}"]
  validation_method         = "DNS"
}

# ALB에서 사용
# terraform/alb.tf (또는 ALB Controller가 자동 연결)
```

**결론**: 🗑️ **제거 (사용 안함)**  
**우선순위**: N/A  
**작업**: Ansible에서 해당 playbook 제거

---

### 4.2 Metrics Server

**작업 내용**:
```bash
kubectl apply -f https://github.com/kubernetes-sigs/metrics-server/releases/latest/download/components.yaml
kubectl patch deployment metrics-server -n kube-system --type='json' \
  -p='[{"op": "add", "path": "/spec/template/spec/containers/0/args/-", "value": "--kubelet-insecure-tls"}]'
```

**현재 코드 위치**: `ansible/playbooks/05-addons.yml`

**대안**: ✅ **ArgoCD + Helm**

```yaml
# argocd/apps/metrics-server.yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: metrics-server
  namespace: argocd
spec:
  source:
    repoURL: https://kubernetes-sigs.github.io/metrics-server
    chart: metrics-server
    targetRevision: 3.11.0
    helm:
      values: |
        args:
          - --kubelet-insecure-tls
  destination:
    server: https://kubernetes.default.svc
    namespace: kube-system
  syncPolicy:
    automated:
      prune: true
      selfHeal: true
```

**결론**: ✅ **ArgoCD + Helm로 이관**  
**우선순위**: 중간 (HPA 필요 시 필수)  
**예상 작업 시간**: 30분

---

### 4.3 EBS CSI Driver

**작업 내용**:
```bash
kubectl apply -k "github.com/kubernetes-sigs/aws-ebs-csi-driver/deploy/kubernetes/overlays/stable/?ref=release-1.24"
```

**현재 코드 위치**: `ansible/playbooks/05-1-ebs-csi-driver.yml`

**대안**: ✅ **ArgoCD + Helm**

```yaml
# argocd/apps/ebs-csi-driver.yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: aws-ebs-csi-driver
  namespace: argocd
spec:
  source:
    repoURL: https://kubernetes-sigs.github.io/aws-ebs-csi-driver
    chart: aws-ebs-csi-driver
    targetRevision: 2.24.0
    helm:
      values: |
        enableVolumeScheduling: true
        enableVolumeResizing: true
        enableVolumeSnapshot: true
  destination:
    server: https://kubernetes.default.svc
    namespace: kube-system
  syncPolicy:
    automated:
      prune: true
      selfHeal: true
```

**결론**: ✅ **ArgoCD + Helm로 이관**  
**우선순위**: 높음 (PersistentVolume 필수)  
**예상 작업 시간**: 1시간

---

### 4.4 AWS Load Balancer Controller

**작업 내용**:
```bash
helm install aws-load-balancer-controller eks/aws-load-balancer-controller \
  -n kube-system \
  --set clusterName=k8s-sesacthon \
  --set serviceAccount.create=true
```

**현재 코드 위치**: `ansible/playbooks/07-alb-controller.yml`

**대안**: ✅ **ArgoCD + Helm**

```yaml
# argocd/apps/alb-controller.yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: aws-load-balancer-controller
  namespace: argocd
spec:
  source:
    repoURL: https://aws.github.io/eks-charts
    chart: aws-load-balancer-controller
    targetRevision: 1.6.0
    helm:
      values: |
        clusterName: k8s-sesacthon
        serviceAccount:
          create: true
          name: aws-load-balancer-controller
          annotations:
            eks.amazonaws.com/role-arn: arn:aws:iam::ACCOUNT_ID:role/AWSLoadBalancerControllerRole
  destination:
    server: https://kubernetes.default.svc
    namespace: kube-system
  syncPolicy:
    automated:
      prune: true
      selfHeal: true
```

**결론**: ✅ **ArgoCD + Helm로 이관**  
**우선순위**: 높음 (Ingress 필수)  
**예상 작업 시간**: 1시간

---

## 📋 Category 5: GitOps 도구

### 5.1 ArgoCD 설치

**작업 내용**:
```bash
kubectl create namespace argocd
kubectl apply -n argocd -f https://raw.githubusercontent.com/argoproj/argo-cd/stable/manifests/install.yaml
```

**현재 코드 위치**: `ansible/roles/argocd/tasks/main.yml`

**대안 검토**: ⚠️ **Chicken-Egg 문제**
- ArgoCD로 ArgoCD 자체를 설치할 수 없음

**가능한 옵션**:
1. ✅ **Terraform null_resource + Helm** (추천)
2. ✅ **Terraform null_resource + kubectl**
3. ⚠️ Ansible 유지 (최소한의 Ansible 역할)

**추천 방법**: ✅ **Terraform null_resource + Helm**

```hcl
# terraform/argocd.tf
resource "null_resource" "argocd_install" {
  depends_on = [null_resource.master_init]
  
  connection {
    type        = "ssh"
    user        = "ubuntu"
    private_key = file("~/.ssh/sesacthon.pem")
    host        = aws_eip.master.public_ip
  }
  
  provisioner "remote-exec" {
    inline = [
      # Helm 설치
      "curl https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3 | bash",
      
      # ArgoCD 설치
      "helm repo add argo https://argoproj.github.io/argo-helm",
      "helm repo update",
      "helm install argocd argo/argo-cd -n argocd --create-namespace --version 5.51.0",
      
      # 설치 완료 대기
      "kubectl wait --for=condition=available --timeout=300s deployment/argocd-server -n argocd"
    ]
  }
}
```

**결론**: ✅ **Terraform null_resource + Helm**  
**우선순위**: 높음 (필수)  
**예상 작업 시간**: 2시간

---

### 5.2 Atlantis 설치

**작업 내용**:
```yaml
kubectl apply -f atlantis-deployment.yaml
```

**현재 코드 위치**: `ansible/playbooks/09-atlantis.yml`

**대안**: ✅ **ArgoCD + Helm**

```yaml
# argocd/apps/atlantis.yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: atlantis
  namespace: argocd
spec:
  source:
    repoURL: https://runatlantis.github.io/helm-charts
    chart: atlantis
    targetRevision: 4.17.0
    helm:
      values: |
        orgWhitelist: github.com/your-org/*
        github:
          user: atlantis-bot
          token: <secret>
          secret: <webhook-secret>
  destination:
    server: https://kubernetes.default.svc
    namespace: atlantis
  syncPolicy:
    automated:
      prune: true
      selfHeal: true
```

**결론**: ✅ **ArgoCD + Helm로 이관**  
**우선순위**: 중간 (Terraform GitOps)  
**예상 작업 시간**: 1시간

---

## 📋 Category 6: 애플리케이션 데이터베이스

### 6.1 PostgreSQL 설치

**작업 내용**:
```yaml
helm install postgresql bitnami/postgresql
```

**현재 코드 위치**: `ansible/roles/postgresql/tasks/main.yml`

**대안**: ✅ **ArgoCD + Helm (Bitnami)**

```yaml
# argocd/apps/postgresql.yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: postgresql
  namespace: argocd
spec:
  source:
    repoURL: https://charts.bitnami.com/bitnami
    chart: postgresql
    targetRevision: 12.12.0
    helm:
      values: |
        auth:
          username: sesacthon
          password: <secret>
          database: sesacthon_db
        primary:
          persistence:
            size: 20Gi
            storageClass: gp3
  destination:
    server: https://kubernetes.default.svc
    namespace: database
  syncPolicy:
    automated:
      prune: true
      selfHeal: true
```

**결론**: ✅ **ArgoCD + Helm로 이관**  
**우선순위**: 높음 (애플리케이션 필수)  
**예상 작업 시간**: 1시간

---

### 6.2 Redis 설치

**대안**: ✅ **ArgoCD + Helm (Bitnami)**

```yaml
# argocd/apps/redis.yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: redis
  namespace: argocd
spec:
  source:
    repoURL: https://charts.bitnami.com/bitnami
    chart: redis
    targetRevision: 18.0.0
```

**결론**: ✅ **ArgoCD + Helm로 이관**  
**우선순위**: 높음  
**예상 작업 시간**: 1시간

---

### 6.3 RabbitMQ 설치

**대안**: ✅ **ArgoCD + Helm (Bitnami)**

```yaml
# argocd/apps/rabbitmq.yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: rabbitmq
  namespace: argocd
spec:
  source:
    repoURL: https://charts.bitnami.com/bitnami
    chart: rabbitmq
    targetRevision: 12.0.0
```

**결론**: ✅ **ArgoCD + Helm로 이관**  
**우선순위**: 높음  
**예상 작업 시간**: 1시간

---

### 6.4 Monitoring (Prometheus Operator)

**작업 내용**:
```bash
helm install kube-prometheus-stack prometheus-community/kube-prometheus-stack
```

**현재 코드 위치**: `ansible/playbooks/08-monitoring.yml`

**대안**: ✅ **ArgoCD + Helm**

```yaml
# argocd/apps/monitoring.yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: kube-prometheus-stack
  namespace: argocd
spec:
  source:
    repoURL: https://prometheus-community.github.io/helm-charts
    chart: kube-prometheus-stack
    targetRevision: 51.0.0
    helm:
      values: |
        grafana:
          enabled: true
          adminPassword: <secret>
        prometheus:
          prometheusSpec:
            retention: 15d
            storageSpec:
              volumeClaimTemplate:
                spec:
                  storageClassName: gp3
                  resources:
                    requests:
                      storage: 50Gi
  destination:
    server: https://kubernetes.default.svc
    namespace: monitoring
  syncPolicy:
    automated:
      prune: true
      selfHeal: true
```

**결론**: ✅ **ArgoCD + Helm로 이관**  
**우선순위**: 중간 (모니터링)  
**예상 작업 시간**: 2시간

---

## 📋 Category 7: Kubernetes 리소스

### 7.1 Namespaces

**작업 내용**:
```bash
kubectl apply -f namespaces.yaml
```

**현재 코드 위치**: `ansible/playbooks/10-namespaces.yml`

**현재 상태**: ✅ **이미 ArgoCD로 관리 중**
- `k8s/namespaces/domain-based.yaml` 존재
- `k8s/foundations/namespaces/domain-based.yaml` 존재

**결론**: ✅ **이미 완료** (Ansible 제거만 필요)  
**우선순위**: 높음  
**예상 작업 시간**: 10분 (Ansible playbook 제거)

---

### 7.2 Ingress 리소스

**현재 상태**: ✅ **이미 ArgoCD로 관리 중**
- `k8s/ingress/` 디렉토리 존재

**결론**: ✅ **이미 완료**  
**우선순위**: 높음  
**예상 작업 시간**: 0분

---

### 7.3 IngressClass

**작업 내용**:
```yaml
apiVersion: networking.k8s.io/v1
kind: IngressClass
metadata:
  name: alb
spec:
  controller: ingress.k8s.aws/alb
```

**현재 코드 위치**: `ansible/playbooks/07-1-ingress-class.yml`

**대안**: ✅ **ArgoCD** (Kubernetes 리소스)

```yaml
# k8s/infrastructure/ingress-class.yaml
apiVersion: networking.k8s.io/v1
kind: IngressClass
metadata:
  name: alb
  annotations:
    ingressclass.kubernetes.io/is-default-class: "true"
spec:
  controller: ingress.k8s.aws/alb
```

**결론**: ✅ **ArgoCD로 이관** (k8s/infrastructure/)  
**우선순위**: 높음  
**예상 작업 시간**: 30분

---

## 📋 Category 8: 노드 관리 ⚠️ (Operator 필수)

### 8.1 Node Labels

**작업 내용**:
```bash
kubectl label nodes k8s-api-auth workload=api domain=auth phase=1
```

**현재 코드 위치**: `ansible/playbooks/label-nodes.yml`

**대안 검토**:
- ❌ Terraform: 클러스터 외부라 불가능
- ❌ user-data: 노드가 자기 자신에게 label 불가 (RBAC 제한)
- ❌ ArgoCD: Node 리소스 관리 불가 (보안상 제한)
- ✅ **Operator 필요**

**이유**:
1. EC2 태그 → K8s Label 자동 매핑 필요
2. 노드는 자기 자신을 수정할 RBAC 권한 없음
3. 동적으로 새 노드가 추가될 때 자동 Label 필요

**Operator 구현**:

```python
@kopf.on.create('v1', 'nodes')
def apply_labels_from_ec2_tags(spec, name, **kwargs):
    """EC2 태그를 Kubernetes Label로 자동 매핑"""
    
    # EC2 태그 가져오기
    ec2_tags = get_ec2_tags_by_node_name(name)
    
    # K8s Label로 변환
    labels = {
        'workload': ec2_tags.get('Workload', 'unknown'),
        'domain': ec2_tags.get('Domain', 'unknown'),
        'phase': ec2_tags.get('Phase', 'unknown'),
        'topology.kubernetes.io/zone': ec2_tags.get('AZ', 'unknown')
    }
    
    # Node에 Label 적용
    patch_node_labels(name, labels)
    
    logger.info(f"Applied labels to node {name}: {labels}")
```

**결론**: ❌ **Operator 필수**  
**우선순위**: 높음 (NodeAffinity, Pod 스케줄링에 필수)  
**예상 작업 시간**: 2시간

---

### 8.2 Node Taints

**작업 내용**:
```bash
kubectl taint nodes k8s-postgresql workload=database:NoSchedule
```

**대안**: ❌ **Operator 필요**

**이유**:
- 특정 Workload에만 Pod 배치하기 위해 Taint 필요
- EC2 태그 기반으로 자동 Taint 설정

**Operator 구현**:

```python
@kopf.on.create('v1', 'nodes')
def apply_taints_by_workload(spec, name, **kwargs):
    """Workload별 자동 Taint 설정"""
    
    # EC2 태그에서 Workload 확인
    ec2_tags = get_ec2_tags_by_node_name(name)
    workload = ec2_tags.get('Workload')
    
    # Workload별 Taint 규칙
    taint_rules = {
        'database': [
            {'key': 'workload', 'value': 'database', 'effect': 'NoSchedule'}
        ],
        'monitoring': [
            {'key': 'workload', 'value': 'monitoring', 'effect': 'NoSchedule'}
        ]
    }
    
    if workload in taint_rules:
        taints = taint_rules[workload]
        patch_node_taints(name, taints)
        logger.info(f"Applied taints to node {name}: {taints}")
```

**결론**: ❌ **Operator 필수**  
**우선순위**: 중간 (일반 API는 불필요, DB만 격리)  
**예상 작업 시간**: 1시간

---

### 8.3 Provider ID 패치 (kubectl patch)

**작업 내용**:
```bash
kubectl patch node <node-name> \
  -p '{"spec":{"providerID":"aws:///<AZ>/<INSTANCE_ID>"}}'
```

**현재 코드 위치**: `ansible/playbooks/03-1-set-provider-id.yml`

**대안 분석**:
1. **Worker 노드 자체 설정 (user-data)**: ✅ 가능
   ```bash
   # kubelet에 미리 설정
   KUBELET_EXTRA_ARGS="--provider-id=aws:///$AZ/$INSTANCE_ID"
   ```

2. **kubectl patch (Master에서)**: ❌ Operator 필요
   - user-data가 실패했을 때 Fallback
   - 검증 및 자동 수정

**Operator 역할**: 검증 + 수정

```python
@kopf.on.create('v1', 'nodes')
def verify_and_fix_provider_id(spec, name, **kwargs):
    """Provider ID 검증 및 자동 수정"""
    
    provider_id = spec.get('providerID')
    
    # Provider ID가 없거나 잘못된 경우
    if not provider_id or not provider_id.startswith('aws:///'):
        logger.warning(f"Node {name} has invalid Provider ID: {provider_id}")
        
        # EC2 메타데이터에서 올바른 값 가져오기
        ec2_info = get_ec2_instance_info_by_node_name(name)
        correct_provider_id = f"aws:///{ec2_info['az']}/{ec2_info['instance_id']}"
        
        # Node 패치
        patch_node_provider_id(name, correct_provider_id)
        logger.info(f"Fixed Provider ID for node {name}: {correct_provider_id}")
```

**결론**: ⚠️ **user-data (기본) + Operator (검증/수정)**  
**우선순위**: 높음 (ALB Controller 필수)  
**예상 작업 시간**: 
- user-data: 30분
- Operator: 1시간

---

## 📋 Category 9: 기타

### 9.1 etcd 백업 설정

**작업 내용**:
```bash
# CronJob으로 etcd 백업
0 2 * * * /usr/local/bin/backup-etcd.sh
```

**현재 코드 위치**: `ansible/playbooks/09-etcd-backup.yml`

**대안**: ✅ **ArgoCD (CronJob 리소스)**

```yaml
# k8s/infrastructure/etcd-backup-cronjob.yaml
apiVersion: batch/v1
kind: CronJob
metadata:
  name: etcd-backup
  namespace: kube-system
spec:
  schedule: "0 2 * * *"  # 매일 새벽 2시
  jobTemplate:
    spec:
      template:
        spec:
          containers:
          - name: etcd-backup
            image: bitnami/etcd:3.5
            command:
            - /bin/sh
            - -c
            - |
              ETCDCTL_API=3 etcdctl snapshot save /backup/etcd-$(date +%Y%m%d).db \
                --endpoints=https://127.0.0.1:2379 \
                --cacert=/etc/kubernetes/pki/etcd/ca.crt \
                --cert=/etc/kubernetes/pki/etcd/server.crt \
                --key=/etc/kubernetes/pki/etcd/server.key
              
              # S3에 업로드
              aws s3 cp /backup/etcd-$(date +%Y%m%d).db s3://sesacthon-backups/etcd/
          restartPolicy: OnFailure
```

**결론**: ✅ **ArgoCD (CronJob)로 이관**  
**우선순위**: 낮음 (운영 안정화 후)  
**예상 작업 시간**: 1시간

---

### 9.2 Route53 업데이트

**작업 내용**:
```bash
# ALB DNS를 Route53 A 레코드로 등록
aws route53 change-resource-record-sets ...
```

**현재 코드 위치**: `ansible/playbooks/09-route53-update.yml`

**대안**: ✅ **Terraform** (이미 관리 중)

**확인**: `terraform/route53.tf` 파일 존재 여부 확인 필요

**대안 2**: ✅ **External-DNS** (K8s Operator)

```yaml
# argocd/apps/external-dns.yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: external-dns
  namespace: argocd
spec:
  source:
    repoURL: https://kubernetes-sigs.github.io/external-dns
    chart: external-dns
    targetRevision: 1.13.0
    helm:
      values: |
        provider: aws
        aws:
          region: ap-northeast-2
        txtOwnerId: k8s-sesacthon
        policy: sync
```

**결론**: ✅ **Terraform (정적) 또는 External-DNS (동적)**  
**우선순위**: 낮음  
**예상 작업 시간**: 1시간

---

## 📊 최종 작업 계획

### Phase 1: Terraform user-data (OS ~ K8s 패키지 설치)
**예상 시간**: 4시간

| 작업 | 시간 | 우선순위 |
|------|------|---------|
| OS 설정 스크립트 | 1h | 높음 |
| Docker 설치 스크립트 | 1h | 높음 |
| K8s 패키지 설치 스크립트 | 0.5h | 높음 |
| Master init (null_resource) | 2h | 높음 |
| Worker join (user-data + SSM) | 2h | 높음 |
| Provider ID (user-data 기본) | 0.5h | 높음 |

---

### Phase 2: ArgoCD Apps (K8s 리소스 및 Add-ons)
**예상 시간**: 10시간

| 작업 | 시간 | 우선순위 |
|------|------|---------|
| ArgoCD 설치 (Terraform) | 2h | 높음 |
| CNI (VPC-CNI) | 1h | 높음 |
| EBS CSI Driver | 1h | 높음 |
| ALB Controller | 1h | 높음 |
| Metrics Server | 0.5h | 중간 |
| PostgreSQL | 1h | 높음 |
| Redis | 1h | 높음 |
| RabbitMQ | 1h | 높음 |
| Monitoring | 2h | 중간 |
| Atlantis | 1h | 중간 |
| IngressClass | 0.5h | 높음 |

---

### Phase 3: Node Lifecycle Operator (핵심)
**예상 시간**: 5시간

| 작업 | 시간 | 우선순위 |
|------|------|---------|
| Operator 설계 | 1h | 높음 |
| Node Labels (EC2 태그 매핑) | 2h | 높음 |
| Provider ID 검증/수정 | 1h | 높음 |
| Node Taints | 1h | 중간 |
| 테스트 및 문서화 | 1h | 높음 |

---

### Phase 4: Ansible 제거 및 정리
**예상 시간**: 2시간

| 작업 | 시간 |
|------|------|
| Ansible playbook 제거 | 0.5h |
| Ansible roles 제거 | 0.5h |
| GitHub Actions 업데이트 | 0.5h |
| 문서 업데이트 | 0.5h |

---

## 🎯 총 예상 작업 시간

**총합**: **21시간** (약 3일)

- Phase 1 (Terraform user-data): 4시간
- Phase 2 (ArgoCD Apps): 10시간
- Phase 3 (Operator): 5시간
- Phase 4 (정리): 2시간

---

## 📝 참고 링크

### Helm Charts
- [AWS VPC CNI](https://github.com/aws/amazon-vpc-cni-k8s)
- [AWS EBS CSI Driver](https://github.com/kubernetes-sigs/aws-ebs-csi-driver)
- [AWS Load Balancer Controller](https://github.com/aws/aws-load-balancer-controller)
- [Metrics Server](https://github.com/kubernetes-sigs/metrics-server)
- [ArgoCD](https://github.com/argoproj/argo-helm)
- [Bitnami Charts](https://github.com/bitnami/charts)
- [Prometheus Stack](https://github.com/prometheus-community/helm-charts)

### Operator 개발
- [Kopf Framework](https://kopf.readthedocs.io/)
- [Kubernetes Python Client](https://github.com/kubernetes-client/python)

### Terraform
- [AWS Provider](https://registry.terraform.io/providers/hashicorp/aws/latest/docs)
- [null_resource](https://registry.terraform.io/providers/hashicorp/null/latest/docs/resources/resource)
- [SSM Parameter Store](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/ssm_parameter)

---

**다음 단계**: Phase 1 - Terraform user-data 스크립트 작성

