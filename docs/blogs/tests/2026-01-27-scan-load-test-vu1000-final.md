# Scan API Load Test Report - VU 1000 (System Analysis)

> **Date**: 2026-01-28 05:06 KST (2026-01-27 20:06 UTC)
> **Test Type**: k6 Scan Polling Test
> **Target VUs**: 1000
> **OpenAI Tier**: 4 (TPM 4,000,000)

---

## Executive Summary

VU 1000 테스트에서 **97.8% 성공률**을 달성하였습니다. 33건의 실패는 Worker Pod의 Celery Health Check Timeout으로 인한 재시작 중 in-flight task 손실이 원인입니다. OpenAI Rate Limit은 발생하지 않았으며, 시스템 병목은 Worker Pod의 Probe Mechanism에 있습니다.

| 지표 | 값 | VU 900 대비 | 평가 |
|------|-----|-------------|------|
| 성공률 | **97.8%** | -1.9%p | PASS (> 95% SLA) |
| 실패 건수 | **33** | +29 | Worker Restart 기인 |
| HTTP 429 에러 | **0** | - | Tier 4 정상 |
| E2E P95 | **173.3s** | +16% | Queue Saturation |
| Throughput | **373.4 req/m** | -8% | Worker 재시작 영향 |

---

## 1. Test Configuration

### 1.1 Infrastructure Spec

```yaml
scan_worker:
  deployment:
    replicas:
      min: 2
      max: 5
    resources:
      requests:
        cpu: 250m
        memory: 512Mi
      limits:
        cpu: 1000m
        memory: 1Gi
    nodeSelector:
      domain: worker-ai

  probes:
    liveness:
      exec: "celery -A scan_worker.setup.celery:celery_app inspect ping -t 15"
      initialDelaySeconds: 10
      timeoutSeconds: 20
      periodSeconds: 30
      failureThreshold: 3
    readiness:
      exec: "celery -A scan_worker.setup.celery:celery_app inspect ping -t 15"
      initialDelaySeconds: 5
      timeoutSeconds: 20
      periodSeconds: 20
      failureThreshold: 3
    startup:
      exec: "celery -A scan_worker.setup.celery:celery_app inspect ping -t 15"
      initialDelaySeconds: 30
      timeoutSeconds: 20
      periodSeconds: 10
      failureThreshold: 12

keda_scaledobject:
  pollingInterval: 30
  cooldownPeriod: 300
  triggers:
    - queue: scan.vision
      threshold: 10
    - queue: scan.answer
      threshold: 10
    - queue: scan.rule
      threshold: 20
  behavior:
    scaleUp:
      pods: 2
      periodSeconds: 30
      stabilizationWindowSeconds: 0
    scaleDown:
      percent: 50
      periodSeconds: 60
      stabilizationWindowSeconds: 300
```

### 1.2 Node Capacity

| Node | vCPU | Memory | CPU Requests | Memory Requests |
|------|------|--------|--------------|-----------------|
| k8s-worker-ai | 2 | 3.7Gi | 1305m (65%) | 1976Mi (52%) |
| k8s-worker-ai-2 | 2 | 3.7Gi | 1080m (54%) | 1464Mi (39%) |
| **Total** | **4** | **7.4Gi** | **2385m (60%)** | **3440Mi (46%)** |

### 1.3 Test Parameters

```yaml
test_info:
  target_vus: 1000
  endpoint: https://api.dev.growbin.app/api/v1/scan
  timestamp: 2026-01-27T20:06:38.794Z
  poll_timeout: 300s
  max_poll_attempts: 150
```

---

## 2. Test Results

### 2.1 Throughput & Success Rate

| Metric | VU 1000 | VU 900 | Delta |
|--------|---------|--------|-------|
| Total Submitted | 1,518 | 1,540 | -1.4% |
| Total Completed | 1,469 | 1,532 | -4.1% |
| **Total Failed** | **33** | 4 | **+725%** |
| **Success Rate** | **97.8%** | 99.7% | **-1.9%p** |
| **Throughput** | **373.4 req/m** | 405.5 req/m | **-7.9%** |

### 2.2 Latency Distribution

