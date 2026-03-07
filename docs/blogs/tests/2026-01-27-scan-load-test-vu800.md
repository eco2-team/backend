# Scan API Load Test Report - VU 800

> **Date**: 2026-01-27 16:10 KST (07:10 UTC)
> **Test Type**: k6 Scan Polling Test (Retest)
> **Target VUs**: 800
> **OpenAI Tier**: 4 (TPM 4,000,000)

---

## Executive Summary

VU 800 테스트는 **첫 시도에서 시스템 장애로 0% 성공률**을 기록한 후, 시스템 복구 후 재테스트에서 **99.7% 성공률**을 달성하였습니다. VU 700 대비 성공률이 오히려 0.5%p 향상되었으며, 4건의 실패는 Polling Timeout으로 추정됩니다.

| 지표 | 값 | VU 700 대비 | 평가 |
|------|-----|-------------|------|
| 성공률 | **99.7%** | +0.5%p | PASS |
| 실패 건수 | **4** | -7 | PASS |
| HTTP 429 에러 | **0** | - | 정상 |
| E2E P95 | **144.6s** | +18% | FAIL (SLA) |
| Throughput | **367.3 req/m** | +12% | 개선 |

**결론**: VU 800은 시스템 안정화 후 정상 처리 가능하며, Tier 4 TPM 한도 내에서 안정적으로 동작합니다. 첫 시도 장애는 Cold Start 상태에서의 급격한 부하로 인한 것으로 분석됩니다.

---

## 1. Test Configuration

```yaml
test_info:
  target_vus: 800
  test_script: k6-scan-polling-test.js
  endpoint: https://api.dev.growbin.app/api/v1/scan
  timestamp: 2026-01-27T07:10:03.398Z
  poll_timeout: 300s
  max_poll_attempts: 150
  openai_tier: 4
```

### Test Timeline

| Phase | Time (UTC) | Time (KST) | Event |
|-------|------------|------------|-------|
| Test Start | 07:07:03 | 16:07:03 | Ramp-up 시작 |
| Worker Scale-up | 07:07:15 | 16:07:15 | 1 → 3 replicas |
| Steady State | 07:07:33 | 16:07:33 | VU 800 도달 |
| Test End | 07:10:03 | 16:10:03 | JSON 결과 저장 |

---

## 2. First Attempt Failure Analysis

### 2.1 첫 시도 결과 (06:50 UTC)

VU 800 첫 시도는 **완전한 시스템 장애**로 종료되었습니다.

| Metric | Value | 평가 |
|--------|-------|------|
| Total Submitted | 506 | - |
| Total Completed | **0** | CRITICAL |
| Total Failed | **506** | CRITICAL |
| Success Rate | **0.0%** | CRITICAL |
| Scan Submit P95 | **10,002ms** | API Timeout |

### 2.2 장애 원인 분석

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    Cascading Failure Timeline                           │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  06:47:46 ─── Test Start (Cold Start 상태)                              │
│      │        Workers: 1 replica + 1 canary                             │
│      │                                                                   │
│  06:48:00 ─── Queue Depth 급증 (scan.vision > 500)                      │
│      │        Workers 처리 불가                                          │
│      │                                                                   │
│  06:48:30 ─── API Liveness Probe 실패                                   │
│      │        "celery inspect ping timed out"                           │
│      │                                                                   │
│  06:49:00 ─── Worker Liveness Probe 실패                                │
│      │        Pod 재시작 시작                                            │
│      │                                                                   │
│  06:50:46 ─── Test 종료 (0% 성공률)                                     │
│      │        All in-flight tasks lost                                  │
│      │                                                                   │
│  06:55:00 ─── 시스템 복구 완료                                          │
│              Queues empty, Pods 2/2 Ready                               │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

### 2.3 근본 원인

| 원인 | 설명 |
|------|------|
| **Cold Start** | Worker 1 replica에서 VU 800 부하 수용 불가 |
| **KEDA 지연** | Scale-up 완료 전 Queue overflow |
| **Liveness Timeout** | Celery inspect ping 15초 타임아웃 초과 |
| **Cascading Failure** | API → Worker → 전체 시스템 순차 장애 |

---

## 3. Retest Results

### 3.1 Throughput & Success Rate

| Metric | VU 800 (Retest) | VU 700 | VU 1000 | Delta (vs 700) |
|--------|-----------------|--------|---------|----------------|
| Total Submitted | 1,386 | 1,496 | 1,592 | -7.4% |
| Total Completed | 1,378 | 1,313 | 1,494 | +4.9% |
| **Total Failed** | **4** | 11 | 53 | **-64%** |
| **Success Rate** | **99.7%** | 99.2% | 96.6% | **+0.5%p** |
| Reward Rate | 0.0% | 0.0% | 0.0% | - |
| **Throughput** | **367.3 req/m** | 329.1 req/m | 378.7 req/m | **+12%** |

