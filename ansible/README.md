# Ansible Playbooks

이 디렉터리는 Terraform로 생성된 14-Node 클러스터에 대해 **최소한의 부트스트랩만 수행**합니다. 나머지 리소스(Calico Helm, ExternalSecrets, Operators, 애플리케이션)는 전부 ArgoCD(App-of-Apps)에서 관리되므로, Ansible의 책임 범위는 아래처럼 단순화되었습니다.

## 담당 범위
1. OS/컨테이너 런타임 준비 (`common`, `docker`, `kubernetes` roles)
2. `kubeadm init` / `kubeadm join` 으로 Control Plane + Worker 조인
3. Calico VXLAN Always + BGP OFF (Helm과 동일 설정) 1회 설치
4. ArgoCD Core 설치 + Root App Sync (이후 Wave 0~70 GitOps 자동 배포)

이상이 완료되면 Ansible은 더 이상 실행하지 않습니다. Secret, Operator, Ingress 등은 Wave 10~70에서 ExternalSecrets/Helm/Kustomize가 처리합니다.

## 실행 방법
```bash
cd ansible
ansible-playbook -i inventory/hosts.ini site.yml \
  -e kubectl_user=ubuntu
```

> ⚠️ Terraform output `ansible_inventory` 를 `inventory/hosts.ini` 에 반영한 뒤 실행하세요.

## 주요 파일
| 파일 | 설명 |
|------|------|
| `inventory/hosts.ini` | 14 노드(master/api/worker/infra) IP 정보 (Terraform output) |
| `inventory/group_vars/all.yml` | Kubernetes/ArgoCD 버전, 네트워크 CIDR 등 최소 변수 |
| `site.yml` | 위 네 단계(bootstrap → kubeadm → Calico → ArgoCD)만 수행 |
| `playbooks/02-master-init.yml` `03-worker-join.yml` 등 | kubeadm 관련 태스크 |
| `playbooks/04-cni-install.yml` | Calico VXLAN Always + BGP Disabled 설정 |
| `playbooks/label-nodes.yml` | Namespace/Tier 라벨 일관성 유지 |

## GitOps 연계
- Terraform → AWS SSM(Parameter Store)에 인프라/비밀번호 기록
- Wave 10/11에서 ExternalSecrets Operator가 `/sesacthon/{env}/**` 경로를 읽어 Secret 생성
- Wave 5 이후(Calico Helm 포함)는 모두 ArgoCD Root App이 책임지므로, Ansible은 재실행하지 않는다.

상세 플로우는 `docs/architecture/deployment/ANSIBLE_BOOTSTRAP_PLAN.md` 와 `docs/architecture/gitops/ARGOCD_SYNC_WAVE_PLAN.md` 를 참고하세요.
