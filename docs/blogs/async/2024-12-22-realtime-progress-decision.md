# 비동기 파이프라인의 실시간 진행상황 전달: SSE vs WebSocket vs Webhook

> **의사결정 기록** - Celery Chain 기반 이미지 분류 파이프라인에서 클라이언트에게 단계별 진행상황을 실시간으로 전달하기 위한 아키텍처 선택 과정

## 배경

### 시스템 구조

```
Client → scan-api → Celery Chain → ?
                    ├── vision_task (GPT Vision, ~2-3초)
                    ├── rule_task (RAG, ~0.1초)
                    └── answer_task (GPT Answer, ~2초)
```

전체 파이프라인이 4-5초 소요되는 상황에서, 사용자에게 "지금 무슨 단계인지" 실시간으로 보여주고 싶었다.

### 인프라 환경

- **Backend**: Kubernetes + Istio Service Mesh
- **Message Broker**: RabbitMQ (Celery)
- **Frontend**: Vercel에 배포된 React 앱 (Next.js)
- **기존 캐시**: Redis 클러스터 운영 중

---

## 검토한 옵션들

### 1. 단계별 Webhook

```
Celery Worker ──POST──▶ Vercel (Frontend Server) ──Push──▶ Browser
```

**장점**:
- 기존 Webhook 인프라 재사용
- 구현 단순 (각 task에 1줄 추가)

**단점**:
- ⚠️ **Vercel 과금 위험** - Serverless Function이 Webhook을 받아 브라우저로 전달해야 함
- 클라이언트 서버가 필수

### 2. Server-Sent Events (SSE)

```
Browser ◀════GET════ scan-api (HTTP 연결 유지)
                         ▲
                         │ Celery Events (RabbitMQ)
                         ▼
                    Celery Worker
```

**장점**:
- 클라이언트 서버 불필요 (브라우저가 직접 연결)
- HTTP/2 멀티플렉싱으로 연결 효율적
- 브라우저 자동 재연결 지원
- **기존 RabbitMQ + Celery 인프라 활용** (추가 인프라 없음)

**단점**:
- scan-api Pod이 연결을 유지해야 함

### 3. WebSocket

```
Browser ◀═══WS═══▶ scan-api
                      ▲
                      │ Redis Pub/Sub
                      ▼
                 Celery Worker
```

**장점**:
- 양방향 통신 가능

**단점**:
- HTTP/2 멀티플렉싱 불가 (각 WS = 별도 TCP)
- Istio 설정 추가 필요 (`upgradeConfigs`)
- 연결당 리소스 소모 더 높음

---

## Vercel 과금 분석

Vercel 공식 가격 페이지에서 확인한 주요 항목:

### Serverless Functions (Webhook 수신 시)

| 항목 | Hobby (무료) | Pro ($20/월) |
|------|-------------|--------------|
| **Active CPU** | 4시간/월 | $0.128/시간 |
| **Invocations** | 1M/월 | $0.60/1M 이후 |
| **Memory (GB-hr)** | 360 GB-hr/월 | $0.0106/GB-hr |

### Edge Requests

| 항목 | Hobby | Pro |
|------|-------|-----|
| **포함량** | 1M/월 | 10M/월 |
| **초과 시** | - | $2/1M |

### 문제 시나리오

**Webhook 방식 채택 시**:
```
1,000 DAU × 10 스캔/일 × 3 Webhook(단계별) = 30,000 요청/일
                                            = 900,000 요청/월
```

각 Webhook 처리에 Vercel Function이 100ms 실행된다면:
- Active CPU: 900,000 × 0.1초 = 25시간/월
- **예상 추가 비용**: ~$2.5/월 (Pro 기준)

단순 Webhook만으로는 비용이 크지 않지만, **문제는 Webhook을 받아서 브라우저로 전달하는 로직**이다.

SSE나 WebSocket을 Vercel에서 유지하면:
- 연결당 Active CPU 지속 소모
- 4-5초 파이프라인 × 동시 사용자 수 = 급격한 비용 증가
- **Serverless의 cold start로 인한 지연**

---

## 서버 부하 비교: SSE vs WebSocket

### 연결당 리소스

| 항목 | SSE | WebSocket |
|------|-----|-----------|
| **메모리** | ~2-4KB | ~4-8KB |
| **CPU (idle)** | 거의 0 | Ping/Pong 처리 |
| **HTTP/2 멀티플렉싱** | ✅ 가능 | ❌ 불가 |
| **File Descriptor** | 공유 가능 (HTTP/2) | 연결당 1개 |

### 1,000 동시 연결 기준

```
┌─────────────────────────────────────────┐
│ SSE (HTTP/2)                            │
│  • Memory: ~2-4MB                       │
│  • TCP 연결: ~100개 (멀티플렉싱)          │
│  • 연결 생성 RPS: ~2,000/s              │
└─────────────────────────────────────────┘

┌─────────────────────────────────────────┐
│ WebSocket                               │
│  • Memory: ~4-8MB                       │
│  • TCP 연결: 1,000개 (각각 별도)          │
│  • 연결 생성 RPS: ~500/s (Upgrade 오버헤드) │
└─────────────────────────────────────────┘
```

### Istio 호환성

| 항목 | SSE | WebSocket |
|------|-----|-----------|
| **기본 지원** | ✅ HTTP | ⚠️ 설정 필요 |
| **VirtualService** | 일반 라우팅 | `upgradeConfigs` 추가 |
| **Load Balancer** | Sticky 불필요 | Sticky 권장 |

---

