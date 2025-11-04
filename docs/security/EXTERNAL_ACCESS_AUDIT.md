# 외부 접근 차단 점검 및 보안 강화

> 날짜: 2025-11-04  
> 목적: MQ, Redis, PostgreSQL 외부 접근 완전 차단 확인 및 NetworkPolicy 적용

---

## ✅ 현재 상태 점검

### 1. RabbitMQ (Message Queue)

**파일**: `ansible/roles/rabbitmq/tasks/main.yml` (Line 115-116)

```yaml
service:
  type: ClusterIP  ✅ 외부 접근 차단
```

**상태**: 
- ✅ **ClusterIP**: 클러스터 내부에서만 접근 가능
- ✅ **포트 노출 없음**: NodePort, LoadBalancer 사용 안 함
- ✅ **DNS**: `rabbitmq.messaging.svc.cluster.local:5672` (내부 전용)
- ℹ️ **Management UI**: `kubectl port-forward`로만 접근 가능

---

### 2. Redis (Cache & State)

**파일**: `ansible/roles/redis/tasks/main.yml` (Line 98)

```yaml
spec:
  type: ClusterIP  ✅ 외부 접근 차단
  ports:
  - port: 6379
    targetPort: 6379
    name: redis
```

**상태**:
- ✅ **ClusterIP**: 클러스터 내부에서만 접근 가능
- ✅ **포트 노출 없음**: NodePort, LoadBalancer 사용 안 함
- ✅ **DNS**: `redis.default.svc.cluster.local:6379` (내부 전용)
- ❌ **인증 없음**: Redis AUTH 미설정 (내부 전용이므로 선택사항)

---

### 3. PostgreSQL (Database)

**파일**: `ansible/roles/postgresql/tasks/main.yml` (Line 115)

```yaml
spec:
  type: ClusterIP  ✅ 외부 접근 차단
  ports:
  - port: 5432
    targetPort: 5432
    protocol: TCP
```

**상태**:
- ✅ **ClusterIP**: 클러스터 내부에서만 접근 가능
- ✅ **포트 노출 없음**: NodePort, LoadBalancer 사용 안 함
- ✅ **DNS**: `postgres.default.svc.cluster.local:5432` (내부 전용)
- ✅ **인증**: PostgreSQL 비밀번호 Secret으로 관리

---

## 🔒 보안 강화: NetworkPolicy 추가

현재 ClusterIP만으로도 외부 접근은 차단되지만, **클러스터 내부에서도 허가된 Pod만 접근**하도록 NetworkPolicy를 추가합니다.

### 1. RabbitMQ NetworkPolicy

**파일**: `ansible/roles/rabbitmq/tasks/networkpolicy.yml` (NEW)

```yaml
---
# RabbitMQ NetworkPolicy - Celery Worker만 접근 허용
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
  # 1. Celery Workers (Async Workers) 허용
  - from:
    - namespaceSelector:
        matchLabels:
          name: default
      podSelector:
        matchLabels:
          app: celery-worker
    ports:
    - protocol: TCP
      port: 5672  # AMQP
  
  # 2. RabbitMQ Management (클러스터 내부 모니터링)
  - from:
    - namespaceSelector:
        matchLabels:
          name: monitoring
      podSelector:
        matchLabels:
          app: prometheus
    ports:
    - protocol: TCP
      port: 15672  # Management
  
  # 3. RabbitMQ 클러스터 내부 통신 (확장 시)
  - from:
    - podSelector:
        matchLabels:
          app.kubernetes.io/name: rabbitmq
    ports:
    - protocol: TCP
      port: 4369   # epmd
    - protocol: TCP
      port: 25672  # inter-node

---
# RabbitMQ Egress Policy (필요 시)
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: rabbitmq-egress
  namespace: messaging
spec:
  podSelector:
    matchLabels:
      app.kubernetes.io/name: rabbitmq
  policyTypes:
  - Egress
  egress:
  # DNS 해석 허용
  - to:
    - namespaceSelector:
        matchLabels:
          name: kube-system
      podSelector:
        matchLabels:
          k8s-app: kube-dns
    ports:
    - protocol: UDP
      port: 53
  
  # RabbitMQ 클러스터 내부 통신
  - to:
    - podSelector:
        matchLabels:
          app.kubernetes.io/name: rabbitmq
```

---

### 2. Redis NetworkPolicy

**파일**: `ansible/roles/redis/tasks/networkpolicy.yml` (NEW)

```yaml
---
# Redis NetworkPolicy - FastAPI + Celery만 접근 허용
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
  # 1. FastAPI 애플리케이션 허용
  - from:
    - podSelector:
        matchLabels:
          app: fastapi
    ports:
    - protocol: TCP
      port: 6379
  
  # 2. Celery Workers 허용 (Result Backend)
  - from:
    - podSelector:
        matchLabels:
          app: celery-worker
    ports:
    - protocol: TCP
      port: 6379
  
  # 3. Backend 서비스 허용
  - from:
    - podSelector:
        matchLabels:
          tier: backend
    ports:
    - protocol: TCP
      port: 6379

---
# Redis Egress Policy
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: redis-egress
  namespace: default
spec:
  podSelector:
    matchLabels:
      app: redis
  policyTypes:
  - Egress
  egress:
  # DNS 해석만 허용
  - to:
    - namespaceSelector:
        matchLabels:
          name: kube-system
      podSelector:
        matchLabels:
          k8s-app: kube-dns
    ports:
    - protocol: UDP
      port: 53
```

