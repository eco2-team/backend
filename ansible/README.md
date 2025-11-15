# Ansible Playbooks

이 디렉터리는 Terraform으로 생성된 14-Node 클러스터에 Kubernetes 구성요소를 배치할 때 사용하는 최소 Playbook 모음입니다. 현재 GitOps 파이프라인(App of Apps + Helm)으로 대부분 이관되었으며, Ansible은 다음 3가지만 담당합니다.

1. `playbooks/04-kubernetes.yml` – kubeadm 기반 제어 플레인/워커 부트스트랩
2. `playbooks/07-alb-controller.yml` – (옵션) ArgoCD가 대신 설치하도록 기본 비활성화됨
3. `playbooks/10-namespaces.yml` – 도메인 네임스페이스/NetworkPolicy/ServiceMonitor 프리셋 적용

## 실행 방법

```bash
cd ansible
ansible-playbook -i inventory/hosts.ini playbooks/10-namespaces.yml \
  -e kubectl_user=ubuntu
```

> ⚠️  Terraform output 으로 생성되는 `ansible_inventory` 를 `inventory/hosts.ini` 에 반영했는지 확인하세요.

## 주요 파일

| 파일 | 설명 |
|------|------|
| `inventory/hosts.ini` | 14 노드(master/api/worker/infra) IP 정보 |
| `inventory/group_vars/all.yml` | 버전, CIDR, NodePort 등 공통 변수 |
| `playbooks/07-alb-controller.yml` | 기본값으로 Skip (ArgoCD Helm Wave 15 관리) |
| `playbooks/08-monitoring.yml` | (Legacy) Helm 설치 참고 – 현재는 ArgoCD Helm Chart 사용 |
| `playbooks/09-atlantis.yml` | Helm/ArgoCD 기반 Atlantis 배포 안내 |
| `playbooks/10-namespaces.yml` | 네임스페이스/NetworkPolicy/ServiceMonitor 적용 |

## GitOps 연계

- Terraform Apply → `terraform-outputs` ConfigMap 에 Ansible inventory 저장
- ArgoCD PreSync Hook 에서 `playbooks/10-namespaces.yml` 를 호출할 수 있도록 설계되어 있음
- Helm/ArgoCD 가 ALB Controller, kube-prometheus-stack, 데이터베이스를 관리하므로 Ansible에서는 중복 배포를 제거

자세한 내용은 `docs/architecture/operations/OPERATOR-DESIGN-SPEC.md` 와 `docs/deployment/platform/INFRASTRUCTURE_DEPLOYMENT.md` 를 참고하세요.
