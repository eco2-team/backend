# 600 VU Load Test: Throughput Saturation Analysis

> **Date**: 2025-12-29 19:30~19:40 KST  
> **Test Duration**: 270.1s (4m30s)  
> **Result**: 33.2% Completion Rate (Throughput Saturation)

---

## Overview

600 VU 부하 테스트에서 **Node CPU 100% 포화**가 약 4.5분간 지속되어 33.2% completion rate를 기록했다.
Connection Pool 이슈(이전 테스트에서 해결)와 달리, 이번은 **처리 용량 한계**에 도달한 것이다.

---

## Test Results

### k6 Summary

| Metric | Value |
|--------|-------|
| Target VUs | 600 |
| Scan API Success | 2,117 (100%) |
| **Completion Rate** | **574 / 2,117 = 33.2%** |
| Throughput | 7.84 RPS |
| E2E Latency p95 | 76.8s |
| Completion Time p95 | 76.7s |

### Timeline Analysis

```
┌──────────────────────────────────────────────────────────────────────────┐
│                        600 VU Load Test Timeline                         │
├──────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  Node CPU %                                                              │
│  100%│          ┌──────────────────────────┐                             │
│   80%│         ╱                            ╲                            │
│   60%│        ╱                              ╲                           │
│   40%│       ╱                                ╲                          │
│   20%│──────╱                                  ╲────────────             │
│      └────────────────────────────────────────────────────────────────   │
│          19:30  19:31  19:32  19:33  19:34  19:35  19:36  19:37          │
│                 ├──────── 100% Saturation ────────┤                      │
│                                                                          │
│  Queue Depth                                                             │
│  800│              ▲ 748                                                 │
│  600│         ╱────────╲                                                 │
│  400│       ╱            ╲                                               │
│  200│──────╱              ╲────                                          │
│      └────────────────────────────────────────────────────────────────   │
│          19:30  19:31  19:32  19:33  19:34  19:35  19:36  19:37          │
└──────────────────────────────────────────────────────────────────────────┘
```

---

## Prometheus Metrics

### 노드별 부하 관측

| Node | IP | Peak CPU | 역할 |
|------|-----|----------|------|
| **k8s-worker-ai** | 10.0.1.127 | **100.0%** 🔴 | scan-worker |
| **k8s-api-scan** | 10.0.3.219 | **65.6%** ⚠️ | scan-api |
| k8s-api-auth | 10.0.1.53 | 42.8% | auth-api, ext-authz |
| k8s-ingress-gateway | 10.0.1.150 | 34.8% | Istio Ingress |
| k8s-redis-cache | 10.0.2.202 | 23.4% | Redis Cache |
| k8s-rabbitmq | 10.0.2.148 | 14.9% | RabbitMQ |

### Worker Node (k8s-worker-ai) CPU Timeline

| Time (KST) | CPU % | Status |
|------------|-------|--------|
| 19:31:00 | 10.1% | Normal |
| 19:31:30 | **81.6%** | ⚠️ Rising |
| 19:32:00 | **100.0%** | 🔴 Saturated |
| 19:32:30 | **100.0%** | 🔴 Saturated |
| 19:33:00 | **100.0%** | 🔴 Saturated |
| 19:33:30 | **100.0%** | 🔴 Saturated |
| 19:34:00 | **100.0%** | 🔴 Saturated |
| 19:34:30 | **100.0%** | 🔴 Saturated |
| 19:35:00 | **100.0%** | 🔴 Saturated |
| 19:35:30 | **100.0%** | 🔴 Saturated |
| 19:36:00 | 96.5% | Cooling |
| 19:36:30 | 25.6% | Normal |

**Saturation Duration**: 약 4.5분 (19:31:30 ~ 19:36:00)

### Worker Pods Scaling

| Time (KST) | Pods | Memory | Event |
|------------|------|--------|-------|
| 19:28:00 | 3 | 676 MB | Initial |
| 19:29:00 | 4 | 753 MB | KEDA scale-up |
| 19:31:30 | **6** | 899 MB | Peak scale |
| 19:32:00 | 6 | **1,140 MB** | Memory spike |
| 19:32:30 | 4 | 633 MB | Pods crashed |
| 19:33:00 | 3 | 532 MB | Stabilized |