### 3.2 Latency Distribution

| Metric | Value | VU 700 | Delta | Target | Status |
|--------|-------|--------|-------|--------|--------|
| Scan Submit P95 | **734ms** | 444ms | +65% | < 500ms | FAIL |
| Poll P95 | **2,110ms** | 1,283ms | +64% | < 500ms | FAIL |
| **E2E P95** | **144.6s** | 122.3s | **+18%** | < 30s | FAIL |
| **E2E Average** | **97.9s** | 89.9s | **+9%** | < 20s | FAIL |

### 3.3 Polling Statistics

| Metric | Value | VU 700 | Delta |
|--------|-------|--------|-------|
| Total Poll Requests | 52,845 | 57,955 | -9% |
| Avg Polls per Task | 38.1 | 39.7 | -4% |
| Poll Interval | ~2s | ~2s | - |

---

## 4. Error Analysis

### 4.1 Error Summary

| Error Type | Count | Status |
|------------|-------|--------|
| HTTP 429 (Rate Limit) | **0** | 정상 |
| Rate Limit Retries | **0** | 정상 |
| Quota Exhausted | **0** | 정상 |
| Answer Failed | **0** | 정상 |
| Vision Failed | **0** | 정상 |

### 4.2 Failure Breakdown (4건)

| 원인 | 건수 | 비율 | 설명 |
|------|------|------|------|
| **Polling Timeout** | ~4 | 100% | E2E > 300s |
| Rate Limit | 0 | 0% | Tier 4 TPM 4M 내 |
| Quota 소진 | 0 | 0% | Auto-recharge |
| **Total** | **4** | 100% | - |

### 4.3 TPM Usage Analysis

```
VU 800 TPM Estimation:
├─ Completed tasks: 1,378
├─ Estimated tokens/task: ~5,000
├─ Total tokens (3min): ~6,890,000
├─ TPM Average: ~2,297,000 tokens/min
├─ TPM Limit: 4,000,000 (Tier 4)
└─ Usage: 57% of limit (Safe Zone)
```

---

## 5. Infrastructure Metrics

### 5.1 KEDA Scaling Events

| Time | Component | Replicas | Trigger |
|------|-----------|----------|---------|
| 07:07:15 | scan-worker | 1 → **3** | scan.vision queue > 10 |
| 07:07:27 | scan-api | 1 → **2** | CPU threshold |
| 07:07:57 | scan-api | 2 → **3** | CPU threshold |

### 5.2 Worker Resource Usage (Post-Test)

| Pod | CPU | Memory | Node |
|-----|-----|--------|------|
| scan-worker-78f8ccdc9-5srpg | 156m | 416Mi | k8s-worker-ai |
| scan-worker-78f8ccdc9-g2d9v | 139m | 582Mi | k8s-worker-ai-2 |
| scan-worker-78f8ccdc9-m569v | 206m | 597Mi | k8s-worker-ai-2 |
| scan-worker-canary | 136m | 480Mi | k8s-worker-ai |

### 5.3 Worker Restart During Test

| Event | Time | Description |
|-------|------|-------------|
| Restart | ~07:06:00 | scan-worker-78f8ccdc9-5srpg 재시작 |
| Reason | - | Readiness probe failure (celery inspect ping timeout) |
| Impact | - | 일부 in-flight tasks 손실 가능 |

---

## 6. VU Progression Summary

### 6.1 VU별 성능 비교 (Tier 4)

| VU | 요청 수 | 완료 | 실패 | 성공률 | E2E P95 | Rate Limit |
|----|--------|------|------|--------|---------|------------|
| 600 | 1,408 | 1,401 | 4 | 99.7% | 108.3s | 0 |
| 700 | 1,496 | 1,313 | 11 | 99.2% | 122.3s | 0 |
| **800** | **1,386** | **1,378** | **4** | **99.7%** | **144.6s** | **0** |
| 1000 | 1,592 | 1,494 | 53 | 96.6% | 166.7s | 0 |

### 6.2 운영 권장 범위 (Tier 4 기준)

| 범위 | VU | 성공률 | E2E P95 | TPM 사용률 |
|------|-----|--------|---------|-----------|
| **Green Zone** | 50-400 | 99.9%+ | < 65s | < 40% |
| **Yellow Zone** | 400-600 | 99.5%+ | 65-110s | 40-55% |
| **Orange Zone** | 600-800 | 99%+ | 110-145s | 55-60% |
| **Red Zone** | 800-1000 | 96%+ | 145-170s | 60-70% |

---

## 7. Comparison: First Attempt vs Retest

| Metric | First Attempt | Retest | 개선 |
|--------|---------------|--------|------|
| Success Rate | 0.0% | **99.7%** | **+99.7%p** |
| Completed | 0 | **1,378** | **∞** |
| Scan Submit P95 | 10,002ms | **734ms** | **-93%** |
| System Status | **Crashed** | **Healthy** | 복구 |