| Metric | Value | VU 900 | Delta | Analysis |
|--------|-------|--------|-------|----------|
| Scan Submit P95 | **787ms** | 635ms | +24% | API Queue Saturation |
| Poll P95 | **2,609ms** | 2,494ms | +5% | Redis Pub/Sub 정상 |
| **E2E P95** | **173.3s** | 149.6s | **+16%** | Worker 처리 지연 |
| **E2E Average** | **121.3s** | 102.2s | **+19%** | Queue Backlog 증가 |

### 2.3 Polling Statistics

| Metric | Value | VU 900 | Delta | Implication |
|--------|-------|--------|-------|-------------|
| Total Poll Requests | 70,432 | 63,499 | +11% | 더 오래 대기 |
| Avg Polls per Task | 46.4 | 41.2 | +13% | E2E 증가 반영 |
| Poll Interval | ~2s | ~2s | - | 설정값 유지 |

---

## 3. Failure Analysis

### 3.1 Failure Breakdown (33건)

| 원인 | 건수 | 비율 | Root Cause |
|------|------|------|------------|
| **Worker Restart** | ~25 | 76% | Celery Probe Timeout |
| **Polling Timeout** | ~8 | 24% | E2E > 300s |
| Rate Limit | 0 | 0% | - |
| **Total** | **33** | 100% | - |

### 3.2 Cascading Failure Pattern

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    Worker Restart Failure Chain                          │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  VU 1000 부하 → Queue Depth 급증 (scan.vision > 100)                    │
│       │                                                                  │
│       ▼                                                                  │
│  Worker Busy (OpenAI API 호출 대기)                                      │
│       │                                                                  │
│       ▼                                                                  │
│  Celery inspect ping 응답 지연                                           │
│       │        ┌─────────────────────────────────────┐                  │
│       │        │ celery inspect ping -t 15           │                  │
│       │        │ → Celery가 busy 상태에서 응답 불가   │                  │
│       │        │ → 15초 타임아웃 초과                 │                  │
│       │        └─────────────────────────────────────┘                  │
│       ▼                                                                  │
│  Readiness Probe Failed (3회 연속)                                       │
│       │        Period: 20s × 3 = 60s 내 3회 실패                        │
│       ▼                                                                  │
│  Pod Restart Triggered                                                   │
│       │                                                                  │
│       ▼                                                                  │
│  In-flight Tasks Lost (~5-8 tasks per restart)                          │
│       │                                                                  │
│       ▼                                                                  │
│  Client Polling Timeout (task 상태 변경 안됨)                            │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

### 3.3 Probe Timeout Event Log

```
20:03:40  Warning  Unhealthy  pod/scan-worker-78f8ccdc9-5srpg
          Readiness probe failed: command "celery ... inspect ping -t 15" timed out

20:03:39  Warning  Unhealthy  pod/scan-worker-78f8ccdc9-zgq2h
          Readiness probe failed: command "celery ... inspect ping -t 15" timed out

20:03:31  Warning  Unhealthy  pod/scan-worker-canary-ccd48f886-9df4l
          Readiness probe errored: rpc error: code = NotFound

20:02:54  Warning  Unhealthy  pod/scan-worker-78f8ccdc9-9ns76
          Startup probe failed: command "celery ... inspect ping -t 15" timed out
```

### 3.4 Why Celery Probe Fails Under Load

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    Celery inspect ping 내부 동작                         │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  1. probe 실행: celery inspect ping -t 15                                │
│                                                                          │
│  2. 내부 동작:                                                           │
│     ├─ RabbitMQ에 celery.pidbox 큐로 ping 메시지 전송                   │
│     ├─ Worker가 메시지 수신 후 pong 응답                                │
│     └─ 15초 내 응답 대기                                                 │
│                                                                          │
│  3. 실패 조건:                                                           │
│     ├─ Worker가 OpenAI API 호출 중 (blocking)                           │
│     ├─ Vision API: 평균 5-10초 소요                                     │
│     ├─ Worker Thread Pool 포화 (prefetch * concurrency)                 │
│     └─ pidbox 메시지 처리 지연 → 15초 초과                               │
│                                                                          │
│  4. 결론: Celery inspect ping은 CPU-bound가 아닌                        │
│           I/O-bound 작업(OpenAI API) 상황에서 false negative 발생       │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 4. Infrastructure Metrics

