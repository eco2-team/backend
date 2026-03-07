# Scan API Load Test Report - VU 600 (Limit Test)

> **Date**: 2026-01-27 13:52 KST (04:52 UTC)
> **Test Type**: k6 Scan Polling Test (Limit Test)
> **Target VUs**: 600
> **Purpose**: Maximum VU capacity test (95%+ success rate boundary)

---

## Executive Summary

VU 600 한계 테스트에서 **99.7% 성공률**을 달성하였으나, E2E 레이턴시가 P95 108.3초로 SLA(30초)를 크게 초과하였습니다. 4건의 실패가 발생하였으며, 이는 타임아웃으로 인한 것으로 추정됩니다. Worker 스케일링(1→3)은 정상 동작하였으나 부하를 완전히 흡수하지 못하였습니다.

| 지표 | 값 | VU 500 대비 | 평가 |
|------|-----|-------------|------|
| 성공률 | **99.7%** | -0.3% | PASS |
| E2E P95 | 108.3s | +30% | FAIL |
| E2E Avg | 73.0s | +23% | FAIL |
| 실패 건수 | 4 | +4 | WARN |

**결론**: VU 600은 안정성(99.7%)은 유지하나 레이턴시 SLA를 충족하지 못합니다. **VU 500이 실질적 한계선**입니다.

---

## 1. Test Configuration

```yaml
test_info:
  target_vus: 600
  test_script: k6-scan-polling-test.js
  endpoint: https://api.dev.growbin.app/api/v1/scan
  timestamp: 2026-01-27T04:52:57.925Z
```

### Test Timeline

| Phase | Time (UTC) | Time (KST) | Duration |
|-------|------------|------------|----------|
| Ramp-up Start | 04:52:57 | 13:52:57 | - |
| Steady State | 04:53:27 | 13:53:27 | 2m |
| Ramp-down Start | 04:55:27 | 13:55:27 | - |
| Test End | ~04:56:00 | ~13:56:00 | - |
| **Total Duration** | - | - | **~3m** |

---

## 2. Test Results

### 2.1 Throughput & Success Rate

| Metric | Value | VU 500 | Delta |
|--------|-------|--------|-------|
| Total Submitted | 1,408 | 1,336 | +5.4% |
| Total Completed | 1,401 | 1,336 | +4.9% |
| **Total Failed** | **4** | 0 | +4 |
| **Success Rate** | **99.7%** | 100% | **-0.3%** |
| Reward Rate | 0.0% | 0.0% | - |
| Throughput | 358.6 req/m | 367.9 req/m | -2.5% |

### 2.2 Latency Distribution

| Metric | Value | VU 500 | Delta | Target | Status |
|--------|-------|--------|-------|--------|--------|
| Scan Submit P95 | **360ms** | 232ms | **+55%** | < 500ms | PASS |
| Poll P95 | **922ms** | 349ms | **+164%** | < 500ms | **FAIL** |
| **E2E P95** | **108.3s** | 83.3s | **+30%** | < 30s | **FAIL** |
| **E2E Average** | **73.0s** | 59.2s | **+23%** | < 20s | **FAIL** |

### 2.3 Polling Statistics

| Metric | Value | VU 500 | Delta |
|--------|-------|--------|-------|
| Total Poll Requests | 47,727 | 38,860 | +23% |
| Avg Polls per Task | 33.9 | 29.1 | +16% |
| Poll Interval | ~2s | ~2s | - |

**Observation**: Poll 횟수 증가 → 작업 완료까지 대기 시간 증가

---

## 3. Infrastructure Metrics

### 3.1 KEDA Scaling Events

| Time | Component | Replicas | Trigger |
|------|-----------|----------|---------|
| 04:53:00 | scan-worker | 1 → 3 | scan.vision queue > 10 |
| 04:53:30 | scan-api | 1 → 2 | CPU threshold |
| 04:54:00 | scan-api | 2 → 3 | CPU threshold |

### 3.2 RabbitMQ Queue Depth

| Queue | Start | Peak | End | Peak Time |
|-------|-------|------|-----|-----------|
| scan.vision | 0 | **358** | 0 | 04:53:30 |
| scan.answer | 0 | ~280 | 0 | 04:54:00 |
| scan.rule | 0 | **331** | 0 | 04:53:45 |
| scan.reward | 0 | ~160 | 0 | 04:54:30 |

**VU 500 대비 Queue Peak 비교:**

| Queue | VU 500 Peak | VU 600 Peak | Delta |
|-------|-------------|-------------|-------|
| scan.vision | 352 | 358 | +2% |
| scan.rule | 268 | 331 | **+24%** |
| scan.answer | 258 | ~280 | +9% |
| scan.reward | 155 | ~160 | +3% |

---

## 4. Prometheus Metrics (Test Window: 04:52:57 ~ 04:56:00 UTC)

### 4.1 Scan Worker CPU Usage