### RabbitMQ Queue Depth

| Time (KST) | Messages | Status |
|------------|----------|--------|
| 19:31:00 | 288 | Filling |
| 19:32:00 | 624 | High |
| 19:34:00 | **748** | Peak |
| 19:35:30 | 291 | Draining |

### Event Router Throughput

| Time (KST) | Events/sec |
|------------|------------|
| 19:31:00 | 20.1 |
| 19:32:30 | 79.8 |
| 19:34:00 | **80.5** (Peak) |
| 19:35:00 | 58.3 |
| 19:36:00 | 47.3 |

---

## 관측 사항

### 1. Worker Node CPU 100% 포화

```
관측: k8s-worker-ai 노드 (2 cores)에서 CPU 100% 상태가 4.5분간 지속
원인: 6개의 scan-worker Pod가 동일 노드에 배치되어 리소스 경합 발생
```

- KEDA가 Queue 증가를 감지하고 3→6 pods 스케일 아웃 성공
- 그러나 **모든 Pod가 동일 노드에 배치**되어 노드 CPU 포화
- Pod Anti-affinity 미설정으로 분산 배치 실패

### 2. scan-api 노드 부하 증가

```
관측: k8s-api-scan 노드 CPU 65.6%까지 상승 (평소 ~10%)
원인: 600 VU 요청을 받아 RabbitMQ로 Task 발행하는 과정에서 부하 발생
```

- scan-api는 API 요청 → RabbitMQ 발행만 담당 (I/O bound)
- 600 VU에서도 100%에 도달하지 않아 **현재로서는 병목 아님**
- 다만 800+ VU에서는 잠재적 병목 가능성 존재

### 3. Worker Pod 메모리 급증 후 감소

```
관측: 19:32:00에 메모리 1,140MB 피크 후 633MB로 급감
원인: OOMKilled 또는 Crash로 인한 Pod 재시작
```

- 6 pods × 100 greenlets = 600개 동시 OpenAI API 호출
- 각 greenlet이 요청/응답 데이터를 메모리에 보유
- 메모리 limit 근접 시 Pod 강제 종료 발생

### 4. Queue 적체 현상

```
관측: RabbitMQ에 최대 748개 메시지 적체 (19:34:00)
원인: 처리 속도 < 유입 속도 → 백프레셔 발생
```

- 유입: 7.84 RPS (Scan API)
- 처리: 600 greenlets × (1 / 25초) ≈ 24 tasks/sec (이론적)
- 실제로는 CPU 포화로 greenlet 컨텍스트 스위칭 지연 → 처리량 저하

---

## 문제점 분석

### Greenlet 동시성 모델의 한계

scan-worker는 **Celery + gevent**를 사용한다. gevent는 Greenlet 기반의 협력적 멀티태스킹을 제공한다.

```
┌─────────────────────────────────────────────────────────────┐
│              Greenlet (Green Thread) 특성                    │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  장점:                                                      │
│  • 경량 (~4-8KB per greenlet vs ~1MB per OS thread)         │
│  • 유저 모드 컨텍스트 스위칭 → 오버헤드 최소화               │
│  • I/O-bound 작업에 최적화 (OpenAI API 호출)                │
│                                                             │
│  단점:                                                      │
│  • 협력적 스케줄링 → 명시적 yield 필요                      │
│  • GIL 영향 → CPU-bound 작업 시 병목                        │
│  • 단일 프로세스 내 실행 → 멀티코어 활용 불가               │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

**문제 1: 컨텍스트 스위칭 오버헤드**

```python
# 현재 설정
celery worker -P gevent -c 100  # 100 greenlets per worker
```

- 100개의 greenlet이 동시에 OpenAI API 응답 대기
- I/O 대기 중 gevent hub로 제어권 전환 (yield)
- 응답 도착 시 다시 greenlet으로 컨텍스트 스위칭
- **600 greenlets (6 pods × 100)가 동시에 스위칭** → CPU 오버헤드

**문제 2: M:1 모델의 한계**

```
┌─────────────────────────────────────────────────────────────┐
│                 Greenlet M:1 Mapping                         │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌──────────────────────────────────────┐                   │
│  │         OS Thread (1개)              │                   │
│  │  ┌───┐ ┌───┐ ┌───┐ ┌───┐    ┌───┐   │                   │
│  │  │ G │ │ G │ │ G │ │ G │... │ G │   │  ← 100 Greenlets  │
│  │  │ 1 │ │ 2 │ │ 3 │ │ 4 │    │100│   │                   │
│  │  └───┘ └───┘ └───┘ └───┘    └───┘   │                   │
│  │              ↓                      │                   │
│  │         gevent Hub                  │                   │
│  │         (Event Loop)                │                   │
│  └──────────────────────────────────────┘                   │
│                    ↓                                        │
│              CPU Core 1개               ← 병목!             │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

