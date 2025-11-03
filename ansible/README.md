# 🤖 Ansible - K8s 클러스터 설정

## 🚀 빠른 시작

```bash
# 1. Inventory 확인 (Terraform이 생성)
cat inventory/hosts.ini

# 2. 연결 테스트
ansible all -i inventory/hosts.ini -m ping

# 3. 전체 Playbook 실행
ansible-playbook -i inventory/hosts.ini site.yml
```

## 📋 Playbooks

```
site.yml - 마스터 플레이북 (모든 단계 실행)

개별 실행:
├─ 00-prerequisites.yml (roles/common)
├─ 01-k8s-install.yml (roles/docker, kubernetes)
├─ 02-master-init.yml (kubeadm init)
├─ 03-worker-join.yml (kubeadm join)
├─ 04-cni-install.yml (Flannel)
├─ 05-addons.yml (Ingress, Cert-manager)
├─ 06-argocd.yml (roles/argocd)
├─ 07-rabbitmq.yml (roles/rabbitmq)
└─ 08-monitoring.yml (Prometheus + Grafana)
```

## ⏱️ 실행 시간

```
총 30분:
├─ Prerequisites: 5분
├─ Docker: 3분
├─ Kubernetes: 5분
├─ Master Init: 3분
├─ Worker Join: 2분
├─ CNI: 2분
├─ Add-ons: 5분
├─ ArgoCD: 3분
└─ RabbitMQ: 2분
```

## 🔧 변수 수정

`inventory/group_vars/all.yml`:

```yaml
rabbitmq_password: "your-password"
grafana_admin_password: "your-password"
```

## 🎯 특정 단계만 실행

```bash
# Master만
ansible-playbook -i inventory/hosts.ini site.yml --limit masters

# ArgoCD만 재설치
ansible-playbook -i inventory/hosts.ini site.yml --tags argocd

# 특정 Playbook만
ansible-playbook -i inventory/hosts.ini playbooks/06-argocd.yml
```

---

**문서**: [IaC 구성 가이드](../docs/architecture/iac-terraform-ansible.md)