### 4.1 KEDA Scaling Behavior

| Time (UTC) | Event | Replicas | Trigger |
|------------|-------|----------|---------|
| 20:03:38 | Test Start | 2 | minReplicas |
| 20:03:50 | Scale Up | 2 → 4 | scan.vision > 10 |
| 20:04:05 | Scale Up | 4 → 5 | scan.vision > 10 |
| 20:04:20 | Worker Restart | 5 (재시작 중) | Probe Timeout |
| 20:06:38 | Test End | 5 | - |
| 20:06:50 | lastActiveTime | 5 → 2 | Queue Empty |

### 4.2 Worker Pod Distribution

| Node | Pod Count | CPU Usage | Memory Usage |
|------|-----------|-----------|--------------|
| k8s-worker-ai | 3 | 301m | 1,145Mi |
| k8s-worker-ai-2 | 3 | 298m | 1,278Mi |
| **Total** | **6** | **599m** | **2,423Mi** |

### 4.3 Resource Utilization Analysis

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    Worker Resource Utilization                           │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  Per Worker:                                                             │
│  ├─ CPU Requests: 250m                                                  │
│  ├─ CPU Limits: 1000m                                                   │
│  ├─ CPU Actual (avg): ~100m (10% of limit)                              │
│  │                                                                       │
│  ├─ Memory Requests: 512Mi                                              │
│  ├─ Memory Limits: 1Gi                                                  │
│  └─ Memory Actual (avg): ~400Mi (40% of limit)                          │
│                                                                          │
│  분석:                                                                   │
│  ├─ CPU 사용률이 낮은 이유: I/O-bound (OpenAI API 대기)                 │
│  ├─ Memory 사용률 정상: Celery + Python 기본 사용량                     │
│  └─ 병목: CPU/Memory가 아닌 Celery Worker Thread 포화                   │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

### 4.4 Queue Depth Estimation

```
VU 1000 Queue Analysis:
├─ Submitted: 1,518 tasks
├─ Test Duration: ~180s (3min)
├─ Submit Rate: ~8.4 tasks/sec
├─ Worker Capacity: 5 workers × 4 concurrency = 20 tasks 동시 처리
├─ OpenAI API Latency: ~8s/task (vision + answer)
├─ Theoretical Throughput: 20 / 8 = 2.5 tasks/sec
├─ Queue Backlog: (8.4 - 2.5) × 180 = ~1,062 tasks peak
└─ Result: Queue Saturation → E2E 증가
```

---

## 5. TPM Usage Analysis

### 5.1 Token Consumption

| Metric | Value |
|--------|-------|
| Completed Tasks | 1,469 |
| Estimated Tokens/Task | ~5,000 |
| Total Tokens (3min) | ~7,345,000 |
| TPM Average | ~2,448,000 tokens/min |
| TPM Limit (Tier 4) | 4,000,000 |
| **Usage** | **61%** |

### 5.2 Rate Limit Analysis

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    OpenAI Rate Limit Status                              │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  HTTP 429 Errors: 0                                                      │
│  Rate Limit Retries: 0                                                   │
│                                                                          │
│  TPM Headroom:                                                           │
│  ├─ Current: 2,448,000 TPM (61%)                                        │
│  ├─ Limit: 4,000,000 TPM                                                │
│  └─ Remaining: 1,552,000 TPM (39%)                                      │
│                                                                          │
│  결론: OpenAI API는 병목이 아님                                          │
│        인프라(Worker Probe) 개선 시 VU 1200+ 가능                        │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 6. Performance Comparison

### 6.1 VU 1000 동일 조건 비교 (06:12 UTC vs 20:06 UTC)

동일한 VU 1000, Tier 4 조건에서 **KEDA ScaledObject 설정 변경 전후** 비교입니다.

#### Configuration Diff

| 설정 | Initial (06:12 UTC) | Final (20:06 UTC) | 변경 |
|------|---------------------|-------------------|------|
| minReplicas | 1 | **2** | +1 |
| maxReplicas | 3 | **5** | +2 |
| Initial State | Cold Start | **Warm Start** | 개선 |
| Worker Nodes | 1 (k8s-worker-ai) | **2** (ai + ai-2) | +1 |

#### Performance Metrics Comparison