- Greenlet은 **단일 OS 스레드**에서 실행
- 아무리 greenlet을 늘려도 **단일 코어만 사용**
- Pod가 늘어나면 프로세스가 늘어나서 멀티코어 활용 가능
- 그러나 **모든 Pod가 같은 노드**에 있으면 노드 CPU가 병목

**문제 3: Long-running I/O의 영향**

```
OpenAI API 응답 시간: 15-30초

Timeline (1 greenlet):
├─── Request 전송 (10ms)
├─── I/O 대기 (yield → hub로 전환)
│    ← 이 시간 동안 다른 greenlet 실행
├─── 응답 수신 (hub → greenlet으로 스위칭)
└─── 결과 처리 (50ms)

문제: 100 greenlets × 6 pods = 600개가 동시에 I/O 대기
     → gevent hub가 600개 greenlet의 상태를 관리
     → 스위칭 오버헤드 누적
```

### 처리량 계산

```
Theoretical Capacity:
─────────────────────
• Greenlets: 100 × 6 pods = 600
• OpenAI 응답: ~25초 (평균)
• 이론적 처리량: 600 / 25 = 24 tasks/sec

Observed Capacity:
──────────────────
• Event Router: 80.5 events/sec (peak)
• Completion: 574 / 270초 ≈ 2.13 tasks/sec

Gap 원인:
─────────
1. CPU 포화로 greenlet 스위칭 지연
2. 메모리 부족으로 Pod crash
3. SSE 타임아웃 (90초) 초과
```

---

## Chain of Events

```
600 VU 요청 시작
    ↓
Ingress Gateway → ext-authz → scan-api
    ↓
scan-api: RabbitMQ에 Task 발행 (7.84 RPS)
    ↓
KEDA: Queue 증가 감지 → Worker Scale-out (3→6 pods)
    ↓
각 Worker: 100 Greenlets 생성 → 600 동시 OpenAI API 호출
    ↓
OpenAI API 응답 대기 (15-30초/요청)
    ↓
gevent hub: 600 greenlets 컨텍스트 스위칭 관리
    ↓
단일 노드 (2 cores)에서 CPU 100% 포화
    ↓
메모리 1,140MB 급증 → Pod OOMKilled/Crash
    ↓
Worker 수 감소 (6→3 pods) → 처리 용량 절반 감소
    ↓
SSE 타임아웃 (90초) 초과 → 클라이언트 연결 종료
    ↓
33.2% Completion Rate (574 / 2,117)
```

---

## Bottleneck Summary

| Component | Capacity | Observed | Status |
|-----------|----------|----------|--------|
| Worker Node CPU | 2 cores | 100% × 4.5분 | 🔴 Saturated |
| scan-api Node CPU | 2 cores | 65.6% | ⚠️ High |
| Worker Memory | ~2GB | 1,140MB peak | ⚠️ Near limit |
| Greenlets/pod | 100 | 100 | ✅ Normal |
| RabbitMQ | ∞ | 748 messages | ✅ Normal |
| Event Router | ~80 evt/s | 80.5 evt/s | ⚠️ At limit |
| Redis | - | 1.7% CPU | ✅ Normal |
| PostgreSQL | - | 3.0% CPU | ✅ Normal |

---

## Performance Baseline Comparison

| VU | Completion | E2E p95 | Node CPU | Workers |
|----|------------|---------|----------|---------|
| 200 | 99.8% | 33s | ~40% | 3 |
| 250 | 99.9% | 40s | ~50% | 3 |
| 300 | 99.9% | 48s | ~60% | 3 |
| 400 | 98.2% | 55s | ~75% | 3 |
| 500 | 94.0% | 65s | ~85% | 3 |
| **600** | **33.2%** | **77s** | **100%** | 3-6 |

