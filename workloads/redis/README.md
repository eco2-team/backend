# Redis Infrastructure (17-Node Architecture)

Spotahome Redis Operator 기반 Redis 클러스터 관리

## 구조

```
workloads/redis/
├── base/
│   ├── auth-redis-failover.yaml     # Auth 전용 (Blacklist, OAuth)
│   ├── streams-redis-failover.yaml  # SSE 이벤트 전용
│   ├── cache-redis-failover.yaml    # Celery Result + 도메인 캐시
│   └── kustomization.yaml
├── dev/
│   └── kustomization.yaml           # replicas: 1 (HA 비활성)
└── prod/
    └── kustomization.yaml           # replicas: 3 (Full HA)
```

## Service 네이밍 규칙

Spotahome Redis Operator가 자동 생성하는 Service:

| Service | 용도 | 포트 | 예시 |
|---------|------|------|------|
| `rfr-{name}` | Redis Master 접근 | 6379 | `rfr-auth-redis.redis.svc.cluster.local` |
| `rfs-{name}` | Sentinel 접근 | 26379 | `rfs-auth-redis.redis.svc.cluster.local` |
| `rfr-{name}-readonly` | Read Replica 접근 | 6379 | `rfr-auth-redis-readonly.redis.svc.cluster.local` |

## Redis 인스턴스별 설정

| Redis | Service | DB | 용도 | eviction | Storage |
|-------|---------|-----|------|----------|---------|
| **auth-redis** | `rfr-auth-redis:6379` | 0 | JWT Blacklist (ext-authz, auth-api) | noeviction | PVC (AOF) |
| **auth-redis** | `rfr-auth-redis:6379` | 3 | OAuth State (auth-api) | noeviction | PVC (AOF) |
| **streams-redis** | `rfr-streams-redis:6379` | 0 | SSE 이벤트 (scan-api, scan-worker) | noeviction | emptyDir |
| **cache-redis** | `rfr-cache-redis:6379` | 0 | Celery Result Backend | allkeys-lru | emptyDir |
| **cache-redis** | `rfr-cache-redis:6379` | 1 | Celery Beat 스케줄러 | allkeys-lru | emptyDir |
| **cache-redis** | `rfr-cache-redis:6379` | 5 | Location 캐시 | allkeys-lru | emptyDir |
| **cache-redis** | `rfr-cache-redis:6379` | 6 | Image 캐시 | allkeys-lru | emptyDir |

## HA 구성

### Production (3+3)

```
┌─────────────────────────────────────────────────────────┐
│  Sentinel Cluster (rfs-{name})                          │
│  ┌───────────┐  ┌───────────┐  ┌───────────┐          │
│  │ Sentinel-0│  │ Sentinel-1│  │ Sentinel-2│          │
│  └─────┬─────┘  └─────┬─────┘  └─────┬─────┘          │
│        └──────────────┼──────────────┘                  │
│                       │ Quorum (2/3)                    │
│                       ▼                                  │
│  ┌─────────────────────────────────────────────────┐   │
│  │  Redis Cluster (rfr-{name})                      │   │
│  │  ┌─────────┐  ┌─────────┐  ┌─────────┐         │   │
│  │  │ Master  │──│ Replica │──│ Replica │         │   │
│  │  │ (RW)    │  │ (RO)    │  │ (RO)    │         │   │
│  │  └─────────┘  └─────────┘  └─────────┘         │   │
│  └─────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────┘
```

### Development (1+1)

- Sentinel: 1 (Quorum 불가, 장애 감지만)
- Redis: 1 (Master only, Replica 없음)
- HA 비활성화, 리소스 절약

## Failover 설정

```yaml
sentinel:
  customConfig:
    - "down-after-milliseconds 5000"   # 5초 무응답 시 장애 판정
    - "failover-timeout 10000"         # 10초 이내 failover 완료
```

## 환경변수 매핑

| 서비스 | 환경변수 | 값 |
|--------|----------|-----|
| ext-authz | `AUTH_REDIS_URL` | `redis://rfr-auth-redis.redis.svc.cluster.local:6379/0` |
| auth-api | `AUTH_REDIS_BLACKLIST_URL` | `redis://rfr-auth-redis.redis.svc.cluster.local:6379/0` |
| auth-api | `AUTH_REDIS_OAUTH_STATE_URL` | `redis://rfr-auth-redis.redis.svc.cluster.local:6379/3` |
| scan-api | `REDIS_STREAMS_URL` | `redis://rfr-streams-redis.redis.svc.cluster.local:6379/0` |
| scan-worker | `REDIS_STREAMS_URL` | `redis://rfr-streams-redis.redis.svc.cluster.local:6379/0` |
| workers | `CELERY_RESULT_BACKEND` | `redis://rfr-cache-redis.redis.svc.cluster.local:6379/0` |
| celery-beat | `CELERY_RESULT_BACKEND` | `redis://rfr-cache-redis.redis.svc.cluster.local:6379/1` |
| image-api | `IMAGE_REDIS_URL` | `redis://rfr-cache-redis.redis.svc.cluster.local:6379/6` |

## 검증 명령어

```bash
# RedisFailover 상태 확인
kubectl get redisfailover -n redis

# Pod 상태 확인
kubectl get pods -n redis

# Service 확인
kubectl get svc -n redis | grep rfr

# Master 확인 (Sentinel 쿼리)
kubectl exec -n redis rfs-auth-redis-0 -- \
  redis-cli -p 26379 SENTINEL master mymaster

# Replication 상태
kubectl exec -n redis rfr-auth-redis-0 -- \
  redis-cli INFO replication

# 연결 테스트
kubectl exec -n redis rfr-auth-redis-0 -- \
  redis-cli PING
```

## 마이그레이션 참고

### 기존 Bitnami Helm → Spotahome Operator

1. 기존: `dev-redis-node-0.dev-redis-headless.redis.svc.cluster.local`
2. 신규: `rfr-{name}.redis.svc.cluster.local`

### 롤백 시

1. `28-redis-cluster.yaml` 삭제
2. `27-redis-operator.yaml`을 기존 Bitnami Helm으로 복원
3. 환경변수를 기존 형식으로 원복
