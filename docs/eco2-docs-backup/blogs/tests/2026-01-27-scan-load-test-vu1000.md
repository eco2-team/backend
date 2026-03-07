# Scan API Load Test Report - VU 1000 (Limit Test)

> **Date**: 2026-01-27 14:11 KST (05:11 UTC)
> **Test Type**: k6 Scan Polling Test (Extreme Limit Test)
> **Target VUs**: 1000
> **Purpose**: 시스템 한계점 확인 (Breaking Point Test)

---

## Executive Summary

VU 1000 극한 테스트에서 **92.5% 성공률**로 95% SLA를 하회하였습니다. **97건의 실패 중 81건(83%)이 OpenAI API Rate Limit(TPM 2M 초과) 및 Quota 소진**으로 인한 것으로 확인되었습니다. 테스트 시작 3분 후(05:10:09) Rate Limit에 도달하였고, 48초 후(05:10:57) Quota가 완전히 소진되었습니다.

| 지표 | 값 | VU 600 대비 | 평가 |
|------|-----|-------------|------|
| 성공률 | **92.5%** | -7.2% | **FAIL** |
| 실패 건수 | **97** | +93 | **CRITICAL** |
| HTTP 429 에러 | **1,017** | - | **CRITICAL** |
| Quota 소진 | **166건** | - | **CRITICAL** |
| E2E P95 | **175.4s** | +62% | **FAIL** |

**Root Cause**: OpenAI API TPM(Tokens Per Minute) 한도 2,000,000 초과 → Rate Limit → Quota 소진

---

## 1. Test Configuration

```yaml
test_info:
  target_vus: 1000
  test_script: k6-scan-polling-test.js
  endpoint: https://api.dev.growbin.app/api/v1/scan
  timestamp: 2026-01-27T05:11:02.847Z
  poll_timeout: 300s  # 5분 (VU 600 대비 증가)
  max_poll_attempts: 150
```

### Test Timeline

| Phase | Time (UTC) | Time (KST) | Event |
|-------|------------|------------|-------|
| Test Start | 05:07:00 | 14:07:00 | Ramp-up 시작 |
| Worker Restart | 05:09:10 | 14:09:10 | Memory pressure로 재시작 |
| **Rate Limit Hit** | **05:10:09** | **14:10:09** | **첫 429 에러 발생** |
| Peak 429 | 05:10:28 | 14:10:28 | 25 errors/sec |
| **Quota Exhausted** | **05:10:57** | **14:10:57** | **insufficient_quota 시작** |
| Test End | 05:11:02 | 14:11:02 | JSON 결과 저장 |

---

## 2. Test Results

### 2.1 Throughput & Success Rate

| Metric | Value | VU 600 | VU 500 | Delta (vs 600) |
|--------|-------|--------|--------|----------------|
| Total Submitted | 1,645 | 1,408 | 1,336 | +16.8% |
| Total Completed | 1,204 | 1,401 | 1,336 | -14.1% |
| **Total Failed** | **97** | 4 | 0 | **+2325%** |
| **Success Rate** | **92.5%** | 99.7% | 100% | **-7.2%** |
| Reward Rate | 0.0% | 0.0% | 0.0% | - |
| Throughput | 301.1 req/m | 358.6 req/m | 367.9 req/m | -16.0% |

### 2.2 Latency Distribution

| Metric | Value | VU 600 | Delta | Target | Status |
|--------|-------|--------|-------|--------|--------|
| Scan Submit P95 | **787ms** | 360ms | **+119%** | < 500ms | **FAIL** |
| Poll P95 | **2,772ms** | 922ms | **+201%** | < 500ms | **FAIL** |
| **E2E P95** | **175.4s** | 108.3s | **+62%** | < 30s | **FAIL** |
| **E2E Average** | **121.4s** | 73.0s | **+66%** | < 20s | **FAIL** |

### 2.3 Polling Statistics

| Metric | Value | VU 600 | Delta |
|--------|-------|--------|-------|
| Total Poll Requests | 74,922 | 47,727 | +57% |
| Avg Polls per Task | 44.9 | 33.9 | +32% |
| Poll Interval | ~2s | ~2s | - |

---

## 3. Failure Analysis (Root Cause: OpenAI Rate Limit)

### 3.1 Error Summary

