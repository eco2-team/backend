# SSE Gateway 샤딩 아키텍처 구현 및 트러블슈팅

> **작성일**: 2024-12-27  
> **환경**: dev (ap-northeast-2)  
> **목적**: SSE Gateway의 대규모 샤딩 아키텍처 구현 및 발생한 이슈 해결

---

## 1. 개요

### 1.1. 배경

KEDA + Karpenter 도입 이후, SSE(Server-Sent Events) 기반 실시간 스트리밍 아키텍처를 구축하는 과정에서 여러 이슈가 발생했습니다.

**주요 이슈:**
- SSE Gateway 노드 배포 및 초기화
- 샤딩 아키텍처 설계 문제 (할당 vs 라우팅 불일치)
- Race Condition (SSE 연결 전 이벤트 발행)
- Redis 클라이언트 분리 (Streams vs Cache)

### 1.2. 최종 아키텍처

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        SSE 샤딩 아키텍처 (B안)                            │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  ┌─────────────┐                                                        │
│  │ Client App  │                                                        │
│  │             │                                                        │
│  └──────┬──────┘                                                        │
│         │ GET /api/v1/stream?job_id=xxx                                 │
│         ▼                                                               │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │                     Istio Ingress Gateway                        │   │
│  │  ┌──────────────────┐    ┌──────────────────────────────────┐   │   │
│  │  │ EnvoyFilter      │    │ DestinationRule                  │   │   │
│  │  │ query → header   │───►│ Consistent Hash (X-Job-Id)       │   │   │
│  │  │ job_id → X-Job-Id│    │ hash(X-Job-Id) % 4 → Pod 선택    │   │   │
│  │  └──────────────────┘    └──────────────────────────────────┘   │   │
│  └───────────────────────────────────┬─────────────────────────────┘   │
│                                      │                                  │
│                   ┌──────────────────┼──────────────────┐              │
│                   │                  │                  │              │
│                   ▼                  ▼                  ▼              │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │              SSE Gateway StatefulSet (replicas=4)                │   │
│  │  ┌────────────┐ ┌────────────┐ ┌────────────┐ ┌────────────┐    │   │
│  │  │sse-gateway │ │sse-gateway │ │sse-gateway │ │sse-gateway │    │   │
│  │  │    -0      │ │    -1      │ │    -2      │ │    -3      │    │   │
│  │  │ shard: 0   │ │ shard: 1   │ │ shard: 2   │ │ shard: 3   │    │   │
│  │  └─────┬──────┘ └─────┬──────┘ └─────┬──────┘ └─────┬──────┘    │   │
│  └────────┼──────────────┼──────────────┼──────────────┼───────────┘   │
│           │              │              │              │               │
│           ▼              ▼              ▼              ▼               │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │                     Redis Streams (Sharded)                      │   │
│  │  ┌────────────┐ ┌────────────┐ ┌────────────┐ ┌────────────┐    │   │
│  │  │scan:events │ │scan:events │ │scan:events │ │scan:events │    │   │
│  │  │    :0      │ │    :1      │ │    :2      │ │    :3      │    │   │
│  │  └────────────┘ └────────────┘ └────────────┘ └────────────┘    │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                                      ▲                                  │
│                                      │ publish_stage_event              │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │                      scan-worker (Celery)                        │   │
│  │         hash(job_id) % 4 → scan:events:N에 publish               │   │
│  └─────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Issue #1: SSE Gateway 노드 배포

### 2.1. 현상

SSE Gateway 전용 노드 배포 후 Pod가 Pending 또는 ImagePullBackOff 상태:

```bash
$ kubectl get pods -n sse-consumer
NAME                          READY   STATUS             RESTARTS   AGE
sse-gateway-974b5bdbb-ckfgq   0/2     ImagePullBackOff   0          5m
```

### 2.2. 원인 분석

**문제 1: 이미지 태그 불일치**

CI 워크플로우에서 `sse-gateway` 이미지 태그에 `-api` suffix가 붙음:
- 빌드된 이미지: `mng990/eco2:sse-gateway-api-dev-latest`
- Deployment 참조: `mng990/eco2:sse-gateway-dev-latest`

**문제 2: DockerHub Secret 누락**

`sse-consumer` namespace에 `dockerhub-secret`이 없음.

**문제 3: NetworkPolicy 누락**

istio-proxy가 istiod와 통신 불가:
```
connection error: dial tcp 10.99.96.130:15012: i/o timeout
```

### 2.3. 해결책

