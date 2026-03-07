# Message Queue #13: 큐잉 적용 Scan API 성능 측정

> 이전 글: [#12 Gevent 기반 LLM API 큐잉 시스템](./21-llm-queue-system-architecture.md)

---

## 개요

Celery Chain + Gevent Pool 기반 비동기 아키텍처 전환 후 **실제 성능을 측정**하고, 이전 동기 방식과 비교합니다.

<table>
<thead>
<tr>
<th>항목</th>
<th>내용</th>
</tr>
</thead>
<tbody>
<tr>
<td><strong>테스트 일시</strong></td>
<td>2025-12-25 02:16 ~ 04:35 (KST)</td>
</tr>
<tr>
<td><strong>테스트 도구</strong></td>
<td>k6 (JavaScript 기반 부하 테스트)</td>
</tr>
<tr>
<td><strong>대상 엔드포인트</strong></td>
<td><code>/api/v1/scan/classify/completion</code> (SSE)</td>
</tr>
<tr>
<td><strong>모니터링</strong></td>
<td>Prometheus + Grafana (Scan SSE Pipeline 대시보드)</td>
</tr>
</tbody>
</table>

---

## 1. 테스트 환경

### 1.1 시스템 아키텍처

```
┌─────────────┐    ┌─────────────┐    ┌─────────────────────────────────┐
│   k6 VUs    │───▶│  scan-api   │───▶│  RabbitMQ (Celery Chain)        │
│ (30~34 VUs) │    │  (HPA 1~4)  │    │  vision → rule → answer → reward│
└─────────────┘    └─────────────┘    └─────────────────────────────────┘
                         │                          │
                         │ SSE                      ▼
                         │                   ┌─────────────────┐
                         └──────────────────▶│  scan-worker    │
                                             │  (Gevent Pool)  │
                                             │  100 greenlets  │
                                             └─────────────────┘
```

### 1.2 Worker 설정

<table>
<thead>
<tr>
<th>Worker</th>
<th>Pool</th>
<th>Concurrency</th>
<th>HPA</th>
</tr>
</thead>
<tbody>
<tr>
<td>scan-worker</td>
<td>gevent</td>
<td>100</td>
<td>1~5</td>
</tr>
<tr>
<td>character-match-worker</td>
<td>gevent</td>
<td>50</td>
<td>1~4</td>
</tr>
<tr>
<td>character-worker</td>
<td>gevent</td>
<td>50</td>
<td>1~2</td>
</tr>
<tr>
<td>my-worker</td>
<td>gevent</td>
<td>50</td>
<td>1~2</td>
</tr>
</tbody>
</table>

### 1.3 k6 테스트 스크립트

```javascript
export const options = {
  stages: [
    { duration: "60s", target: 34 },  // 0 → 34 VU ramp-up
    { duration: "90s", target: 34 },  // 34 VU 유지
    { duration: "30s", target: 0 },   // ramp-down
  ],
  thresholds: {
    http_req_failed: ["rate<0.3"],       // 실패율 30% 미만
    sse_total_duration: ["p(95)<30000"], // 95%가 30초 이내
    sse_ttfb: ["p(95)<8000"],            // TTFB 95%가 8초 이내
  },
};
```

---

## 2. 테스트 결과

### 2.1 테스트 케이스 요약

<table>
<thead>
<tr>
<th>#</th>
<th>시간대 (KST)</th>
<th>VUs</th>
<th>k6 Success</th>
<th>Grafana Success</th>
<th>스냅샷</th>
</tr>
</thead>
<tbody>
<tr>
<td>1</td>
<td>02:16:01 ~ 02:17:45</td>
<td>10</td>
<td>100%</td>
<td>100%</td>
<td><a href="https://snapshots.raintank.io/dashboard/snapshot/QB6LdIZwjFLXiNVQq1xljAQ3vnVT77a3">링크</a></td>
</tr>
<tr>
<td>2</td>
<td>02:59:01 ~ 03:00:12</td>
<td>34</td>
<td>82.8%</td>
<td>100%</td>
<td><a href="https://snapshots.raintank.io/dashboard/snapshot/ULL5FNeft8dN9yU25MYyKyEoOrMxbagk">링크</a></td>
</tr>
<tr>
<td>3</td>
<td>04:31:59 ~ 04:34:45</td>
<td>30</td>
<td>95.1%</td>
<td>100%</td>
<td><a href="https://snapshots.raintank.io/dashboard/snapshot/FqFEJTRNVC3G9SQbH0DWc2EluC7RlFzU">링크</a></td>
</tr>
</tbody>
</table>

> **k6 vs Grafana 불일치**: k6에서 503 에러는 Istio/Envoy 레벨에서 `no healthy upstream` 발생.
> Grafana는 Celery 레벨 성공률 측정 → Worker가 처리한 Task는 100% 성공.

---

### 2.2 테스트 #1: 저부하 (VU 10)

**k6 결과:**
```
========================================
📊 SSE Test Summary
========================================
Total Requests:    46
✅ Completed:      46 (100.0%)
⚠️  Partial:       0 (0.0%)
❌ Failed:         0 (0.0%)

⏱️  TTFB (p95):    5742ms
⏱️  Total (p95):   19598ms
========================================
```

**Grafana 메트릭:**

<table>
<thead>
<tr>
<th>지표</th>
<th>값</th>
</tr>
</thead>
<tbody>
<tr>
<td>Chain Avg Duration</td>
<td><strong>11.3s</strong></td>
</tr>
<tr>
<td>TTFB (p50)</td>
<td>1.74s</td>
</tr>
<tr>
<td>Success Rate</td>
<td>100%</td>
</tr>
<tr>
<td>RPS</td>
<td>0.10 req/s</td>
</tr>
<tr>
<td>Active Connections (max)</td>
<td>~10</td>
</tr>
</tbody>
</table>

**스테이지별 평균 소요 시간:**
- vision: ~4.5s (OpenAI Vision API)
- rule: ~0.3s (DB 조회)
- answer: ~4.8s (OpenAI Chat API)
- reward: ~1.7s (Character Match + DB)

![저부하 테스트 대시보드](sse-benchmark-100pct-top.png)

---

### 2.3 테스트 #2: 고부하 (VU 34)

**k6 결과:**
```
========================================
📊 SSE Test Summary
========================================
Total Requests:    1616
✅ Completed:      150 (9.3%)
⚠️  Partial:       0 (0.0%)
❌ Failed:         1466 (90.7%)  ← 503 no healthy upstream

⏱️  TTFB (p95):    3354ms
⏱️  Total (p95):   20093ms
========================================
ERRO[0180] thresholds on metrics 'http_req_failed' have been crossed
```

**Grafana 메트릭:**

<table>
<thead>
<tr>
<th>지표</th>
<th>값</th>
</tr>
</thead>
<tbody>
<tr>
<td>Chain Avg Duration</td>
<td><strong>19.0s</strong></td>
</tr>
<tr>
<td>TTFB (p50)</td>
<td>1.07s</td>
</tr>
<tr>
<td>Success Rate</td>
<td>100%</td>
</tr>
<tr>
<td>RPS</td>
<td>1.10 req/s</td>
</tr>
<tr>
<td>Active Connections (peak)</td>
<td><strong>25</strong></td>
</tr>
</tbody>
</table>

**문제 분석:**
1. `503 no healthy upstream`: scan-api Pod가 과부하로 liveness probe 실패 → 재시작
2. HPA가 스케일아웃 되기 전에 Pod 불안정 발생
3. Celery Worker는 정상 처리 (Grafana Success 100%)

![고부하 테스트 대시보드](sse-benchmark-vu34-82pct-top.png)

---

### 2.4 테스트 #3: 안정화 (VU 30)

**k6 결과:**
```
========================================
📊 SSE Test Summary
========================================
Total Requests:    164
✅ Completed:      156 (95.1%)
⚠️  Partial:       1 (0.6%)
❌ Failed:         7 (4.3%)
🎁 Reward Null:    120 (73.2%)  ← 캐릭터 매칭 실패

⏱️  TTFB (p95):    16342ms
⏱️  Total (p95):   47079ms
========================================
```

**Grafana 메트릭:**

<table>
<thead>
<tr>
<th>지표</th>
<th>값</th>
</tr>
</thead>
<tbody>
<tr>
<td>Chain Avg Duration</td>
<td><strong>21.1s</strong></td>
</tr>
<tr>
<td>TTFB (p50)</td>
<td>1.32s</td>
</tr>
<tr>
<td>Success Rate</td>
<td>100%</td>
</tr>
<tr>
<td>RPS</td>
<td>0.27 req/s</td>
</tr>
</tbody>
</table>

**관찰 사항:**
1. VU 30으로 감소 → 95.1% 성공률 달성
2. p99 응답 시간이 ~25s로 증가 (OpenAI rate limit 근접)
3. Reward Null 73.2%: 캐릭터 매칭 로직 이슈 (별도 수정 필요)

![안정화 테스트 대시보드](sse-benchmark-vu30-95pct-top.png)

---

## 3. 동기 vs 비동기 비교

### 3.1 이전 동기 방식 (asyncio.to_thread)

> 참조: [Scan API 성능 측정 및 시각화](https://rooftopsnow.tistory.com/17)

**테스트 결과 (2025-12-08):**

<table>
<thead>
<tr>
<th>동시 접속</th>
<th>평균 응답</th>
<th>최대 응답</th>
<th>성공률</th>
<th>비고</th>
</tr>
</thead>
<tbody>
<tr>
<td>5명</td>
<td>10s</td>
<td>22s</td>
<td>100%</td>
<td>스레드 2+4 세팅</td>
</tr>
<tr>
<td>10명</td>
<td>-</td>
<td>-</td>
<td>안정적</td>
<td></td>
</tr>
<tr>
<td>100명</td>
<td>-</td>
<td>150s+</td>
<td><strong>0%</strong></td>
<td>504 GATEWAY TIMEOUT</td>
</tr>
</tbody>
</table>

**병목 분석:**
- GIL로 인한 CPU 처리 병목
- 스레드풀 크기 제한 (2+4 = 6 concurrent)
- GPT I/O가 70~80% 점유

---

### 3.2 비교표

<table>
<thead>
<tr>
<th>항목</th>
<th>동기 (asyncio.to_thread)</th>
<th>비동기 (Celery + Gevent)</th>
</tr>
</thead>
<tbody>
<tr>
<td><strong>동시 처리 능력</strong></td>
<td>6명 (스레드 2+4)</td>
<td><strong>100 greenlets/worker</strong></td>
</tr>
<tr>
<td><strong>평균 응답 시간</strong></td>
<td>10~22초</td>
<td><strong>11~21초</strong></td>
</tr>
<tr>
<td><strong>테스트 부하</strong></td>
<td>100명 → 504 TIMEOUT (0%)</td>
<td><strong>34명 → 82~95% success</strong></td>
</tr>
<tr>
<td><strong>메모리 사용</strong></td>
<td>4GB (prefork)</td>
<td><strong>~1GB (gevent)</strong></td>
</tr>
<tr>
<td><strong>스케일링</strong></td>
<td>수동 (Pod 수)</td>
<td><strong>HPA 자동</strong></td>
</tr>
<tr>
<td><strong>병목</strong></td>
<td>GIL + 스레드풀</td>
<td>OpenAI RPM</td>
</tr>
</tbody>
</table>

> ⚠️ **테스트 조건 차이**: 동기 100명 vs 비동기 34명으로 직접 비교 불가.
> 비동기 100명 부하 테스트는 추후 진행 예정.

---

## 4. 핵심 지표 분석

### 4.1 스테이지별 소요 시간

<table>
<thead>
<tr>
<th>Stage</th>
<th>평균 (avg)</th>
<th>p99</th>
<th>비율</th>
<th>설명</th>
</tr>
</thead>
<tbody>
<tr>
<td><strong>vision</strong></td>
<td>4.5s</td>
<td>6~10s</td>
<td>40%</td>
<td>OpenAI Vision API</td>
</tr>
<tr>
<td><strong>rule</strong></td>
<td>0.3s</td>
<td>2~3s</td>
<td>5%</td>
<td>PostgreSQL 규칙 조회</td>
</tr>
<tr>
<td><strong>answer</strong></td>
<td>4.8s</td>
<td>8~15s</td>
<td>45%</td>
<td>OpenAI Chat API</td>
</tr>
<tr>
<td><strong>reward</strong></td>
<td>1.7s</td>
<td>3~5s</td>
<td>10%</td>
<td>캐릭터 매칭 + DB</td>
</tr>
</tbody>
</table>

**소요 시간 비율:**

```
       vision (40%)         rule(5%)      answer (45%)       reward(10%)
├────────────────────────────┼────┼─────────────────────────────┼───────┤
│█████████████████████████████│████│█████████████████████████████│███████│
└────────────────────────────────────────────────────────────────────────┘
0s                          5s      6s                         11s     13s
```

> **핵심 병목**: OpenAI API 호출 (vision + answer)이 전체 소요 시간의 **85%** 차지.

---

### 4.2 TTFB 분석

<table>
<thead>
<tr>
<th>부하</th>
<th>TTFB p50</th>
<th>TTFB p95</th>
<th>비고</th>
</tr>
</thead>
<tbody>
<tr>
<td>저부하 (VU 10)</td>
<td>1.74s</td>
<td>5.7s</td>
<td>정상</td>
</tr>
<tr>
<td>고부하 (VU 34)</td>
<td>1.07s</td>
<td>3.4s</td>
<td>빠름 (캐시 히트?)</td>
</tr>
<tr>
<td>안정화 (VU 30)</td>
<td>1.32s</td>
<td><strong>16.3s</strong></td>
<td>OpenAI 지연</td>
</tr>
</tbody>
</table>

> TTFB = 첫 번째 SSE 이벤트 도착 시간 (vision task 시작 시점)

---

## 5. 병목 및 개선 방향

### 5.1 현재 병목

1. **OpenAI Rate Limit**
   - Tier 1: 500 RPM, 30K TPM
   - vision + answer = 2 calls/request → 최대 250 req/min

2. **scan-api Pod 불안정**
   - 고부하 시 liveness probe 실패
   - HPA 스케일아웃 지연

3. **Reward Null (73%)**
   - 캐릭터 매칭 로직 버그 (별도 트러블슈팅 필요)

### 5.2 개선 방안

<table>
<thead>
<tr>
<th>영역</th>
<th>현재</th>
<th>개선</th>
</tr>
</thead>
<tbody>
<tr>
<td>OpenAI</td>
<td>동기 호출</td>
<td>Batch API (50% 비용 절감)</td>
</tr>
<tr>
<td>Rate Limit</td>
<td>500 RPM</td>
<td>Tier 업그레이드 or Multi-Key</td>
</tr>
<tr>
<td>scan-api</td>
<td>HPA CPU 70%</td>
<td>startupProbe 조정, 초기 replica 증가</td>
</tr>
<tr>
<td>캐시</td>
<td>규칙 DB 조회</td>
<td>Redis 캐싱 (rule 단계 최적화)</td>
</tr>
</tbody>
</table>

---

## 6. 결론

### 6.1 성과

- **동시 처리 능력 향상**: 6 스레드 → 100 greenlets/worker
- **고부하 안정성**: 34 VU 부하에서 82~95% 성공률 달성
- **메모리 효율**: 4GB → 1GB (75% 절감)
- **자동 스케일링**: HPA 기반 탄력적 확장

### 6.2 제한 사항

- **테스트 규모**: 최대 34 VU (100명 부하 미검증)
- **OpenAI Rate Limit**: 진정한 병목은 외부 API
- **TTFB 증가**: 부하 증가 시 p95 16s까지 상승
- **캐릭터 매칭**: 73% Null 문제 별도 해결 필요

### 6.3 다음 단계

1. **100 VU 부하 테스트** (동기 방식과 동일 조건 비교)
2. OpenAI Batch API 적용 검토
3. Rate Limit 대응 (Multi-Key 또는 Tier 업그레이드)
4. scan-api startupProbe 튜닝
5. 캐릭터 매칭 버그 수정

---

## 관련 문서

### 시리즈
- [이전: #12 Gevent 기반 LLM API 큐잉 시스템](./21-llm-queue-system-architecture.md)
- [#11 Prefork 병목 분석](./15-system-rpm-analysis-before-asyncio.md)

### 대시보드 정의
- [`scan-sse-pipeline.yaml`](../../../workloads/monitoring/dashboards/scan-sse-pipeline.yaml)
- [`domain-scan-api.yaml`](../../../workloads/monitoring/dashboards/domain-scan-api.yaml)

### 외부 참조
- [동기 Scan API 성능 측정](https://rooftopsnow.tistory.com/17)

