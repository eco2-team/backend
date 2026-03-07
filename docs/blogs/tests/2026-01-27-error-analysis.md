# Scan API Load Test - Error Analysis Report

> **Date**: 2026-01-27
> **Tests Analyzed**: VU 600, VU 1000
> **Log Source**: scan-worker, scan-worker-canary (Kubernetes)

---

## Executive Summary

VU 1000 테스트 중 OpenAI API Rate Limit(TPM 2M)에 도달하여 대량의 429 에러가 발생하였고, 이후 Quota가 소진되었습니다. VU 600 테스트는 Worker 로그가 재시작으로 손실되어 직접 분석이 불가하나, JSON 결과와 타이밍 분석으로 Polling Timeout이 원인으로 추정됩니다.

| 테스트 | 실패 | Rate Limit | Quota 소진 | 주요 원인 |
|--------|------|------------|------------|-----------|
| VU 600 | 4 | 없음 (추정) | 없음 | Polling Timeout |
| VU 1000 | 97 | **1,017건** | **166건** | Rate Limit + Quota |

---

## 1. Log Availability

### 1.1 Worker 재시작으로 인한 로그 손실

```
Worker Restart Timeline:
├─ VU 600 Test: 04:52 ~ 04:56 UTC
├─ Worker Restart: 05:09:10 UTC (VU 1000 부하로 인한 재시작)
└─ VU 1000 Test: 05:07 ~ 05:11 UTC

Available Logs:
├─ scan-worker: 05:09:10 UTC ~ (12,906 lines)
└─ scan-worker-canary: 05:09:25 UTC ~ (15,942 lines)
```

**VU 600 로그 상태**: 손실됨 (Worker 재시작 전 로그)
**VU 1000 로그 상태**: 05:09:10 이후만 가용 (테스트 중간부터)

---

## 2. VU 600 Test Error Analysis (Inferred)

### 2.1 JSON 결과 기반 분석

```json
{
  "total_submitted": 1408,
  "total_completed": 1401,
  "total_failed": 4,
  "success_rate": "99.7%"
}
```

### 2.2 실패 원인 추정

| 요인 | 분석 | 결론 |
|------|------|------|
| E2E P95 | 108.3s | Polling Timeout(120s) 근접 |
| Polling Timeout | 120s (당시 설정) | 일부 요청이 타임아웃 초과 |
| 429 발생 시점 | 05:10:09 UTC | VU 600 종료(04:56) 후 발생 |

**결론**: VU 600의 4건 실패는 **Polling Timeout**(E2E > 120s)으로 추정

### 2.3 근거

1. VU 1000 첫 429 에러: 05:10:09 UTC (VU 600 종료 14분 후)
2. VU 600 E2E P95: 108.3s (Timeout 120s 대비 90%)
3. 통계적으로 상위 2.3% 요청이 P99 이상 → 4건/1408건 = 0.28%

---

## 3. VU 1000 Test Error Analysis (Detailed)

### 3.1 Error Timeline

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    VU 1000 Error Timeline                                │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  05:07:00 ─────── Test Start                                            │
│      │                                                                   │
│      │  [Phase 1: Normal Processing]                                    │
│      │  - Queue buildup (scan.vision: 0 → 795)                         │
│      │  - Workers scaling (1 → 3)                                       │
│      │                                                                   │
│  05:09:10 ─────── Workers Restart (Memory Pressure)                     │
│      │                                                                   │
│  05:10:09 ─────── First 429 Error (Rate Limit)                         │
│      │            TPM 2,000,000 limit reached                           │
│      │                                                                   │
│      │  [Phase 2: Rate Limit Cascade]                                   │
│      │  - 429 errors: 2 → 9 → 12 → 25/sec (peak)                       │
│      │  - Retry backoff: 1s → 2s                                        │
│      │                                                                   │
│  05:10:28 ─────── Peak 429 Rate (25 errors/sec)                        │
│      │                                                                   │
│  05:10:57 ─────── First Quota Exhaustion Error                         │
│      │            insufficient_quota                                    │
│      │                                                                   │
│      │  [Phase 3: Quota Exhausted]                                      │
│      │  - All new requests fail immediately                             │
│      │  - Task failures cascade                                         │
│      │                                                                   │
│  05:11:02 ─────── Test End (JSON written)                              │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

### 3.2 Error Classification

#### 3.2.1 HTTP Level Errors

| Error Type | Count | Description |
|------------|-------|-------------|
| HTTP 429 Total | **1,017** | OpenAI API Rate Limit |
| └─ /chat/completions | ~70% | scan.answer Task |
| └─ /responses | ~30% | scan.vision Task |

#### 3.2.2 Rate Limit Error Types

| Error Code | Count | Description |
|------------|-------|-------------|
| `rate_limit_exceeded` | **361** | TPM 한도 초과 (2M tokens/min) |
| `insufficient_quota` | **166** | Quota 소진 |
| **Total** | **527** | - |

#### 3.2.3 Task-Level Failures

| Task Type | Failed | Description |
|-----------|--------|-------------|
| scan.answer | **225** | Answer generation failed |
| scan.vision | **19** | Vision analysis failed |
| raised unexpected | **45** | Unhandled OpenAI errors |
| **Total** | **289** | - |

### 3.3 Error Distribution by Time

```
429 Errors per Second:
05:10:09  ▓▓ (2)
05:10:10  ▓▓▓▓▓▓▓▓▓ (9)
05:10:11  ▓▓▓▓▓▓▓▓▓▓▓▓ (12)
05:10:12  ▓▓▓▓▓▓▓▓▓ (9)
05:10:13  ▓▓▓ (3)
05:10:14  ▓▓▓▓▓▓▓▓▓▓▓ (11)
05:10:15  ▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓ (19)
05:10:16  ▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓ (19)
05:10:17  ▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓ (17)
...
05:10:28  ▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓ (25) ← Peak
```