**CI 워크플로우 수정** (`.github/workflows/ci-services.yml`):
```yaml
# AS-IS
SERVICE_SLUG="${SERVICE}-api"

# TO-BE
if [[ "$SERVICE" == *"-gateway"* ]]; then
  SERVICE_SLUG="${SERVICE}"
else
  SERVICE_SLUG="${SERVICE}-api"
fi
```

**ExternalSecret 추가** (`workloads/secrets/external-secrets/dev/dockerhub-pull-secret.yaml`):
```yaml
# sse-consumer namespace 추가
- kind: ExternalSecret
  metadata:
    name: dockerhub-secret
    namespace: sse-consumer
```

**NetworkPolicy 수정** (`workloads/network-policies/base/allow-sse-gateway.yaml`):
```yaml
egress:
  # Istio Control Plane (istiod)
  - to:
    - namespaceSelector:
        matchLabels:
          kubernetes.io/metadata.name: istio-system
    ports:
    - protocol: TCP
      port: 15010  # istiod discovery
    - protocol: TCP
      port: 15012  # istiod mTLS CA
```

**커밋:**
- `fix(ci): correct sse-gateway image tag (remove -api suffix)`
- `fix(external-secrets): add dockerhub-secret for sse-consumer namespace`
- `fix(network-policy): allow sse-gateway to istiod communication`

---

## 3. Issue #2: 샤딩 할당 vs 라우팅 불일치

### 3.1. 현상

SSE 스트림에서 이벤트가 수신되지 않음:

```bash
$ curl -s "https://api.dev.growbin.app/api/v1/stream?job_id=xxx"
: keepalive
: keepalive
# ... 이벤트 없음
```

### 3.2. 원인 분석

**샤딩 아키텍처의 두 요소:**

| 요소 | 설명 | 구현 상태 |
|------|------|----------|
| **할당 (Allocation)** | Worker가 어느 shard에 이벤트 저장 | ✅ `hash(job_id) % shard_count` |
| **라우팅 (Routing)** | 클라이언트가 어느 Pod로 연결 | ❌ X-Job-Id 헤더 없음 |

**문제:**
- Worker: `hash(job_id) % 4` → shard 0~3 중 하나에 publish
- SSE-Gateway: `SSE_SHARD_ID=0` 고정 → shard 0만 XREAD
- 라우팅: 클라이언트가 X-Job-Id 헤더를 안 보냄 → 라운드로빈

**결과:** job_id가 shard 1, 2, 3에 저장되면 SSE-Gateway가 읽지 못함

### 3.3. 임시 해결 (shard_count=1)

```yaml
# 모든 Deployment에서 SSE_SHARD_COUNT=1
- name: SSE_SHARD_COUNT
  value: '1'
```

### 3.4. 최종 해결: StatefulSet + Consistent Hash

**1. Deployment → StatefulSet 전환:**
```yaml
apiVersion: apps/v1
kind: StatefulSet
metadata:
  name: sse-gateway
spec:
  serviceName: sse-gateway-headless
  replicas: 4
  podManagementPolicy: Parallel
```

**2. Pod Index = Shard ID (동적 추출):**
```python
# domains/sse-gateway/config.py
def get_pod_index() -> int:
    pod_name = os.environ.get("POD_NAME", "sse-gateway-0")
    match = re.search(r"-(\d+)$", pod_name)
    return int(match.group(1)) if match else 0

class Settings(BaseSettings):
    @property
    def sse_shard_id(self) -> int:
        return get_pod_index()
```

**3. EnvoyFilter: Query → Header 변환:**
```lua
-- /api/v1/stream?job_id=xxx → X-Job-Id: xxx
local path = request_handle:headers():get(":path")
if path and string.find(path, "/api/v1/stream") then
  local job_id = string.match(path, "job_id=([^&]+)")
  if job_id then
    request_handle:headers():replace("X-Job-Id", job_id)
  end
end
```

**4. DestinationRule Consistent Hash:**
```yaml
loadBalancer:
  consistentHash:
    httpHeaderName: X-Job-Id
```

**커밋:**
- `feat(sse-gateway): convert Deployment to StatefulSet`
- `feat(envoy-filter): add query to header conversion for SSE routing`

---

## 4. Issue #3: Race Condition (SSE 연결 전 이벤트 발행)

### 4.1. 현상

SSE 연결 후 일부 이벤트가 누락됨:

```
Timeline:
T+0ms   POST /api/v1/scan → job_id 생성
T+10ms  Worker: publish_stage_event("queued")
T+50ms  Client: GET /api/v1/stream?job_id=xxx  ← 이미 "queued" 이벤트 지나감
T+100ms Worker: publish_stage_event("vision")  ← 이것부터 수신
```