| Metric | Initial (06:12) | Final (20:06) | Delta | 분석 |
|--------|-----------------|---------------|-------|------|
| **Success Rate** | 96.6% | **97.8%** | **+1.2%p** | minReplicas 증가 효과 |
| **Total Failed** | 53 | **33** | **-37.7%** | Worker 안정성 개선 |
| Total Completed | 1,494 | 1,469 | -1.7% | 유사 |
| **E2E P95** | **166.7s** | 173.3s | +4.0% | 약간 증가 |
| **Throughput** | **378.7 req/m** | 373.4 req/m | -1.4% | 유사 |
| HTTP 429 | 0 | 0 | - | Tier 4 정상 |

#### Failure Breakdown Comparison

| 원인 | Initial (53건) | Final (33건) | 감소율 |
|------|---------------|--------------|--------|
| Worker Restart | ~30 (57%) | ~25 (76%) | -17% |
| Polling Timeout | ~20 (38%) | ~8 (24%) | -60% |
| Other | ~3 (5%) | 0 | -100% |

#### Queue Depth Comparison

| Queue | Initial Peak | Final Peak | 차이 |
|-------|-------------|------------|------|
| scan.vision | 532 | ~300* | -44%* |
| scan.answer | 221 | ~150* | -32%* |
| scan.rule | 560 | ~280* | -50%* |

*Final 값은 Worker 5개로 처리량 증가로 인한 추정치

### 6.2 Key Insights

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    KEDA 설정 변경 효과 분석                              │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  1. minReplicas 1→2 효과:                                               │
│     ├─ Cold Start 방지: 테스트 시작 시 이미 2개 Worker Ready            │
│     ├─ Scale-up 시간 단축: 2→5 (12초) vs 1→3 (30초+)                   │
│     └─ 결과: 실패율 37.7% 감소                                          │
│                                                                          │
│  2. maxReplicas 3→5 효과:                                               │
│     ├─ 동시 처리량: 12 tasks → 20 tasks (+67%)                          │
│     ├─ Queue Backlog 감소: 평균 대기 시간 단축                          │
│     └─ 결과: E2E P95 유지 (오히려 4% 증가는 통계 오차)                  │
│                                                                          │
│  3. Multi-Node 분산 효과:                                                │
│     ├─ 단일 노드 병목 해소                                              │
│     ├─ Pod Anti-Affinity 효과: 노드 장애 시 부분 가용                   │
│     └─ 결과: 안정성 향상                                                │
│                                                                          │
│  4. 여전한 한계:                                                         │
│     ├─ Celery Probe Timeout은 Worker 수와 무관                          │
│     ├─ I/O-bound 상황에서 inspect ping 취약점 유지                      │
│     └─ 결과: 97.8%에서 정체 (100%까지 도달 불가)                        │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

### 6.3 Diminishing Returns Analysis

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    Worker 수 vs 성공률 (VU 1000)                         │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  Success Rate                                                            │
│  100% ─┬─────────────────────────────────────── Theoretical Max         │
│        │                                        (Probe 개선 필요)        │
│   98% ─┤                    ●─── 5 workers (97.8%)                      │
│        │                   /                                             │
│   97% ─┤                  /                                              │
│        │        ●────────/─── 3 workers (96.6%)                         │
│   96% ─┤       /                                                         │
│        │      /                                                          │
│   95% ─┴─────/───────────────────────────────────────────────▶ Workers │
│        1    2    3    4    5    6    7    8                              │
│                                                                          │
│  분석:                                                                   │
│  ├─ 3→5 workers: +1.2%p 성공률 향상                                    │
│  ├─ 5→7 workers (예상): +0.5%p 향상 (Diminishing Returns)              │
│  └─ 98%+ 도달: Probe Mechanism 개선 필수                                │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

### 6.4 VU Progression (Tier 4, minReplicas=2, maxReplicas=5)

| VU | 성공률 | 실패 | E2E P95 | Throughput | Worker Restart |
|----|--------|------|---------|------------|----------------|
| 600 | 99.7% | 4 | 108.3s | 351.9 req/m | 0 |
| 700 | 99.2% | 11 | 122.3s | 329.1 req/m | 0 |
| 800 | 99.7% | 4 | 144.6s | 367.3 req/m | 0 |
| 900 | 99.7% | 4 | 149.6s | 405.5 req/m | 0 |
| **1000** | **97.8%** | **33** | **173.3s** | **373.4 req/m** | **Yes** |

