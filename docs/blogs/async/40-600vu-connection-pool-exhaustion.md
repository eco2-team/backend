# 600 VU 부하 테스트 - Connection Pool 고갈 트러블슈팅

> **Date**: 2025-12-29  
> **Tags**: #troubleshooting #load-test #redis #celery #connection-pool  
> **PR**: [#235](https://github.com/eco2-team/backend/pull/235)

## 📋 개요

600 VU 부하 테스트에서 Completion Rate이 급격히 하락하는 현상 발생. 원인 분석 결과 **Redis Connection Pool 고갈**과 **Celery Producer Pool 한계 초과**가 동시에 발생한 것으로 확인.

---

## 🔴 증상

### k6 테스트 결과
```
VU: 600
Duration: 3m
Completion Rate: 낮음 (정확한 수치 미기록)
```

### 시스템 상태
- scan-worker: KEDA에 의해 1 → 3 pods 스케일 업 (정상)
- scan-api: 3 pods (정상)
- k8s-worker-ai 노드: CPU 16%, Memory 77% (여유)
- RabbitMQ: 큐 비어있음 (테스트 종료 후)

---

## 🔍 로그 분석

### 1. Redis Connection Error (scan-api)

```json
{
  "@timestamp": "2025-12-29T09:33:02.214+00:00",
  "message": "scan_result_cache_error",
  "log.level": "warning",
  "labels": {
    "job_id": "bcd5c719-316a-4d8a-b6b5-c3f57b6ec73f",
    "error": "Too many connections"
  }
}
```

**발생 건수**: 133건  
**발생 시간대**: 09:33:02 ~ 09:35:05 (약 2분간)

**Stack Trace**:
```python
raise ConnectionError("Too many connections") from None
redis.exceptions.ConnectionError: Too many connections
```

### 2. Celery Producer Pool Exhausted (scan-worker)

```python
Traceback (most recent call last):
  File "/usr/local/lib/python3.11/site-packages/kombu/resource.py", line 73, in acquire
    R = self._resource.get(block=block, timeout=timeout)
_queue.Empty

During handling of the above exception, another exception occurred:
  File "/usr/local/lib/python3.11/site-packages/kombu/resource.py", line 48, in _add_when_empty
    raise self.LimitExceeded(self.limit)
```

**원인**: Celery worker의 `broker_pool_limit` 기본값(10)이 600 VU 동시 요청을 처리하기에 부족

---

## 📊 원인 분석

### 연쇄 장애 흐름

```
600 VU 동시 요청
        ↓
┌───────┴───────┐
↓               ↓
Redis Cache     RabbitMQ
연결 폭증       메시지 폭증
        ↓               ↓
"Too many       "LimitExceeded"
connections"    (Producer Pool)
        ↓               ↓
캐시 저장       Worker 통신
실패            실패
        ↓               ↓
└───────┬───────┘
        ↓
Completion Rate 저하
```

### 설정값 분석

| 컴포넌트 | 설정 | 기존값 | 문제 |
|----------|------|--------|------|
| scan-api Redis Cache | `max_connections` | 20 per pod | 3 pods × 20 = 60 연결 < 600 VU |
| Celery Worker | `broker_pool_limit` | 10 (기본값) | Worker 간 통신에 부족 |

### Redis 현재 상태 (테스트 후)

```
# kubectl exec -n redis rfr-cache-redis-0 -- redis-cli INFO clients
connected_clients:3046
maxclients:10000
```

- `maxclients`(10000)는 충분하지만, 클라이언트 측 Connection Pool이 부족

---

## 🛠️ 해결 방안

### 1. Redis Cache Connection Pool 증가

**파일**: `domains/_shared/events/redis_client.py`

```python
# 변경 전
_async_cache_client = aioredis.from_url(
    _REDIS_CACHE_URL,
    max_connections=20,  # 부족
)

# 변경 후
_async_cache_client = aioredis.from_url(
    _REDIS_CACHE_URL,
    max_connections=100,  # 600 VU 대응
)
```

**계산**:
- Pod당 100 연결 × 3 pods = 300 연결
- 600 VU에서 동시 캐시 조회는 약 200~300건 예상
- 여유분 포함하여 100으로 설정

### 2. Celery Broker Pool Limit 증가

**파일**: `domains/_shared/celery/config.py`

```python
def get_celery_config(self) -> dict[str, Any]:
    return {
        # 변경 전: 기본값 10
        # 변경 후
        "broker_pool_limit": 50,
        ...
    }
```

**계산**:
- Worker Pod당 50 연결
- KEDA 최대 스케일 3 pods × 50 = 150 연결
- RabbitMQ 채널 한계 충분 (수천 개 지원)

---

## 📈 예상 효과

| 지표 | 변경 전 | 변경 후 (예상) |
|------|---------|----------------|
| Redis 연결 오류 | 133건/테스트 | 0건 |
| Celery Pool 오류 | 발생 | 미발생 |
| Completion Rate | 낮음 | 99%+ |

---

## 🔄 후속 조치

1. **PR 머지 후 재테스트**: 600 VU 부하 테스트 재실행
2. **모니터링 대시보드 추가**: Redis 연결 수, Celery Pool 사용량 메트릭
3. **HPA 검토**: scan-api Pod 수 증가 고려 (현재 3 → 5)

---

## 📚 참고

### Redis Connection Pool 동작

```
┌─────────────────────────────────────────────────┐
│ scan-api Pod (1/3)                              │
│                                                 │
│  Request 1 ─┐                                   │
│  Request 2 ─┼─→ ConnectionPool ─→ Redis Cache   │
│  Request 3 ─┘   (max: 100)                      │
│  ...                                            │
│  Request n ─→ Pool Full → ConnectionError       │
└─────────────────────────────────────────────────┘
```

### Celery Broker Pool 동작

```
┌─────────────────────────────────────────────────┐
│ scan-worker Pod (1/3)                           │
│                                                 │
│  Task 1 ────┐                                   │
│  Task 2 ────┼─→ Producer Pool ─→ RabbitMQ       │
│  Task 3 ────┘   (limit: 50)                     │
│  ...                                            │
│  Control ───→ Pool Full → LimitExceeded         │
└─────────────────────────────────────────────────┘
```

---

## 🏷️ 관련 링크

- **PR**: [#235 - fix: 600 VU 부하 테스트 대응 - Connection Pool 한계 증가](https://github.com/eco2-team/backend/pull/235)
- **이전 포스팅**: [39-event-router-code-deep-dive.md](./39-event-router-code-deep-dive.md)
- **부하 테스트 시리즈**: [22-scan-sse-performance-benchmark.md](./22-scan-sse-performance-benchmark.md)