### 4.2. 해결책 (5가지)

**1. done 순서 수정:**
```python
# AS-IS: done 먼저 → cache 나중
publish_stage_event(..., "done", ...)
_cache_result(task_id, done_result)

# TO-BE: cache 먼저 → done 나중
_cache_result(task_id, done_result)  # 결과 커밋 확정
publish_stage_event(..., "done", ...)  # 커밋 완료 신호
```

**2. State KV 스냅샷:**
```python
# publish_stage_event에서 현재 상태 저장
redis_client.setex(
    f"scan:state:{job_id}",
    STATE_TTL,
    json.dumps(event, ensure_ascii=False)
)
```

**3. /result 202 방어:**
```python
@router.get("/result/{job_id}")
async def get_result(job_id: str) -> ClassificationResponse | JSONResponse:
    result = await service.get_result(job_id)
    if result is None:
        state = await service.get_state(job_id)
        if state is not None:
            return JSONResponse(
                status_code=202,
                content={"status": "processing", "current_stage": state.get("stage")},
                headers={"Retry-After": "2"},
            )
        raise HTTPException(status_code=404)
    return result
```

**4. 이벤트 seq 추가:**
```python
STAGE_ORDER = {"queued": 0, "vision": 1, "rule": 2, "answer": 3, "reward": 4, "done": 5}

def publish_stage_event(...):
    base_seq = STAGE_ORDER.get(stage, 99) * 10
    seq = base_seq + (1 if status == "completed" else 0)
    event["seq"] = str(seq)
```

**5. Idempotency Key:**
```python
@router.post("")
async def submit_scan(
    payload: ClassificationRequest,
    x_idempotency_key: str | None = Header(None, alias="X-Idempotency-Key"),
) -> ScanSubmitResponse:
    if x_idempotency_key:
        cache_client = await get_async_cache_client()
        existing = await cache_client.get(f"idempotency:{x_idempotency_key}")
        if existing:
            return ScanSubmitResponse.model_validate_json(existing)
```

**커밋:**
- `fix(race-condition): cache result before done event`
- `feat(state-snapshot): store current state in Redis KV`
- `feat(result-api): return 202 Accepted when processing`
- `feat(events): add monotonic sequence number`
- `feat(idempotency): add X-Idempotency-Key support`

---

## 5. Issue #4: Redis 클라이언트 분리 (Streams vs Cache)

### 5.1. 현상

`/result/{job_id}` API가 `processing` 상태 반환하지만, SSE에서는 `done` 이벤트 수신됨:

```bash
$ curl .../api/v1/scan/result/xxx
{"status": "processing", "current_stage": "done"}  # 모순!
```

### 5.2. 원인 분석

**Redis 분리 구조:**
```
┌─────────────────┐     ┌─────────────────┐
│ Redis Streams   │     │ Redis Cache     │
│ rfr-streams-    │     │ rfr-cache-      │
│ redis:6379/0    │     │ redis:6379/0    │
├─────────────────┤     ├─────────────────┤
│ - scan:events:* │     │ - scan:result:* │
│ - scan:state:*  │     │ - idempotency:* │
└─────────────────┘     └─────────────────┘
```

**문제:** `get_result()`가 Streams Redis에서 결과를 찾으려 함

```python
# AS-IS (잘못된 코드)
async def get_result(self, job_id: str):
    streams_client = await get_async_redis_client()  # Streams Redis
    cache_key = f"scan:result:{job_id}"
    return await streams_client.get(cache_key)  # 항상 None

# TO-BE (올바른 코드)
async def get_result(self, job_id: str):
    cache_client = await get_async_cache_client()  # Cache Redis
    cache_key = f"scan:result:{job_id}"
    return await cache_client.get(cache_key)
```

### 5.3. 환경변수 누락

Worker/API Pod에 `REDIS_CACHE_URL` 환경변수가 없어 기본값(`localhost:6379/1`) 사용:

```yaml
# 추가 필요
- name: REDIS_CACHE_URL
  value: redis://rfr-cache-redis.redis.svc.cluster.local:6379/0
```

**커밋:**
- `fix(redis): use cache client for result retrieval`
- `fix(deployment): add REDIS_CACHE_URL env var`

---

## 6. 최종 구성

### 6.1. 변경된 파일 목록