---

### 3. PostgreSQL NetworkPolicy

**파일**: `ansible/roles/postgresql/tasks/networkpolicy.yml` (NEW)

```yaml
---
# PostgreSQL NetworkPolicy - FastAPI + Celery만 접근 허용
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: postgres-ingress
  namespace: default
spec:
  podSelector:
    matchLabels:
      app: postgres
  policyTypes:
  - Ingress
  ingress:
  # 1. FastAPI 애플리케이션 허용
  - from:
    - podSelector:
        matchLabels:
          app: fastapi
    ports:
    - protocol: TCP
      port: 5432
  
  # 2. Backend 서비스 허용
  - from:
    - podSelector:
        matchLabels:
          tier: backend
    ports:
    - protocol: TCP
      port: 5432
  
  # 3. Celery Workers 허용 (필요 시)
  - from:
    - podSelector:
        matchLabels:
          app: celery-worker
    ports:
    - protocol: TCP
      port: 5432

---
# PostgreSQL Egress Policy
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: postgres-egress
  namespace: default
spec:
  podSelector:
    matchLabels:
      app: postgres
  policyTypes:
  - Egress
  egress:
  # DNS 해석만 허용
  - to:
    - namespaceSelector:
        matchLabels:
          name: kube-system
      podSelector:
        matchLabels:
          k8s-app: kube-dns
    ports:
    - protocol: UDP
      port: 53
  
  # PostgreSQL Replication (확장 시)
  - to:
    - podSelector:
        matchLabels:
          app: postgres
    ports:
    - protocol: TCP
      port: 5432
```

---

## 🔧 Ansible 통합

### ansible/roles/rabbitmq/tasks/main.yml

```yaml
# 기존 RabbitMQ 설치 후 추가
- name: RabbitMQ NetworkPolicy 적용
  shell: |
    kubectl apply -f - <<EOF
    apiVersion: networking.k8s.io/v1
    kind: NetworkPolicy
    metadata:
      name: rabbitmq-ingress
      namespace: {{ rabbitmq_namespace }}
    spec:
      podSelector:
        matchLabels:
          app.kubernetes.io/name: rabbitmq
      policyTypes:
      - Ingress
      ingress:
      - from:
        - namespaceSelector:
            matchLabels:
              kubernetes.io/metadata.name: default
          podSelector:
            matchLabels:
              app: celery-worker
        ports:
        - protocol: TCP
          port: 5672
      - from:
        - podSelector:
            matchLabels:
              app.kubernetes.io/name: rabbitmq
        ports:
        - protocol: TCP
          port: 4369
        - protocol: TCP
          port: 25672
    EOF
  register: rabbitmq_netpol
  changed_when: "'created' in rabbitmq_netpol.stdout or 'configured' in rabbitmq_netpol.stdout"
```

### ansible/roles/redis/tasks/main.yml

```yaml
# Redis Service 생성 후 추가
- name: Redis NetworkPolicy 적용
  shell: |
    kubectl apply -f - <<EOF
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
        ports:
        - protocol: TCP
          port: 6379
      - from:
        - podSelector:
            matchLabels:
              app: celery-worker
        ports:
        - protocol: TCP
          port: 6379
    EOF
  register: redis_netpol
  changed_when: "'created' in redis_netpol.stdout or 'configured' in redis_netpol.stdout"
```

### ansible/roles/postgresql/tasks/main.yml

```yaml
# PostgreSQL Service 생성 후 추가
- name: PostgreSQL NetworkPolicy 적용
  shell: |
    kubectl apply -f - <<EOF
    apiVersion: networking.k8s.io/v1
    kind: NetworkPolicy
    metadata:
      name: postgres-ingress
      namespace: {{ postgres_namespace }}
    spec:
      podSelector:
        matchLabels:
          app: postgres
      policyTypes:
      - Ingress
      ingress:
      - from:
        - podSelector:
            matchLabels:
              tier: backend
        ports:
        - protocol: TCP
          port: 5432
      - from:
        - podSelector:
            matchLabels:
              app: celery-worker
        ports:
        - protocol: TCP
          port: 5432
    EOF
  register: postgres_netpol
  changed_when: "'created' in postgres_netpol.stdout or 'configured' in postgres_netpol.stdout"
```

---

## 📊 보안 수준 비교

### Before (ClusterIP만)

```
외부 → ❌ 차단 (ClusterIP)
클러스터 내 모든 Pod → ✅ 접근 가능
```