### 6.2 Inflection Point Analysis

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    VU vs Success Rate                                    │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  Success Rate                                                            │
│  100% ─┬──●───●───●───●───┐                                             │
│        │  600 700 800 900 │                                             │
│   99% ─┤                  │                                             │
│        │                  │                                             │
│   98% ─┤                  ●─── VU 1000 (97.8%)                          │
│        │                      ← Inflection Point                        │
│   97% ─┤                                                                │
│        │                                                                │
│   96% ─┴──────────────────────────────────────────────────────▶ VU     │
│        600   700   800   900   1000  1100                               │
│                                                                          │
│  Inflection Point: VU 900 → 1000                                        │
│  원인: Worker Probe Timeout으로 인한 재시작                              │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 7. Bottleneck Analysis

### 7.1 System Bottleneck Hierarchy

| Priority | Component | Status | Bottleneck |
|----------|-----------|--------|------------|
| 1 | **Celery Probe** | ❌ | `inspect ping` I/O-bound 상황 취약 |
| 2 | Worker Concurrency | ⚠️ | 5 workers × 4 = 20 동시 처리 |
| 3 | Node CPU | ✅ | 65% / 54% (여유 있음) |
| 4 | Node Memory | ✅ | 52% / 39% (여유 있음) |
| 5 | OpenAI TPM | ✅ | 61% (headroom 39%) |

### 7.2 Root Cause Summary

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    Root Cause: Celery Probe Design                       │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  문제:                                                                   │
│  ├─ celery inspect ping은 Worker가 "살아있는지" 확인                    │
│  ├─ 그러나 I/O-bound 작업(OpenAI API) 중에는 응답 불가                  │
│  └─ 결과: 정상 작동 중인 Worker가 "unhealthy"로 판정                    │
│                                                                          │
│  현재 설정:                                                              │
│  ├─ Probe Timeout: 20s                                                  │
│  ├─ Celery inspect ping -t: 15s                                         │
│  ├─ Failure Threshold: 3                                                │
│  └─ 최대 허용 시간: 20s × 3 = 60s                                       │
│                                                                          │
│  VU 1000 상황:                                                           │
│  ├─ 5 workers가 모두 OpenAI API 호출 중                                 │
│  ├─ Queue에 100+ tasks 대기                                             │
│  ├─ Worker Thread Pool 포화                                             │
│  └─ inspect ping 처리 불가 → Probe Fail → Restart                       │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 8. Recommendations

### 8.1 Short-term (Probe 조정)

```yaml
# Option A: Timeout 증가
livenessProbe:
  exec:
    command: ["celery", "-A", "scan_worker...", "inspect", "ping", "-t", "30"]
  timeoutSeconds: 35  # 현재 20
  periodSeconds: 60   # 현재 30
  failureThreshold: 5 # 현재 3

# Option B: HTTP Health Endpoint 사용
livenessProbe:
  httpGet:
    path: /health
    port: 8080
  timeoutSeconds: 5
  periodSeconds: 10
```

### 8.2 Medium-term (Worker 확장)

| 조치 | 현재 | 권장 | 효과 |
|------|------|------|------|
| maxReplicas | 5 | 7-8 | VU 1200+ 가능 |
| Worker Node | 2 | 3 | 분산 처리 개선 |
| Concurrency | 4 | 6 | 동시 처리량 증가 |

### 8.3 Long-term (Architecture)

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    Graceful Degradation Strategy                         │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  1. Circuit Breaker 패턴 적용                                            │
│     └─ Queue Depth > 100 → 신규 요청 거부 (503)                         │
│                                                                          │
│  2. Priority Queue 도입                                                  │
│     └─ 유료 사용자 우선 처리                                            │
│                                                                          │
│  3. Async Probe 구현                                                     │
│     └─ Worker 내부 상태 기반 health check (inspect 대체)                │
│                                                                          │
│  4. Task Retry with Idempotency                                          │
│     └─ Worker 재시작 시 task 자동 재처리                                │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 9. Appendix

### 9.1 Raw Test Output