| 파일 | 변경 내용 |
|------|----------|
| `workloads/domains/sse-gateway/base/statefulset.yaml` | Deployment → StatefulSet |
| `workloads/domains/sse-gateway/base/service-headless.yaml` | 신규 생성 |
| `workloads/domains/sse-gateway/base/kustomization.yaml` | 리소스 목록 업데이트 |
| `workloads/routing/gateway/base/envoy-filter.yaml` | query→header 로직 추가 |
| `domains/sse-gateway/config.py` | Pod 인덱스 동적 추출 |
| `domains/sse-gateway/core/broadcast_manager.py` | 동적 shard_id |
| `workloads/domains/scan-worker/base/deployment.yaml` | SSE_SHARD_COUNT=4 |
| `workloads/domains/scan/base/deployment.yaml` | SSE_SHARD_COUNT=4, REDIS_CACHE_URL |

### 6.2. 설정값 요약

| 항목 | 값 | 설명 |
|------|-----|------|
| SSE_SHARD_COUNT | 4 | 전체 shard 수 (고정) |
| StatefulSet replicas | 4 | SSE-Gateway Pod 수 (= shard_count) |
| Pod Index | 0-3 | Shard ID로 사용 |
| Consistent Hash | X-Job-Id | Istio 라우팅 키 |

---

## 7. 디버깅 체크리스트

### 7.1. SSE 연결 문제

```bash
# 1. SSE-Gateway Pod 상태 확인
kubectl get pods -n sse-consumer -o wide

# 2. SSE-Gateway 로그 확인
kubectl logs -n sse-consumer -l app=sse-gateway --tail=50

# 3. Redis Streams 내용 확인
kubectl exec -n redis rfr-streams-redis-0 -- redis-cli XRANGE scan:events:0 - + COUNT 10

# 4. VirtualService 확인
kubectl get virtualservice -n sse-consumer

# 5. EnvoyFilter 적용 확인
kubectl get envoyfilter -n istio-system
```

### 7.2. 샤딩 문제

```bash
# 1. shard_count 일치 확인
kubectl exec -n scan deploy/scan-worker -- env | grep SSE_SHARD
kubectl exec -n scan deploy/scan-api -- env | grep SSE_SHARD
kubectl exec -n sse-consumer sse-gateway-0 -- env | grep SSE_SHARD

# 2. Pod Index 확인
kubectl get pods -n sse-consumer -o name | sort

# 3. 특정 job_id의 shard 계산
python3 -c "print(hash('your-job-id') % 4)"
```

### 7.3. Race Condition 문제

```bash
# 1. State 스냅샷 확인
kubectl exec -n redis rfr-streams-redis-0 -- redis-cli GET "scan:state:your-job-id"

# 2. 결과 캐시 확인
kubectl exec -n redis rfr-cache-redis-0 -- redis-cli GET "scan:result:your-job-id"

# 3. Idempotency 캐시 확인
kubectl exec -n redis rfr-cache-redis-0 -- redis-cli GET "idempotency:your-key"
```

---

## 8. 핵심 교훈

### 8.1. 샤딩 아키텍처

- **할당(Allocation) + 라우팅(Routing)** 두 요소가 일치해야 함
- `shard_count`는 고정하고, Pod↔Shard 매핑을 동적으로
- StatefulSet으로 Pod 이름 보장 → Pod Index = Shard ID

### 8.2. Race Condition

- 비동기 시스템에서 "순서 보장"은 명시적으로 구현해야 함
- 이벤트 발행 전 상태 커밋 (done 순서 수정)
- 재접속 지원 (State KV 스냅샷, 이벤트 리플레이)
- 클라이언트 방어 (202 Accepted, Retry-After)

### 8.3. Redis 분리

- Streams와 Cache는 용도가 다름 → 클라이언트도 분리
- 환경변수로 URL 관리 (`REDIS_STREAMS_URL`, `REDIS_CACHE_URL`)
- 기본값 의존하지 않고 모든 환경에서 명시적 설정

---

## 9. 관련 문서

- [29-keda-troubleshooting-20251226.md](./29-keda-troubleshooting-20251226.md) - KEDA 트러블슈팅
- [30-karpenter-iam-provisioning.md](./30-karpenter-iam-provisioning.md) - Karpenter IAM 프로비저닝
- [31-sse-fanout-optimization.md](./31-sse-fanout-optimization.md) - SSE Fan-out 최적화

---

## 10. 참고 자료

- [Redis Streams 공식 문서](https://redis.io/docs/latest/develop/data-types/streams/)
- [Istio Consistent Hash](https://istio.io/latest/docs/reference/config/networking/destination-rule/#LoadBalancerSettings-ConsistentHashLB)
- [Kubernetes StatefulSet](https://kubernetes.io/docs/concepts/workloads/controllers/statefulset/)
- [Envoy Lua Filter](https://www.envoyproxy.io/docs/envoy/latest/configuration/http/http_filters/lua_filter)