| Error Category | Count | Percentage |
|----------------|-------|------------|
| **HTTP 429 (Rate Limit)** | **1,017** | - |
| Rate Limit (TPM Exceeded) | 361 | - |
| Quota Exhausted | 166 | - |
| Answer Generation Failed | 225 | - |
| Vision Analysis Failed | 19 | - |
| Task Raised Unexpected | 45 | - |

### 3.2 Failure Breakdown (97건)

| 원인 | 건수 | 비율 | 설명 |
|------|------|------|------|
| **Quota 소진** | ~45 | 46% | insufficient_quota 에러 |
| **Rate Limit (TPM)** | ~35 | 36% | 429 retry 소진 후 실패 |
| **Polling Timeout** | ~12 | 12% | E2E > 300s |
| **기타** | ~5 | 5% | Worker 재시작 등 |
| **Total** | **97** | 100% | - |

### 3.3 Error Timeline

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    Error Progression Timeline                            │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  05:07:00 ─── Test Start                                                │
│      │                                                                   │
│      │  [Phase 1: Normal Processing - 3분간]                            │
│      │  - OpenAI API 정상 응답                                          │
│      │  - TPM 사용량 증가 중                                            │
│      │                                                                   │
│  05:10:09 ─── First 429 Error ──────────────────────────────────────    │
│      │        "Rate limit reached for gpt-5.2"                          │
│      │        "TPM: Limit 2000000, Used 2000000"                        │
│      │                                                                   │
│      │  [Phase 2: Rate Limit Cascade - 48초간]                          │
│      │  - 429 에러 폭발: 2 → 9 → 25/sec (peak)                         │
│      │  - Retry with backoff: 1s → 2s                                   │
│      │  - 총 1,017건 429 에러                                           │
│      │                                                                   │
│  05:10:57 ─── Quota Exhausted ──────────────────────────────────────    │
│      │        "You exceeded your current quota"                         │
│      │        "insufficient_quota"                                      │
│      │                                                                   │
│      │  [Phase 3: Complete Failure - 5초간]                             │
│      │  - 모든 새 요청 즉시 실패                                        │
│      │  - 166건 quota 에러                                              │
│      │                                                                   │
│  05:11:02 ─── Test End                                                  │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

### 3.4 429 Errors per Second

```
Time (UTC)    Count   Visualization
05:10:09      2       ▓▓
05:10:10      9       ▓▓▓▓▓▓▓▓▓
05:10:11      12      ▓▓▓▓▓▓▓▓▓▓▓▓
05:10:12      9       ▓▓▓▓▓▓▓▓▓
05:10:13      3       ▓▓▓
05:10:14      11      ▓▓▓▓▓▓▓▓▓▓▓
05:10:15      19      ▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓
05:10:16      19      ▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓
05:10:17      17      ▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓
05:10:28      25      ▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓ ← Peak
```

---

## 4. Example Error Logs

### 4.1 Rate Limit Error (TPM Exceeded)

```log
[2026-01-27 05:10:10,032: INFO/MainProcess] HTTP Request: POST https://api.openai.com/v1/responses "HTTP/1.1 429 Too Many Requests"

[2026-01-27 05:10:10,359: INFO/MainProcess] HTTP Request: POST https://api.openai.com/v1/responses "HTTP/1.1 429 Too Many Requests"

[2026-01-27 05:10:10,364: INFO/MainProcess] HTTP Request: POST https://api.openai.com/v1/chat/completions "HTTP/1.1 429 Too Many Requests"
```

### 4.2 Rate Limit Retry (TPM)

```log
[2026-01-27 05:10:XX: WARNING/MainProcess] retry: Retry in 1s: RateLimitError("Error code: 429 - {'error': {'message': 'Rate limit reached for gpt-5.2 in organization org-r1GOpn91CxbMX7YU9zBXAONV on tokens per min (TPM): Limit 2000000, Used 2000000, Requested 1482. Please try again in 44ms. Visit https://platform.openai.com/account/rate-limits to learn more.', 'type': 'tokens', 'param': None, 'code': 'rate_limit_exceeded'}}")

[2026-01-27 05:10:XX: WARNING/MainProcess] retry: Retry in 2s: RateLimitError("Error code: 429 - {'error': {'message': 'Rate limit reached for gpt-5.2 in organization org-r1GOpn91CxbMX7YU9zBXAONV on tokens per min (TPM): Limit 2000000, Used 2000000, Requested 3873. Please try again in 116ms. Visit https://platform.openai.com/account/rate-limits to learn more.', 'type': 'tokens', 'param': None, 'code': 'rate_limit_exceeded'}}")
```

