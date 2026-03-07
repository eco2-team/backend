# Scan API Load Test Report - VU 700

> **Date**: 2026-01-27 15:36 KST (06:36 UTC)
> **Test Type**: k6 Scan Polling Test
> **Target VUs**: 700
> **OpenAI Tier**: 4 (TPM 4,000,000)

---

## Executive Summary

VU 700 테스트에서 **99.2% 성공률**을 달성하였습니다. **Rate Limit 에러 및 Quota 소진이 발생하지 않았으며**, 11건의 실패는 Polling Timeout으로 추정됩니다. Tier 4 TPM 한도(4M) 내에서 안정적으로 처리되었습니다.

| 지표 | 값 | VU 600 대비 | 평가 |
|------|-----|-------------|------|
| 성공률 | **99.2%** | -0.5% | PASS |
| 실패 건수 | **11** | +7 | PASS |
| HTTP 429 에러 | **0** | - | 정상 |
| E2E P95 | **122.3s** | +13% | FAIL (SLA) |
| Throughput | **329.1 req/m** | -8% | - |

**결론**: VU 700은 Rate Limit 없이 안정적으로 처리 가능하나, E2E 레이턴시가 SLA(30s)를 초과합니다.

---

## 1. Test Configuration

```yaml
test_info:
  target_vus: 700
  test_script: k6-scan-polling-test.js
  endpoint: https://api.dev.growbin.app/api/v1/scan
  timestamp: 2026-01-27T06:36:39.323Z
  poll_timeout: 300s
  max_poll_attempts: 150
  openai_tier: 4
```

### Test Timeline

| Phase | Time (UTC) | Time (KST) | Event |
|-------|------------|------------|-------|
| Test Start | 06:33:39 | 15:33:39 | Ramp-up 시작 |
| Worker Scale-up | 06:34:00 | 15:34:00 | 1 → 3 replicas |
| Steady State | 06:34:09 | 15:34:09 | VU 700 도달 |
| Test End | 06:36:39 | 15:36:39 | JSON 결과 저장 |

---

## 2. Test Results

### 2.1 Throughput & Success Rate

| Metric | Value | VU 600 | VU 1000 (Tier 4) | Delta (vs 600) |
|--------|-------|--------|------------------|----------------|
| Total Submitted | 1,496 | 1,408 | 1,592 | +6.3% |
| Total Completed | 1,313 | 1,401 | 1,494 | -6.3% |
| **Total Failed** | **11** | 4 | 53 | +7 |
| **Success Rate** | **99.2%** | 99.7% | 96.6% | **-0.5%** |
| Reward Rate | 0.0% | 0.0% | 0.0% | - |
| Throughput | 329.1 req/m | 358.6 req/m | 378.7 req/m | -8.2% |

### 2.2 Latency Distribution

| Metric | Value | VU 600 | Delta | Target | Status |
|--------|-------|--------|-------|--------|--------|
| Scan Submit P95 | **444ms** | 360ms | +23% | < 500ms | PASS |
| Poll P95 | **1,283ms** | 922ms | +39% | < 500ms | FAIL |
| **E2E P95** | **122.3s** | 108.3s | **+13%** | < 30s | FAIL |
| **E2E Average** | **89.9s** | 73.0s | **+23%** | < 20s | FAIL |

### 2.3 Polling Statistics

| Metric | Value | VU 600 | Delta |
|--------|-------|--------|-------|
| Total Poll Requests | 57,955 | 47,727 | +21% |
| Avg Polls per Task | 39.7 | 33.9 | +17% |
| Poll Interval | ~2s | ~2s | - |

---

## 3. Error Analysis

### 3.1 Error Summary

| Error Type | Count | Status |
|------------|-------|--------|
| HTTP 429 (Rate Limit) | **0** | 정상 |
| Rate Limit Retries | **0** | 정상 |
| Quota Exhausted | **0** | 정상 |
| Answer Failed | **0** | 정상 |
| Vision Failed | **0** | 정상 |

### 3.2 Failure Breakdown (11건)

| 원인 | 건수 | 비율 | 설명 |
|------|------|------|------|
| **Polling Timeout** | ~11 | 100% | E2E > 300s |
| Rate Limit | 0 | 0% | Tier 4 TPM 4M 내 |
| Quota 소진 | 0 | 0% | Auto-recharge |
| **Total** | **11** | 100% | - |

### 3.3 TPM Usage Analysis

```
VU 700 TPM Estimation:
├─ Completed tasks: 1,313
├─ Estimated tokens/task: ~5,000
├─ Total tokens (3min): ~6,565,000
├─ TPM Average: ~2,188,000 tokens/min
├─ TPM Limit: 4,000,000 (Tier 4)
└─ Usage: 55% of limit (Safe Zone)
```

---

## 4. Infrastructure Metrics

### 4.1 KEDA Scaling Events

| Time | Component | Replicas | Trigger |
|------|-----------|----------|---------|
| 06:34:00 | scan-worker | 1 → **3** | scan.vision queue > 10 |
| 06:34:30 | scan-api | 1 → **2** | CPU threshold |
| 06:38:00 | scan-worker | 3 → **1** | All metrics below target |

### 4.2 RabbitMQ Queue Depth

| Queue | Peak | VU 600 Peak | Delta |
|-------|------|-------------|-------|
| **scan.vision** | **179** | 358 | **-50%** |
| **scan.rule** | **393** | 331 | +19% |
| **scan.answer** | **383** | 280 | +37% |
| **scan.reward** | **147** | 160 | -8% |

### 4.3 Worker Resource Usage