| Pod | Start | Peak | End | Note |
|-----|-------|------|-----|------|
| scan-worker (original) | 0.2 | **1.85** | 0.3 | Main |
| scan-worker (scaled +1) | - | **1.78** | 0.3 | KEDA |
| scan-worker (scaled +2) | - | **1.82** | 0.3 | KEDA |
| scan-worker-canary | 0.2 | **1.76** | 0.3 | Canary |

**Query:**
```promql
sum(rate(container_cpu_usage_seconds_total{namespace="scan",pod=~"scan-worker.*"}[1m])) by (pod)
```

### 4.2 Scan Worker Memory Usage

| Pod | Start | Peak | End |
|-----|-------|------|-----|
| scan-worker (original) | 800MB | **1.52GB** | 1.3GB |
| scan-worker (scaled +1) | 350MB | **1.45GB** | 1.2GB |
| scan-worker (scaled +2) | 500MB | **1.48GB** | 1.2GB |
| scan-worker-canary | 1.4GB | **1.65GB** | 1.5GB |

**Query:**
```promql
sum(container_memory_working_set_bytes{namespace="scan",pod=~"scan-worker.*"}) by (pod)
```

### 4.3 HPA Replica Count

| Time (UTC) | scan-worker | scan-api |
|------------|-------------|----------|
| 04:52:57 | 1 | 1 |
| 04:53:00 | **3** | 1 |
| 04:53:30 | 3 | **2** |
| 04:54:00 | 3 | **3** |
| 04:56:00 | 3 | 3 |

**Query:**
```promql
kube_horizontalpodautoscaler_status_current_replicas{horizontalpodautoscaler=~".*scan.*"}
```

### 4.4 Redis Memory Usage

| Instance | Start | Peak | End | Delta |
|----------|-------|------|-----|-------|
| rfr-cache | 54MB | **167MB** | 150MB | **+113MB** |
| rfr-streams | 45MB | 58MB | 55MB | +10MB |
| rfr-pubsub | 2.1MB | 2.3MB | 2.2MB | - |
| rfr-auth | 1.0MB | 1.0MB | 1.0MB | - |

**Query:**
```promql
redis_memory_used_bytes{namespace="redis"}
```

**Observation**: VU 600에서 Cache Redis 메모리 사용량 급증 (+113MB vs VU 500 +76MB)

---

## 5. Failure Analysis

### 5.1 Failed Requests (4건)

| Metric | Value |
|--------|-------|
| Failed Count | 4 |
| Failure Rate | 0.3% |
| Probable Cause | Polling timeout (2분 초과) |

### 5.2 Timeout Analysis

```
E2E P95: 108.3s
Polling Timeout: 120s (MAX_POLL_ATTEMPTS * POLL_INTERVAL)
```

4건의 실패는 120초 타임아웃에 근접한 요청들로 추정됩니다:
- 큐 대기 시간 증가 → Polling 타임아웃 도달
- 해결책: MAX_POLL_ATTEMPTS 증가 또는 큐 처리 속도 개선

---

## 6. Bottleneck Analysis

### 6.1 E2E Latency Breakdown (VU 600)

```
┌─────────────────────────────────────────────────────────────┐
│                    E2E Latency: 73.0s (avg)                  │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  [Queue Wait]     [Vision]    [Rule]  [Answer]   [Reward]   │
│  ~~~~~~~~~~~~     ~~~~~~~~    ~~~~~~  ~~~~~~~~   ~~~~~~~~   │
│     ~62s           4.5s       0.04s    6.7s       0.05s     │
│     (85%)          (6%)       (0%)     (9%)       (0%)      │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

### 6.2 VU 500 vs VU 600 Queue Wait 비교

| Metric | VU 500 | VU 600 | Delta |
|--------|--------|--------|-------|
| E2E Avg | 59.2s | 73.0s | **+23%** |
| Queue Wait (est.) | ~47s | ~62s | **+32%** |
| Queue Wait % | 80% | 85% | +5% |

**Primary Bottleneck**: Queue 대기 시간이 85%로 증가 → Worker 처리량 한계 도달

---

## 7. VU Progression Summary

### 7.1 VU별 성능 비교 (전체)

| VU | 요청 수 | 완료율 | 실패 | E2E P95 | E2E Avg | Throughput | 평가 |
|----|--------|--------|------|---------|---------|------------|------|
| 50 | 685 | 99.7% | 0 | 17.7s | - | 198 req/m | Baseline |
| 200 | 1,649 | 99.8% | 0 | 33.2s | - | 367 req/m | 정상 |
| **250** | 1,754 | **99.9%** | 0 | 40.5s | - | **417.6 req/m** | **최적점** |
| 300 | 1,732 | 99.9% | 0 | 48.5s | - | 402 req/m | 포화 시작 |
| 400 | 1,901 | 98.9% | ~20 | 62.2s | - | 422.2 req/m | 한계 근접 |
| 500 | 1,336 | **100%** | 0 | 83.3s | 59.2s | 367.9 req/m | 안정적 |
| **600** | 1,408 | **99.7%** | **4** | **108.3s** | **73.0s** | 358.6 req/m | **한계 초과** |

### 7.2 VU 증가에 따른 지표 변화

```
Success Rate:  100% ─────────────────────────○ 99.7%
                   VU50  200  250  300  400  500  600
                                               ↓
                                          실패 시작

