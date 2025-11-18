## Kubernetes 라벨/테인트 리팩토링 (2025-11)

### 배경
- `kubernetes.io/*` 사용자 정의 라벨이 Kubernetes 1.28에서 거부되면서 kubelet이 기동하지 않는 문제가 발생.
- 기존에는 `sesacthon.io/*` 커스텀 prefix를 임시로 사용했으나, 표준 라벨(예: `app.kubernetes.io/*`, `alb.ingress.kubernetes.io/*`)까지 함께 바뀌어 컨트롤러/도구가 동작하지 않는 부작용이 생김.
- 문서 `docs/infrastructure/k8s-label-annotation-system.md`를 기준으로 **표준 prefix + 일반 라벨(domain/service/worker-type/infra-type)** 체계를 새로 정의.

### 변경 범위
1. **Terraform (`terraform/main.tf`)**
   - `local.kubelet_profiles`에서 `--node-labels` 구성을 `role=<...>` + `domain`, `service`, `worker-type`, `infra-type`, `workload`, `tier`, `phase` 조합으로 재작성하고 `role=control-plane` taint를 새로 정의.
   - 인프라 노드 taint를 `domain=<data|integration|observability>` 구조로 통일.
2. **Ansible**
   - `playbooks/tasks/fix-node-labels.yml`: Terraform과 동일한 `node_labels` 문자열 적용.
   - `playbooks/02-master-init.yml`: 기본 control-plane taint(legacy)를 제거하고 `role=control-plane:NoSchedule` 커스텀 taint로 교체.
   - `playbooks/tasks/cni-install.yml`: CoreDNS toleration 패치를 Calico 설치 이후 단계로 이동하고, `role=control-plane` 및 `domain=*` 기반으로만 toleration을 유지.
3. **Workloads/Platform**
   - API Deployments(`workloads/apis/*/base/deployment.yaml`): `nodeSelector.kubernetes.io/service=*` → `nodeSelector.domain=*` 변경.
   - Data CRs:
     - `platform/cr/base/postgres-cluster.yaml`
     - `platform/cr/base/redis-{replication,sentinel}.yaml`
     - `platform/cr/base/rabbitmq-cluster.yaml`
     - 모두 `nodeSelector.infra-type`와 `tolerations.domain` 기반으로 재작성, `kubernetes.io/tier` 제거.
4. **문서**
   - `docs/infrastructure/k8s-label-annotation-system.md`: 전체 예시/명령어를 새 라벨 체계로 업데이트하고, “기존 → 신규” 비교 표 추가.

### 적용 가이드
1. **클러스터 재배포**: Terraform → Ansible → ArgoCD 순으로 새 노드에 라벨/테인트가 자동 반영되도록 하며, `kubectl get nodes -L domain,service,infra-type`으로 검증.
2. **기존 클러스터 마이그레이션**:
   - `migrate_node_labels=true` 로 Ansible 태스크 실행 → kubeadm reset + 재조인.
   - 워크로드 재배포 전까지 dual-label이 필요하면, `domain` 라벨을 추가한 뒤 구 키를 제거하는 순서로 진행.
3. **검증 체크리스트**:
   - `kubectl get pods -A --field-selector=status.phase=Pending` (스케줄 실패 파드 유무)
   - `kubectl describe nodes <name>` (label/taint 최종 확인)
   - CoreDNS/ExternalDNS/ALB 등의 표준 어노테이션이 `kubernetes.io/*` 로 복원되었는지 점검.

### 향후 작업
- Terraform/Ansible 외 다른 코드(Helm values, 문서, 스크립트)에 남아 있는 구 라벨 검증.
- CI 단계에서 `rg "sesacthon\\.io"` 검사로 재발 방지.
- 운영 중 노드 라벨 변경 시 `docs/infrastructure/k8s-label-annotation-system.md`를 단일 소스로 유지.

