# 노드 변경사항 영향 분석

> 날짜: 2025-11-04  
> 목적: Storage 노드 분리(5→7 Nodes)가 NetworkPolicy, Ingress, Calico 설정에 미치는 영향 분석

---

## 📋 변경 사항 요약

### 노드 구성 변경

**Before (5 Nodes)**:
```
├─ Master (t3.large, 8GB)
├─ Worker-1 (t3.medium, 4GB)
├─ Worker-2 (t3.medium, 4GB)
├─ Storage (t3.large, 8GB) ❌ RabbitMQ + PostgreSQL + Redis
└─ Monitoring (t3.medium, 4GB)
```

**After (7 Nodes)**:
```
├─ Master (t3.large, 8GB)
├─ Worker-1 (t3.medium, 4GB)
├─ Worker-2 (t3.medium, 4GB)
├─ RabbitMQ (t3.small, 2GB) ⭐ 전용 노드
├─ PostgreSQL (t3.small, 2GB) ⭐ 전용 노드
├─ Redis (t3.small, 2GB) ⭐ 전용 노드
└─ Monitoring (t3.medium, 4GB)
```

### 노드 레이블 변경

| 노드 | Before | After | 변경 사항 |
|------|--------|-------|-----------|
| k8s-storage | `workload=storage` | (삭제) | 노드 자체 삭제 |
| k8s-rabbitmq | - | `workload=message-queue` | 신규 생성 |
| k8s-postgresql | - | `workload=database` | 신규 생성 |
| k8s-redis | - | `workload=cache` | 신규 생성 |

---

## 🔍 영향 분석

### 1️⃣ NetworkPolicy 영향

#### ✅ 결론: **영향 없음**

**이유**:
- NetworkPolicy는 **`podSelector`** 기반으로 동작
- Pod의 레이블(예: `app=postgres`, `app=redis`)을 사용하여 트래픽 제어
- 노드의 레이블(`workload=storage` → `workload=database`)과는 **독립적**

#### 예시: PostgreSQL NetworkPolicy

```yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: postgres-ingress
  namespace: default
spec:
  podSelector:
    matchLabels:
      app: postgres  # ← Pod 레이블 기반 (노드 레이블 아님!)
  policyTypes:
  - Ingress
  ingress:
  - from:
    - podSelector:
        matchLabels:
          tier: backend  # Backend Pod만 허용
    ports:
    - protocol: TCP
      port: 5432
```

**동작 확인**:
- PostgreSQL Pod가 `k8s-storage` 노드에 있든
- PostgreSQL Pod가 `k8s-postgresql` 노드에 있든
- **NetworkPolicy는 정상 작동**

#### 권장 사항

```yaml
# RabbitMQ NetworkPolicy (messaging namespace)
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: rabbitmq-ingress
  namespace: messaging
spec:
  podSelector:
    matchLabels:
      app.kubernetes.io/name: rabbitmq
  policyTypes:
  - Ingress
  ingress:
  - from:
    - podSelector:
        matchLabels:
          tier: backend
    - podSelector:
        matchLabels:
          app: celery-worker
    ports:
    - protocol: TCP
      port: 5672
```

```yaml
# Redis NetworkPolicy (default namespace)
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: redis-ingress
  namespace: default
spec:
  podSelector:
    matchLabels:
      app: redis
  policyTypes:
  - Ingress
  ingress:
  - from:
    - podSelector:
        matchLabels:
          tier: backend
    - podSelector:
        matchLabels:
          app: celery-worker
    ports:
    - protocol: TCP
      port: 6379
```

---

### 2️⃣ Ingress 영향

#### ✅ 결론: **영향 없음**

**이유**:
- Ingress는 **Service**를 통해 Pod에 접근
- ALB Controller는 `target-type: instance` 사용 → Worker Node의 **NodePort**로 트래픽 전달
- Pod가 어느 노드에 있든 **Service Discovery**를 통해 자동으로 찾아감

#### 현재 Ingress 설정

