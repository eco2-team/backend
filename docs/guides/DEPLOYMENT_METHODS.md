# 배포 방법 정리

## 클러스터 구성요소별 설치 방법

### Helm으로 설치된 것들

1. **kube-prometheus-stack** (monitoring namespace)
   - Chart: `prometheus-community/kube-prometheus-stack`
   - 확인: `helm list -n monitoring`

2. **aws-load-balancer-controller** (kube-system namespace)
   - Chart: `aws/aws-load-balancer-controller`
   - 확인: `helm list -n kube-system`

### kubectl apply로 설치된 것들

1. **ArgoCD** (argocd namespace)
   - 설치: `kubectl apply -f https://raw.githubusercontent.com/argoproj/argo-cd/stable/manifests/install.yaml`
   - 확인: `kubectl get pods -n argocd`
   - **주의**: Helm Release가 아님 (Helm으로 설치 가능하지만 현재는 kubectl apply 사용)

2. **Cert-manager** (cert-manager namespace)
   - 설치: `kubectl apply -f https://github.com/cert-manager/cert-manager/releases/download/v1.13.0/cert-manager.yaml`
   - 확인: `kubectl get pods -n cert-manager`

3. **EBS CSI Driver** (kube-system namespace)
   - 설치: `kubectl apply -k ...`
   - 확인: `kubectl get pods -n kube-system -l app=ebs-csi-driver`

4. **Redis** (default namespace)
   - 설치: `kubectl apply -f ...`
   - 확인: `kubectl get pods -l app=redis`

### Operator로 관리되는 것들

1. **RabbitMQ** (messaging namespace)
   - Operator 설치: `kubectl apply -f https://github.com/rabbitmq/cluster-operator/releases/latest/download/cluster-operator.yml`
   - CR 생성: `kubectl apply -f RabbitmqCluster CR`
   - 확인: `kubectl get rabbitmqcluster -n messaging`
   - **주의**: Helm Release가 아님

## check-cluster-health.sh 검증 방식

### Helm Release 확인
- `kube-prometheus-stack` (monitoring)
- `aws-load-balancer-controller` (kube-system)

### Pod 상태 확인
- **ArgoCD**: `kubectl get pods -n argocd`
- **RabbitMQ**: Operator 관리 (RabbitmqCluster CR 확인)

## ArgoCD를 Helm으로 설치하려면?

현재는 `kubectl apply`로 설치하지만, Helm Chart도 사용 가능:

```bash
helm repo add argo https://argoproj.github.io/argo-helm
helm install argocd argo/argo-cd -n argocd --create-namespace
```

하지만 현재 Ansible playbook에서는 `kubectl apply` 방식을 사용하므로, 스크립트도 Pod 상태로 확인하도록 수정했습니다.

