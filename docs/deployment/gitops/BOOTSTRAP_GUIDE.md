# 클러스터 부트스트랩 & 정리 가이드

## 📋 목차

1. [클러스터 배포 (Bootstrap)](#클러스터-배포)
2. [클러스터 삭제 (Destroy)](#클러스터-삭제)
3. [잔여물 정리 (Cleanup)](#잔여물-정리)
4. [문제 해결](#문제-해결)

---

## 🚀 클러스터 배포

### 기본 배포

```bash
# 전체 배포 (Terraform + Ansible + ArgoCD)
bash scripts/deployment/bootstrap_cluster.sh
```

### 옵션별 배포

```bash
# Ansible만 재실행 (Terraform은 건너뛰기)
bash scripts/deployment/bootstrap_cluster.sh --skip-terraform

# ArgoCD 설정 건너뛰기
bash scripts/deployment/bootstrap_cluster.sh --skip-argocd

# 사전 점검 건너뛰기 (잔여물이 있어도 강제 실행)
bash scripts/deployment/bootstrap_cluster.sh --skip-preflight-check
```

### 사전 점검

배포 전 스크립트는 자동으로 다음 항목을 확인합니다:

- ✅ 기존 Terraform 리소스 존재 여부
- ✅ Ansible inventory 파일 잔여물
- ✅ kubeadm join 임시 스크립트

⚠️ 잔여물이 발견되면 경고를 표시하고 계속 진행할지 묻습니다.

---

## 🗑️ 클러스터 삭제

### 기본 삭제

```bash
# 대화형 삭제 (확인 필요)
bash scripts/deployment/destroy_cluster.sh
```

### 완전 삭제 (권장)

```bash
# 자동 승인 + 모든 잔여물 정리
bash scripts/deployment/destroy_cluster.sh --cleanup-all -y
```

### 옵션별 삭제

```bash
# ArgoCD root-app 먼저 삭제
bash scripts/deployment/destroy_cluster.sh --delete-root-app

# 자동 승인 (CI/CD용)
bash scripts/deployment/destroy_cluster.sh -y

# 잔여물 정리 포함
bash scripts/deployment/destroy_cluster.sh --cleanup-all
```

### destroy --cleanup-all이 정리하는 항목

1. **Ansible 파일**
   - `ansible/inventory/hosts.ini`
   - `ansible/inventory/hosts.tmp`
   - `/tmp/kubeadm_join_command.sh`

2. **Terraform 백업**
   - `terraform/terraform.tfstate.backup`
   - `terraform/tfplan*`

3. **로그 파일**
   - 7일 이상 된 `logs/*.log` 파일

4. **kubeconfig**
   - `kubernetes-admin@kubernetes` 컨텍스트 제거
   - `kubernetes` 클러스터 정보 제거
   - `kubernetes-admin` 사용자 정보 제거

---

## 🧹 잔여물 정리

### 독립 실행 cleanup 스크립트

```bash
# DRY-RUN: 삭제 대상만 확인
bash scripts/utilities/cleanup-deployment-artifacts.sh --dry-run

# 실제 정리 실행
bash scripts/utilities/cleanup-deployment-artifacts.sh

# 로그 파일도 정리
bash scripts/utilities/cleanup-deployment-artifacts.sh --cleanup-logs

# Terraform state도 정리 (⚠️ 위험)
bash scripts/utilities/cleanup-deployment-artifacts.sh --cleanup-tf-state
```

### 수동 정리 (필요 시)

```bash
# Ansible 잔여물
rm -f ansible/inventory/hosts.ini
rm -f ansible/inventory/hosts.tmp
rm -f /tmp/kubeadm_join_command.sh

# Terraform 백업
rm -f terraform/terraform.tfstate.backup
rm -f terraform/tfplan*

# kubeconfig 정리
kubectl config delete-context kubernetes-admin@kubernetes
kubectl config delete-cluster kubernetes
kubectl config delete-user kubernetes-admin
```

---

## 🔧 문제 해결

### 문제: "reserved role label" 에러

**증상:**
```
failed to validate kubelet flags: unknown 'sesacthon.io' or 'k8s.io' labels
```

**원인:**
Kubernetes 1.24+ 버전에서 Kubernetes 내부 role prefix가 제한됨

**해결:**
- ✅ Terraform/Ansible이 `role=<api|worker|infrastructure>` 라벨만 사용하도록 수정됨
- 새로 배포하면 자동으로 올바른 라벨 사용

---

### 문제: "잔여물이 남아서 재배포 실패"

**증상:**
```
[bootstrap] ⚠️ 경고: 기존 Terraform 리소스가 존재합니다.
```

**해결 1: 완전 삭제 후 재배포**
```bash
bash scripts/deployment/destroy_cluster.sh --cleanup-all -y
bash scripts/deployment/bootstrap_cluster.sh
```

**해결 2: 강제 진행**
```bash
bash scripts/deployment/bootstrap_cluster.sh --skip-preflight-check
```

---

### 문제: "Ansible inventory 없음"

**증상:**
```
ERROR: Unable to find '/path/to/hosts.ini'
```

**해결:**
```bash
# Terraform output으로 inventory 재생성
cd terraform
terraform output -raw ansible_inventory > ../ansible/inventory/hosts.ini
```

---

### 문제: "Worker 노드 조인 실패"

**증상:**
```
kubelet health check failed: connection refused
```

**해결:**
```bash
# 실패한 노드들 정리 후 재조인
cd ansible
ansible-playbook -i inventory/hosts.ini playbooks/fix-node-labels.yml
ansible-playbook -i inventory/hosts.ini playbooks/rejoin-workers.yml
```

---

## 📊 배포 상태 확인

### Terraform 리소스

```bash
cd terraform
terraform show
```

### 클러스터 노드

```bash
kubectl get nodes -o wide
kubectl get nodes --show-labels
```

### Ansible inventory

```bash
cat ansible/inventory/hosts.ini
```

---

## 🔄 재배포 Best Practice

### 1. 완전한 정리 후 재배포

```bash
# 1️⃣ 클러스터 삭제 + 완전 정리
bash scripts/deployment/destroy_cluster.sh --cleanup-all -y

# 2️⃣ 상태 확인 (옵션)
bash scripts/utilities/cleanup-deployment-artifacts.sh --dry-run

# 3️⃣ 재배포
bash scripts/deployment/bootstrap_cluster.sh
```

### 2. Ansible만 재실행

```bash
# Terraform 인프라는 유지하고 Ansible만 재실행
bash scripts/deployment/bootstrap_cluster.sh --skip-terraform
```

### 3. ArgoCD 재배포

```bash
# ArgoCD root-app만 재적용
kubectl delete -n argocd -f clusters/dev/root-app.yaml
kubectl apply -n argocd -f clusters/dev/root-app.yaml
```

---

## ⚡ 빠른 참조

| 작업 | 명령어 |
|------|--------|
| 전체 배포 | `bash scripts/deployment/bootstrap_cluster.sh` |
| 완전 삭제 | `bash scripts/deployment/destroy_cluster.sh --cleanup-all -y` |
| 정리 확인 | `bash scripts/utilities/cleanup-deployment-artifacts.sh --dry-run` |
| 잔여물 정리 | `bash scripts/utilities/cleanup-deployment-artifacts.sh` |
| Worker 재조인 | `ansible-playbook -i ansible/inventory/hosts.ini playbooks/rejoin-workers.yml` |

---

## 🆘 긴급 복구

### 완전히 망가진 경우

```bash
# 1. AWS 리소스 수동 확인
aws ec2 describe-instances --filters "Name=tag:Project,Values=sesacthon"

# 2. Terraform으로 강제 정리
cd terraform
terraform destroy -auto-approve

# 3. 로컬 정리
bash scripts/utilities/cleanup-deployment-artifacts.sh --cleanup-tf-state

# 4. 처음부터 재배포
bash scripts/deployment/bootstrap_cluster.sh
```

---

**작성일**: 2025-11-17  
**버전**: v1.0  
**문서 담당**: Backend Team