```yaml
# ArgoCD Ingress
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: argocd-ingress
  namespace: argocd
  annotations:
    alb.ingress.kubernetes.io/target-type: instance  # ← NodePort 사용
    alb.ingress.kubernetes.io/backend-protocol: HTTPS
    alb.ingress.kubernetes.io/healthcheck-path: /argocd/health
spec:
  ingressClassName: alb
  rules:
  - host: growbin.app
    http:
      paths:
      - path: /argocd
        pathType: Prefix
        backend:
          service:
            name: argocd-server
            port:
              number: 443
```

#### 트래픽 흐름

```
Internet
  ↓
Route53 (Alias → ALB DNS)
  ↓
ALB (growbin-alb)
  ↓
Target Group (instance 타입)
  ↓
Worker Node:NodePort (예: 30001)
  ↓
Service (ClusterIP - argocd-server)
  ↓
Pod (ArgoCD Server)
```

**동작 확인**:
- ArgoCD Pod가 Master 노드에 있든
- Grafana Pod가 Worker-1 노드에 있든
- API Pod가 Worker-2 노드에 있든
- **Ingress는 정상 작동**

#### target-type: instance의 중요성

```
✅ target-type: instance
  → ALB가 Worker Node IP:NodePort로 트래픽 전달
  → Calico Pod IP (192.168.x.x)가 VPC CIDR(10.0.0.0/16) 밖에 있어도 문제 없음
  → SNAT(natOutgoing: true)를 통해 응답 가능

❌ target-type: ip (사용 불가)
  → ALB가 Pod IP로 직접 트래픽 전달 시도
  → Pod IP (192.168.x.x)는 VPC CIDR 밖
  → ALB가 Pod에 접근 불가 → 504 Gateway Timeout
```

---

### 3️⃣ Calico BGP 비활성화 확인

#### ✅ 현재 설정: **BGP 비활성화됨**

**파일**: `ansible/playbooks/04-cni-install.yml`

```yaml
# BGP 완전 비활성화
- name: Calico VXLAN 전용 설정 (BGP 완전 비활성화)
  shell: |
    # 1. IP Pool을 VXLAN 전용으로 설정
    kubectl patch ippool default-ipv4-ippool --type=merge --patch='
    {
      "spec": {
        "ipipMode": "Never",
        "vxlanMode": "Always",
        "natOutgoing": true
      }
    }'
    
    # 2. BGP 완전 비활성화
    kubectl apply -f - <<EOF
    apiVersion: crd.projectcalico.org/v1
    kind: BGPConfiguration
    metadata:
      name: default
    spec:
      nodeToNodeMeshEnabled: false  # ← BGP Mesh 비활성화
      asNumber: 64512
    EOF
```

#### 검증 방법

```bash
# 1. BGPConfiguration 확인
kubectl get bgpconfiguration default -o yaml

# 예상 출력:
spec:
  nodeToNodeMeshEnabled: false  # ✅ BGP 비활성화
  asNumber: 64512

# 2. BIRD 프로세스 확인 (BGP 데몬)
kubectl exec -n kube-system $(kubectl get pods -n kube-system -l k8s-app=calico-node -o jsonpath='{.items[0].metadata.name}') -- ps aux | grep bird

# 예상 결과: 출력 없음 (BIRD 프로세스 없음)
```

#### ⚠️ BGP가 활성화되어 있다면?

**문제점**:
- VXLAN과 BGP가 동시에 활성화되면 네트워크 오버헤드 증가
- BGP는 불필요 (VXLAN이 모든 라우팅 처리)

**수정 방법**:
```bash
kubectl apply -f - <<EOF
apiVersion: crd.projectcalico.org/v1
kind: BGPConfiguration
metadata:
  name: default
spec:
  nodeToNodeMeshEnabled: false
  asNumber: 64512
EOF

# calico-node Pod 재시작
kubectl delete pods -n kube-system -l k8s-app=calico-node
```

---

### 4️⃣ Calico VXLAN: Always 확인

#### ✅ 현재 설정: **VXLAN Always 모드**

**파일**: `ansible/playbooks/04-cni-install.yml`