### 4.3 Quota Exhausted Error

```log
[2026-01-27 05:10:57,XXX: WARNING/MainProcess] retry: Retry in 2s: RateLimitError("Error code: 429 - {'error': {'message': 'You exceeded your current quota, please check your plan and billing details. For more information on this error, read the docs: https://platform.openai.com/docs/guides/error-codes/api-errors.', 'type': 'insufficient_quota', 'param': None, 'code': 'insufficient_quota'}}")

[2026-01-27 05:11:22,571: ERROR/MainProcess] Task scan.answer[397f3543-91e4-40eb-b17b-663662f0fca1] raised unexpected: OpenAIError("Error code: 429 - {'error': {'message': 'You exceeded your current quota, please check your plan and billing details. For more information on this error, read the docs: https://platform.openai.com/docs/guides/error-codes/api-errors.', 'type': 'insufficient_quota', 'param': None, 'code': 'insufficient_quota'}}")
```

### 4.4 Task Failure Logs

```log
[2026-01-27 05:10:32,249: ERROR/MainProcess] Answer generation failed

[2026-01-27 05:10:58,556: ERROR/MainProcess] Answer generation failed

[2026-01-27 05:11:29,710: ERROR/MainProcess] Answer generation failed

[2026-01-27 05:11:29,728: ERROR/MainProcess] Task scan.answer[9425030c-0c56-45d2-b7c9-5c9493859fca] raised unexpected: OpenAIError("Error code: 429 - {'error': {'message': 'You exceeded your current quota...'}}")
```

### 4.5 Last Successful Tasks Before Rate Limit

```log
[2026-01-27 05:10:09,598: INFO/MainProcess] Task scan.rule[2e9781b7-8edb-470b-821d-0aec4bb9368e] succeeded in 5.711309377104044s

[2026-01-27 05:10:09,600: INFO/MainProcess] Task scan.vision[4ddd146d-b47e-450f-8612-8bcc27b8b60a] succeeded in 14.496931365225464s

[2026-01-27 05:10:09,603: INFO/MainProcess] Task scan.answer[c5f481a7-e22a-422b-80ee-0fbf9cf70bd8] succeeded in 15.328937161713839s

# ↑ 05:10:09.603 - Last successful answer task
# ↓ 05:10:10.032 - First 429 error (0.4초 후)
```

---

## 5. OpenAI API Limits Analysis

### 5.1 Current Limits

| Limit Type | Value | VU 1000 상태 | 실제 사용 |
|------------|-------|--------------|-----------|
| TPM (Tokens Per Minute) | 2,000,000 | **EXCEEDED** | ~2,500,000 |
| RPM (Requests Per Minute) | 10,000 | OK | **1,361** (peak) |
| Daily Quota | Prepaid balance | **EXHAUSTED** | - |

### 5.2 RPM Analysis from Logs

로그에서 추출한 OpenAI API 호출 현황입니다:

```
OpenAI HTTP Requests per Minute:
─────────────────────────────────────────────────
Time (UTC)   Requests   Status
─────────────────────────────────────────────────
05:09        338        Normal processing
05:10        1,361      Peak (Rate Limit 도달)
05:11        131        Quota exhausted
─────────────────────────────────────────────────
Total        1,830      (3분간)
```

**Endpoint 분포**:

| Endpoint | Count | Percentage | Purpose |
|----------|-------|------------|---------|
| `/v1/chat/completions` | 1,391 | 76% | scan.answer |
| `/v1/responses` | 439 | 24% | scan.vision |
| **Total** | **1,830** | 100% | - |

**RPM vs Limit 분석**:

```
Peak RPM:  1,361 requests/min (05:10 UTC)
RPM Limit: 10,000 requests/min
Usage:     13.6% of RPM limit

결론: RPM은 여유가 있으며, TPM이 병목 지점입니다
```

### 5.3 Token Consumption Estimate