---

## Key Findings

1. **단일 노드 한계**: k8s-worker-ai (2 cores)는 **500 VU가 실질적 상한선**
2. **KEDA는 정상 작동**: 부하 증가 시 3→6 pods 스케일 아웃 성공
3. **노드 CPU가 병목**: Pod 증가해도 동일 노드에 배치되어 성능 향상 없음
4. **2차 병목 존재**: scan-api 노드 65.6%로 고부하 상태 관측
5. **Greenlet M:1 모델 한계**: 단일 프로세스가 단일 코어만 활용 → 멀티코어 활용 불가
6. **메모리 압박**: 1,140MB 피크 후 Pod 감소 (6→3) 관측

---

## 튜닝 방안 검토

### ❌ Prefork 전환 불가

[이전 분석](https://rooftopsnow.tistory.com/72)에서 Prefork가 I/O-bound 워크로드에서 효과 없음을 확인했다.

```
이코에코 워크로드 분석:
• OpenAI API 호출이 전체의 65% 차지 (vision 30% + answer 35%)
• 완전한 I/O-bound 워크로드

Prefork 한계:
• CPU-bound에만 효과적
• I/O 대기 시간에 프로세스가 블로킹 → 리소스 낭비
• 메모리 오버헤드 (~50-100MB per process)
• Celery AsyncIO Pool은 5.6.0에서도 미지원
```

### ✅ 가능한 튜닝 방안 (동일 노드 스펙)

#### 1. Greenlet 감소 + Pod 증가 (권장)

```yaml
# 현재: 3 pods × 100 greenlets = 300 (CPU 100%)
# 변경: 5 pods × 50 greenlets = 250 (CPU ~65%)

# deployment.yaml
spec:
  replicas: 5  # 3 → 5
  containers:
    - args: ["-c", "50"]  # 100 → 50
```

```
┌─────────────────────────────────────────────────────────────┐
│              Greenlet 분산 전략                              │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  현재 (CPU 100%):                                           │
│  ┌─────────┐ ┌─────────┐ ┌─────────┐                       │
│  │ Pod 1   │ │ Pod 2   │ │ Pod 3   │                       │
│  │ 100 G   │ │ 100 G   │ │ 100 G   │  = 300 greenlets     │
│  └─────────┘ └─────────┘ └─────────┘                       │
│  ↓ 동일 노드에서 300개 컨텍스트 스위칭 → CPU 포화           │
│                                                             │
│  변경 (CPU ~65%):                                           │
│  ┌──────┐ ┌──────┐ ┌──────┐ ┌──────┐ ┌──────┐             │
│  │ 50 G │ │ 50 G │ │ 50 G │ │ 50 G │ │ 50 G │ = 250 G     │
│  └──────┘ └──────┘ └──────┘ └──────┘ └──────┘             │
│  ↓ Pod당 스위칭 오버헤드 50% 감소                          │
│  ↓ 프로세스 수 증가 → 멀티코어 활용 가능                   │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

| 상태 | Pods | Greenlets/pod | Total | 예상 CPU |
|------|------|---------------|-------|----------|
| 현재 | 3-6 | 100 | 300-600 | 100% 🔴 |
| 변경 | 4-8 | 50 | 200-400 | ~65% ✅ |

#### 2. Connection Pool 추가 최적화

```python
# 연결 수 제한으로 greenlet 병목 완화
http_client = httpx.Client(
    limits=httpx.Limits(
        max_connections=30,            # 100 → 30 (제한)
        max_keepalive_connections=20,
        keepalive_expiry=60,           # 30 → 60 (재사용 증가)
    ),
)
```

원리:
```
100 greenlets → 30 connections
                 ↓
일부 greenlet은 connection 대기 (yield)
                 ↓
컨텍스트 스위칭 분산 → CPU 부하 감소
```

#### 3. Gevent 세부 튜닝

```python
# libuv 사용 (더 효율적인 이벤트 루프)
import gevent
gevent.config.loop = 'libuv'

# DNS resolver 최적화
import gevent.resolver.ares
gevent.config.resolver = 'ares'
```

### 🔮 AsyncIO 전환 방안

> Celery 5.6.0에서도 AsyncIO Pool 미지원 ([참고](https://rooftopsnow.tistory.com/72))

AsyncIO로 전환하려면 **Celery Chain을 포기**하고 다음 방안 중 선택해야 한다.

#### Option A: 단일 Task로 통합 (Celery 유지)

```python
# 현재 (Chain)
chain(vision | rule | answer | reward).apply_async()

# 변경 (단일 Task)
@celery_app.task
def scan_pipeline_task(image_url: str, job_id: str):
    """4단계를 하나의 Task에서 순차 처리"""
    vision_result = call_openai_vision(image_url)
    publish_event(job_id, "vision", "completed")
    
    rule_result = apply_rules(vision_result)
    publish_event(job_id, "rule", "completed")
    
    answer_result = generate_answer(vision_result, rule_result)
    publish_event(job_id, "answer", "completed")
    
    reward_result = evaluate_reward(answer_result)
    publish_event(job_id, "reward", "completed")
    
    return {...}
```

| 장점 | 단점 |
|------|------|
| Celery 생태계 유지 (Beat, Flower) | 부분 실패 시 전체 재실행 |
| Task 간 메시지 오버헤드 제거 | Chain의 장점 포기 |
| AsyncIO 전환 시 변환 용이 | |

#### Option B: arq (asyncio-native task queue)

```python
# arq worker
async def scan_pipeline(ctx: dict, image_url: str, job_id: str):
    """AsyncIO 네이티브 파이프라인"""
    client = AsyncOpenAI()
    
    vision_result = await client.chat.completions.create(...)
    await publish_event(job_id, "vision", "completed")
    
    rule_result = await asyncio.to_thread(apply_rules, vision_result)
    await publish_event(job_id, "rule", "completed")
    
    answer_result = await client.chat.completions.create(...)
    await publish_event(job_id, "answer", "completed")
    
    return {...}

class WorkerSettings:
    functions = [scan_pipeline]
    max_jobs = 100  # 동시 처리 (greenlet 대체)
```

| 장점 | 단점 |
|------|------|
| 네이티브 async/await | Celery 생태계 포기 |
| 메모리 ~50% 절감 (2-4KB vs 4-8KB) | Chain, DLQ 미지원 |
| Event Loop 단일화 | 전면 코드 재작성 |

> ⚠️ arq 재처리 한계: Chain 미지원으로 부분 실패 시 전체 재실행 필요, DLQ도 수동 구현 필요.
> 상세: [arq: AsyncIO-native Task Queue](../foundations/arq-asyncio-task-queue.md)

### 방안 비교

| 방안 | 복잡도 | 효과 | 코드 변경 | AsyncIO |
|------|--------|------|----------|---------|
| Greenlet 감소 + Pod 증가 | ⭐ | 높음 | 최소 | ❌ |
| Connection Pool 조정 | ⭐⭐ | 중간 | 중간 | ❌ |
| Gevent 튜닝 (libuv) | ⭐⭐ | 낮음 | 중간 | ❌ |
| 단일 Task 통합 (Option A) | ⭐⭐ | 중간 | 중간 | ⚠️ 준비 |
| arq 전환 (Option B) | ⭐⭐⭐⭐⭐ | 최고 | 전면 | ✅ |

---

## References

- [Celery Prefork 병목 지점 분석](https://rooftopsnow.tistory.com/72) - I/O-bound에서 Prefork 효과 없음
- [Celery Chain + Celery Events](https://rooftopsnow.tistory.com/65) - 현재 4단계 Chain 구조
- [동시성 모델과 Green Thread](https://rooftopsnow.tistory.com/74) - Greenlet, Coroutine 비교
- [Event Loop: Gevent](https://rooftopsnow.tistory.com/73) - gevent 동작 원리
- [arq: AsyncIO-native Task Queue](../foundations/arq-asyncio-task-queue.md) - AsyncIO 대안
- [arq Documentation](https://arq-docs.helpmanual.io/) - 공식 문서
- [Connection Pool Exhaustion (이전 이슈)](./40-600vu-connection-pool-exhaustion.md)
- [500 VU Load Test Results](../../../README.md#performance-metrics)
- k6 Result: `k6-load-test-vu600-2025-12-29T10-35-11-580Z.json`
