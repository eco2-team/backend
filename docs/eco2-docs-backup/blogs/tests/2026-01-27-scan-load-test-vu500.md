# Scan API Load Test Report - VU 500

> **Date**: 2026-01-27 04:00 KST
> **Test Type**: k6 Scan Polling Test
> **Target VUs**: 500
> **Grafana Snapshot**: [Dashboard Link](https://snapshots.raintank.io/dashboard/snapshot/acaYWQuYqSHJSXzV54qnA0c8N0FGMX6R?orgId=0&from=2026-01-27T03:57:10.725Z&to=2026-01-27T04:01:13.725Z&timezone=browser&refresh=10s)

---

## Executive Summary

VU 500 부하 테스트에서 **100% 성공률**을 달성했으나, E2E 레이턴시가 평균 59.2초로 높게 측정되었다. 주요 병목은 LLM API 호출 지연(Vision 4.5s + Answer 6-7s)이며, Worker 스케일링은 정상 동작했다.

| 지표 | 값 | 평가 |
|------|-----|------|
| 성공률 | **100%** | PASS |
| E2E P95 | 83.3s | WARN |
| 리워드율 | 0% | FAIL (측정 오류 의심) |

---

## 1. Test Configuration

```yaml
test_info:
  target_vus: 500
  test_script: k6-scan-polling-test.js
  endpoint: https://api.dev.growbin.app/api/v1/scan
  timestamp: 2026-01-27T04:00:09.595Z
```

### Test Timeline

| Phase | Time (UTC) | Time (KST) | Duration |
|-------|------------|------------|----------|
| Ramp-up Start | 03:57:10 | 12:57:10 | - |
| Steady State | 03:57:40 | 12:57:40 | 2m |
| Ramp-down Start | 03:59:40 | 12:59:40 | - |
| Test End | 04:01:13 | 13:01:13 | - |
| **Total Duration** | - | - | **~4m** |

### Grafana Dashboard

**Snapshot URL**: [View Dashboard](https://snapshots.raintank.io/dashboard/snapshot/acaYWQuYqSHJSXzV54qnA0c8N0FGMX6R?orgId=0&from=2026-01-27T03:57:10.725Z&to=2026-01-27T04:01:13.725Z&timezone=browser&refresh=10s)

주요 패널:
- Scan API Request Rate
- Worker CPU/Memory Usage
- RabbitMQ Queue Depth
- E2E Latency Distribution
- KEDA Scaling Events

---

## 2. Test Results

### 2.1 Throughput & Success Rate

| Metric | Value |
|--------|-------|
| Total Submitted | 1,336 |
| Total Completed | 1,336 |
| Total Failed | 0 |
| **Success Rate** | **100.0%** |
| Reward Rate | 0.0% |
| Throughput | 367.9 req/m |

### 2.2 Latency Distribution

| Metric | Value | Target | Status |
|--------|-------|--------|--------|
| Scan Submit P95 | 232ms | < 500ms | PASS |
| Poll P95 | 349ms | < 500ms | PASS |
| **E2E P95** | **83.3s** | < 30s | FAIL |
| **E2E Average** | **59.2s** | < 20s | FAIL |

### 2.3 Polling Statistics

| Metric | Value |
|--------|-------|
| Total Poll Requests | 38,860 |
| Avg Polls per Task | 29.1 |
| Poll Interval | ~2s (estimated) |

---

## 3. Infrastructure Metrics

### 3.1 Cluster Overview

**Test Time Snapshot (04:00 KST)**

#### Scan Namespace Pods

| Pod | Status | Restarts | Node | CPU | Memory |
|-----|--------|----------|------|-----|--------|
| scan-worker-78f8ccdc9-wtxmw | Running | 1 | k8s-worker-ai | 25m | 287Mi |
| scan-worker-canary-ccd48f886-9df4l | Running | 1 | k8s-worker-ai | 24m | 310Mi |
| scan-api-589c5d4c69-g857f | Running | 0 | k8s-api-scan | 6m | 149Mi |
| scan-api-canary-76b4c99cb8-hk9fv | Running | 0 | k8s-api-scan | 5m | 113Mi |
| celery-beat-75c84f45fd-5sdxp | Running | 0 | k8s-worker-ai-2 | 4m | 133Mi |

#### Worker Node Resource (k8s-worker-ai)

| Resource | Usage | Allocation |
|----------|-------|------------|
| CPU | 389m (19%) | 1305m requests / 8750m limits (437% overcommit) |
| Memory | 2.6Gi (69%) | 1976Mi requests / 7296Mi limits |

### 3.2 Scan Worker Configuration

```yaml
deployment:
  replicas: 1 (+ 1 canary)

container:
  image: mng990/eco2:scan-worker-dev-latest
  resources:
    requests:
      cpu: 250m
      memory: 512Mi
    limits:
      cpu: 1
      memory: 1Gi

celery:
  pool: gevent
  concurrency: 100
  prefetch_multiplier: 1
  queues:
    - scan.vision
    - scan.rule
    - scan.answer
    - scan.reward
```

### 3.3 KEDA ScaledObject & HPA

#### ScaledObject Configuration

```yaml
scan-worker-scaledobject:
  scaleTargetRef: Deployment/scan-worker
  minReplicaCount: 1
  maxReplicaCount: 3
  pollingInterval: 30s
  cooldownPeriod: 300s
  fallback:
    failureThreshold: 3
    replicas: 2

  triggers:
    - type: rabbitmq
      queueName: scan.vision
      value: "10"  # Scale when queue > 10
    - type: rabbitmq
      queueName: scan.answer
      value: "10"
    - type: rabbitmq
      queueName: scan.rule
      value: "20"

  behavior:
    scaleUp:
      stabilizationWindow: 0s
      policies:
        - type: Pods, value: 2, period: 30s
    scaleDown:
      stabilizationWindow: 300s
      policies:
        - type: Percent, value: 50, period: 60s
```

#### KEDA Health Status (Post-Test)

| Metric | Status | Failures |
|--------|--------|----------|
| s0-rabbitmq-scan-vision | Happy | 0 |
| s1-rabbitmq-scan-answer | Happy | 0 |
| s2-rabbitmq-scan-rule | Happy | 0 |

#### Scale Events During Test

| Time | Event | Reason |
|------|-------|--------|
| **04:00:10 UTC** | Last Active | Triggers became active |
| **~03:59 UTC** | Scale to 3 | `scan.vision` queue above target (10) |

**HPA Event Log:**
```
SuccessfulRescale: New size: 3; reason: external metric
s0-rabbitmq-scan-vision above target
```

### 3.4 RabbitMQ Status

| Metric | Value |
|--------|-------|
| Pod | eco2-rabbitmq-server-0 |
| CPU | 45m |
| Memory | 554Mi |
| Queue Status | Empty (post-test) |

### 3.5 Redis Cluster Status

#### Redis Pods (Post-Test)

| Pod | Purpose | CPU | Memory | Node |
|-----|---------|-----|--------|------|
| rfr-streams-redis-0 | Event Streams | 10m | 123Mi | k8s-redis-streams |
| rfr-pubsub-redis-0 | Pub/Sub (Leader) | 7m | 70Mi | k8s-redis-pubsub |
| rfr-pubsub-redis-1 | Pub/Sub (Replica) | 8m | 72Mi | k8s-redis-pubsub |
| rfr-pubsub-redis-2 | Pub/Sub (Replica) | 9m | 67Mi | k8s-redis-pubsub |
| rfr-cache-redis-0 | Cache | 8m | 218Mi | k8s-redis-cache |
| rfr-auth-redis-0 | Auth Sessions | 7m | 66Mi | k8s-redis-auth |

#### Redis Sentinel Pods

| Pod | CPU | Memory |
|-----|-----|--------|
| rfs-streams-redis | 8m | 55Mi |
| rfs-pubsub-redis (x3) | 7-8m | 51-52Mi |
| rfs-cache-redis | 8m | 69Mi |
| rfs-auth-redis | 8m | 51Mi |

**Observation**: Redis 클러스터는 테스트 중 안정적으로 유지됨. Cache Redis 메모리 사용량(218Mi)이 다른 인스턴스 대비 높음.

### 3.6 All Cluster Nodes Resource

| Node | CPU | CPU% | Memory | Mem% | Role |
|------|-----|------|--------|------|------|
| k8s-worker-ai | 389m | 19% | 2.6Gi | 69% | AI Workers |
| k8s-worker-ai-2 | 76m | 3% | 2.1Gi | 56% | Celery Beat |
| k8s-api-scan | 69m | 3% | 2.4Gi | 65% | Scan API |
| k8s-rabbitmq | 119m | 5% | 2.0Gi | 55% | Message Queue |
| k8s-redis-streams | 108m | 5% | 1.2Gi | 66% | Redis Streams |
| k8s-redis-pubsub | 172m | 8% | 1.5Gi | 86% | Redis Pub/Sub |
| k8s-logging | 250m | 12% | 7.2Gi | 94% | ELK Stack |

**Warning**: `k8s-logging` 노드 메모리 94% 사용 중 - ELK 스택 리소스 점검 필요

---

## 4. Prometheus Metrics (Test Window: 03:57:10 ~ 04:01:13 UTC)

### 4.1 Scan Worker CPU Usage

| Pod | Start | Peak | End | Trend |
|-----|-------|------|-----|-------|
| scan-worker-78f8ccdc9-wtxmw | 1.53 | 1.72 | 0.23 | ↗↘ |
| scan-worker-78f8ccdc9-jhrgg | - | 1.83 | 0.34 | ↗↘ (scale-up) |
| scan-worker-78f8ccdc9-sqcbr | - | 1.84 | 0.36 | ↗↘ (scale-up) |
| scan-worker-canary | 1.46 | 1.74 | 0.35 | ↗↘ |

**Query:**
```promql
sum(rate(container_cpu_usage_seconds_total{namespace="scan",pod=~"scan-worker.*"}[1m])) by (pod)
```

### 4.2 Scan Worker Memory Usage

| Pod | Start | Peak | End |
|-----|-------|------|-----|
| scan-worker-wtxmw | 750MB | 1.30GB | 1.17GB |
| scan-worker-jhrgg | 337MB | 1.18GB | 1.12GB |
| scan-worker-sqcbr | 481MB | 1.24GB | 1.14GB |
| scan-worker-canary | 1.42GB | 1.62GB | 1.55GB |

**Query:**
```promql
sum(container_memory_working_set_bytes{namespace="scan",pod=~"scan-worker.*"}) by (pod)
```

### 4.3 HPA Replica Count

| Time (UTC) | scan-worker | scan-api |
|------------|-------------|----------|
| 03:57:10 | **3** | 1 |
| 03:57:40 | 3 | **2** |
| 03:58:10 | 3 | **3** |
| 04:01:13 | 3 | 3 |

**Query:**
```promql
kube_horizontalpodautoscaler_status_current_replicas{horizontalpodautoscaler=~".*scan.*"}
```

**Observation**: scan-worker는 테스트 시작 전 이미 3 replicas로 스케일업됨 (이전 요청 영향)

### 4.4 RabbitMQ Queue Depth

| Queue | Start | Peak | End | Peak Time |
|-------|-------|------|-----|-----------|
| scan.vision | 352 | 352 | 0 | 03:57:10 |
| scan.answer | 14 | **258** | 0 | 03:58:10 |
| scan.rule | 73 | **268** | 0 | 03:57:40 |
| scan.reward | 2 | **155** | 0 | 03:58:40 |

**Query:**
```promql
rabbitmq_queue_messages{queue=~"scan.*"}
```

**Observation**: 테스트 종료 시 모든 큐가 0으로 drain됨 (정상 처리 완료)

### 4.5 RabbitMQ Consumer Count

| Queue | Min | Max | Steady |
|-------|-----|-----|--------|
| scan.vision | 2 | 4 | 4 |
| scan.answer | 2 | 4 | 4 |
| scan.rule | 2 | 4 | 4 |
| scan.reward | 2 | 4 | 4 |

**Query:**
```promql
rabbitmq_queue_consumers{queue=~"scan.*"}
```

### 4.6 Scan API CPU Usage

| Pod | Start | Peak | End | Note |
|-----|-------|------|-----|------|
| scan-api-g857f | 0.47 | **1.30** | 0.01 | Original |
| scan-api-vqwzw | - | 0.74 | 0.01 | Scale-up +1 |
| scan-api-pzppj | - | 0.63 | 0.01 | Scale-up +2 |
| scan-api-canary | 0.01 | 0.01 | 0.01 | Idle |

**Query:**
```promql
sum(rate(container_cpu_usage_seconds_total{namespace="scan",pod=~"scan-api.*"}[1m])) by (pod)
```

### 4.7 Redis Memory Usage

| Instance | Start | Peak | End | Delta |
|----------|-------|------|-----|-------|
| rfr-streams | 42.7MB | 51.6MB | 51.6MB | **+8.9MB** |
| rfr-cache | 26.0MB | **102MB** | 102MB | **+76MB** |
| rfr-pubsub-0 | 2.1MB | 2.2MB | 2.1MB | - |
| rfr-auth | 1.0MB | 1.0MB | 1.0MB | - |

**Query:**
```promql
redis_memory_used_bytes{namespace="redis"}
```

**Observation**: rfr-cache 메모리가 테스트 중 4배 증가 (LLM 응답 캐싱)

---

### 4.8 All Workers Status

| Namespace | Worker | Replicas | Node | Status |
|-----------|--------|----------|------|--------|
| **scan** | scan-worker | 1 | k8s-worker-ai | Running |
| **scan** | scan-worker-canary | 1 | k8s-worker-ai | Running |
| **chat** | chat-worker | 1 | k8s-worker-ai | Running |
| **character** | character-match-worker | 2 | k8s-worker-storage, storage-2 | Running |
| **character** | character-worker | 1 (+1 canary) | k8s-worker-storage-2, storage | Running |
| **auth** | auth-worker | 1 (+1 canary) | k8s-worker-storage-2, storage | Running |
| **users** | users-worker | 1 (+1 canary) | k8s-worker-storage, storage-2 | Running |
| **info** | info-worker | 1 | k8s-api-info | Running |

**Total Workers**: 13 pods across 4 nodes

### 3.8 Event Router Configuration

```yaml
redis:
  streams_url: redis://rfr-streams-redis.redis.svc.cluster.local:6379/0
  pubsub_url: redis://pubsub-redis-master.redis.svc.cluster.local:6379/0
```

---

## 5. Worker Log Analysis

### 4.1 Task Processing Times (Sample from Logs)

| Task Type | Min | Max | Avg | Note |
|-----------|-----|-----|-----|------|
| scan.vision | 4.46s | 6.21s | **4.5s** | OpenAI Vision API |
| scan.rule | 0.04s | 0.18s | **0.04s** | Local lookup (Redis) |
| scan.answer | 4.85s | 8.92s | **6.7s** | OpenAI Chat Completion |
| scan.reward | 0.03s | 0.05s | **0.05s** | Character match + event |

#### Detailed Sample (03:59:38 - 03:59:52 KST)

```
03:59:38.311  scan.answer   4.847s  task=fb2e58f9
03:59:38.469  scan.reward   0.035s  task=bf38ff01
03:59:39.002  scan.rule     0.038s  task=deeb6139
03:59:39.071  scan.reward   0.045s  task=9a113200
03:59:39.570  scan.answer   6.685s  task=b2c6ed05
03:59:39.901  scan.reward   0.048s  task=66f5daa8
03:59:40.017  scan.vision   4.564s  task=c5956559  (duration_vision_ms: 4466)
03:59:41.025  scan.reward   0.038s  task=8b47d5bf
03:59:41.061  scan.answer   7.637s  task=3037e333
03:59:42.502  scan.rule     0.042s  task=236ccd0b  (duration_rule_ms: 0.175)
03:59:44.630  scan.answer   6.899s  task=d6f35d05
03:59:45.010  scan.answer   8.916s  task=d64ee5b2
03:59:47.353  scan.answer   5.809s  task=fd18b15e
03:59:52.583  scan.reward   0.055s  task=4c96d003
```

**Task Statistics (from logs):**
- Tasks processed in last hour: **574 succeeded**
- Tasks processed in last 2 hours: **1,148 total** (vision + rule + answer + reward)
- Estimated tasks during test window (4m): **~300 complete scan flows**

### 4.2 Task Flow

```
scan.vision (4.5s avg)
    ↓
scan.rule (0.04s)
    ↓
scan.answer (6.7s avg)
    ↓
scan.reward (0.05s)
────────────────────
Total: ~11-12s per task (sequential)
```

### 4.3 Observations from Logs

1. **LLM API Calls**: 모든 OpenAI API 호출 성공 (HTTP 200)
2. **Reward Processing**: `reward_character_event_dispatched` 정상 발생
3. **Character Match**: `Character match completed` 로그 확인
4. **Worker Sync**: 간헐적 heartbeat miss 발생 (users-worker-canary)

---

## 6. Bottleneck Analysis

### 5.1 E2E Latency Breakdown

```
┌─────────────────────────────────────────────────────────────┐
│                    E2E Latency: 59.2s (avg)                  │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  [Queue Wait]     [Vision]    [Rule]  [Answer]   [Reward]   │
│  ~~~~~~~~~~~~     ~~~~~~~~    ~~~~~~  ~~~~~~~~   ~~~~~~~~   │
│     ~47s           4.5s       0.04s    6.7s       0.05s     │
│     (80%)          (8%)       (0%)     (11%)      (0%)      │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

**Primary Bottleneck: Queue Wait Time (~47s)**

- Worker concurrency: 100 (gevent)
- 2 workers total (stable + canary)
- Max concurrent tasks: 200
- VU 500 with burst → Queue backlog

### 5.2 Why Queue Wait is High

1. **HPA Scale-up Delay**: 부하 감지 후 스케일업까지 지연
2. **OpenAI Rate Limits**: Vision API 동시 요청 제한 가능성
3. **gevent Greenlet Scheduling**: I/O 대기 중 context switch 오버헤드

### 5.3 Reward Rate 0% 분석

#### Worker 로그 (정상 처리 확인)
```
[INFO] Character match completed
[INFO] reward_character_event_dispatched
[INFO] scan_task_completed
[INFO] Task scan.reward[...] succeeded in 0.05s
```

#### k6 테스트 로직 (k6-scan-polling-test.js:258-263)
```javascript
// 보상 확인
if (result.reward && result.reward.points > 0) {
  rewardReceived.add(1);
  rewardRate.add(1);
} else {
  rewardRate.add(0);
}
```

#### Root Cause

k6 스크립트가 `result.reward.points`를 기대하지만, 실제 응답에서:
1. **`reward` 필드가 없거나** - Polling 응답 스키마에 reward가 미포함
2. **`points` 필드가 없거나** - 다른 필드명 사용 (예: `reward.amount`, `reward.value`)
3. **Worker 응답과 API 응답 불일치** - Worker에서 reward 처리는 되지만 API 응답에 미반영

**Action Required:**
- [ ] GET /scan/{job_id}/result 응답 스키마 확인
- [ ] reward 필드 포함 여부 검증
- [ ] k6 스크립트 reward 판정 로직 수정

---

## 7. Comparison with Previous Tests

### 7.1 Today's Tests (2026-01-27)

| Metric | 1차 (03:41) | 2차 (04:00) | Change |
|--------|-------------|-------------|--------|
| Submitted | 254 | 1,336 | +426% |
| Completed | 0 | 1,336 | - |
| Failed | 35 | 0 | -100% |
| Success Rate | 0% | 100% | FIXED |
| E2E P95 | 0.3s | 83.3s | N/A* |

*1차 테스트는 시스템 장애로 인해 비정상 종료

### 7.2 vs Blog VU 500 Test (Reference: [블로그 108번](https://rooftopsnow.tistory.com/108))

| Metric | Blog VU 500 | 금일 VU 500 | Delta | 비고 |
|--------|-------------|-------------|-------|------|
| 요청 수 | 1,990 | 1,336 | -33% | 테스트 시간 차이 |
| **완료율** | 94.0% | **100%** | **+6%** | 개선 |
| 성공률 | 99.7% | 100% | +0.3% | - |
| **E2E P95** | 76.4s | **83.3s** | **+9%** | 악화 |
| E2E Avg | - | 59.2s | - | - |
| Throughput | 438 req/m | 367.9 req/m | -16% | - |
| 보상 수령률 | 91.2% | 0%* | - | 측정 오류 |
| Scan API P95 | 154ms | 232ms | +51% | - |

**분석:**
- **완료율 개선**: 94% → 100% (+6%) - 시스템 안정화
- **E2E P95 악화**: 76.4s → 83.3s (+9%) - 대기열 증가
- **Throughput 감소**: 438 → 367.9 req/m (-16%) - 요청 수 차이

### 7.3 VU별 추이 (Blog 데이터 기준)

| VU | 요청 수 | 완료율 | E2E P95 | Throughput | 평가 |
|----|--------|--------|---------|------------|------|
| 50 | 685 | 99.7% | 17.7s | 198 req/m | Baseline |
| 200 | 1,649 | 99.8% | 33.2s | 367 req/m | 정상 |
| **250** | 1,754 | **99.9%** | 40.5s | **417.6 req/m** | **최적점** |
| 300 | 1,732 | 99.9% | 48.5s | 402 req/m | 포화 시작 |
| 400 | 1,901 | 98.9% | 62.2s | 422.2 req/m | 한계 근접 |
| 500 | 1,990 | 94.0% | 76.4s | 438 req/m | SLA 초과 |
| **금일 500** | 1,336 | **100%** | **83.3s** | 367.9 req/m | 안정화됨 |

**결론:**
- **안정성**: 금일 테스트가 완료율 100%로 더 안정적
- **성능**: E2E 레이턴시는 약간 증가 (+9%)
- **권장 VU**: SLA(E2E < 60s) 기준 250-300 VU 권장

---

## 8. Recommendations

### 8.1 Short-term (Immediate)

| Action | Priority | Impact |
|--------|----------|--------|
| HPA minReplicas 2로 상향 | HIGH | Queue wait 50% 감소 예상 |
| k6 reward 측정 로직 점검 | HIGH | 정확한 리워드율 측정 |
| Prefetch multiplier 조정 (2-4) | MEDIUM | Throughput 개선 |

### 8.2 Mid-term

| Action | Priority | Impact |
|--------|----------|--------|
| Vision/Answer 병렬 처리 검토 | MEDIUM | E2E 레이턴시 감소 |
| OpenAI Batch API 활용 | MEDIUM | Rate limit 회피 |
| Worker 노드 추가 (k8s-worker-ai-3) | LOW | 스케일 한계 확장 |

### 8.3 Configuration Changes

```yaml
# Recommended HPA changes
keda-hpa-scan-worker-scaledobject:
  minReplicas: 2  # Changed from 1
  maxReplicas: 5  # Changed from 3
  metrics:
    - s0-rabbitmq-scan-vision: 5  # Lower threshold
```

---

## 9. Appendix

### 9.1 Prometheus Query Reference

아래 쿼리들을 사용해 테스트 시간대 메트릭을 수집했습니다.

| Metric | PromQL Query |
|--------|--------------|
| Worker CPU | `sum(rate(container_cpu_usage_seconds_total{namespace="scan",pod=~"scan-worker.*"}[1m])) by (pod)` |
| Worker Memory | `sum(container_memory_working_set_bytes{namespace="scan",pod=~"scan-worker.*"}) by (pod)` |
| API CPU | `sum(rate(container_cpu_usage_seconds_total{namespace="scan",pod=~"scan-api.*"}[1m])) by (pod)` |
| HPA Replicas | `kube_horizontalpodautoscaler_status_current_replicas{horizontalpodautoscaler=~".*scan.*"}` |
| RabbitMQ Queue Depth | `rabbitmq_queue_messages{queue=~"scan.*"}` |
| RabbitMQ Consumers | `rabbitmq_queue_consumers{queue=~"scan.*"}` |
| Redis Memory | `redis_memory_used_bytes{namespace="redis"}` |

**Time Range Parameters:**
```
start=1769486230  # 2026-01-27T03:57:10Z
end=1769486473    # 2026-01-27T04:01:13Z
step=30s
```

### 9.2 Raw Test Output

```json
{
  "test_info": {
    "target_vus": 500,
    "duration_seconds": 1769486191.701171
  },
  "results": {
    "total_submitted": 1336,
    "total_completed": 1336,
    "total_failed": 0,
    "success_rate": "100.0%",
    "reward_rate": "0.0%"
  },
  "latency": {
    "scan_submit_p95": "232ms",
    "poll_p95": "349ms",
    "e2e_p95": "83.3s",
    "e2e_avg": "59.2s"
  },
  "polling": {
    "total_poll_requests": 38860,
    "avg_polls_per_task": "29.1"
  },
  "throughput": {
    "requests_per_minute": "367.9 req/m"
  }
}
```

### 9.3 Test Environment

| Component | Version/Config |
|-----------|----------------|
| k6 | v0.49+ |
| Kubernetes | Self-managed (kubeadm) |
| Istio | 1.24.1 |
| RabbitMQ | 3.x (Cluster Operator) |
| Celery | 5.x (gevent pool) |
| OpenAI Model | gpt-5.2 |
| Prometheus | kube-prometheus-stack |

### 9.4 Related Files

- Test Script: `e2e-tests/performance/k6-scan-polling-test.js`
- Result JSON: `k6-scan-polling-vu500-2026-01-27T04-00-09-595Z.json`
- HPA Config: `k8s/scaling/scan-worker-scaledobject.yaml`
- Grafana Snapshot: [Link](https://snapshots.raintank.io/dashboard/snapshot/acaYWQuYqSHJSXzV54qnA0c8N0FGMX6R)

---

*Last Updated: 2026-01-27 13:40 KST*

---

## Changelog

| Time | Update |
|------|--------|
| 13:10 | Initial report created |
| 13:15 | Added Redis cluster metrics, node resource table, detailed task processing samples |
| 13:18 | Added reward rate 0% root cause analysis from k6 script review |
| 13:25 | Added Grafana snapshot link, KEDA ScaledObject config, test timeline, all workers status |
| 13:40 | Added Prometheus metrics (Section 4), blog VU comparison (Section 7), PromQL query reference |