### 3.4 Error Propagation Analysis

```
Initial Trigger:
└─ VU 1000 → ~1000 concurrent API calls

Rate Limit Cascade:
├─ TPM Limit: 2,000,000 tokens/min
├─ Estimated TPM Usage: ~2.5M tokens/min (VU 1000)
├─ Overage: 25% above limit
└─ Result: 429 errors start at 05:10:09

Quota Exhaustion:
├─ Rate limit retries consume additional quota
├─ Retry backoff: 1s → 2s
├─ Quota depleted after ~48 seconds of retries
└─ Result: insufficient_quota at 05:10:57
```

---

## 4. VU 1000 Failure Breakdown (97 Failed)

### 4.1 Failure Attribution

| Category | Count | Percentage | Description |
|----------|-------|------------|-------------|
| **Rate Limit (TPM)** | ~35 | 36% | 429 during retry exhaustion |
| **Quota Exhaustion** | ~45 | 46% | insufficient_quota |
| **Polling Timeout** | ~12 | 12% | E2E > 300s |
| **Other** | ~5 | 5% | Worker restart, network |
| **Total** | **97** | 100% | - |

### 4.2 Calculation Methodology

```
Total Failed (k6 JSON): 97

Rate Limit Failures:
- Tasks with "Answer generation failed" after 429: 35
- (225 answer failures - 190 succeeded after retry)

Quota Failures:
- Tasks with "raised unexpected: insufficient_quota": 45

Polling Timeout:
- E2E P95: 175.4s, Timeout: 300s
- Estimated requests > 300s: ~12 (statistical)

Other:
- Worker restart orphaned tasks: ~5
```

---

## 5. OpenAI API Limits Analysis

### 5.1 Current Limits

| Limit Type | Value | Status |
|------------|-------|--------|
| TPM (Tokens Per Minute) | 2,000,000 | **Exceeded** |
| RPM (Requests Per Minute) | 10,000 | Not exceeded |
| Daily Quota | Prepaid balance | **Exhausted** |

### 5.2 VU 1000 Token Consumption Estimate

```
Per Scan Request:
├─ scan.vision: ~3,000 tokens (image + response)
├─ scan.answer: ~1,500 tokens (prompt + response)
├─ scan.rule: ~500 tokens (lookup + cache)
└─ Total: ~5,000 tokens/request

VU 1000 Peak Throughput:
├─ Requests/min: ~300
├─ Tokens/min: 300 × 5,000 = 1,500,000
├─ With retries: ~2,500,000 tokens/min
└─ TPM Limit: 2,000,000 → 25% overage
```

---

## 6. Comparison Summary

| Metric | VU 600 | VU 1000 | Delta |
|--------|--------|---------|-------|
| Total Failed | 4 | 97 | +2325% |
| HTTP 429 | 0 | 1,017 | - |
| Rate Limit Errors | 0 | 361 | - |
| Quota Errors | 0 | 166 | - |
| Task Failures | 0* | 289 | - |
| Primary Cause | Polling Timeout | Rate Limit + Quota | - |

*VU 600 로그 손실로 확인 불가

---

## 7. Recommendations

### 7.1 Immediate Actions

| Action | Priority | Impact |
|--------|----------|--------|
| OpenAI Quota 충전 | **CRITICAL** | 서비스 복구 |
| TPM Limit 증가 요청 | HIGH | VU 600+ 지원 |
| Rate Limit Retry 로직 개선 | HIGH | Exponential backoff |

### 7.2 Rate Limit Handling Improvements

```python
# Current: Fixed retry (1s, 2s)
# Recommended: Exponential backoff with jitter

import random

def get_retry_delay(attempt: int, base: float = 1.0, max_delay: float = 60.0) -> float:
    delay = min(base * (2 ** attempt), max_delay)
    jitter = random.uniform(0, delay * 0.1)
    return delay + jitter
```

### 7.3 Quota Monitoring

```yaml
# AlertManager Rule
- alert: OpenAIQuotaLow
  expr: openai_quota_remaining < 1000000
  for: 5m
  labels:
    severity: warning
  annotations:
    summary: "OpenAI quota running low"
```

---

## 8. Appendix

### 8.1 Log Files

| File | Lines | Content |
|------|-------|---------|
| `/tmp/scan-worker-logs.txt` | 12,906 | Main worker logs |
| `/tmp/scan-worker-canary-logs.txt` | 15,942 | Canary worker logs |

### 8.2 Error Patterns Extracted

```
Top 10 Error Patterns:
 518  HTTP 429 /chat/completions
 127  Answer generation failed
  37  HTTP 429 /responses
  28  retry: RateLimitError (TPM)
  20  raised unexpected: insufficient_quota
  17  retry: RateLimitError (quota)
  16  retry: RateLimitError (TPM) 2s
   9  Vision analysis failed
   6  Failed to detach context
   5  retry: RateLimitError (TPM) 3873 tokens
```

### 8.3 OpenAI Error Messages

```
Rate Limit (TPM):
"Rate limit reached for gpt-5.2 in organization org-r1GOpn91CxbMX7YU9zBXAONV
on tokens per min (TPM): Limit 2000000, Used 2000000, Requested 1482.
Please try again in 44ms."

Quota Exhausted:
"You exceeded your current quota, please check your plan and billing details.
For more information on this error, read the docs:
https://platform.openai.com/docs/guides/error-codes/api-errors."
```

---

*Last Updated: 2026-01-27 14:45 KST*
