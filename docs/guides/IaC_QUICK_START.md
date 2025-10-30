# ⚡ IaC 빠른 시작 가이드

## 🚀 One-command 배포

```bash
# 전체 클러스터 프로비저닝 (35분)
./scripts/provision.sh
```

---

## 📋 단계별 실행

### 1. Terraform (5분)

```bash
cd terraform

# 초기화
terraform init

# 계획 확인
terraform plan

# 적용
terraform apply

# Inventory 생성
terraform output -raw ansible_inventory > ../ansible/inventory/hosts.ini
```

### 2. Ansible (30분)

```bash
cd ansible

# 연결 테스트
ansible all -i inventory/hosts.ini -m ping

# 전체 설치
ansible-playbook -i inventory/hosts.ini site.yml
```

### 3. ArgoCD Applications 등록

```bash
# Master에 SSH 접속
ssh ubuntu@$(cd terraform && terraform output -raw master_public_ip)

# Applications 등록
kubectl apply -f argocd/applications/all-services.yaml

# ArgoCD UI 접속
kubectl port-forward svc/argocd-server -n argocd 8080:443
# https://localhost:8080
```

---

## ✅ 생성된 리소스

### AWS (Terraform)

```
✅ VPC
✅ Subnets ×3
✅ Internet Gateway
✅ Route Tables
✅ Security Groups ×2
✅ EC2 Instances ×3
✅ EBS Volumes ×3
✅ Elastic IP ×1

비용: $91/월
```

### Kubernetes (Ansible)

```
✅ Docker
✅ kubeadm, kubelet, kubectl
✅ Control Plane (Master)
✅ Worker Nodes ×2
✅ Flannel CNI
✅ Nginx Ingress
✅ Cert-manager
✅ Metrics Server
✅ ArgoCD
✅ RabbitMQ
✅ Prometheus + Grafana

총 Pod: 약 30개
```

---

## 🔍 확인

```bash
# 클러스터 상태
kubectl get nodes

# 모든 Pod
kubectl get pods -A

# ArgoCD Applications
kubectl get applications -n argocd

# RabbitMQ
kubectl get pods -n messaging
```

---

## 🗑️ 삭제

```bash
# 전체 인프라 삭제
./scripts/destroy.sh

# 비용 절감: $105/월 → $0
```

---

## 📚 상세 문서

- [IaC 설계 문서](docs/architecture/iac-terraform-ansible.md)
- [K8s 클러스터 구축](docs/architecture/k8s-cluster-setup.md)
- [최종 아키텍처](docs/architecture/final-k8s-architecture.md)

---

**총 36개 IaC 파일**  
**구축 시간**: 35분  
**비용**: $105/월

