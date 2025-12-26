# Infrastructure Pod Scheduling

인프라 Pod를 Master(Control Plane) 노드에 집중 배치하여 Worker 노드 리소스를 확보합니다.

## 배경

Worker 노드(특히 `worker-storage`)에 인프라 Pod들이 과도하게 배치되어 워커 Pod 스케줄링에 리소스 부족이 발생했습니다.

**개선 효과:**
- worker-storage CPU: 99% → 91% (-155m)
- worker-storage Memory: 97% → 80% (-660Mi)

## 이동 대상 Pod

### ArgoCD Apps로 관리 (자동 적용)

| 파일 | Pod | Helm Chart |
|------|-----|------------|
| `60-kiali.yaml` | kiali | kiali-server |
| `61-jaeger.yaml` | jaeger | jaeger |
| `08-cert-manager.yaml` | cert-manager, webhook, cainjector | cert-manager |
| `10-secrets-operator.yaml` | external-secrets, webhook, certController | external-secrets |
| `20-monitoring-operator.yaml` | kube-state-metrics | kube-prometheus-stack |

### 수동 적용 필요 (이 디렉토리)

| Patch 파일 | Pod | 이유 |
|-----------|-----|------|
| `coredns-patch.yaml` | coredns | kubeadm 관리 |
| `calico-kube-controllers-patch.yaml` | calico-kube-controllers | Calico 설치 시 관리 |
| `ebs-csi-controller-patch.yaml` | ebs-csi-controller | Helm Chart로 관리되지만 ArgoCD 미등록 |
| `metrics-server-patch.yaml` | dev-metrics-server | Helm Chart로 관리되지만 ArgoCD 미등록 |
| `argocd-applicationset-patch.yaml` | argocd-applicationset-controller | ArgoCD 자체 컴포넌트 |

## 적용 방법

### 1. 개별 적용 (kubectl patch)

```bash
# Master 노드에서 실행
kubectl patch deployment coredns -n kube-system --type=strategic --patch-file=coredns-patch.yaml
kubectl patch deployment calico-kube-controllers -n kube-system --type=strategic --patch-file=calico-kube-controllers-patch.yaml
kubectl patch deployment ebs-csi-controller -n kube-system --type=strategic --patch-file=ebs-csi-controller-patch.yaml
kubectl patch deployment dev-metrics-server -n kube-system --type=strategic --patch-file=metrics-server-patch.yaml
kubectl patch deployment argocd-applicationset-controller -n argocd --type=strategic --patch-file=argocd-applicationset-patch.yaml
```

### 2. 일괄 적용 (Ansible Playbook)

```bash
cd /path/to/ansible
ansible-playbook -i inventory/hosts.ini playbooks/apply-infra-scheduling.yml
```

## 확인 방법

```bash
# Master 노드에 배치된 인프라 Pod 확인
kubectl get pods -A -o wide | grep k8s-master | grep -E "(coredns|calico-kube-controllers|ebs-csi-controller|metrics-server|applicationset)"

# Worker 노드 리소스 여유 확인
kubectl describe node k8s-worker-storage | grep -A6 'Allocated resources'
```

## 주의사항

- **DaemonSet은 이동하지 않음**: calico-node, ebs-csi-node, kube-proxy, fluent-bit, node-exporter
- **ArgoCD selfHeal**: Helm Chart로 관리되는 Pod는 ArgoCD가 자동으로 원복할 수 있으므로 ArgoCD Apps 설정 변경 필수
- **kubeadm 업그레이드**: kubeadm upgrade 시 coredns 설정이 초기화될 수 있음
