# Ansible 경량 부트스트랩 계획 (GitOps 우선 클러스터)

> **목적**: Terraform로 노드를 만든 뒤, **최소한의 Ansible 작업**만으로 “ArgoCD Root-App이 동작할 수 있는 Kubernetes 베이스”를 마련하고 나머지는 GitOps(Helm/Kustomize/Operators)에 위임한다.
>
> **대상**: `refactor/gitops-sync-wave` 브랜치에서 운영 중인 14-Node 아키텍처 (dev/prod 동일 흐름)

---

## 1. 범위와 가정

### 포함
- Ubuntu 22.04 노드 OS 준비(패키지, 커널 파라미터, 컨테이너 런타임)
- `kubeadm init/join` 을 통한 Control Plane + Worker 설정
- **초기 네트워크 플러그인** 배포 (Calico manifest 1회 적용)  
  > ArgoCD Wave 5(Calico Helm)를 적용하기 전까지 Pod 네트워킹이 필요하므로, 부트스트랩 단계에서 공식 manifest로 1회 설치한다. 이후 Helm 버전이 sync되면 동일 구성으로 덮어쓰도록 한다.
- ArgoCD 설치 및 Root App 초기 Sync
- Terraform Output/SSM 파이프라인 연동 (ExternalSecrets operator가 필요로 하는 값 저장)

### 제외
- Postgres/Redis/RabbitMQ/Monitoring 등 **모든 애드온** (Helm + Kustomize에서 Wave별 배포)
- ExternalSecrets/Operators/Ingress/Namespace 등 Kubernetes 리소스 구성 (GitOps가 담당)
- Atlantis, Loki, EFK 등 선택적 GitOps/Observability 툴 (향후 확장)

---

## 2. 단계별 계획

| Phase | 목적 | 주요 태스크 | 비고 |
|-------|------|-------------|------|
| 0 | Terraform 완료 확인 | - EC2, VPC, SSM Parameter 배포 상태 확인<br>- `terraform output` → `ansible/inventory/hosts.ini` 재생성 | 이미 자동화됨 (`auto-rebuild.sh` Step 0) |
| 1 | OS 준비 | - Time sync, 커널 모듈, sysctl (bridge-nf-call-iptables 등)<br>- containerd + runc 설치, Cgroup v2 설정<br>- kubeadm/kubelet/kubectl 설치 및 버전 pin | 기존 `bootstrap-os` role 유지 |
| 2 | Control Plane 구축 | - `kubeadm init` + kubeconfig 배포<br>- `kubeadm join` for workers/infrastructure nodes<br>- etcd/cluster 상태 검증 | `site.yml`에서 첫 2개의 플레이만 남김 |
| 3 | Base Add-on | - Calico manifest 적용 (official operator 설치 아님)<br>- EBS CSI/metrics-server가 필요하면 여기서 임시 설치 (선택) | GitOps Helm(Calico Wave 5)와 동일 설정 유지 |
| 4 | ArgoCD 설치 | - `kubectl create namespace argocd`<br>- `kubectl apply -n argocd -f install.yaml` (혹은 Helm)<br>- **관리자 비밀번호는 Terraform → SSM(`/platform/argocd-admin-password`)에 생성 후 ExternalSecret(`argocd-admin-secret`)으로 배포** | GitOps Root-App을 통해 ArgoCD 자체를 다시 관리할 계획이라면 차후 Helm 전환 가능 |
| 5 | Root App 부트스트랩 | - `argocd login` (주석 or 문서 안내)<br>- `argocd app create root-app ...` 또는 `kubectl apply -f clusters/{env}/root-app.yaml`<br>- `argocd app sync root-app` 으로 Wave 0~70 자동 진행<br>- Wave 11에서 `workloads/secrets/external-secrets`가 `/sesacthon/{env}/**` SSM Parameter를 동기화해 DB/RabbitMQ/Redis/Grafana/ArgoCD Secret이 준비됨 | 여기서부터 모든 리소스는 GitOps 컨트롤 |