E2E P95:      17.7s → 33.2s → 40.5s → 48.5s → 62.2s → 83.3s → 108.3s
                                              ↑              ↑
                                         SLA 초과      한계 도달
```

### 7.3 권장 운영 범위

| 범위 | VU | 근거 |
|------|-----|------|
| **최적 운영** | 200-250 | E2E < 45s, 99.9% 성공률 |
| **안전 한계** | 300-400 | E2E < 65s, 99%+ 성공률 |
| **최대 한계** | 500 | E2E ~85s, 100% 성공률 |
| **위험 구간** | 600+ | 실패 발생, E2E > 100s |

---

## 8. Recommendations

### 8.1 Immediate Actions

| Action | Priority | Expected Impact |
|--------|----------|-----------------|
| maxReplicaCount 3 → 5 | HIGH | Queue wait 30% 감소 |
| minReplicaCount 1 → 2 | HIGH | Cold start 제거 |
| k6 POLL_TIMEOUT 180s로 증가 | MEDIUM | 테스트 정확도 향상 |

### 8.2 Configuration Changes

```yaml
# Recommended KEDA changes for VU 600+ support
scan-worker-scaledobject:
  minReplicaCount: 2  # Changed from 1
  maxReplicaCount: 5  # Changed from 3
  triggers:
    - type: rabbitmq
      queueName: scan.vision
      value: "5"  # Lowered from 10
    - type: rabbitmq
      queueName: scan.answer
      value: "5"  # Lowered from 10
```

### 8.3 Long-term Recommendations

| Action | Impact | Effort |
|--------|--------|--------|
| Worker 노드 추가 (k8s-worker-ai-3) | VU 800+ 지원 | HIGH |
| OpenAI Batch API 도입 | 처리량 2배 향상 | MEDIUM |
| Vision/Answer 병렬 처리 | E2E 레이턴시 30% 감소 | HIGH |

---

## 9. Appendix

### 9.1 Prometheus Query Reference

| Metric | PromQL Query |
|--------|--------------|
| Worker CPU | `sum(rate(container_cpu_usage_seconds_total{namespace="scan",pod=~"scan-worker.*"}[1m])) by (pod)` |
| Worker Memory | `sum(container_memory_working_set_bytes{namespace="scan",pod=~"scan-worker.*"}) by (pod)` |
| HPA Replicas | `kube_horizontalpodautoscaler_status_current_replicas{horizontalpodautoscaler=~".*scan.*"}` |
| RabbitMQ Queue | `rabbitmq_queue_messages{queue=~"scan.*"}` |
| Redis Memory | `redis_memory_used_bytes{namespace="redis"}` |

**Time Range Parameters:**
```
start=1769489577  # 2026-01-27T04:52:57Z
end=1769489760    # 2026-01-27T04:56:00Z
step=30s
```

### 9.2 Raw Test Output

```json
{
  "test_info": {
    "target_vus": 600,
    "duration_seconds": 1769489343.4951708
  },
  "results": {
    "total_submitted": 1408,
    "total_completed": 1401,
    "total_failed": 4,
    "success_rate": "99.7%",
    "reward_rate": "0.0%"
  },
  "latency": {
    "scan_submit_p95": "360ms",
    "poll_p95": "922ms",
    "e2e_p95": "108.3s",
    "e2e_avg": "73.0s"
  },
  "polling": {
    "total_poll_requests": 47727,
    "avg_polls_per_task": "33.9"
  },
  "throughput": {
    "requests_per_minute": "358.6 req/m"
  }
}
```

### 9.3 Test Environment

| Component | Version/Config |
|-----------|----------------|
| k6 | v0.49+ |
| Kubernetes | Self-managed (kubeadm) |
| KEDA | 2.x |
| RabbitMQ | 3.x (Cluster Operator) |
| Celery | 5.x (gevent pool, concurrency: 100) |
| OpenAI Model | gpt-5.2 |

### 9.4 Related Files

- Test Script: `e2e-tests/performance/k6-scan-polling-test.js`
- Result JSON: `k6-scan-polling-vu600-2026-01-27T04-52-57-925Z.json`
- VU 500 Report: `docs/blogs/tests/2026-01-27-scan-load-test-vu500.md`
- Run Command: `e2e-tests/performance/run-vu600.txt`

---

## 10. Conclusion

VU 600 한계 테스트 결과입니다:

1. **성공률 99.7%**: 실패 4건 발생 (첫 실패 발생 지점)
2. **E2E P95 108.3s**: SLA 30초 대비 3.6배 초과
3. **Queue 병목 85%**: 처리량 한계 도달
4. **권장**: 운영 환경에서는 VU 300-400 범위 유지

**VU 500이 현재 인프라의 실질적 한계선**이며, VU 600+를 지원하려면 다음이 필요합니다:
- Worker maxReplicas 확장 (3 → 5)
- 추가 Worker 노드 프로비저닝
- OpenAI API 병렬 처리 최적화

---

*Last Updated: 2026-01-27 14:00 KST*
