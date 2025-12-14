# ext-authz 성능 튜닝 계획서

## 개요

ext-authz 서비스의 동시처리량 및 응답 시간을 최적화하기 위한 단계별 튜닝 계획입니다.

### 현재 인프라 스펙

| 항목 | 스펙 |
|------|------|
| **auth 노드** | t3.small (2 vCPU, 2GB RAM) |
| **Redis 노드** | t3.small/medium (2 vCPU, 2-4GB RAM) |
| **ext-authz Pod** | CPU 50m~200m, Memory 64Mi~128Mi |

### 현재 설정 (Baseline)

```go
// main.go - gRPC 서버
grpcServer := grpc.NewServer()  // 기본 설정

// redis.go - Redis 클라이언트
client := redis.NewClient(opts)  // 기본 PoolSize: GOMAXPROCS * 10 = 20
```

---

## 튜닝 단계

### Step 0: Baseline 측정 ✅

**상태**: 완료 (진행 중)

**목표**: 기본 설정에서 안정적인 동시 사용자 수 확인

**테스트 결과**:
- [x] 1,000 Users → RPS ~450, 안정적 통과
- [ ] 10,000 Users → 측정 중

**측정 명령어**:
```bash
ACCESS_TOKEN="<token>" AUTH_METHOD=header locust -f tests/performance/test_ext_authz.py \
  --host https://api.dev.growbin.app \
  --users 1000 --spawn-rate 100 --run-time 60s --headless \
  ExtAuthzHeaderUser
```

**Prometheus 쿼리** (모니터링):
| 메트릭 | 쿼리 |
|--------|------|
| p99 Latency | `histogram_quantile(0.99, sum(rate(ext_authz_request_duration_seconds_bucket[5m])) by (le))` |
| p99 JWT Verify | `histogram_quantile(0.99, sum(rate(ext_authz_jwt_verify_duration_seconds_bucket[5m])) by (le))` |
| p99 Redis Lookup | `histogram_quantile(0.99, sum(rate(ext_authz_redis_lookup_duration_seconds_bucket[5m])) by (le))` |
| Success Rate | `sum(rate(ext_authz_requests_total{result="allow"}[5m])) / sum(rate(ext_authz_requests_total[5m])) * 100` |
| CPU Usage (cores) | `sum(rate(container_cpu_usage_seconds_total{namespace="auth", pod=~"ext-authz.*"}[5m]))` |
| Memory Usage (GB) | `sum(container_memory_working_set_bytes{namespace="auth", pod=~"ext-authz.*"}) / 1024 / 1024 / 1024` |
| RPS | `sum(rate(ext_authz_requests_total[5m]))` |
| In-Flight Requests | `ext_authz_requests_in_flight` |

---

### Step 1: Redis Pool Size 튜닝

**상태**: ✅ 완료

**변경 파일**:
- `domains/ext-authz/internal/config/config.go`
- `domains/ext-authz/internal/store/redis.go`
- `domains/ext-authz/main.go`

**변경 내용**:
```go
// config.go - 환경변수 지원 추가
RedisPoolSize:      getEnvAsInt("REDIS_POOL_SIZE", 100),       // default 20 → 100
RedisMinIdleConns:  getEnvAsInt("REDIS_MIN_IDLE_CONNS", 20),   // warm connections
RedisPoolTimeoutMs: getEnvAsInt("REDIS_POOL_TIMEOUT_MS", 2000), // 2s (fast fail)
RedisReadTimeoutMs: getEnvAsInt("REDIS_READ_TIMEOUT_MS", 1000), // 1s

// redis.go - PoolOptions 구조체 추가
type PoolOptions struct {
    PoolSize      int
    MinIdleConns  int
    PoolTimeout   time.Duration
    ReadTimeout   time.Duration
    WriteTimeout  time.Duration
}

// main.go - 풀 설정 적용
poolOpts := &store.PoolOptions{
    PoolSize:     cfg.RedisPoolSize,
    MinIdleConns: cfg.RedisMinIdleConns,
    PoolTimeout:  time.Duration(cfg.RedisPoolTimeoutMs) * time.Millisecond,
    ReadTimeout:  time.Duration(cfg.RedisReadTimeoutMs) * time.Millisecond,
}
```

**환경변수 설정** (ConfigMap/Deployment):
```yaml
- name: REDIS_POOL_SIZE
  value: "100"       # 기본값 (스트레스 테스트 기반)
- name: REDIS_MIN_IDLE_CONNS
  value: "20"
- name: REDIS_POOL_TIMEOUT_MS
  value: "2000"      # 2초 (빠른 실패)
- name: REDIS_READ_TIMEOUT_MS
  value: "1000"      # 1초
```

**적용된 값** (스트레스 테스트 결과 기반):
| 항목 | 기본값 | 튜닝값 | 근거 |
|------|--------|--------|------|
| PoolSize | 20 | 100 | 동시 처리 230개 대응 |
| MinIdleConns | 0 | 20 | Cold start 방지 |
| PoolTimeout | 4s | 2s | 빠른 실패 (backpressure) |
| ReadTimeout | 3s | 1s | 빠른 타임아웃 |