**문제점**:
- 클러스터 내 악의적인 Pod가 DB/MQ/Cache 접근 가능
- 테스트 Pod, 임시 Pod도 접근 가능
- 최소 권한 원칙 위반

---

### After (ClusterIP + NetworkPolicy)

```
외부 → ❌ 차단 (ClusterIP)
클러스터 내 허가된 Pod → ✅ 접근 가능
클러스터 내 기타 Pod → ❌ 차단 (NetworkPolicy)
```

**장점**:
- ✅ 최소 권한 원칙 준수
- ✅ Zero Trust 네트워크
- ✅ 공격 표면 최소화
- ✅ 규정 준수 (Compliance)

---

## 🔍 점검 스크립트

### scripts/diagnostics/check-network-security.sh

```bash
#!/bin/bash
# 네트워크 보안 점검 스크립트

set -e

MASTER_IP=${1:-""}
SSH_USER=${2:-"ubuntu"}

if [ -z "$MASTER_IP" ]; then
    echo "사용법: $0 <MASTER_IP> [SSH_USER]"
    exit 1
fi

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🔒 네트워크 보안 점검"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

ssh $SSH_USER@$MASTER_IP << 'EOF'
echo "1️⃣ Service 타입 확인"
echo ""
echo "RabbitMQ:"
kubectl get svc -n messaging rabbitmq -o jsonpath='{.spec.type}' 2>/dev/null || echo "  Service 없음"
echo ""

echo "Redis:"
kubectl get svc -n default redis -o jsonpath='{.spec.type}' 2>/dev/null || echo "  Service 없음"
echo ""

echo "PostgreSQL:"
kubectl get svc -n default postgres -o jsonpath='{.spec.type}' 2>/dev/null || echo "  Service 없음"
echo ""
echo ""

echo "2️⃣ NetworkPolicy 확인"
echo ""
echo "RabbitMQ:"
kubectl get networkpolicy -n messaging rabbitmq-ingress 2>/dev/null && echo "  ✅ NetworkPolicy 있음" || echo "  ⚠️  NetworkPolicy 없음"

echo "Redis:"
kubectl get networkpolicy -n default redis-ingress 2>/dev/null && echo "  ✅ NetworkPolicy 있음" || echo "  ⚠️  NetworkPolicy 없음"

echo "PostgreSQL:"
kubectl get networkpolicy -n default postgres-ingress 2>/dev/null && echo "  ✅ NetworkPolicy 있음" || echo "  ⚠️  NetworkPolicy 없음"
echo ""
echo ""

echo "3️⃣ 외부 포트 노출 확인"
echo ""
NODEPORTS=$(kubectl get svc -A -o json | jq -r '.items[] | select(.spec.type=="NodePort") | "\(.metadata.name) (\(.metadata.namespace))"')
if [ -z "$NODEPORTS" ]; then
    echo "  ✅ NodePort Service 없음 (안전)"
else
    echo "  ⚠️  NodePort Service 발견:"
    echo "$NODEPORTS"
fi
echo ""

LOADBALANCERS=$(kubectl get svc -A -o json | jq -r '.items[] | select(.spec.type=="LoadBalancer") | "\(.metadata.name) (\(.metadata.namespace))"')
if [ -z "$LOADBALANCERS" ]; then
    echo "  ✅ LoadBalancer Service 없음 (안전)"
else
    echo "  ⚠️  LoadBalancer Service 발견:"
    echo "$LOADBALANCERS"
fi
echo ""

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✅ 점검 완료"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
EOF
```

---

## ✅ 점검 결과 요약

### 현재 상태

| 서비스 | Service 타입 | 외부 접근 | NetworkPolicy | 상태 |
|--------|-------------|----------|---------------|------|
| RabbitMQ | ClusterIP | ❌ 차단 | ⚠️ 없음 | 기본 안전 |
| Redis | ClusterIP | ❌ 차단 | ⚠️ 없음 | 기본 안전 |
| PostgreSQL | ClusterIP | ❌ 차단 | ⚠️ 없음 | 기본 안전 |

### 권장 사항

✅ **즉시 적용**:
1. NetworkPolicy 추가 (RabbitMQ, Redis, PostgreSQL)
2. Pod 레이블 표준화 (`tier: backend`, `app: celery-worker` 등)
3. 네임스페이스 레이블 추가 (`name: default`, `name: messaging`)

✅ **추가 보안**:
1. Redis AUTH 설정 (선택사항)
2. PostgreSQL SSL/TLS 설정
3. RabbitMQ TLS 설정
4. 정기적 보안 스캔

---

## 🎯 결론

### 현재
- ✅ **외부 접근**: 완전 차단 (ClusterIP)
- ⚠️ **내부 접근**: 모든 Pod 접근 가능

### 권장
- ✅ **외부 접근**: 완전 차단 (ClusterIP)
- ✅ **내부 접근**: 허가된 Pod만 (NetworkPolicy)

**NetworkPolicy를 추가하면 Zero Trust 아키텍처 구현 완료!** 🔒

---

**작성일**: 2025-11-04  
**버전**: 1.0.0