## 최종 결정: SSE

### 선택 이유

1. **클라이언트 서버 불필요**
   - Vercel Function 호출 없이 브라우저 → K8s 직접 연결
   - Vercel 과금 회피

2. **서버 부하 최소화**
   - HTTP/2 멀티플렉싱으로 연결 효율적
   - WebSocket 대비 메모리/CPU 절반 수준

3. **기존 인프라 활용**
   - **Celery Events 활용** (추가 인프라 없음!)
   - RabbitMQ가 이미 task 이벤트를 발행 중
   - Redis Pub/Sub 추가 불필요
   - Istio 설정 변경 불필요

4. **구현 복잡도**
   - FastAPI `StreamingResponse` 활용
   - Celery Event Receiver로 task 상태 수신
   - 브라우저 `EventSource` API 사용 (자동 재연결)

### 포기한 것

- 양방향 통신 (클라이언트 → 서버 메시지)
  - 현재 요구사항에 불필요
  - 필요 시 별도 REST API 호출로 해결 가능

---

## 구현 개요

### Backend (FastAPI + Celery Events)

```python
@router.get("/scan/{task_id}/stream")
async def stream_progress(task_id: str):
    async def event_generator():
        # Celery가 이미 발행하는 task events 수신
        with celery_app.connection() as connection:
            recv = celery_app.events.Receiver(connection, handlers={
                'task-started': on_task_started,
                'task-succeeded': on_task_succeeded,
                'task-failed': on_task_failed,
            })
            
            for event in recv.itercapture():
                # task_id가 scan chain에 속하는지 필터링
                if is_scan_chain_task(event, task_id):
                    step = get_step_from_task(event)
                    yield f"data: {json.dumps({'step': step, 'status': event['type']})}\n\n"
                    
                    if step == 'answer' and event['type'] == 'task-succeeded':
                        break
    
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream"
    )
```

### Celery Task (코드 변경 없음!)

```python
# Celery가 자동으로 다음 이벤트들을 RabbitMQ로 발행:
# - task-sent
# - task-received
# - task-started
# - task-succeeded  ← 이벤트 활용
# - task-failed
# - task-retried

@celery_app.task(name="scan.vision", queue="scan.vision")
def vision_task(...):
    # 기존 로직 그대로 - 추가 코드 없음
    ...
```

### Frontend (React)

```typescript
const eventSource = new EventSource(`/api/scan/${taskId}/stream`);
eventSource.onmessage = (e) => {
  const data = JSON.parse(e.data);
  setProgress(data.progress);
  if (data.step === 'answer' && data.status === 'task-succeeded') {
    eventSource.close();
  }
};
```

### 핵심: 추가 인프라 없음

```
기존 RabbitMQ → Celery Events → scan-api Event Receiver → SSE → Browser
                (이미 발행 중)     (새로 구독)
```

Redis Pub/Sub 추가 불필요 - Celery가 이미 모든 task 이벤트를 RabbitMQ로 발행하고 있음!

---

## 결론

| 기준 | Webhook | SSE | WebSocket |
|------|---------|-----|-----------|
| Vercel 과금 | ⚠️ 위험 | ✅ 안전 | ✅ 안전 |
| 서버 부하 | ✅ 낮음 | ✅ 낮음 | ⚠️ 중간 |
| 구현 복잡도 | ✅ 낮음 | ✅ 낮음 | ⚠️ 중간 |
| 양방향 통신 | ❌ 불가 | ❌ 불가 | ✅ 가능 |

**SSE**가 우리 요구사항(단방향 진행상황 푸시)에 가장 적합하며, Vercel 과금을 피하면서 높은 RPS를 달성할 수 있는 선택이다.

---

## 관련 변경: Reward 동기화 비동기 분리

SSE 구현과 함께, reward 처리에서 my 도메인 동기화도 비동기 큐로 분리했다.

### 변경 전 (동기 gRPC)

```
CharacterService._grant_and_sync()
├── INSERT character_ownerships (동기)
├── commit (동기)
└── gRPC: my.grant_character (동기, 블로킹)
```

### 변경 후 (비동기 큐)

```
CharacterService._grant_and_sync()
├── INSERT character_ownerships (동기)
├── commit (동기)
└── sync_to_my_task.delay() (비동기, Fire & Forget)
    └── my.sync 큐로 발행
        └── Celery Worker: gRPC 호출
```

### 이점

1. **응답 지연 감소**: gRPC 호출 대기 없이 즉시 반환
2. **장애 격리**: my 도메인 장애가 character 도메인에 영향 안 줌
3. **자동 재시도**: Celery가 실패 시 exponential backoff로 재시도
4. **Eventual Consistency**: 로컬 저장 성공 후 동기화는 비동기로 처리

---

## 참고 자료

- [Vercel Pricing](https://vercel.com/pricing)
- [MDN: Server-Sent Events](https://developer.mozilla.org/en-US/docs/Web/API/Server-sent_events)
- [FastAPI StreamingResponse](https://fastapi.tiangolo.com/advanced/custom-response/#streamingresponse)
- [Celery Events and Monitoring](https://docs.celeryq.dev/en/stable/userguide/monitoring.html)
- [Redis Pub/Sub vs Celery Events 비교](https://redis.io/docs/latest/develop/pubsub/) - 우리는 Celery Events 선택

---

*작성일: 2024-12-22*
*최종 수정: 2024-12-22 (Celery Events 기반으로 변경, Reward 동기화 분리 추가)*
*프로젝트: Eco² 분리배출 AI 서비스*