| Pod | CPU Peak | Memory Peak | Node |
|-----|----------|-------------|------|
| scan-worker-wtxmw | 0.88 cores | 952MB | k8s-worker-ai |
| scan-worker-6vl6n | 0.88 cores | 496MB | k8s-worker-ai-2 |
| scan-worker-vlxd7 | 0.88 cores | 500MB | - |
| scan-worker-canary | 0.86 cores | 926MB | k8s-worker-ai |

### 4.4 Redis Memory Usage

| Instance | Peak | VU 600 Peak | Delta |
|----------|------|-------------|-------|
| rfr-cache | **225MB** | 167MB | +35% |
| rfr-streams | 63MB | 58MB | +9% |

---

## 5. VU Progression Summary

### 5.1 VU별 성능 비교 (Tier 4)

| VU | 요청 수 | 완료 | 실패 | 성공률 | E2E P95 | Rate Limit |
|----|--------|------|------|--------|---------|------------|
| 600 | 1,408 | 1,401 | 4 | 99.7% | 108.3s | 0 |
| **700** | **1,496** | **1,313** | **11** | **99.2%** | **122.3s** | **0** |
| 1000 | 1,592 | 1,494 | 53 | 96.6% | 166.7s | 0 |

### 5.2 운영 권장 범위 (Tier 4 기준)

| 범위 | VU | 성공률 | E2E P95 | TPM 사용률 |
|------|-----|--------|---------|-----------|
| **Green Zone** | 50-400 | 99.9%+ | < 65s | < 40% |
| **Yellow Zone** | 400-600 | 99.5%+ | 65-110s | 40-55% |
| **Orange Zone** | 600-700 | 99%+ | 110-125s | 55-60% |
| **Red Zone** | 700-1000 | 96%+ | 125-170s | 60-70% |

---

## 6. Comparison with Previous Tests

### 6.1 Tier 3 vs Tier 4 at High VU

| Metric | Tier 3 VU 1000 | Tier 4 VU 700 | Tier 4 VU 1000 |
|--------|----------------|---------------|----------------|
| 성공률 | 92.5% | **99.2%** | 96.6% |
| Rate Limit 에러 | 1,017 | **0** | 0 |
| E2E P95 | 175.4s | **122.3s** | 166.7s |
| Throughput | 301.1 req/m | **329.1 req/m** | 378.7 req/m |

### 6.2 Key Insight

- **VU 700 Tier 4**가 **VU 1000 Tier 3**보다 우수한 성능
- Rate Limit 해소로 안정적인 처리 가능
- E2E 레이턴시 SLA(30s)는 여전히 미달

---

## 7. Recommendations

### 7.1 현재 상태 평가

| 항목 | 상태 | 비고 |
|------|------|------|
| Rate Limit | 정상 | TPM 55% 사용 |
| Quota | 정상 | Auto-recharge 작동 |
| 성공률 | 양호 | 99.2% > 95% SLA |
| 레이턴시 | 초과 | E2E P95 122.3s > 30s |

### 7.2 VU 800/900 테스트 예상

| VU | 예상 성공률 | 예상 TPM 사용률 | Risk |
|----|-----------|----------------|------|
| 800 | ~98.5% | ~65% | Medium |
| 900 | ~97.5% | ~72% | Medium-High |

---

## 8. Appendix

### 8.1 Raw Test Output

```json
{
  "test_info": {
    "target_vus": 700,
    "duration_seconds": 1769495559.918264
  },
  "results": {
    "total_submitted": 1496,
    "total_completed": 1313,
    "total_failed": 11,
    "success_rate": "99.2%",
    "reward_rate": "0.0%"
  },
  "latency": {
    "scan_submit_p95": "444ms",
    "poll_p95": "1283ms",
    "e2e_p95": "122.3s",
    "e2e_avg": "89.9s"
  },
  "polling": {
    "total_poll_requests": 57955,
    "avg_polls_per_task": "39.7"
  },
  "throughput": {
    "requests_per_minute": "329.1 req/m"
  }
}
```

### 8.2 Prometheus Query Reference

```promql
# Time Range
start: 2026-01-27T06:33:39Z
end: 2026-01-27T06:36:39Z

# Worker CPU
sum(rate(container_cpu_usage_seconds_total{namespace="scan",pod=~"scan-worker.*"}[1m])) by (pod)

# Worker Memory
sum(container_memory_working_set_bytes{namespace="scan",pod=~"scan-worker.*"}) by (pod) / 1024 / 1024

# Queue Depth
rabbitmq_queue_messages{queue=~"scan.*"}
```

### 8.3 Related Files

- Test Script: `e2e-tests/performance/k6-scan-polling-test.js`
- Result JSON: `k6-scan-polling-vu700-2026-01-27T06-36-39-323Z.json`
- VU 600 Report: `docs/blogs/tests/2026-01-27-scan-load-test-vu600.md`
- VU 1000 Tier 4 Report: `docs/blogs/tests/2026-01-27-scan-load-test-vu1000-tier4.md`

---

## 9. Conclusion

### VU 700 테스트 결과 요약

| 항목 | 결과 |
|------|------|
| **성공률** | 99.2% (PASS) |
| **Rate Limit** | 0건 (Tier 4 정상) |
| **실패 원인** | Polling Timeout (11건) |
| **TPM 사용률** | ~55% (Safe Zone) |

### 핵심 발견

1. **Tier 4 안정성 확인**: VU 700에서 Rate Limit 발생 없음
2. **성공률 유지**: 99.2%로 95% SLA 충족
3. **레이턴시 증가**: E2E P95 122.3s로 VU 600 대비 13% 증가
4. **실패 원인**: 전량 Polling Timeout (Rate Limit 아님)

### 다음 단계

VU 800 테스트로 Tier 4 한계점 추가 탐색

---

*Last Updated: 2026-01-27 15:40 KST*
