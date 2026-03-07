# Message Queue #16: Spotahome Redis Operator로 Redis HA 구현

> **작업 일시**: 2025-12-26  
> **목표**: Kubernetes 네이티브 Redis HA 구현  
> **이전 문서**: [#15 Redis 3-Node 클러스터 프로비저닝](./25-redis-3node-cluster-provisioning.md)

---

## 개요

EC2 노드 프로비저닝이 완료되면 Kubernetes 위에 Redis를 배포해야 한다.
단순 StatefulSet으로도 가능하지만, HA(High Availability)와 자동 Failover를 위해
**Kubernetes Operator 패턴**을 도입한다.

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
2. **자동 Failover**: Master 장애 시 Sentinel이 자동으로 Replica를 승격
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
spec:
  sentinel:
    replicas: 3      # Quorum 보장 (2/3)
    resources:
      limits:
        cpu: 100m
        memory: 128Mi
  redis:
    replicas: 3      # Master 1 + Replica 2
    resources:
      limits:
        cpu: 500m
        memory: 1Gi
    storage:
      persistentVolumeClaim:
        spec:
          accessModes: [ReadWriteOnce]
          resources:
            requests:
              storage: 1Gi
          storageClassName: gp3
    customConfig:
      - "maxmemory-policy noeviction"  # 보안 데이터 보호
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
    replicas: 1      # dev: 최소 구성
    resources:
      limits:
        cpu: 200m
        memory: 512Mi
    storage:
      emptyDir: {}   # 휘발성 (TTL로 자동 정리)
    customConfig:
      - "maxmemory-policy noeviction"  # 이벤트 유실 방지
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
        cpu: 200m
        memory: 512Mi
    storage:
      emptyDir: {}
    customConfig:
      - "maxmemory-policy allkeys-lru"  # 메모리 부족 시 eviction
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

```
Sync-wave 24: PostgreSQL
Sync-wave 27: Redis Operator (CRD + Deployment)
Sync-wave 28: RedisFailover CRs (auth, streams, cache)
Sync-wave 29+: 애플리케이션 (Redis 의존)
```

### Operator → CR 의존성

```yaml
# clusters/dev/apps/27-redis-operator.yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: dev-redis-operator
  annotations:
    argocd.argoproj.io/sync-wave: "27"
spec:
  source:
    repoURL: https://spotahome.github.io/redis-operator
    chart: redis-operator
    targetRevision: 3.3.1

# clusters/dev/apps/28-redis-cluster.yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: dev-redis-cluster
  annotations:
    argocd.argoproj.io/sync-wave: "28"
spec:
  source:
    path: workloads/redis/dev
```

**sync-wave 간격의 의미**:
- 27 → 28: Operator가 CRD를 등록한 후 CR 생성
- CR이 먼저 생성되면 `no matches for kind "RedisFailover"` 에러

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

## 모니터링: Redis Sentinel 상태 확인

```bash
# Sentinel 상태
kubectl exec -n redis rfr-auth-redis-0 -- redis-cli -p 26379 SENTINEL master mymaster

# Master 정보
kubectl exec -n redis rfr-auth-redis-0 -- redis-cli INFO replication

# Failover 테스트
kubectl delete pod -n redis rfr-auth-redis-0
# → Sentinel이 Replica를 Master로 승격
```

---

## 트러블슈팅

### 1. CRD 미등록 에러

```
error: unable to recognize "redisfailover.yaml": 
no matches for kind "RedisFailover" in version "databases.spotahome.com/v1"
```

**해결**: Redis Operator가 먼저 배포되어야 함 (sync-wave 순서 확인)

### 2. Sentinel Quorum 미달

```
# Sentinel 로그
-failover-abort-no-good-slave
```

**해결**: `sentinel.replicas` 및 `redis.replicas` 최소 3개 설정 (prod)

### 3. PVC Pending

```
# PVC 상태
kubectl get pvc -n redis
```

**해결**: StorageClass 존재 여부, Node Affinity 확인

---

## 참고 자료

- [Spotahome Redis Operator GitHub](https://github.com/spotahome/redis-operator)
- [Redis Sentinel 공식 문서](https://redis.io/docs/latest/operate/oss_and_stack/management/sentinel/)
- [Operator Pattern - Kubernetes](https://kubernetes.io/docs/concepts/extend-kubernetes/operator/)

---

## Commits & PR

### Pull Request

- **PR #225**: [feat: Redis 3-node Cluster + Redis Streams SSE Migration](https://github.com/eco2-team/backend/pull/225)

### Commits

| Hash | Message |
|------|---------|
| `5c63a0c` | feat: Redis 3-node cluster + Redis Streams SSE migration |

---

## 관련 문서

- [#15 Redis 3-Node 클러스터 프로비저닝](./25-redis-3node-cluster-provisioning.md)
- [#14 Redis Streams SSE 전환](./24-redis-streams-sse-migration.md)
- [workloads/redis/README.md](../../../workloads/redis/README.md)

