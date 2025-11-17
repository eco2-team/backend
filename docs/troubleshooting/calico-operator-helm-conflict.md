# Calico Operator/Helm 중복 설치

> **배경**: Ansible 부트스트랩에서 `https://raw.githubusercontent.com/projectcalico/calico/v3.26.x/manifests/calico.yaml`을 적용한 뒤, ArgoCD Wave 5가 Tigera Operator Helm 차트를 재설치하면서 서로 다른 리소스 스택이 충돌했던 이력을 정리한다.

---

## 1. 증상

- `calico-node` DaemonSet이 `kube-system`과 `calico-system` 두 네임스페이스에 동시에 존재하거나, Helm Sync 시 `AlreadyExists` / `Field is immutable` 오류 발생
- Root-App Wave 5(`dev-calico`, `prod-calico`)가 계속 `Progressing` 상태에서 완료되지 않음
- `tigera-operator` Deployment가 CrashLoop → `Installation default` CR이 `Failed` 상태

---

## 2. 원인

| 항목 | 설명 |
|------|------|
| Ansible Bootstrap | v3.26.x manifest를 그대로 적용하여 `calico-*` 리소스를 `kube-system` 네임스페이스에 생성 |
| GitOps Wave 5 | `platform/helm/calico/app.yaml`이 Tigera Operator(v3.27.0) + `Installation` CR(VXLAN, BGP Disabled)을 배포 |
| 결과 | 서로 다른 CRD/리소스 구조가 동시에 존재하며, Helm이 기존 리소스를 덮어쓰지 못해 Drift 발생 |

---

## 3. 해결 절차

1. **기존 Manifest 제거**
   ```bash
   kubectl delete -f https://raw.githubusercontent.com/projectcalico/calico/v3.26.4/manifests/calico.yaml
   kubectl delete namespace calico-system --ignore-not-found
   ```
2. **Tigera Operator 재설치**
   - `ansible/playbooks/04-cni-install.yml` 실행 → v3.27.0 `tigera-operator.yaml` + `Installation` CR을 적용
   - `Installation` 스펙은 Helm values와 동일하게 VXLAN Only, `bgp: Disabled`, `ipPools[].cidr = {{ pod_network_cidr }}` 로 구성
3. **상태 검증**
   ```bash
   kubectl get installation default -o yaml
   # spec.calicoNetwork.bgp == Disabled, encapsulation == VXLAN 확인
   kubectl wait --for=condition=ready pod -n calico-system -l k8s-app=calico-node --timeout=300s
   ```
4. **ArgoCD 재동기화**
   ```bash
   argocd app sync dev-calico
   argocd app wait dev-calico --timeout 300
   ```

---

## 4. 예방 팁

- 부트스트랩 단계에서 항상 Tigera Operator 버전과 Helm overlay(`patch-application.yaml`)를 동기화한다.
- `ansible/roles/argocd/tasks/main.yml`에 포함된 CNI Pre-check를 활용해 Calico DaemonSet이 준비되지 않았다면 ArgoCD 설치를 중단한다.
- 신규 클러스터를 만들기 전에 `ansible/playbooks/04-cni-install.yml`만 단독으로 실행해 vxlan/bgp 설정을 검증한 뒤 Root-App을 배포한다.

---

## 5. 참고 문서

- `platform/helm/calico/{env}/patch-application.yaml`
- `ansible/playbooks/04-cni-install.yml`
- `docs/infrastructure/05-cni-comparison.md`