```
Per Scan Request (estimated):
├─ scan.vision:  ~3,000 tokens (image analysis)
├─ scan.answer:  ~1,500 tokens (response generation)
├─ scan.rule:    ~500 tokens (rule lookup)
└─ Total:        ~5,000 tokens/request

VU 1000 Peak Load:
├─ Concurrent requests: ~300/min (worker capacity)
├─ Tokens/min:          300 × 5,000 = 1,500,000
├─ With retries:        ~2,500,000 tokens/min
├─ TPM Limit:           2,000,000
└─ Overage:             25% above limit
```

### 5.4 Why Rate Limit at 05:10:09?

```
Test started: 05:07:00
Rate limit hit: 05:10:09 (3분 9초 후)

Calculation:
- 3분간 누적 요청: ~1,000 requests
- 1분당 토큰 사용: ~1,500,000 tokens (추정)
- 분당 리밋 접근: 3분 후 TPM 2M 도달
- Burst traffic: 동시 요청으로 인해 TPM 초과
```

---

## 6. Infrastructure Metrics

### 6.1 KEDA Scaling Events

| Time (UTC) | Component | Replicas | Trigger |
|------------|-----------|----------|---------|
| 05:07:00 | scan-worker | 1 | Initial |
| 05:07:30 | scan-worker | 1 → **3** | scan.vision queue > 10 |
| 05:08:00 | scan-api | 1 → 2 → **3** | CPU threshold |

### 6.2 RabbitMQ Queue Depth

| Queue | Start | Peak | End | Note |
|-------|-------|------|-----|------|
| **scan.vision** | 0 | **795** | 0 | 2.2x VU 600 |
| **scan.rule** | 0 | **509** | 0 | +54% |
| **scan.answer** | 0 | **312** | 0 | +11% |
| **scan.reward** | 0 | **164** | 0 | +3% |

### 6.3 Worker Resource Usage

| Pod | CPU Peak | Memory Peak | Note |
|-----|----------|-------------|------|
| scan-worker-d56bh | 1.85 cores | 1,499MB | Scale-up |
| scan-worker-v7lj7 | 1.85 cores | 1,527MB | Scale-up |
| scan-worker-wtxmw | 1.72 cores | 1,774MB | Original |
| scan-worker-canary | 1.82 cores | 1,596MB | Canary |

**Warning**: Memory 1.5-1.7GB (Limit 1Gi 초과) → OOMKill 위험

---

## 7. VU Progression Summary

### 7.1 전체 VU 성능 비교

| VU | 요청 수 | 완료 | 실패 | 성공률 | E2E P95 | 실패 원인 |
|----|--------|------|------|--------|---------|-----------|
| 50 | 685 | 683 | 0 | 99.7% | 17.7s | - |
| 200 | 1,649 | 1,646 | 0 | 99.8% | 33.2s | - |
| **250** | 1,754 | 1,752 | 0 | **99.9%** | 40.5s | - |
| 300 | 1,732 | 1,730 | 0 | 99.9% | 48.5s | - |
| 400 | 1,901 | 1,880 | ~20 | 98.9% | 62.2s | Timeout |
| 500 | 1,336 | 1,336 | 0 | **100%** | 83.3s | - |
| 600 | 1,408 | 1,401 | 4 | 99.7% | 108.3s | Timeout |
| **1000** | 1,645 | 1,204 | **97** | **92.5%** | **175.4s** | **Rate Limit + Quota** |

### 7.2 운영 권장 범위

| 범위 | VU | 성공률 | E2E P95 | OpenAI TPM 상태 |
|------|-----|--------|---------|-----------------|
| **Green Zone** | 50-250 | 99.9%+ | < 45s | OK (~50%) |
| **Yellow Zone** | 250-400 | 99%+ | 45-65s | OK (~75%) |
| **Orange Zone** | 400-500 | 99.7%+ | 65-85s | Warning (~90%) |
| **Red Zone** | 500-600 | 99%+ | 85-110s | Near Limit |
| **Breaking Point** | 1000+ | < 95% | > 175s | **EXCEEDED** |

---

## 8. Recommendations

### 8.1 Immediate (Critical)