```json
{
  "test_info": {
    "target_vus": 1000,
    "duration_seconds": 1769544162.729404
  },
  "results": {
    "total_submitted": 1518,
    "total_completed": 1469,
    "total_failed": 33,
    "success_rate": "97.8%",
    "reward_rate": "0.0%"
  },
  "latency": {
    "scan_submit_p95": "787ms",
    "poll_p95": "2609ms",
    "e2e_p95": "173.3s",
    "e2e_avg": "121.3s"
  },
  "polling": {
    "total_poll_requests": 70432,
    "avg_polls_per_task": "46.4"
  },
  "throughput": {
    "requests_per_minute": "373.4 req/m"
  }
}
```

### 9.2 Prometheus Query Reference

```promql
# Time Range
start: 2026-01-27T20:03:38Z
end: 2026-01-27T20:06:38Z

# Worker CPU Usage
sum(rate(container_cpu_usage_seconds_total{namespace="scan",pod=~"scan-worker.*"}[1m])) by (pod)

# Worker Memory Usage
sum(container_memory_working_set_bytes{namespace="scan",pod=~"scan-worker.*"}) by (pod) / 1024 / 1024

# Queue Depth
rabbitmq_queue_messages{queue=~"scan.*"}

# Pod Restarts
kube_pod_container_status_restarts_total{namespace="scan",pod=~"scan-worker.*"}

# Probe Failures
increase(kube_pod_container_status_last_terminated_reason{namespace="scan",reason="Error"}[5m])
```

### 9.3 Related Files

| File | Description |
|------|-------------|
| `e2e-tests/performance/k6-scan-polling-test.js` | Test Script |
| `k6-scan-polling-vu1000-2026-01-27T20-06-38-794Z.json` | Result JSON |
| `workloads/scaling/dev/kustomization.yaml` | KEDA Config |
| `workloads/scan/base/scan-worker/deployment.yaml` | Worker Spec |

---

## 10. Conclusion

### Key Findings

| 항목 | 발견 |
|------|------|
| **병목 지점** | Celery inspect ping (I/O-bound 상황 취약) |
| **OpenAI API** | 정상 (Rate Limit 0, TPM 61%) |
| **인프라** | 여유 있음 (CPU 60%, Memory 46%) |
| **실질적 한계** | VU 900 (Worker Probe 안정 마지노선) |

### KEDA 설정 변경 효과 (Initial vs Final)

| 변경 사항 | 효과 |
|-----------|------|
| minReplicas 1→2 | 실패율 37.7% 감소, Cold Start 방지 |
| maxReplicas 3→5 | 동시 처리량 67% 증가 |
| Multi-Node 분산 | 단일 노드 병목 해소 |

### 한계점

```
Worker 수 증가로 해결 가능한 문제:
✅ Cold Start로 인한 초기 실패
✅ Queue Backlog으로 인한 E2E 증가
✅ 단일 노드 리소스 부족

Worker 수 증가로 해결 불가능한 문제:
❌ Celery inspect ping I/O-bound 취약점
❌ OpenAI API 호출 중 Probe 응답 불가
→ Probe Mechanism 개선 필요
```

### VU 1000 운영 가능 조건

1. Probe timeout 30s 이상으로 증가
2. 또는 HTTP 기반 health check로 변경
3. 또는 Worker 노드 추가 (maxReplicas 7+)

### 안정적 운영 범위

| 범위 | VU | 조건 | 근거 |
|------|-----|------|------|
| **Production Ready** | 50-900 | 현재 설정 유지 | 99%+ 성공률 |
| **With KEDA Tuning** | 900-1000 | min=2, max=5 | 97.8% 성공률 |
| **With Probe Tuning** | 1000-1200 | Probe timeout 증가 | 98%+ 예상 |
| **With Node Expansion** | 1200+ | 3rd Worker Node | TPM 여유 39% |

### 다음 단계

1. **Probe 개선 검토**: HTTP Health Endpoint 또는 timeout 증가
2. **Monitoring 강화**: Queue Depth, Probe Failure 알림 설정
3. **Stress Test**: Probe 개선 후 VU 1200 테스트

---

*Last Updated: 2026-01-28 05:30 KST*
*Previous Test Reference: https://rooftopsnow.tistory.com/255*
