# Calico GitOps Incident (2025-11-18)

문제 요약:

- Ansible이 초기 배포한 **Tigera Operator + Installation CR**가 클러스터에 남아 있는 상태에서, ArgoCD(Helm)로 동일 리소스를 재배포하려다 충돌이 발생했다.
- CRD가 1MB 이상이라 **client-side apply**가 `metadata.annotations` 256KiB 제한을 초과했고, `ServerSideApply=true`를 적용해도 기존 Installation의 finalizer/FSM이 남아 있어 Argo가 계속 `waiting for deletion...` 상태에 머물렀다.
- Calico CNI가 내려간 탓에 모든 노드는 `node.kubernetes.io/network-unavailable` taint가 유지되었고, 플랫폼/데이터/워크로드 계층 Application들이 연쇄적으로 OutOfSync/Progressing 상태가 되었다.

---

## 1. Application 상태 스냅샷

`kubectl get application -n argocd` (2025-11-18 21:00 KST)

| Application | Sync Status | Health Status |
|-------------|-------------|---------------|
| dev-alb-controller | OutOfSync | Progressing |
| dev-api-auth / my / scan / character / location / info / chat | **Synced** | Degraded |
| dev-calico | **OutOfSync** | Progressing |
| dev-data-clusters | OutOfSync | Healthy |
| dev-external-dns / external-secrets / grafana / ingress | OutOfSync | Progressing |
| dev-kube-prometheus-stack | OutOfSync | Missing |
| dev-postgres-operator / dev-redis-operator / dev-rabbitmq-operator | OutOfSync | Healthy |
| dev-root | OutOfSync | Healthy |
| 나머지 (crds, namespaces, network-policies, etc.) | Synced | Healthy |

→ Calico가 멈추면서 가장 상단(플랫폼)부터 하위 Application 전체가 OutOfSync로 전파된 사례다.

---

## 2. 타임라인 (요약)

| 시각 | 이벤트 |
|------|--------|
| 19:00~20:00 | `dev-calico`가 `OutOfSync / waiting for deletion of operator.tigera.io/Installation/default`. Argo는 tigera 리소스만 prune 반복. |
| 20:30 | `ServerSideApply=true` 적용 → annotation 용량 오류는 해소되었지만 finalizer로 인해 OperationState가 갱신되지 않음. |
| 21:00 | `Installation/default` finalizer 제거/삭제 성공. 그러나 CRD(`installations.operator.tigera.io`, `apiservers.operator.tigera.io`)가 남아 있어 새 Sync가 진행되지 않음. |
| 21:10~21:30 | Calico 관련 CRD를 수동 삭제. 그래도 OperationState가 reset되지 않고 이벤트가 멈춤. |
| 21:40 이후 | 네트워크가 죽어 `kubectl logs`, `argocd login --core`, `port-forward` 모두 실패. |
| 22:00 | RCA: “Calico를 GitOps에서 관리하지 않고 Ansible Playbook (`04-cni-install.yml`) 전용으로 관리” 방향 확정. GitOps 매니페스트(05-calico.yaml, platform/helm/calico/**) 제거. |

---

## 3. 원인 및 교훈

1. **Ownership 충돌**  
   - Ansible 설치 → Argo(Helm) 재배포 간 Ownership이 겹치면 finalizer/annotation 문제를 야기한다. 기존 리소스를 깨끗이 지우거나 GitOps에서 제외해야 한다.

2. **CRD 용량 + client-side apply**  
   - Tigera CRD는 1MB 이상이므로 SSA 필수. 그렇지 않으면 `metadata.annotations: Too long` 에러가 반복된다.

3. **CNI 다운 시 추가 작업도 불가**  
   - 네트워크가 죽으면 Argo를 비롯한 대부분의 운영 명령(`kubectl logs`, `argocd login`, `port-forward`)이 kubelet 10250 포트 접근 실패로 막힌다. 수동 복구 시에는 Quickstart 매니페스트를 직접 apply 해야 함.

### OutOfSync 파급 구조 (세부)

1. **Calico/Tigera Operator (플랫폼 계층)**  
   - Ansible로 선 설치된 `Installation/default` + 다수 CRD가 GitOps 배포와 충돌하면서 Argo가 항상 `waiting for deletion…`에 머무름.  
   - SSA 미적용 시에는 CRD `metadata.annotations` 256KiB 제한에도 막혀 `dev-calico`부터 `dev-root`까지 연쇄적으로 OutOfSync가 확산되었다.

2. **플랫폼 컴포넌트 종속성**  
   - `dev-external-dns`, `dev-external-secrets`, `dev-grafana`, `dev-ingress`, `dev-kube-prometheus-stack`은 Calico/네트워크 의존성이 높은데, CNI가 내려가면서 파드가 Pending 상태에 머물러 해당 Application이 OutOfSync를 반복했다.

3. **데이터/워크로드 계층**  
   - `dev-data-clusters`, `dev-rabbitmq-operator`, `dev-postgres-operator` 등은 리소스 정의는 정상이라 Health=Healthy지만, Calico 불능 때문에 실제 파드가 스케줄되지 않아 Sync 상태만 OutOfSync로 남음.

4. **비즈니스 로직 계층**
   - API 서비스(`dev-api-*`)는 이미지/헬스 체크 문제로 Degraded 상태였지만 Sync 자체는 유지 → 근본 원인은 여전히 Calico에 기인.

---

## 4. 해결 / 후속 조치

1. **GitOps 경로에서 제거**  
   - `clusters/dev/apps/05-calico.yaml` 및 `platform/helm/calico/**` 삭제 완료.
   - `dev-root` App-of-Apps에서 Calico Application 참조 제거.

2. **Ansible 전담**  
   - Calico/Tigera 설치는 `ansible/playbooks/04-cni-install.yml` 및 `tasks/cni-install.yml`에서만 수행.
   - README/Runbook에 “Calico = Ansible 소관” 명시, Quickstart 링크 포함.

3. **재발 방지**  
   - 향후 CNI 교체/업그레이드는 Ansible Playbook을 통해 수행한 뒤, GitOps 환경에는 Calico 관련 리소스를 추가하지 않는다.
   - OperationState가 멈출 경우 `kubectl patch application <app> --type merge -p '{"status":{"reconciledAt":null,"operationState":null}}'` 로 초기화하는 절차를 Runbook에 추가.