```yaml
# IPPool VXLAN 설정
kubectl patch ippool default-ipv4-ippool --type=merge --patch='
{
  "spec": {
    "ipipMode": "Never",
    "vxlanMode": "Always",  # ← VXLAN 항상 사용
    "natOutgoing": true     # ← SNAT 활성화
  }
}'

# FelixConfiguration 설정
kubectl apply -f - <<EOF
apiVersion: crd.projectcalico.org/v1
kind: FelixConfiguration
metadata:
  name: default
spec:
  bpfEnabled: false
  ipipEnabled: false       # ← IPIP 비활성화
  vxlanEnabled: true       # ← VXLAN 활성화
EOF

# DaemonSet 환경변수 설정
kubectl set env daemonset/calico-node -n kube-system \
  CALICO_IPV4POOL_VXLAN=Always \
  FELIX_VXLANENABLED=true
```

#### 검증 방법

```bash
# 1. IPPool 확인
kubectl get ippool default-ipv4-ippool -o yaml

# 예상 출력:
spec:
  vxlanMode: Always        # ✅
  ipipMode: Never          # ✅
  natOutgoing: true        # ✅
  cidr: 192.168.0.0/16

# 2. FelixConfiguration 확인
kubectl get felixconfiguration default -o yaml

# 예상 출력:
spec:
  vxlanEnabled: true       # ✅
  ipipEnabled: false       # ✅
  bpfEnabled: false        # ✅

# 3. calico-node 환경변수 확인
kubectl get daemonset calico-node -n kube-system -o jsonpath='{.spec.template.spec.containers[0].env}' | jq '.[] | select(.name | contains("VXLAN"))'

# 예상 출력:
{
  "name": "CALICO_IPV4POOL_VXLAN",
  "value": "Always"
}
```

#### VXLAN 모드 동작 원리

```
┌─────────────────────────────────────────────────────────────────┐
│                       Calico VXLAN Mode                         │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  Node A (10.0.1.10)              Node B (10.0.2.20)            │
│    ├─ Pod-1 (192.168.1.5)         ├─ Pod-2 (192.168.2.10)     │
│    └─ vxlan.calico (VTEP)         └─ vxlan.calico (VTEP)      │
│             ↓                              ↓                    │
│             └──────────────────────────────┘                    │
│                  VXLAN Tunnel (UDP 4789)                        │
│                                                                 │
│  ✅ Pod IP (192.168.x.x)가 VPC CIDR 밖에 있어도 문제 없음      │
│  ✅ VXLAN 터널을 통해 Node 간 Pod 통신                         │
│  ✅ natOutgoing: true → 외부 통신 시 SNAT (Node IP로 변환)    │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

#### ⚠️ VXLAN이 Never라면?

**문제점**:
- Pod 간 통신 불가
- Ingress → Service → Pod 경로 단절

**수정 방법**:
```bash
kubectl patch ippool default-ipv4-ippool --type=merge --patch='
{
  "spec": {
    "vxlanMode": "Always",
    "ipipMode": "Never",
    "natOutgoing": true
  }
}'

# calico-node Pod 재시작
kubectl delete pods -n kube-system -l k8s-app=calico-node
```

---

## 🛠️ 노드 변경 후 검증 스크립트

### 자동 점검 스크립트

**파일**: `scripts/diagnostics/check-node-changes-impact.sh`

```bash
#!/bin/bash
# 노드 변경사항이 NetworkPolicy, Ingress, Calico 설정에 미치는 영향 점검

MASTER_IP="52.79.238.50"
SSH_KEY="~/.ssh/sesacthon.pem"

# 1. 노드 구성 확인
ssh -i "$SSH_KEY" ubuntu@"$MASTER_IP" \
  "kubectl get nodes -L workload"

# 2. NetworkPolicy 확인
ssh -i "$SSH_KEY" ubuntu@"$MASTER_IP" \
  "kubectl get networkpolicy -A"

# 3. Ingress target-type 확인
ssh -i "$SSH_KEY" ubuntu@"$MASTER_IP" \
  "kubectl get ingress -A -o jsonpath='{.items[*].metadata.annotations.alb\.ingress\.kubernetes\.io/target-type}'"

