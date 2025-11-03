# Helm Release 상태 확인 가이드

## `helm list` 빈 값이 나오는 이유

`helm list`는 기본적으로 **현재 namespace** 또는 **default namespace**의 Release만 보여줍니다.

### 올바른 확인 방법

#### 1. 모든 namespace의 Release 확인
```bash
helm list -A
```

#### 2. 특정 namespace의 Release 확인
```bash
# Monitoring (Prometheus, Grafana)
helm list -n monitoring

# ArgoCD
helm list -n argocd

# kube-system (ALB Controller)
helm list -n kube-system
```

#### 3. 상세 정보와 함께 확인
```bash
helm list -A -o table
```

## 현재 클러스터의 Helm Release 예상 위치

### ✅ 정상적으로 설치되어 있을 Release

1. **prometheus** (monitoring namespace)
   ```bash
   helm list -n monitoring
   ```
   - Chart: `kube-prometheus-stack`
   - Status: `deployed`

2. **argocd** (argocd namespace)
   ```bash
   helm list -n argocd
   ```
   - Chart: `argo-cd`
   - Status: `deployed`

3. **aws-load-balancer-controller** (kube-system namespace)
   ```bash
   helm list -n kube-system
   ```
   - Chart: `aws-load-balancer-controller`
   - Status: `deployed`

### ❌ Helm Release가 아닌 것

- **RabbitMQ**: Operator로 관리 (RabbitmqCluster CR)
  - `kubectl get rabbitmqcluster -n messaging`
  - `helm list`에 표시되지 않음 (정상)

## 상태 확인 명령어 체크리스트

### Master 노드에서 실행

```bash
# 1. 모든 Helm Release 확인
helm list -A

# 2. Monitoring 확인
helm list -n monitoring
helm status prometheus -n monitoring

# 3. ArgoCD 확인
helm list -n argocd
helm status argocd -n argocd

# 4. ALB Controller 확인
helm list -n kube-system
helm status aws-load-balancer-controller -n kube-system

# 5. Pod로 확인 (Helm이 없어도)
kubectl get pods -n monitoring
kubectl get pods -n argocd
```

## 문제 해결

### `helm list`가 빈 값인 경우

1. **namespace를 지정하지 않았을 때**
   ```bash
   # ❌ 잘못된 방법 (default namespace만 확인)
   helm list
   
   # ✅ 올바른 방법
   helm list -A  # 모든 namespace
   helm list -n monitoring  # 특정 namespace
   ```

2. **Helm이 설치되지 않았을 때**
   ```bash
   which helm
   # 없으면: kubectl로 Pod 상태 확인
   kubectl get pods -n monitoring
   ```

3. **Release가 실제로 없을 때**
   - Pod는 실행 중이지만 Helm Release가 없는 경우
   - 직접 `kubectl apply`로 배포된 경우

## check-cluster-health.sh 동작 방식

스크립트는 다음 순서로 확인합니다:

1. `helm status` 명령으로 상태 확인 시도
2. 실패 시 `helm list -n <namespace>`로 재확인
3. 그래도 없으면 Pod 상태로 확인

따라서 `helm list`만 실행하면 빈 값이 나올 수 있지만, 스크립트는 namespace를 지정하므로 정상 작동합니다.