> ⛳ **핵심**: Phase 5 완료 이후에는 Ansible이 아닌 ArgoCD가 Operators/CRDs/Ingress/Apps를 배포하므로, Ansible 변경을 CD로 감지할 필요가 없다.

---

## 3. 유지/삭제할 Ansible Role

| Role | 유지 이유 | 비고 |
|------|-----------|------|
| `bootstrap-os` | 패키지/컨테이너 런타임 설치 | Phase 1 |
| `kubeadm-init`, `kubeadm-join` | Control Plane/Worker 구성 | Phase 2 |
| `install-calico-manifest` (신규 간소 role) | GitOps 이전까지 CNI 확보 | Phase 3 |
| `install-argocd` | ArgoCD core 설치 | Phase 4 |
| `root-app-bootstrap` | Root App 적용 & 첫 Sync | Phase 5 |

| Role | 제거/중단 사유 |
|------|----------------|
| `postgres`, `redis`, `rabbitmq`, `monitoring`, `ingress`, `namespaces` 등 애드온 역할 | Helm/Kustomize + ArgoCD가 Wave별로 관리하므로 더 이상 필요 없음 |
| `atlantis`, `external-secrets`, `alb-controller` 등 GitOps tool 역할 | 현재 범위에서는 GitOps 배포 대상이 아니며, 향후 Wave 50 확장 시 Helm으로 교체 |

---

## 4. 검증 체크리스트

1. **노드 상태**  
   ```bash
   kubectl get nodes -o wide
   kubectl get nodes -L workload,node-role.kubernetes.io/infrastructure
   ```
2. **Core Add-on**  
   - `kube-system` 네임스페이스 Pod Ready  
   - Calico `calico-node`, `typha` (있는 경우) Running
3. **ArgoCD 상태**  
   ```bash
   kubectl get pods -n argocd
   argocd app list
   ```
4. **Root App Sync**  
   - `argocd app get root-app` → `Sync Status: Synced`  
   - Wave 0/2/3/5 리소스가 정상 적용됐는지 `kubectl get`으로 확인
5. **Operator 기반 워크로드**  
   - `platform-system`, `monitoring`, `postgres`, `redis` 네임스페이스에서 Operator Pod가 생성됐는지 확인 (`kubectl get pods -n ...`)
6. **Drift 방지**  
   - Ansible은 Phase 5 이후 더 이상 실행하지 않고, 변경이 필요할 때 Git(Helm/Kustomize)만 수정하도록 운영 규칙 문서화.

---

## 5. 향후 확장 (Optional)

- **Atlantis/GitOps Tool**: Wave 50에 Atlantis Helm을 추가하고, 부트스트랩에서 `argocd app sync gitops-tools` 만 수행하면 된다.
- **로깅/모니터링 확장**: Loki/EFK 등은 GitOps Helm 오버레이로 배치하되, 부트스트랩 단계에서는 Fluent Bit 같은 DaemonSet을 설치하지 않는다.
- **리눅스 배포판 추가**: Ubuntu 외 AL2, Bottlerocket 등을 도입하려면 Phase 1 Role을 파라미터화.

---

## 6. 참고 문서
- `docs/refactor/gitops-sync-wave-TODO.md` – TODO #12의 실행 계획
- `docs/architecture/gitops/ARGOCD_SYNC_WAVE_PLAN.md` – Wave별 배포 순서
- `docs/architecture/networking/NETWORK_ISOLATION_POLICY.md` – NetworkPolicy 적용 시점
- `docs/architecture/deployment/ATLANTIS_TERRAFORM_FLOW.md` – (향후) Atlantis 재도입 참고

> 이 문서는 GitOps 우선 모델에서 **Ansible을 “경량 부트스트랩 전용”으로 유지하기 위한 기준**이다. 변경 시 꼭 본 문서를 업데이트하고, Ansible Role/Playbook 구조를 동일하게 반영한다.