**예상 효과**:
- 동시 Redis 연결 수 5배 증가 (20 → 100)
- Redis 풀 대기 시간 대폭 감소
- Cold start 지연 방지 (MinIdleConns=20)
- 빠른 실패로 cascading failure 방지

---

### Step 2: gRPC 서버 동시성 설정

**상태**: 대기 중

**변경 파일**: `domains/ext-authz/main.go`

**변경 내용**:
```go
// Before
grpcServer := grpc.NewServer()

// After
grpcServer := grpc.NewServer(
    grpc.MaxConcurrentStreams(100),  // 동시 스트림 수 제한
    grpc.NumStreamWorkers(4),        // 워커 수 (vCPU * 2)
)
```

**환경변수 설정** (선택적):
```yaml
- name: GRPC_MAX_CONCURRENT_STREAMS
  value: "100"
- name: GRPC_NUM_STREAM_WORKERS
  value: "4"
```

**예상 효과**:
- 동시 gRPC 요청 처리량 증가
- 워커 풀을 통한 효율적인 CPU 활용

**커밋 메시지**:
```
perf(ext-authz): configure gRPC server concurrency

- MaxConcurrentStreams: 100
- NumStreamWorkers: 4 (2 vCPU * 2)
```

---

### Step 3: GOMAXPROCS 최적화

**상태**: 대기 중

**변경 파일**: `workloads/domains/ext-authz/base/deployment.yaml`

**변경 내용**:
```yaml
env:
# 기존 환경변수 유지...
- name: GOMAXPROCS
  value: "2"  # vCPU 수와 동일하게 설정
```

**예상 효과**:
- Go 런타임이 컨테이너 CPU 제한을 인식
- 불필요한 context switching 감소
- Redis PoolSize 기본값도 영향받음 (GOMAXPROCS * 10)

**대안 - uber-go/automaxprocs 사용**:
```go
import _ "go.uber.org/automaxprocs"  // 자동으로 cgroup 감지
```

**커밋 메시지**:
```
perf(ext-authz): set GOMAXPROCS=2 for container CPU awareness

- Align Go runtime with container CPU limits (2 vCPU)
- Reduces unnecessary context switching
```

---

### Step 4: Redis 파이프라이닝 (선택적)

**상태**: 대기 중 (현재 구조에서는 불필요)

**적용 조건**: 
- 단일 요청에서 여러 JTI를 조회할 경우
- 현재는 요청당 1개 JTI만 조회하므로 효과 제한적

**변경 내용** (참고용):
```go
// 여러 JTI 배치 조회 시
func (s *Store) AreBlacklisted(ctx context.Context, jtis []string) ([]bool, error) {
    pipe := s.client.Pipeline()
    cmds := make([]*redis.IntCmd, len(jtis))
    
    for i, jti := range jtis {
        cmds[i] = pipe.Exists(ctx, blacklistKey(jti))
    }
    
    _, err := pipe.Exec(ctx)
    if err != nil {
        return nil, err
    }
    
    results := make([]bool, len(jtis))
    for i, cmd := range cmds {
        results[i] = cmd.Val() > 0
    }
    return results, nil
}
```

**커밋 메시지** (적용 시):
```
perf(ext-authz): add Redis pipelining for batch JTI lookup
```

---

## 수평 확장 (HPA) - 추가 옵션

단일 Pod 튜닝 이후에도 처리량이 부족할 경우:

**변경 파일**: `workloads/domains/ext-authz/base/hpa.yaml` (신규)

```yaml
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: ext-authz-hpa
  namespace: auth
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: ext-authz
  minReplicas: 2
  maxReplicas: 5
  metrics:
  - type: Resource
    resource:
      name: cpu
      target:
        type: Utilization
        averageUtilization: 70
```

---

## 테스트 및 측정 체크리스트

각 단계별로 다음을 측정/기록:

- [ ] **p99 Latency** (목표: < 50ms)
- [ ] **RPS** (목표: 현재 대비 +50%)
- [ ] **Success Rate** (목표: > 99.9%)
- [ ] **CPU Usage** (목표: < 80%)
- [ ] **Memory Usage** (목표: < 100Mi)
- [ ] **Redis Connection Pool Usage**
- [ ] **Error Rate** (목표: < 0.1%)

---

## 롤백 계획

문제 발생 시 각 단계별 롤백:

```bash
# ArgoCD로 이전 버전 복원
kubectl -n argocd patch application dev-api-ext-authz \
  --type merge -p '{"spec":{"source":{"targetRevision":"<previous-commit>"}}}'

# 또는 git revert
git revert <commit-hash>
git push origin perf/ext-authz-tuning
```

---

## 브랜치 및 커밋 전략

**브랜치**: `perf/ext-authz-tuning`

**커밋 순서**:
1. `docs: add ext-authz performance tuning plan`
2. `perf(ext-authz): increase Redis pool size to 50`
3. `perf(ext-authz): configure gRPC server concurrency`
4. `perf(ext-authz): set GOMAXPROCS=2`
5. (선택) `perf(ext-authz): add Redis pipelining`

각 커밋 후 PR → merge → 성능 측정 → 다음 단계 진행