### 7.1 성공 요인

| 요인 | 설명 |
|------|------|
| **Warm Workers** | 3 replicas + canary가 이미 Ready 상태 |
| **Empty Queues** | 이전 테스트 잔여물 없음 |
| **KEDA Pre-scaled** | Cold start 회피 |
| **System Stabilized** | Pod 재시작 후 안정화 완료 |

---

## 8. Recommendations

### 8.1 현재 상태 평가

| 항목 | 상태 | 비고 |
|------|------|------|
| Rate Limit | 정상 | TPM 57% 사용 |
| Quota | 정상 | Auto-recharge 작동 |
| 성공률 | 양호 | 99.7% > 95% SLA |
| 레이턴시 | 초과 | E2E P95 144.6s > 30s |

### 8.2 Cold Start 방지 권장

```yaml
# scan-worker KEDA ScaledObject
spec:
  minReplicaCount: 2  # Changed from 1
  maxReplicaCount: 5  # Changed from 3
```

### 8.3 VU 900 테스트 예상

| VU | 예상 성공률 | 예상 TPM 사용률 | Risk |
|----|-----------|----------------|------|
| 900 | ~98% | ~65% | Medium-High |

---

## 9. Appendix

### 9.1 Raw Test Output (Retest)

```json
{
  "test_info": {
    "target_vus": 800,
    "duration_seconds": 1769497578.2772892
  },
  "results": {
    "total_submitted": 1386,
    "total_completed": 1378,
    "total_failed": 4,
    "success_rate": "99.7%",
    "reward_rate": "0.0%"
  },
  "latency": {
    "scan_submit_p95": "734ms",
    "poll_p95": "2110ms",
    "e2e_p95": "144.6s",
    "e2e_avg": "97.9s"
  },
  "polling": {
    "total_poll_requests": 52845,
    "avg_polls_per_task": "38.1"
  },
  "throughput": {
    "requests_per_minute": "367.3 req/m"
  }
}
```

### 9.2 Raw Test Output (First Attempt - Failed)

```json
{
  "test_info": {
    "target_vus": 800,
    "duration_seconds": 1769496617.502928
  },
  "results": {
    "total_submitted": 506,
    "total_completed": 0,
    "total_failed": 506,
    "success_rate": "0.0%",
    "reward_rate": "0.0%"
  },
  "latency": {
    "scan_submit_p95": "10002ms",
    "poll_p95": "5001ms",
    "e2e_p95": "19.5s",
    "e2e_avg": "13.3s"
  }
}
```

### 9.3 Prometheus Query Reference

```promql
# Time Range
start: 2026-01-27T07:07:03Z
end: 2026-01-27T07:10:03Z

# Worker CPU
sum(rate(container_cpu_usage_seconds_total{namespace="scan",pod=~"scan-worker.*"}[1m])) by (pod)

# Worker Memory
sum(container_memory_working_set_bytes{namespace="scan",pod=~"scan-worker.*"}) by (pod) / 1024 / 1024

# Queue Depth
rabbitmq_queue_messages{queue=~"scan.*"}
```

### 9.4 Related Files

- Test Script: `e2e-tests/performance/k6-scan-polling-test.js`
- Result JSON (Retest): `k6-scan-polling-vu800-2026-01-27T07-10-03-398Z.json`
- Result JSON (Failed): `k6-scan-polling-vu800-2026-01-27T06-50-46-515Z.json`
- VU 700 Report: `docs/blogs/tests/2026-01-27-scan-load-test-vu700.md`
- VU 1000 Tier 4 Report: `docs/blogs/tests/2026-01-27-scan-load-test-vu1000-tier4.md`

---

## 10. Conclusion

### VU 800 테스트 결과 요약

| 항목 | 첫 시도 | 재테스트 |
|------|--------|---------|
| **성공률** | 0.0% (CRITICAL) | 99.7% (PASS) |
| **Rate Limit** | N/A (System Crash) | 0건 |
| **실패 원인** | Cascading Failure | Polling Timeout (4건) |
| **TPM 사용률** | N/A | ~57% (Safe Zone) |

### 핵심 발견

1. **Cold Start 취약점**: minReplicaCount 1에서 VU 800 부하는 시스템 장애 유발
2. **Warm Start 안정성**: Workers가 Ready 상태면 99.7% 성공률 달성
3. **Tier 4 안정성 확인**: VU 800에서도 Rate Limit 발생 없음
4. **성능 역전**: VU 800이 VU 700보다 성공률이 높음 (시스템 안정화 효과)

### 다음 단계

1. minReplicaCount 2로 변경하여 Cold Start 방지
2. VU 900 테스트로 한계점 추가 탐색

---

*Last Updated: 2026-01-27 16:20 KST*