| Action | Priority | Expected Impact |
|--------|----------|-----------------|
| **OpenAI Quota 충전** | CRITICAL | 서비스 복구 |
| **TPM Limit 증가 요청** | CRITICAL | 4M TPM으로 업그레이드 |
| Rate Limit Retry 개선 | HIGH | Exponential backoff + jitter |
| maxReplicaCount 3 → 6 | HIGH | Queue 처리 개선 |

### 8.2 Rate Limit Handling Improvements

```python
# Current: Fixed retry (1s, 2s)
# Recommended: Exponential backoff with jitter

import random
from tenacity import retry, wait_exponential_jitter, stop_after_attempt

@retry(
    wait=wait_exponential_jitter(initial=1, max=60, jitter=5),
    stop=stop_after_attempt(5)
)
async def call_openai_api(prompt: str):
    return await openai_client.chat.completions.create(...)
```

### 8.3 OpenAI TPM 요청 분산

```yaml
# Option 1: Multiple API Keys (Round-robin)
openai_keys:
  - key: sk-xxx1  # TPM: 2M
  - key: sk-xxx2  # TPM: 2M
  # Total: 4M TPM

# Option 2: Request Throttling
rate_limiter:
  tokens_per_minute: 1800000  # 90% of limit
  burst_size: 50000
```

---

## 9. Appendix

### 9.1 Error Counts Summary

| Error Type | Main Worker | Canary Worker | Total |
|------------|-------------|---------------|-------|
| HTTP 429 | 738 | 620 | **1,358** |
| Rate Limit (TPM) | ~200 | ~161 | **361** |
| Quota Exhausted | ~100 | ~66 | **166** |
| Answer Failed | ~130 | ~95 | **225** |
| Vision Failed | ~10 | ~9 | **19** |

### 9.2 Log Files Analyzed

| File | Lines | Time Range |
|------|-------|------------|
| scan-worker-logs.txt | 12,906 | 05:09:10 ~ 05:25:06 UTC |
| scan-worker-canary-logs.txt | 15,942 | 05:09:25 ~ 05:25:07 UTC |

### 9.3 Raw Test Output

```json
{
  "test_info": {
    "target_vus": 1000,
    "duration_seconds": 1769490422.936763
  },
  "results": {
    "total_submitted": 1645,
    "total_completed": 1204,
    "total_failed": 97,
    "success_rate": "92.5%",
    "reward_rate": "0.0%"
  },
  "latency": {
    "scan_submit_p95": "787ms",
    "poll_p95": "2772ms",
    "e2e_p95": "175.4s",
    "e2e_avg": "121.4s"
  },
  "polling": {
    "total_poll_requests": 74922,
    "avg_polls_per_task": "44.9"
  },
  "throughput": {
    "requests_per_minute": "301.1 req/m"
  }
}
```

### 9.4 Related Files

- Test Script: `e2e-tests/performance/k6-scan-polling-test.js`
- Result JSON: `k6-scan-polling-vu1000-2026-01-27T05-11-02-847Z.json`
- Error Analysis: `docs/blogs/tests/2026-01-27-error-analysis.md`
- VU 600 Report: `docs/blogs/tests/2026-01-27-scan-load-test-vu600.md`

---

## 10. Conclusion

### VU 1000 실패 원인 확정

| 원인 | 건수 | 비율 |
|------|------|------|
| **OpenAI Quota 소진** | ~45 | 46% |
| **OpenAI Rate Limit (TPM)** | ~35 | 36% |
| Polling Timeout | ~12 | 12% |
| 기타 | ~5 | 5% |
| **Total** | **97** | 100% |

### 핵심 발견

1. **Root Cause**: OpenAI TPM 2M 한도 초과 (05:10:09)
2. **Cascade Effect**: Rate Limit → Retry → Quota 소진 (05:10:57)
3. **시간**: 테스트 시작 3분 후 Rate Limit 도달
4. **영향**: 97건 실패 중 81건(83%)이 OpenAI API 관련
5. **RPM vs TPM**: RPM은 13.6% 사용(1,361/10,000), TPM이 병목 지점

### 다음 단계

1. **즉시**: OpenAI Quota 충전
2. **단기**: TPM Limit 4M으로 업그레이드 요청
3. **중기**: Rate Limit 처리 로직 개선 (exponential backoff)
4. **장기**: Multi-key rotation 또는 Azure OpenAI 병행

---

*Last Updated: 2026-01-27 15:30 KST*
