# 이코에코(Eco2) Message Queue #11: AsyncIO 전환 전 시스템 RPM 현황 분석

> **작성일**: 2025-12-24  
> **GitHub**: [eco2-team/backend](https://github.com/eco2-team/backend)  
> **브랜치**: `feat/high-throughput-workers`  
> **대시보드**: [Grafana Snapshot](https://snapshots.raintank.io/dashboard/snapshot/zz5pBgaMfZXuPDf7TwSLYgcMw103UZUE)

## 1. 개요

본 문서는 Celery Pool을 AsyncIO로 전환하기 전, 현재 시스템의 성능 지표를 기록합니다.
Prometheus에서 수집한 실제 메트릭을 기반으로 작성되었습니다.

### 측정 환경

| 항목 | 값 |
|------|-----|
| 측정 시간 | 2025-12-24 14:39~14:42 KST |
| 누적 요청 수 | 126 requests |
| LLM Provider | OpenAI GPT-5.1 |
| OpenAI Tier | Tier 1 (500 RPM, 500,000 TPM) |
| Celery Pool | prefork |
| scan-worker replicas | 3 |
| scan-worker concurrency | 8 (설정값) |

### 부하 테스트 설정 (Locust)

```
[2025-12-24 14:39:32] Ramping to 100 users at a rate of 10.00 per second
[2025-12-24 14:39:41] All users spawned: {"ScanCompletionUser": 100} (100 total users)
```

| 항목 | 값 |
|------|-----|
| 동시 사용자 | 100 users |
| 램프업 속도 | 10 users/sec |
| 램프업 시간 | ~9초 |
| 테스트 대상 | `/api/v1/scan/classify/completion` (SSE)

---

## 2. 핵심 지표 (Prometheus 실측)

> 📊 **대시보드**: [Grafana Snapshot](https://snapshots.raintank.io/dashboard/snapshot/zz5pBgaMfZXuPDf7TwSLYgcMw103UZUE)

| 지표 | 측정값 | 설명 |
|------|--------|------|
| **Chain Avg Duration** | **41.65초** | 전체 파이프라인 평균 |
| **TTFB (p50)** | **10.00초** | 첫 SSE 이벤트까지 |
| **TTFB (p99)** | **10.00초** | tail latency 안정적 |
| **Requests/sec** | **0.0323 req/s** | 1시간 평균 |
| **RPM** | **1.94 RPM** | 분당 요청 |
| **Success Rate** | **100%** | 126/126 성공 |
| **Active Connections** | **0** | 측정 시점 유휴 |

---

## 3. 스테이지별 성능 분석 (Prometheus 실측)

### 3.1 평균 소요 시간

| Stage | 평균 소요 시간 | 역할 |
|-------|---------------|------|
| **vision** | **12.25초** | GPT-5.1 Vision API |
| **rule** | **8.40초** | RAG 규칙 매칭 |
| **answer** | **14.13초** | GPT-5.1 Chat Completion |
| **reward** | **5.38초** | character.match 동기 호출 |
| **합계** | **~40.16초** | Chain 평균 41.65초와 유사 |

### 3.2 p99 소요 시간 (Tail Latency)

| Stage | p99 소요 시간 | 비고 |
|-------|--------------|------|
| **vision** | **37.91초** | OpenAI API 지연 시 급증 |
| **rule** | **49.75초** | RAG 매칭 최악 케이스 |
| **answer** | **46.63초** | OpenAI API 지연 영향 |
| **reward** | **15.11초** | match worker 대기 |

### 3.3 스테이지 소요 시간 비율

```
┌────────────────────────────────────────────────────────────┐
│                    Stage 소요 시간 비율                      │
├────────────────────────────────────────────────────────────┤
│                                                            │
│  answer ████████████████████████████████████  14.13초 35%  │
│  vision ██████████████████████████████        12.25초 30%  │
│  rule   █████████████████████                  8.40초 21%  │
│  reward █████████████                          5.38초 14%  │
│                                                            │
│  총 소요 시간: ~40.16초 (Chain 평균: 41.65초)               │
│                                                            │
└────────────────────────────────────────────────────────────┘
```

**분석:**
- `answer` (GPT Chat Completion)이 가장 긴 소요 시간 (35%)
- `vision` (GPT Vision)이 두 번째 (30%)
- OpenAI API 호출이 전체의 **65%** 차지

---

## 4. 성능 분석

### 4.1 현재 처리량

| 지표 | 값 | 계산 |
|------|-----|------|
| **실측 RPM** | **1.94 RPM** | Prometheus rate(1h) |
| **실측 RPS** | **0.0323 req/s** | RPM / 60 |
| **Chain 평균** | **41.65초** | avg(sum/count) |

### 4.2 이론적 최대 처리량

| 병목 | 계산 | RPS |
|------|------|-----|
| OpenAI Tier 1 | 500 RPM / 2 calls | **4.17 chains/sec** |
| prefork workers | 9 workers / 41.65초 | **0.22 RPS** |
| **실질 한계** | min(4.17, 0.22) | **~0.22 RPS** |

### 4.3 병목 분석

```
┌─────────────────────────────────────────────────────────────┐
│                    병목 분석                                  │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  🔴 주요 병목: prefork Pool 동기 블로킹                       │
│                                                             │
│  1 request → 1 worker → 41.65초 블로킹                      │
│                                                             │
│  ┌──────────────────────────────────────────┐               │
│  │ Worker 1: ████████████████████████████ 41s              │
│  │ Worker 2:              ████████████████████████ 41s     │
│  │ Worker 3:                           █████████████ 41s   │
│  │           ↑                         ↑                   │
│  │           t=0                       t=41s               │
│  └──────────────────────────────────────────┘               │
│                                                             │
│  9 workers × 41.65초 = 0.22 RPS (이론 최대)                 │
│  실측: 0.0323 RPS (이론의 15%)                              │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## 5. 시스템 제약 분석

### 5.1 물리적 제약

| 리소스 | 설정값 | 실제 | 한계 |
|--------|--------|------|------|
| **노드 메모리** | 4GB | ~3.5GB 가용 | t3.medium |
| **scan-worker replicas** | 3 | 3 | 정상 |
| **concurrency** | 8 | ~6-9 (메모리 제한) | OOM 위험 |
| **총 workers** | 24 (설정) | **6-9 (실제)** | 메모리 병목 |

### 5.2 OpenAI Rate Limit

| Tier | RPM | TPM | Chain RPS |
|------|-----|-----|-----------|
| **현재 (Tier 1)** | 500 | 500,000 | 4.17 (vision+answer 2회) |
| Tier 2 | 2,000 | 2,000,000 | 16.67 |
| Tier 3 | 5,000 | 5,000,000 | 41.67 |

---

## 6. 개선 방안

### 6.1 AsyncIO Pool 전환 (권장)

| 항목 | 현재 (prefork) | 개선 (asyncio) |
|------|---------------|----------------|
| 동시 I/O | 6-9 | **100+** |
| 메모리 | 3.6GB+ | **~100MB** |
| 블로킹 | 100% (41초/req) | **논블로킹** |
| 예상 RPS | 0.22 | **OpenAI 한계까지** |

```yaml
# 변경 전
args: [-P, prefork, -c, '8']

# 변경 후
args: [-P, asyncio, -c, '100']
```

### 6.2 예상 개선 효과

| 지표 | 현재 | AsyncIO 전환 후 |
|------|------|----------------|
| RPS | 0.0323 | **~4 RPS** (OpenAI 한계) |
| RPM | 1.94 | **~240 RPM** |
| 동시 처리 | 6-9 | **100+** |
| 메모리 | 3.6GB | **~100MB** |

---

## 7. 다음 단계

1. **celery-pool-asyncio 도입** → 100+ 동시 I/O
2. **Task를 `async def`로 변환** → 네이티브 비동기
3. **성능 재측정** → AsyncIO 전환 후 비교
4. **OpenAI Tier 업그레이드** 또는 **Gemini 병행** 검토

---

## 8. 참고 자료

- [Grafana Dashboard Snapshot](https://snapshots.raintank.io/dashboard/snapshot/zz5pBgaMfZXuPDf7TwSLYgcMw103UZUE)
- [Celery Pool Types](https://docs.celeryq.dev/en/stable/userguide/workers.html#concurrency)
- [celery-pool-asyncio](https://github.com/kai3341/celery-pool-asyncio)
- [OpenAI Rate Limits](https://platform.openai.com/docs/guides/rate-limits)
- [이전 블로그: Celery Chain + Events](./09-celery-chain-events-part2.md)

---

## 변경 이력

| 날짜 | 내용 |
|------|------|
| 2025-12-24 | 최초 작성 - AsyncIO 전환 전 현황 기록 |
| 2025-12-24 | Prometheus 실측 데이터 기반 수치 업데이트 |
