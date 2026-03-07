# 이코에코(Eco²) Redis Streams for SSE #2: 3-Node Redis Cluster 선언적 배포 (GitOps)

> **작성일**: 2025-12-26  
> **시리즈**: Redis Streams for SSE  
> **이전**: [#1 리소스 프로비저닝](./01-provisioning.md)

---

## 개요

EC2 노드 프로비저닝 후 Kubernetes 위에 Redis를 선언적으로 배포합니다.
Spotahome Redis Operator를 사용하여 Redis + Sentinel HA 구성을 자동화합니다.

---

## Operator 선정: Spotahome vs Bitnami

### 후보 비교

| 기준 | Spotahome Redis Operator | Bitnami Redis (Helm) |
|------|--------------------------|----------------------|
| 배포 방식 | CRD + Operator | Helm Chart |
| HA 구현 | Redis + Sentinel (자동) | 수동 설정 필요 |
| Failover | 자동 (Sentinel 관리) | 수동 또는 외부 도구 |
| 리소스 관리 | CR 단위 선언적 관리 | values.yaml |
| GitOps 친화도 | 높음 (CR = YAML) | 중간 (Helm values) |
| 유지보수 | Operator가 조정(Reconcile) | 직접 관리 |

### Spotahome 선정 이유

1. **선언적 관리**: `RedisFailover` CR 하나로 Redis + Sentinel 구성
2. **자동 Failover**: Master 장애 시 Sentinel이 자동으로 Replica 승격
3. **GitOps 적합**: ArgoCD App-of-Apps 패턴과 자연스럽게 통합
4. **운영 부담 최소화**: Operator가 상태를 지속적으로 조정(Reconcile)

---

## Spotahome Redis Operator 아키텍처

```
┌─────────────────────────────────────────────────────────────┐
│                    Kubernetes Cluster                        │
│                                                              │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  redis-operator (Deployment)                          │   │
│  │  ├─ Watch: RedisFailover CRs                          │   │
│  │  ├─ Create: StatefulSet, Service, ConfigMap           │   │
│  │  └─ Reconcile: 원하는 상태와 현재 상태 동기화          │   │
│  └──────────────────────────────────────────────────────┘   │
│                           │                                  │
│                           ▼                                  │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  RedisFailover CR (auth-redis)                        │   │
│  │                                                        │   │
│  │  ┌─────────────────┐  ┌─────────────────┐            │   │
│  │  │ Redis Master    │  │ Redis Replica   │            │   │
│  │  │ (rfr-auth-redis)│  │ (rfr-auth-redis)│            │   │
│  │  └────────┬────────┘  └────────┬────────┘            │   │
│  │           │                    │                      │   │
│  │  ┌────────┴────────────────────┴────────┐            │   │
│  │  │         Sentinel Cluster             │            │   │
│  │  │  ├─ Master 모니터링                  │            │   │
│  │  │  ├─ Failover 판단 (quorum)           │            │   │
│  │  │  └─ 클라이언트 리디렉션              │            │   │
│  │  └─────────────────────────────────────┘            │   │
│  └──────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

### 생성되는 리소스

| CRD | 생성 리소스 |
|-----|-------------|
| RedisFailover | StatefulSet (Redis), StatefulSet (Sentinel), Service, ConfigMap |

### 서비스 네이밍 규칙

```
rfr-<name>    # Redis Master/Replica Service
rfs-<name>    # Sentinel Service
```

예: `rfr-auth-redis.redis.svc.cluster.local:6379`

---

## RedisFailover CR 설계

### auth-redis (보안 데이터)

```yaml
apiVersion: databases.spotahome.com/v1
kind: RedisFailover
metadata:
  name: auth-redis
  namespace: redis
  labels:
    app: auth-redis
    purpose: auth
spec:
  sentinel:
    replicas: 3      # Quorum 보장 (2/3)
    resources:
      limits:
        cpu: 100m
        memory: 128Mi
    customConfig:
      - down-after-milliseconds 5000
      - failover-timeout 10000
    affinity:
      nodeAffinity:
        requiredDuringSchedulingIgnoredDuringExecution:
          nodeSelectorTerms:
            - matchExpressions:
                - key: redis-cluster
                  operator: In
                  values: [auth]

  redis:
    replicas: 3      # Master 1 + Replica 2
    resources:
      limits:
        cpu: 300m
        memory: 512Mi
    storage:
      persistentVolumeClaim:
        spec:
          accessModes: [ReadWriteOnce]
          storageClassName: gp3
          resources:
            requests:
              storage: 1Gi
    customConfig:
      - "maxmemory 256mb"
      - "maxmemory-policy noeviction"  # 보안 데이터 보호
      - "appendonly yes"               # AOF 영속성
    affinity:
      nodeAffinity:
        requiredDuringSchedulingIgnoredDuringExecution:
          nodeSelectorTerms:
            - matchExpressions:
                - key: redis-cluster
                  operator: In
                  values: [auth]
    exporter:
      enabled: true
      image: oliver006/redis_exporter:v1.62.0
```

**설계 근거**:
- **replicas: 3**: Sentinel quorum(2/3)과 Redis Master + 2 Replica
- **noeviction**: JWT Blacklist, OAuth State는 삭제되면 안 됨
- **PVC**: Master 장애 후 Replica 승격 시 데이터 보존

### streams-redis (SSE 이벤트)

```yaml
apiVersion: databases.spotahome.com/v1
kind: RedisFailover
metadata:
  name: streams-redis
  namespace: redis
spec:
  sentinel:
    replicas: 1      # dev: 최소 구성
  redis:
    replicas: 1
    resources:
      limits:
        cpu: 200m
        memory: 512Mi
    storage:
      emptyDir: {}   # 휘발성 (TTL로 자동 정리)
    customConfig:
      - "maxmemory 256mb"
      - "maxmemory-policy noeviction"  # 이벤트 유실 방지
    affinity:
      nodeAffinity:
        requiredDuringSchedulingIgnoredDuringExecution:
          nodeSelectorTerms:
            - matchExpressions:
                - key: redis-cluster
                  operator: In
                  values: [streams]
    exporter:
      enabled: true
```

**설계 근거**:
- **replicas: 1 (dev)**: 비용 절감, prod에서는 3으로 확장
- **emptyDir**: SSE 이벤트는 TTL(1시간)로 자동 삭제, 영속성 불필요
- **noeviction**: 처리 전 이벤트가 eviction되면 SSE 스트림 끊김

### cache-redis (Celery 결과)

```yaml
apiVersion: databases.spotahome.com/v1
kind: RedisFailover
metadata:
  name: cache-redis
  namespace: redis
spec:
  sentinel:
    replicas: 1
  redis:
    replicas: 1
    resources:
      limits:
        cpu: 300m
        memory: 768Mi
    storage:
      emptyDir: {}
    customConfig:
      - "maxmemory 512mb"
      - "maxmemory-policy allkeys-lru"  # 메모리 부족 시 eviction
    affinity:
      nodeAffinity:
        requiredDuringSchedulingIgnoredDuringExecution:
          nodeSelectorTerms:
            - matchExpressions:
                - key: redis-cluster
                  operator: In
                  values: [cache]
    exporter:
      enabled: true
```

**설계 근거**:
- **allkeys-lru**: Celery 결과는 일정 시간 후 불필요, eviction 허용
- **emptyDir**: 캐시 데이터는 휘발성, 재시작 시 재생성 가능

---

## Eviction Policy 비교

| Redis 인스턴스 | Policy | 근거 |
|----------------|--------|------|
| auth-redis | noeviction | JWT Blacklist 삭제 시 만료된 토큰 재사용 가능 |
| streams-redis | noeviction | 처리 전 이벤트 삭제 시 SSE 스트림 끊김 |
| cache-redis | allkeys-lru | 오래된 Celery 결과는 eviction해도 무방 |

---

## ArgoCD Sync-wave 전략

### 의존성 순서

```
Sync-wave 24: PostgreSQL
Sync-wave 27: Redis Operator (CRD + Deployment)
Sync-wave 28: RedisFailover CRs (auth, streams, cache)
Sync-wave 29+: 애플리케이션 (Redis 의존)
```

### ArgoCD Application 구성

```yaml
# clusters/dev/apps/27-redis-operator.yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: dev-redis-operator
  namespace: argocd
  annotations:
    argocd.argoproj.io/sync-wave: "27"
spec:
  source:
    repoURL: https://spotahome.github.io/redis-operator
    chart: redis-operator
    targetRevision: 3.3.0
    helm:
      values: |
        replicas: 1
        image:
          repository: quay.io/spotahome/redis-operator
          tag: v1.3.0
        resources:
          requests:
            cpu: 100m
            memory: 128Mi
          limits:
            cpu: 200m
            memory: 256Mi
        # Control Plane 노드에 배치
        nodeSelector:
          role: control-plane
        tolerations:
          - key: node-role.kubernetes.io/control-plane
            operator: Exists
            effect: NoSchedule
        serviceAccount:
          create: true
        monitoring:
          enabled: false
  destination:
    server: https://kubernetes.default.svc
    namespace: redis-operator

---
# clusters/dev/apps/28-redis-cluster.yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: dev-redis-cluster
  namespace: argocd
  annotations:
    argocd.argoproj.io/sync-wave: "28"
spec:
  source:
    repoURL: https://github.com/eco2-team/backend.git
    path: workloads/redis/dev
    targetRevision: develop
  destination:
    server: https://kubernetes.default.svc
    namespace: redis
```

**sync-wave 간격의 의미**:
- 27 → 28: Operator가 CRD를 등록한 후 CR 생성
- CR이 먼저 생성되면 `no matches for kind "RedisFailover"` 에러

---

## Kustomize 구조

```
workloads/redis/
├── base/
│   ├── auth-redis-failover.yaml
│   ├── streams-redis-failover.yaml
│   ├── cache-redis-failover.yaml
│   └── kustomization.yaml
├── dev/
│   └── kustomization.yaml        # replicas: 1 patch
└── prod/
    └── kustomization.yaml        # replicas: 3 patch
```

### Dev 환경 Patch

```yaml
# workloads/redis/dev/kustomization.yaml
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization

resources:
  - ../base

patches:
  # HA 비활성 (dev: replicas 1)
  - patch: |
      - op: replace
        path: /spec/sentinel/replicas
        value: 1
      - op: replace
        path: /spec/redis/replicas
        value: 1
    target:
      group: databases.spotahome.com
      version: v1
      kind: RedisFailover
```

### Prod 환경

```yaml
# workloads/redis/prod/kustomization.yaml
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization

resources:
  - ../base

# base가 이미 replicas: 3이므로 추가 patch 불필요
```

---

## 환경변수 매핑

### External Secrets → Deployment

```yaml
# workloads/secrets/external-secrets/dev/api-secrets.yaml
apiVersion: external-secrets.io/v1beta1
kind: ExternalSecret
spec:
  data:
    - secretKey: AUTH_REDIS_BLACKLIST_URL
      remoteRef:
        key: eco2/dev/api
        property: AUTH_REDIS_BLACKLIST_URL
        # 값: redis://rfr-auth-redis.redis.svc.cluster.local:6379/0
```

### 서비스별 Redis 매핑

| 환경변수 | Redis 인스턴스 | DB | 용도 |
|----------|----------------|-----|------|
| AUTH_REDIS_BLACKLIST_URL | rfr-auth-redis | 0 | JWT Blacklist |
| AUTH_REDIS_OAUTH_STATE_URL | rfr-auth-redis | 3 | OAuth State |
| REDIS_STREAMS_URL | rfr-streams-redis | 0 | SSE Events |
| CELERY_RESULT_BACKEND | rfr-cache-redis | 0 | Task Results |
| IMAGE_REDIS_URL | rfr-cache-redis | 6 | Image Cache |

---

## 배포 확인 (실측)

### ArgoCD Sync

```bash
kubectl get applications -n argocd | grep redis

NAME                   SYNC STATUS   HEALTH STATUS
dev-redis-cluster      Synced        Healthy
dev-redis-operator     Synced        Healthy
```

### Redis Operator

```bash
kubectl get pods -n redis-operator -o wide

NAME                                  READY   STATUS    NODE
dev-redis-operator-5fc99ccfcf-ckqqz   1/1     Running   k8s-master
```

### RedisFailover 상태

```bash
kubectl get redisfailover -n redis

NAME            REDIS   SENTINELS   AGE
auth-redis      1       1           20m
cache-redis     1       1           20m
streams-redis   1       1           20m
```

### Pod 확인

```bash
kubectl get pods -n redis -o wide

NAME                                 READY   STATUS    NODE
rfr-auth-redis-0                     3/3     Running   k8s-redis-auth
rfr-cache-redis-0                    3/3     Running   k8s-redis-cache
rfr-streams-redis-0                  3/3     Running   k8s-redis-streams
rfs-auth-redis-66bf8f9657-dzp7v      2/2     Running   k8s-redis-auth
rfs-cache-redis-7845fbdd47-l27dr     2/2     Running   k8s-redis-cache
rfs-streams-redis-7d9c9986d9-twjdx   2/2     Running   k8s-redis-streams
```

> **Note**: `rfr-*` Pod는 `3/3` (Redis + Exporter + Sentinel sidecar), `rfs-*`는 `2/2` (Sentinel + Exporter)

### Services

```bash
kubectl get svc -n redis

NAME                TYPE        CLUSTER-IP       PORT(S)
rfr-auth-redis      ClusterIP   None             9121/TCP    # Headless (Exporter)
rfr-cache-redis     ClusterIP   None             9121/TCP
rfr-streams-redis   ClusterIP   None             9121/TCP
rfs-auth-redis      ClusterIP   10.96.118.174    26379/TCP   # Sentinel
rfs-cache-redis     ClusterIP   10.111.135.35    26379/TCP
rfs-streams-redis   ClusterIP   10.108.155.145   26379/TCP
```

### 메모리 사용량 및 정책

```bash
for pod in rfr-auth-redis-0 rfr-streams-redis-0 rfr-cache-redis-0; do
  kubectl exec -n redis $pod -c redis -- redis-cli INFO memory | grep used_memory_human
  kubectl exec -n redis $pod -c redis -- redis-cli CONFIG GET maxmemory-policy
done
```

| Instance | Used Memory | maxmemory-policy |
|----------|-------------|------------------|
| auth-redis | 872.66K | noeviction |
| streams-redis | 893.45K | noeviction |
| cache-redis | 926.23K | allkeys-lru |

### 앱 연결 확인

```bash
# Scan Worker → Redis Streams
kubectl exec -n scan deployment/scan-worker -c scan-worker -- python3 -c "
import redis
r = redis.from_url('redis://rfr-streams-redis.redis.svc.cluster.local:6379/0')
print('Streams Redis:', r.ping())
"
# Streams Redis: True

# Scan Worker 환경변수
kubectl exec -n scan deployment/scan-worker -- printenv | grep REDIS

CELERY_RESULT_BACKEND=redis://rfr-cache-redis.redis.svc.cluster.local:6379/0
REDIS_STREAMS_URL=redis://rfr-streams-redis.redis.svc.cluster.local:6379/0
```

---

## 트러블슈팅

### 1. CRD 미등록 에러

```
error: unable to recognize "redisfailover.yaml": 
no matches for kind "RedisFailover" in version "databases.spotahome.com/v1"
```

**해결**: Redis Operator가 먼저 배포되어야 함 (sync-wave 순서 확인)

### 2. Helm Values 형식 오류

```yaml
# 오류: YAML 파싱 에러
Failed to load target state: yaml: line 4: did not find expected node content
```

**원인**: Spotahome Redis Operator Helm Chart의 values key가 버전별로 다름

| 키 | 설명 |
|----|------|
| `replicas` (O) | Operator Pod 수 (올바른 키) |
| `replicaCount` (X) | 존재하지 않는 키 |
| `monitoring.enabled` (O) | Prometheus 메트릭 (올바른 키) |
| `serviceMonitor.enabled` (X) | 존재하지 않는 키 |

**해결**: `helm show values spotahome/redis-operator`로 올바른 키 확인

### 3. Repository Not Found

```
Failed to load target state: Repository not found
```

**원인**: ArgoCD Application의 `repoURL`이 잘못된 레포지토리를 가리킴

| 잘못된 URL | 올바른 URL |
|------------|-----------|
| `https://github.com/mng990/eco2-backend.git` | `https://github.com/eco2-team/backend.git` |

**해결**: 모든 Application에서 일관된 `repoURL` 사용

### 4. Sentinel Quorum 미달

```
# Sentinel 로그
-failover-abort-no-good-slave
```

**해결**: `sentinel.replicas` 및 `redis.replicas` 최소 3개 설정 (prod)

### 5. PVC Pending

```bash
kubectl get pvc -n redis
```

**해결**: StorageClass 존재 여부, Node Affinity 확인

---

## 참고 자료

- [Spotahome Redis Operator GitHub](https://github.com/spotahome/redis-operator)
- [Redis Sentinel 공식 문서](https://redis.io/docs/latest/operate/oss_and_stack/management/sentinel/)
- [Operator Pattern - Kubernetes](https://kubernetes.io/docs/concepts/extend-kubernetes/operator/)

---

## 다음 단계

→ [#3: Application Layer 업데이트](./03-application-layer.md)