# 4. Calico BGP 확인
ssh -i "$SSH_KEY" ubuntu@"$MASTER_IP" \
  "kubectl get bgpconfiguration default -o yaml"

# 5. Calico VXLAN 확인
ssh -i "$SSH_KEY" ubuntu@"$MASTER_IP" \
  "kubectl get ippool default-ipv4-ippool -o yaml"
```

### 실행 방법

```bash
cd /Users/mango/workspace/SeSACTHON/backend

# 스크립트 실행
./scripts/diagnostics/check-node-changes-impact.sh

# 또는 Master IP 지정
./scripts/diagnostics/check-node-changes-impact.sh 52.79.238.50
```

### 예상 출력

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
【1】 노드 구성 변경 확인
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📋 현재 노드 목록 (workload 레이블 포함):
NAME             STATUS   WORKLOAD
k8s-master       Ready    <none>
k8s-worker-1     Ready    application
k8s-worker-2     Ready    async-workers
k8s-rabbitmq     Ready    message-queue
k8s-postgresql   Ready    database
k8s-redis        Ready    cache
k8s-monitoring   Ready    monitoring

📊 총 노드 수: 7
✅ 예상대로 7개 노드

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
【2】 NetworkPolicy 영향 분석
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📝 결론:
  ✅ NetworkPolicy는 Pod 레이블(podSelector) 기반
  ✅ 노드 레이블(nodeSelector) 변경은 NetworkPolicy에 영향 없음

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
【3】 Ingress 설정 검증
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📌 argocd-ingress (argocd):
  ✅ target-type: instance (올바름)

📌 grafana-ingress (monitoring):
  ✅ target-type: instance (올바름)

📌 api-ingress (default):
  ✅ target-type: instance (올바름)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
【4】 Calico BGP 비활성화 확인
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

✅ nodeToNodeMeshEnabled: false (BGP 비활성화)
✅ BIRD 프로세스 없음

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
【5】 Calico VXLAN 모드 확인
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📋 IPPool 설정:
  ✅ vxlanMode: Always
  ✅ ipipMode: Never
  ✅ natOutgoing: true

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
✅ 점검 완료!
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

---

## 📊 최종 요약

### 영향 분석 결과

| 항목 | 영향 여부 | 이유 |
|------|-----------|------|
| **NetworkPolicy** | ✅ **영향 없음** | podSelector 기반 (Pod 레이블 사용) |
| **Ingress** | ✅ **영향 없음** | Service Discovery + target-type: instance |
| **Calico BGP** | ✅ **이미 비활성화** | nodeToNodeMeshEnabled: false |
| **Calico VXLAN** | ✅ **Always 모드** | vxlanMode: Always, natOutgoing: true |

### 노드 변경 후 필요한 작업

1. **Pod 재배치 확인**:
   ```bash
   kubectl get pods -o wide --all-namespaces
   ```
   - RabbitMQ → `k8s-rabbitmq` 노드
   - PostgreSQL → `k8s-postgresql` 노드
   - Redis → `k8s-redis` 노드

2. **NetworkPolicy 추가 (권장)**:
   - RabbitMQ, PostgreSQL, Redis에 대한 NetworkPolicy 생성
   - Zero Trust 보안 강화

3. **모니터링**:
   - 각 노드의 리소스 사용량 확인
   - Pod 간 통신 정상 여부 확인

---

## 🎯 결론

**Storage 노드를 RabbitMQ, PostgreSQL, Redis로 분리하는 작업은**:

✅ **NetworkPolicy에 영향 없음** (podSelector 기반)  
✅ **Ingress에 영향 없음** (Service Discovery + target-type: instance)  
✅ **Calico BGP는 이미 비활성화됨** (nodeToNodeMeshEnabled: false)  
✅ **Calico VXLAN은 Always 모드** (vxlanMode: Always)  

**따라서, 노드 분리 작업은 네트워크 정책, Ingress, CNI 설정에 영향을 주지 않으며 안전하게 진행할 수 있습니다.** 🎉

