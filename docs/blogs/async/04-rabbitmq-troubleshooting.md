# 이코에코(Eco²) 비동기 전환 #4: RabbitMQ 트러블슈팅

> 이전 글: [비동기 전환 #3: RabbitMQ 인프라 구축](./03-rabbitmq-infrastructure.md)

---

## 개요

RabbitMQ Operator를 ArgoCD로 배포하면서 발생한 문제들과 해결 과정을 기록한다. Kubernetes Operator 기반 인프라 구축 시 참고할 수 있는 실전 경험이다.

### 트러블슈팅 요약

| # | 문제 | 증상 | 원인 | 해결 시간 |
|---|------|------|------|----------|
| 1 | Operator Path 오류 | ServiceAccount not found | 잘못된 kustomize path | 10분 |
| 2 | Control-Plane Toleration | Pod Pending | 누락된 taint toleration | 15분 |
| 3 | Namespace 충돌 | Sync 실패 | 두 Operator가 동일 NS 생성 | 20분 |
| 4 | 401 Unauthorized | Topology CR Ready=False | Network Policy + 인증 | 1시간 |
| 5 | Finalizer Stuck | CR Deleting 상태 고착 | 리소스 정리 실패 | 30분 |
| 6 | DNS 미등록 | NXDOMAIN | ExternalDNS 전파 대기 | 5분 |
| 7 | Management UI 401 | 브라우저 로그인 실패 | Istio retry + localStorage | 30분 |

---

## 1. Operator Path 오류

### 증상

```bash
$ kubectl get pods -n rabbitmq-system
Error from server: pods is forbidden: error looking up service account rabbitmq-system/rabbitmq-cluster-operator: serviceaccount "rabbitmq-cluster-operator" not found
```

ArgoCD Application은 Synced 상태이지만, Operator Pod가 생성되지 않았다.

### 원인 분석

ArgoCD Application에서 잘못된 path를 참조했다:

```yaml
# 잘못된 설정
source:
  path: config/manager  # Deployment만 포함
```

`config/manager`는 Deployment 정의만 포함하고, ServiceAccount, ClusterRole, ClusterRoleBinding, Namespace, CRD가 빠져있다.

### RabbitMQ Cluster Operator 디렉토리 구조

```
cluster-operator/config/
├── crd/                    # CRD 정의만
├── manager/                # Deployment만 (❌ 불완전)
├── rbac/                   # RBAC만
├── default/                # CRD + RBAC + Deployment (NS 제외)
└── installation/           # 완전한 설치 패키지 (✅ 권장)
    ├── namespace.yaml
    ├── serviceaccount.yaml
    ├── role.yaml
    ├── clusterrole.yaml
    ├── rolebinding.yaml
    ├── clusterrolebinding.yaml
    ├── deployment.yaml
    └── kustomization.yaml
```

### 해결

```yaml
# 올바른 설정
source:
  path: config/installation  # 완전한 설치 패키지
```

**교훈**: Operator 배포 시 공식 문서에서 권장하는 설치 경로를 확인해야 한다.

---

## 2. Control-Plane Toleration 누락

### 증상

```bash
$ kubectl get pods -n rabbitmq-system
NAME                                         READY   STATUS    RESTARTS   AGE
rabbitmq-cluster-operator-6c58b89fd5-xxxxx   0/1     Pending   0          5m

$ kubectl describe pod rabbitmq-cluster-operator-xxx -n rabbitmq-system
Events:
  Warning  FailedScheduling  0/16 nodes are available:
    1 node(s) had untolerated taint {role=control-plane: NoSchedule}
    1 node(s) had untolerated taint {node-role.kubernetes.io/control-plane: }
    ...
```

### 원인 분석

Operator를 control-plane 노드에 배치하려 했으나, 두 개의 taint 중 하나만 toleration을 추가했다:

```yaml
# 누락된 설정
tolerations:
- key: role
  operator: Equal
  value: control-plane
  effect: NoSchedule
# node-role.kubernetes.io/control-plane taint 누락!
```

**k8s-master 노드의 실제 taint**:

```bash
$ kubectl describe node k8s-master | grep Taints
Taints:
  role=control-plane:NoSchedule
  node-role.kubernetes.io/control-plane:NoSchedule  # kubeadm 기본 taint
```

### 해결

두 taint 모두에 대한 toleration 추가:

```yaml
tolerations:
- key: role
  operator: Equal
  value: control-plane
  effect: NoSchedule
- key: node-role.kubernetes.io/control-plane  # 추가
  operator: Exists
  effect: NoSchedule
```

**교훈**: 노드의 실제 taint를 `kubectl describe node`로 확인한 후 toleration을 설정해야 한다.

---

## 3. Namespace 충돌

### 증상

```bash
$ kubectl get applications -n argocd
dev-rabbitmq-operator           Synced    Healthy
dev-rabbitmq-topology-operator  OutOfSync Degraded

# ArgoCD 에러 메시지
Namespace/rabbitmq-system is part of applications argocd/dev-rabbitmq-operator and argocd/dev-rabbitmq-topology-operator
```

### 원인 분석

두 Operator의 `config/installation` 경로 모두 `namespace.yaml`을 포함한다:

```
cluster-operator/config/installation/
└── namespace.yaml  # rabbitmq-system

messaging-topology-operator/config/installation/cert-manager/
└── namespace.yaml  # rabbitmq-system (동일)
```

ArgoCD는 동일 리소스가 여러 Application에 속하면 충돌로 판단한다.

### 해결

Topology Operator에서 Namespace 리소스를 제외한다:

```yaml
# 30-rabbitmq-topology-operator.yaml
source:
  kustomize:
    patches:
    - target:
        kind: Namespace
        name: rabbitmq-system
      patch: |
        $patch: delete
        apiVersion: v1
        kind: Namespace
        metadata:
          name: rabbitmq-system
destination:
  namespace: rabbitmq-system
syncPolicy:
  syncOptions:
  - CreateNamespace=false  # 중요: Cluster Operator가 이미 생성
```

**핵심 포인트**:
- `$patch: delete`로 kustomize 빌드에서 Namespace 제외
- `CreateNamespace=false`로 ArgoCD가 자동 생성하지 않도록 설정
- Cluster Operator(sync-wave 29)가 먼저 Namespace를 생성

**교훈**: 여러 Operator를 같은 namespace에 배포할 때 리소스 소유권을 명확히 해야 한다.

---

## 4. Topology Operator 401 Unauthorized

### 증상

```bash
$ kubectl get vhost -n rabbitmq
NAME         AGE   READY
eco2-vhost   10m   False

$ kubectl describe vhost eco2-vhost -n rabbitmq
Status:
  Conditions:
    Message: Error: API responded with a 401 Unauthorized
    Reason:  FailedCreateOrUpdate
    Status:  False
    Type:    Ready
```

Topology Operator가 RabbitMQ Management API에 인증 실패했다.

### 원인 분석 1: Network Policy

처음에는 Topology Operator가 RabbitMQ에 연결조차 못했다:

```bash
$ kubectl logs -n rabbitmq-system deployment/messaging-topology-operator
dial tcp 10.96.x.x:15672: connection refused
```

**문제**: Network Policy에서 `rabbitmq-system` namespace가 15672 포트 접근을 허용하지 않았다.

### 해결 1: Network Policy 수정

```yaml
# allow-rabbitmq-access.yaml
- from:
  - namespaceSelector:
      matchLabels:
        kubernetes.io/metadata.name: monitoring
  - namespaceSelector:
      matchLabels:
        kubernetes.io/metadata.name: rabbitmq-system  # 추가
  ports:
  - protocol: TCP
    port: 15672
```

### 원인 분석 2: 인증 정보 불일치

Network Policy 수정 후에도 401 오류가 지속되었다. 원인은 **credentials 불일치**였다.

**RabbitmqCluster CR의 override 설정** (문제의 설정):

```yaml
# cluster.yaml (잘못된 설정)
spec:
  override:
    statefulSet:
      spec:
        template:
          spec:
            containers:
            - name: rabbitmq
              env:
              - name: RABBITMQ_DEFAULT_USER
                valueFrom:
                  secretKeyRef:
                    name: rabbitmq-default-user  # 수동 생성 Secret
                    key: username
              - name: RABBITMQ_DEFAULT_PASS
                valueFrom:
                  secretKeyRef:
                    name: rabbitmq-default-user
                    key: password
```

**문제점**:
- Operator는 자동으로 `eco2-rabbitmq-default-user` Secret을 생성
- Topology Operator는 이 자동 생성된 Secret을 참조
- 하지만 RabbitMQ Pod는 수동 Secret의 credentials로 시작
- 결과: **credentials 불일치 → 401 Unauthorized**

```
┌──────────────────┐     "guest/guest"      ┌──────────────────┐
│ Topology Operator│ ─────────────────────▶ │    RabbitMQ      │
│ (auto-generated) │                        │ (manual secret)  │
└──────────────────┘                        └──────────────────┘
         │                                           │
         │ eco2-rabbitmq-default-user                │ rabbitmq-default-user
         │ username: default_user_xxx                │ username: admin
         │ password: abc123...                       │ password: secret123
         └───────────────────────────────────────────┘
                         불일치!
```

### 해결 2: Override 제거

RabbitmqCluster CR에서 credentials override를 제거하고, Operator 자동 생성 Secret을 사용한다:

```yaml
# cluster.yaml (올바른 설정)
spec:
  # override 섹션 제거
  # Credentials: Operator가 자동 생성하는 eco2-rabbitmq-default-user secret 사용
  # Topology Operator가 이 secret을 참조하여 Management API 인증
```

**주의**: 기존 PersistentVolume에 이전 credentials가 저장되어 있으면 Pod 재시작 후에도 이전 사용자 정보가 유지된다.

### 해결 2-1: 수동 사용자 추가 (PV 데이터 유지 시)

PV를 삭제하지 않고 해결하려면 auto-generated 사용자를 수동으로 추가:

```bash
# Auto-generated Secret 확인
$ kubectl get secret eco2-rabbitmq-default-user -n rabbitmq -o jsonpath='{.data.username}' | base64 -d
default_user_cv3Zf99xxx

$ kubectl get secret eco2-rabbitmq-default-user -n rabbitmq -o jsonpath='{.data.password}' | base64 -d
abc123xyz...

# RabbitMQ에 사용자 추가
$ kubectl exec -it eco2-rabbitmq-server-0 -n rabbitmq -- \
    rabbitmqctl add_user default_user_cv3Zf99xxx abc123xyz...

$ kubectl exec -it eco2-rabbitmq-server-0 -n rabbitmq -- \
    rabbitmqctl set_user_tags default_user_cv3Zf99xxx administrator

$ kubectl exec -it eco2-rabbitmq-server-0 -n rabbitmq -- \
    rabbitmqctl set_permissions -p / default_user_cv3Zf99xxx ".*" ".*" ".*"

$ kubectl exec -it eco2-rabbitmq-server-0 -n rabbitmq -- \
    rabbitmqctl set_permissions -p eco2 default_user_cv3Zf99xxx ".*" ".*" ".*"
```

**교훈**: 
- RabbitMQ Operator는 credentials를 자동 관리한다. 수동 override는 Topology Operator와 충돌을 일으킨다.
- Network Policy 설정 시 Operator namespace도 고려해야 한다.

---

## 5. Finalizer Stuck

### 증상

```bash
$ kubectl get vhost,exchange,queue,binding -n rabbitmq
NAME                                   AGE   READY
vhost.rabbitmq.com/eco2-vhost          1h    False

$ kubectl delete vhost eco2-vhost -n rabbitmq
# 무한 대기...

$ kubectl get vhost eco2-vhost -n rabbitmq -o yaml
metadata:
  deletionTimestamp: "2025-12-20T10:00:00Z"
  finalizers:
  - deletion.finalizers.vhosts.rabbitmq.com
```

Topology CRs가 `Deleting` 상태에서 영구히 고착되었다.

### 원인 분석

Kubernetes Custom Resource의 **Finalizer** 메커니즘:

```
┌────────────────────────────────────────────────────────────────────┐
│                     Finalizer 동작 흐름                             │
├────────────────────────────────────────────────────────────────────┤
│                                                                    │
│  1. kubectl delete vhost eco2-vhost                               │
│     ↓                                                              │
│  2. API Server: deletionTimestamp 설정                             │
│     ↓                                                              │
│  3. Topology Operator: RabbitMQ에서 vhost 삭제 시도                │
│     ↓                                                              │
│  4-a. 성공 → finalizer 제거 → CR 완전 삭제                        │
│  4-b. 실패 (401 등) → finalizer 유지 → 삭제 불가 (stuck!)         │
│                                                                    │
└────────────────────────────────────────────────────────────────────┘
```

Operator가 401 오류로 RabbitMQ와 통신할 수 없어서 finalizer를 제거하지 못했다.

### 해결: 수동 Finalizer 제거

```bash
# 단일 리소스
$ kubectl patch vhost eco2-vhost -n rabbitmq \
    --type=json \
    -p='[{"op": "remove", "path": "/metadata/finalizers"}]'

# 전체 Topology CRs (스크립트)
for type in binding exchange queue vhost; do
  for name in $(kubectl get $type -n rabbitmq -o name 2>/dev/null); do
    kubectl patch $name -n rabbitmq \
      --type=json \
      -p='[{"op": "remove", "path": "/metadata/finalizers"}]' \
      2>/dev/null || true
  done
done
```

**주의**: Finalizer를 수동 제거하면 **RabbitMQ 내부의 실제 리소스는 삭제되지 않는다**. 필요 시 `rabbitmqctl`로 수동 정리해야 한다.

### ArgoCD Application 복구

Topology CRs 삭제 후 ArgoCD Application이 `Missing` 상태가 될 수 있다:

```bash
$ kubectl get application dev-rabbitmq-topology -n argocd
NAME                    SYNC STATUS   HEALTH STATUS
dev-rabbitmq-topology   Unknown       Missing
```

**해결**: Root Application 강제 동기화

```bash
$ kubectl patch application dev-root -n argocd \
    --type=merge \
    -p '{"operation":{"sync":{"prune":true}}}'
```

**교훈**: 
- Finalizer는 Operator의 정리 작업 완료를 보장하는 메커니즘이다.
- Operator와 대상 시스템 간 통신이 실패하면 finalizer가 stuck된다.
- 강제 삭제 시 실제 리소스 정리 여부를 확인해야 한다.

---

## 6. DNS 미등록 (NXDOMAIN)

### 증상

브라우저에서 `rabbitmq.dev.growbin.app` 접속 시:

```
사이트에 연결할 수 없음
DNS_PROBE_FINISHED_NXDOMAIN
```

### 원인 분석

ExternalDNS가 Ingress annotation을 감지하고 Route53에 레코드를 생성하는 데 시간이 걸린다.

```bash
# ExternalDNS 로그 확인
$ kubectl logs -n platform-system -l app.kubernetes.io/name=external-dns --tail=50 | grep rabbitmq
time="2025-12-22T02:10:47Z" level=info msg="Desired change: CREATE rabbitmq.dev.growbin.app CNAME"
time="2025-12-22T02:10:47Z" level=info msg="3 record(s) were successfully updated"
```

DNS 레코드는 생성되었지만, 로컬 DNS 캐시에 이전 NXDOMAIN 응답이 캐시되어 있었다.

### 해결

**1. DNS 전파 확인**:

```bash
$ nslookup rabbitmq.dev.growbin.app 8.8.8.8
Server:    8.8.8.8
Address:   8.8.8.8#53

Non-authoritative answer:
rabbitmq.dev.growbin.app  canonical name = k8s-ecoecomain-xxx.ap-northeast-2.elb.amazonaws.com
```

**2. 로컬 DNS 캐시 플러시**:

```bash
# macOS
sudo dscacheutil -flushcache; sudo killall -HUP mDNSResponder

# Chrome 브라우저
chrome://net-internals/#dns → Clear host cache
```

**교훈**: 새 도메인 추가 후 접속 실패 시, 먼저 공용 DNS(8.8.8.8)로 레코드 존재를 확인하고 로컬 캐시를 플러시해야 한다.

---

## 7. Management UI 브라우저 401 Unauthorized

### 증상

```javascript
// 브라우저 콘솔
GET https://rabbitmq.dev.growbin.app/api/whoami 401 (Unauthorized)
main.js:1393 Failed to load resource: the server responded with a status of 401
```

그러나 curl로는 정상 응답:

```bash
$ curl -u 'admin:admin123' https://rabbitmq.dev.growbin.app/api/whoami
{"name":"admin","tags":["administrator"]}
```

### 원인 분석 1: Istio VirtualService retry 설정

VirtualService에 `retriable-4xx`가 포함되어 있었다:

```yaml
retries:
  attempts: 3
  retryOn: connect-failure,reset,retriable-4xx,503  # 문제!
```

**문제점**: 401 응답 시 Istio가 재시도하면서 **Authorization 헤더가 손실**될 수 있다.

### 해결 1: retriable-4xx 제거

```yaml
retries:
  attempts: 3
  retryOn: connect-failure,reset,503  # retriable-4xx 제거
```

### 원인 분석 2: 브라우저 localStorage 캐시

RabbitMQ Management UI는 로그인 정보를 **localStorage**에 저장한다. 이전 잘못된 인증 정보가 캐시되어 있으면 새 비밀번호로 로그인해도 실패한다.

```
┌─────────────────────────────────────────────────────────────────┐
│                    브라우저 인증 흐름                             │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  1. 로그인 폼에서 username/password 입력                         │
│     ↓                                                           │
│  2. JavaScript가 Base64 인코딩 후 localStorage에 저장            │
│     ↓                                                           │
│  3. API 호출 시 localStorage에서 credentials 읽어서 사용         │
│     ↓                                                           │
│  4. 이전 잘못된 credentials 캐시 → 401 Unauthorized             │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### 해결 2: localStorage 삭제

**방법 1: 시크릿/프라이빗 모드**
```
Chrome: Cmd + Shift + N
Safari: Cmd + Shift + N
```

**방법 2: 개발자 도구에서 삭제**
1. `Cmd + Option + I` (개발자 도구)
2. **Application** 탭 → **Storage** 섹션
3. **Local Storage** → `https://rabbitmq.dev.growbin.app` → Clear
4. **Cookies** → `rabbitmq.dev.growbin.app` → Clear
5. 새로고침

**방법 3: 사이트 데이터 삭제**
1. `Cmd + Shift + Delete` (캐시 삭제 창)
2. 시간 범위: 전체 기간
3. "쿠키 및 사이트 데이터" 체크
4. 삭제

### 검증

```bash
# curl로 인증 테스트
$ curl -s -u 'admin:admin123' https://rabbitmq.dev.growbin.app/api/whoami
{"name":"admin","tags":["administrator"]}
```

**교훈**:
- Istio VirtualService의 `retriable-4xx`는 인증이 필요한 서비스에서 문제를 일으킬 수 있다.
- 브라우저에서만 401 발생 시 localStorage/Cookie 캐시를 의심해야 한다.
- 시크릿 모드로 먼저 테스트하면 캐시 문제를 빠르게 확인할 수 있다.

---

## 체크리스트: RabbitMQ Operator 배포

배포 전 확인 사항:

- [ ] Cert-Manager 설치 완료 (Topology Operator Webhook용)
- [ ] 노드 taint 확인 (`kubectl describe node`)
- [ ] Operator path 확인 (`config/installation` 권장)
- [ ] Network Policy에 `rabbitmq-system` namespace 포함
- [ ] RabbitmqCluster CR에서 credentials override 사용 안 함
- [ ] Sync-wave 순서 확인 (Operator → Cluster → Topology)

---

## 참고

### 내부 문서
- [비동기 전환 #3: RabbitMQ 인프라 구축](./03-rabbitmq-infrastructure.md)

### 외부 문서
- [RabbitMQ Operator Troubleshooting](https://www.rabbitmq.com/kubernetes/operator/troubleshooting-operator)
- [Kubernetes Finalizers](https://kubernetes.io/docs/concepts/overview/working-with-objects/finalizers/)

---

## 변경 이력

| 날짜 | 버전 | 변경 내용 |
|------|------|----------|
| 2025-12-20 | 1.0 | 초안 작성 (5개 트러블슈팅 케이스) |
| 2025-12-22 | 1.1 | DNS/브라우저 인증 문제 추가 (#6, #7) |

