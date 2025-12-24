# 이코에코(Eco2) 비동기 전환 #6: Celery Chain + Events 구현

> 이전 글: [비동기 전환 #5: Celery 기반 Scan Pipeline 구현](./05-celery-scan-pipeline.md)

---

## 개요

본 문서는 **Celery Chain을 활용한 단계별 파이프라인 처리**와 **Celery Events 기반 실시간 진행상황 전달(SSE)** 구현 과정을 기록한다.

### 목표

- 4단계 Celery Chain으로 파이프라인 분리 (vision → rule → answer → reward)
- Celery Events + SSE로 클라이언트에게 실시간 진행상황 전달
- Worker 분리: scan-worker (AI) vs character-worker (도메인 동기화)
- 도메인 간 비동기 동기화 (character → my)

### 핵심 성과

| 항목 | Before (Phase 1) | After (Phase 2+3) |
|------|------------------|-------------------|
| **파이프라인** | 단일 Task | 4단계 Chain |
| **실패 시 재시도** | 전체 재실행 | 해당 단계만 |
| **진행상황 전달** | Webhook 완료 시에만 | SSE 실시간 |
| **Worker 구조** | scan-worker 단일 | scan-worker + character-worker |
| **Webhook 응답** | reward 없음 | reward 포함 |

---

## 1. 아키텍처 개요

### 1.1 전체 흐름

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                                                                             │
│  Client                                                                     │
│     │                                                                       │
│     ├─── POST /classify ──────────────────────────────────────────────┐     │
│     │    {"image_url": "...", "callback_url": "..."}                  │     │
│     │                                                                 │     │
│     └─── GET /progress/{task_id} ──────────────────────────────┐     │     │
│          (SSE 연결)                                             │     │     │
│                                                                 │     │     │
│  ┌──────────────────────────────────────────────────────────────┴─────┴──┐  │
│  │                           scan-api                                    │  │
│  │  ┌─────────────────────────────────────────────────────────────────┐  │  │
│  │  │  chain(vision | rule | answer | reward).apply_async()          │  │  │
│  │  └─────────────────────────────────────────────────────────────────┘  │  │
│  │                                │                                      │  │
│  │  ┌─────────────────────────────┴────────────────────────────────┐    │  │
│  │  │  SSE StreamingResponse ◀── Celery Event Receiver            │    │  │
│  │  └──────────────────────────────────────────────────────────────┘    │  │
│  └───────────────────────────────────────────────────────────────────────┘  │
│                                  │                                          │
│                                  ▼                                          │
│  ┌───────────────────────────────────────────────────────────────────────┐  │
│  │                         RabbitMQ                                      │  │
│  │  ┌────────────┐  ┌────────────┐  ┌────────────┐  ┌─────────────────┐  │  │
│  │  │scan.vision │──│ scan.rule  │──│scan.answer │──│reward.character │  │  │
│  │  │   Queue    │  │   Queue    │  │   Queue    │  │    Queue        │  │  │
│  │  └──────┬─────┘  └──────┬─────┘  └──────┬─────┘  └───────┬─────────┘  │  │
│  │         │               │               │                │            │  │
│  │  ┌──────┴───────────────┴───────────────┴────────────────┴─────────┐  │  │
│  │  │         celeryev Exchange (Celery Events)                       │  │  │
│  │  │  task-started, task-succeeded, task-failed ...                 │  │  │
│  │  └──────────────────────────────────────────────────────────────────┘  │  │
│  │                                                    ┌─────────────────┐  │  │
│  │                                                    │   my.sync Queue │  │  │
│  │                                                    └───────┬─────────┘  │  │
│  └───────────────────────────────────────────────────────────┼───────────┘  │
│                     │                                        │              │
│        ┌────────────┴────────────┐              ┌────────────┴────────────┐ │
│        │      scan-worker        │              │   character-worker      │ │
│        │    (worker-ai 노드)     │              │  (worker-storage 노드)  │ │
│        │                         │              │                         │ │
│        │  vision_task (GPT-4V)   │              │  scan_reward_task       │ │
│        │  rule_task (RAG)        │              │  (CharacterService)     │ │
│        │  answer_task (GPT-4)    │              │  sync_to_my_task        │ │
│        └─────────────────────────┘              └─────────────────────────┘ │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 1.2 Queue 구성

| Queue | 처리 Worker | 설명 |
|-------|------------|------|
| `scan.vision` | scan-worker | GPT Vision 이미지 분류 |
| `scan.rule` | scan-worker | RAG 기반 배출 규정 검색 |
| `scan.answer` | scan-worker | GPT 최종 답변 생성 |
| `reward.character` | character-worker | 캐릭터 리워드 평가 + Webhook |
| `my.sync` | character-worker | my 도메인 동기화 |

---

## 2. Celery Chain 구현

### 2.1 Chain 구조 (4단계)

```python
# domains/scan/services/scan.py
from celery import chain
from domains.character.consumers.reward import scan_reward_task

async def _classify_async(self, task_id, user_id, image_url, callback_url):
    """4단계 Celery Chain 실행"""
    
    # vision, rule, answer: scan-worker (worker-ai)
    # reward: character-worker (worker-storage)
    pipeline = chain(
        vision_task.s(str(task_id), str(user_id), image_url, user_input),
        rule_task.s(),
        answer_task.s(),
        scan_reward_task.s(callback_url=callback_url),  # Webhook 전송
    )
    
    pipeline.apply_async()
```

### 2.2 Task 함수는 동기 함수 (def)

> Celery Task 함수는 `def` (동기 함수)로 정의해야 한다. `async def` (코루틴)은 직접 지원되지 않는다.

**Celery의 기본 Worker Pool (prefork)**:
- `multiprocessing` 기반으로 동작
- 각 Worker 프로세스는 **동기 함수**만 실행
- `async def` 코루틴은 네이티브로 지원되지 않음

```python
# ✅ 올바른 방식: def (동기 함수)
@celery_app.task(bind=True, name="scan.vision")
def vision_task(self, task_id, user_id, image_url, user_input):
    result = analyze_images(...)  # 동기 함수 호출
    return {"task_id": task_id, ...}

# ❌ 지원되지 않음: async def (코루틴)
@celery_app.task(bind=True, name="scan.vision")
async def vision_task(self, task_id, user_id, image_url, user_input):
    result = await analyze_images_async(...)  # 실행 불가
    return {"task_id": task_id, ...}
```

**async 함수를 호출해야 하는 경우**:

Task 내부에서 async 함수를 호출해야 한다면, 별도의 이벤트 루프를 생성해야 한다:

```python
# domains/character/consumers/reward.py

def _evaluate_reward_internal(task_id, user_id, ...):
    """동기 함수 내에서 async 함수 호출"""
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            result = loop.run_until_complete(
                _evaluate_reward_async(task_id, user_id, ...)
            )
        finally:
            loop.close()
        return result
    except Exception:
        logger.exception("Reward evaluation failed")
        return None
```

**Worker Pool별 async 지원 현황**:

| Pool | 기반 | async def 지원 | 비고 |
|------|------|---------------|------|
| `prefork` (기본) | multiprocessing | ❌ | 프로젝트에서 사용 중 |
| `threads` | threading | ❌ | GIL 제약 |
| `gevent` | greenlet | ⚠️ | monkey-patching 필요 |
| `eventlet` | greenlet | ⚠️ | monkey-patching 필요 |

> **참고**: Celery 5.x에서도 네이티브 asyncio 코루틴은 공식 지원되지 않음. [Celery GitHub Issue #7874](https://github.com/celery/celery/issues/7874) 참조.

---

### 2.3 Task 간 데이터 전달

Chain에서는 이전 Task의 반환값이 다음 Task의 첫 번째 인자로 자동 전달된다:

```
vision_task ──────▶ rule_task ──────▶ answer_task ──────▶ scan_reward_task
   │                   │                  │                    │
   │ return {          │ return {         │ return {           │ return {
   │   "task_id",      │   **prev,        │   **prev,          │   **prev,
   │   "user_id",      │   "disposal_     │   "final_answer",  │   "reward": {
   │   "classif..",    │    rules",       │   "metadata",      │     "received",
   │   "metadata",     │   "metadata",    │ }                  │     "name", ...
   │ }                 │ }                │                    │   }
   │                   │                  │                    │ }
   └───────────────────┴──────────────────┴────────────────────┘
                              prev_result로 자동 전달
```

### 2.4 Reward를 Chain에 포함한 이유

**기존 문제점 (Fire & Forget 방식)**:
```python
# ❌ 이전 방식: reward가 SSE 결과에 포함되지 않음
def answer_task(self, prev_result):
    _trigger_reward_task.delay(...)  # Fire & Forget, 결과 유실
    return result  # reward 없음!
```

**해결책 (Chain 포함)**:
```python
# ✅ 현재 방식: reward가 Chain 결과에 포함됨
def scan_reward_task(self, prev_result):
    reward = _evaluate_reward(...)
    return {
        **prev_result,
        "reward": reward,  # ✅ SSE로 클라이언트에 전달
    }
```

**동기 vs 비동기 응답 일관성**:

| 필드 | 동기 응답 | 비동기 SSE (수정 전) | 비동기 SSE (수정 후) |
|------|----------|----------------------|----------------------|
| `pipeline_result` | ✅ | ✅ | ✅ |
| `reward` | ✅ | ❌ **누락** | ✅ **포함** |

---

## 3. Celery Events 기반 SSE 구현

### 3.1 Celery Events 활성화

```python
# domains/_shared/celery/config.py

def get_celery_config(self):
    return {
        # ... 기존 설정 ...
        
        # Celery Events 활성화 (SSE 실시간 진행상황용)
        "task_send_sent_event": True,       # task-sent 이벤트 발행
        "worker_send_task_events": True,    # worker에서 task 이벤트 발행
    }
```

### 3.2 Event 종류

Celery Worker가 자동으로 발행하는 이벤트:

| 이벤트 | 발생 시점 | 용도 |
|--------|----------|------|
| `task-sent` | Task가 큐에 발행됨 | - |
| `task-received` | Worker가 Task 수신 | - |
| `task-started` | Task 실행 시작 | SSE: 단계 시작 |
| `task-succeeded` | Task 성공 완료 | SSE: 단계 완료 |
| `task-failed` | Task 실패 | SSE: 에러 알림 |
| `task-retried` | Task 재시도 | - |

### 3.3 SSE 엔드포인트

```python
# domains/scan/api/v1/endpoints/progress.py

@router.get("/{task_id}/progress")
async def stream_progress(
    task_id: str,
    last_event_id: str | None = Header(None, alias="Last-Event-ID"),
) -> StreamingResponse:
    """Celery Events 기반 실시간 진행상황 스트리밍
    
    재접속 지원: Last-Event-ID 헤더로 이어받기 가능
    """
    return StreamingResponse(
        _event_generator(task_id, last_event_id),
        media_type="text/event-stream",
        headers={...},
    )
```

### 3.4 SSE 재접속 지원

연결 끊김 후 재접속 시 이벤트 유실을 방지합니다:

| 항목 | 구현 |
|------|------|
| **event_id** | 각 이벤트에 순차적 ID 부여 (`id:` 필드) |
| **Last-Event-ID** | 클라이언트가 재접속 시 헤더로 전송 |
| **이벤트 캐싱** | Redis에 최근 5분간 이벤트 보관 |
| **재전송** | Last-Event-ID 이후 이벤트 자동 재전송 |

```
┌─────────────────────────────────────────────────────────────────┐
│                    SSE 재접속 흐름                               │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  Client                           Server                        │
│     │                               │                           │
│     │─── GET /progress/{id} ───────▶│                           │
│     │                               │                           │
│     │◀── id: 1, data: {vision} ────│                           │
│     │◀── id: 2, data: {rule} ──────│                           │
│     │                               │                           │
│     │     ⚡ 연결 끊김               │                           │
│     │                               │                           │
│     │─── GET /progress/{id} ───────▶│                           │
│     │    Last-Event-ID: 2           │                           │
│     │                               │                           │
│     │◀── id: 3, data: {answer} ────│  ← 캐시에서 재전송         │
│     │◀── id: 4, data: {reward} ────│                           │
│     │                               │                           │
└─────────────────────────────────────────────────────────────────┘
```

### 3.5 클라이언트 (Frontend)

```typescript
// EventSource API (자동 재접속 + Last-Event-ID 지원)
const eventSource = new EventSource(`/api/v1/scan/${taskId}/progress`);

eventSource.onmessage = (e) => {
  const data = JSON.parse(e.data);
  
  // 진행상황 UI 업데이트
  setProgress(data.progress);
  setCurrentStep(data.step);
  
  // reward 완료 시 최종 결과 처리
  if (data.step === 'reward' && data.status === 'completed') {
    const { result } = data;
    
    // 파이프라인 결과
    setPipelineResult(result.pipeline_result);
    
    // 캐릭터 리워드 (있는 경우)
    if (result.reward?.received) {
      showCharacterReward(result.reward);
    }
    
    eventSource.close();
  }
};

// EventSource는 자동 재접속 + Last-Event-ID 헤더 전송
// 수동 처리 불필요
eventSource.onerror = (e) => {
  console.log('SSE 연결 끊김, 자동 재접속 시도...');
  // EventSource가 자동으로 재접속하며 Last-Event-ID 헤더 전송
};
```

**SSE 이벤트 예시**:

```json
// 진행상황 이벤트
{"task_id": "abc-123", "step": "vision", "status": "started", "progress": 0}
{"task_id": "abc-123", "step": "vision", "status": "completed", "progress": 25}
{"task_id": "def-456", "step": "rule", "status": "completed", "progress": 50}
{"task_id": "ghi-789", "step": "answer", "status": "completed", "progress": 75}

// 최종 결과 이벤트 (ClassificationResponse 스키마와 동일)
{
  "task_id": "jkl-012",
  "step": "reward",
  "status": "completed",
  "progress": 100,
  "result": {
    "task_id": "abc-123",
    "status": "completed",
    "message": "classification completed",
    "pipeline_result": {
      "classification_result": {
        "classification": {
          "major_category": "재활용폐기물",
          "middle_category": "무색페트병",
          "minor_category": "무색페트병(물병)"
        },
        "situation_tags": ["내용물_없음", "플라스틱_재질"],
        "meta": {"user_input": "이 폐기물을 어떻게 분리배출해야 하나요?"}
      },
      "disposal_rules": {...},
      "final_answer": {
        "disposal_steps": {"단계1": "...", "단계2": "..."},
        "insufficiencies": [],
        "user_answer": "..."
      }
    },
    "reward": {
      "received": true,
      "already_owned": false,
      "name": "플라스틱 요정",
      "dialog": "오늘도 분리배출을 잘 해줬구나!",
      "match_reason": "플라스틱류 분류 성공",
      "character_type": "fairy"
    },
    "error": null
  }
}
```

**reward 조건 미충족 시** (insufficiencies 있거나 재활용폐기물이 아닌 경우):

```json
{
  "step": "reward",
  "status": "completed",
  "progress": 100,
  "result": {
    "task_id": "abc-123",
    "status": "completed",
    "message": "classification completed",
    "pipeline_result": {...},
    "reward": null,
    "error": null
  }
}
```

---

## 4. Worker 분리 전략

### 4.1 노드 구성

| 노드 | 역할 | 배포 대상 |
|------|------|----------|
| `worker-ai` | GPU/AI 처리 | scan-worker, celery-beat |
| `worker-storage` | 도메인 동기화 | character-worker |

### 4.2 scan-worker

```yaml
# workloads/domains/scan-worker/base/deployment.yaml

spec:
  template:
    spec:
      containers:
      - name: scan-worker
        args:
        - "-A"
        - "domains.scan.celery_app"
        - "worker"
        - "-Q"
        - "scan.vision,scan.rule,scan.answer"  # AI 큐만 처리
      nodeSelector:
        domain: worker-ai
```

### 4.3 character-worker

```yaml
# workloads/domains/character-worker/base/deployment.yaml

spec:
  template:
    spec:
      containers:
      - name: character-worker
        args:
        - "-A"
        - "domains.character.consumers.reward"
        - "worker"
        - "-Q"
        - "reward.character,my.sync"  # Chain 마지막 단계 + 도메인 동기화
      nodeSelector:
        domain: worker-storage
      tolerations:
      - key: "domain"
        operator: "Equal"
        value: "worker-storage"
        effect: "NoSchedule"
```

### 4.4 Worker 간 Chain 전달

Chain의 마지막 단계가 다른 Worker에서 실행되더라도 Celery가 자동으로 처리:

```
scan-worker (worker-ai)                   character-worker (worker-storage)
┌─────────────────────────────────────┐   ┌─────────────────────────────────┐
│ scan.vision Queue                   │   │ reward.character Queue          │
│ scan.rule Queue                     │   │ my.sync Queue                   │
│ scan.answer Queue                   │   │                                 │
│                                     │   │                                 │
│ vision_task ──▶ rule_task           │   │                                 │
│                   │                 │   │                                 │
│               answer_task           │   │                                 │
│                   │                 │   │                                 │
│                   └──────────────────────▶ scan_reward_task              │
│                                     │   │         │                       │
│                                     │   │         └──▶ sync_to_my_task    │
└─────────────────────────────────────┘   └─────────────────────────────────┘
```

---

## 5. 도메인 간 비동기 동기화

### 5.1 Reward → My 동기화

캐릭터 소유권 저장 후 my 도메인으로 비동기 동기화:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                                                                             │
│  character-api                                                              │
│     │                                                                       │
│     ├── CharacterService._grant_and_sync()                                  │
│     │      │                                                                │
│     │      ├── INSERT character.character_ownerships (동기)                 │
│     │      ├── commit() (동기)                                              │
│     │      └── sync_to_my_task.delay() (비동기, Fire & Forget)              │
│     │             │                                                         │
│     │             │ my.sync 큐로 발행                                       │
│     │             ▼                                                         │
│     │      character-worker                                                 │
│     │             │                                                         │
│     │             └── gRPC: my.UserCharacterService.GrantCharacter          │
│     │                      │                                                │
│     │                      ▼                                                │
│     │               my-api                                                  │
│     │                      │                                                │
│     │                      └── INSERT user_profile.user_characters          │
│     │                                                                       │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 5.2 sync_to_my_task 구현

```python
# domains/character/consumers/sync_my.py

@celery_app.task(
    name="character.sync_to_my",
    queue="my.sync",
    max_retries=5,
    retry_backoff=True,
    retry_backoff_max=60,
)
def sync_to_my_task(
    user_id: str,
    character_id: str,
    character_code: str,
    character_name: str,
    character_type: str | None,
    character_dialog: str | None,
    source: str,
):
    """my 도메인으로 캐릭터 소유권 동기화 (gRPC)"""
    
    client = get_my_client()
    grant_request = GrantCharacterRequest(
        user_id=UUID(user_id),
        character_id=UUID(character_id),
        # ... 기타 필드
    )
    return await client.grant_character(grant_request)
```

### 5.3 장점

| 항목 | 동기 gRPC | 비동기 큐 |
|------|----------|----------|
| **응답 지연** | +100-500ms | ~1ms |
| **장애 격리** | my 장애 → character 영향 | 격리됨 |
| **재시도** | Circuit Breaker만 | Celery 자동 재시도 |
| **모니터링** | gRPC 메트릭 | RabbitMQ 대시보드 |

---

## 6. 타임라인

```
0s      Client: POST /classify
        scan-api: chain(vision | rule | answer | reward).apply_async()
        scan-api: return {"task_id": "xxx", "status": "processing"}
        Client: GET /progress/{task_id} (SSE 연결)
        
0.1s    SSE: {"status": "connected", "task_id": "xxx"}

0.2s    vision_task 시작 (scan-worker)
        SSE: {"step": "vision", "status": "started", "progress": 0}
        
2.5s    vision_task 완료
        SSE: {"step": "vision", "status": "completed", "progress": 25}
        
2.6s    rule_task 완료 (빠름)
        SSE: {"step": "rule", "status": "completed", "progress": 50}
        
4.0s    answer_task 완료
        SSE: {"step": "answer", "status": "completed", "progress": 75}
        
4.1s    scan_reward_task 시작 (character-worker)
        리워드 조건 평가
        
4.5s    scan_reward_task 완료
        SSE: {"step": "reward", "status": "completed", "progress": 100, "result": {...}}
        sync_to_my_task.delay() (캐릭터 획득 시)
        
4.5s+   SSE 연결 종료 (클라이언트가 result 수신 완료)
        
5.0s    my 도메인 동기화 완료 (비동기)
```

---

## 7. 결론

### 7.1 달성 사항

- Celery Chain으로 4단계 파이프라인 분리 (vision → rule → answer → reward)
- Celery Events + SSE로 실시간 진행상황 전달
- Worker 분리 (AI vs 도메인 동기화)
- 동기/비동기 응답 일관성 확보 (reward 필드)
- 도메인 간 비동기 동기화 (Eventual Consistency)

### 7.2 Trade-off

| 항목 | 장점 | 단점 |
|------|------|------|
| **4단계 Chain** | 부분 실패 격리, 응답 일관성 | 복잡도 증가 |
| **SSE** | 실시간, 저비용 | 단방향만 |
| **Worker 분리** | 독립 스케일링 | 운영 복잡도 |
| **비동기 동기화** | 장애 격리 | Eventual Consistency |

### 7.3 향후 계획

- Kafka 도입 검토 (이벤트 영속성 필요 시)
- chat 도메인 비동기 전환
- Worker 오토스케일링

---

## 참고 자료

- [Celery Canvas: Designing Work-flows](https://docs.celeryq.dev/en/stable/userguide/canvas.html)
- [Celery Events and Monitoring](https://docs.celeryq.dev/en/stable/userguide/monitoring.html)
- [MDN: Server-Sent Events](https://developer.mozilla.org/en-US/docs/Web/API/Server-sent_events)
- [FastAPI StreamingResponse](https://fastapi.tiangolo.com/advanced/custom-response/#streamingresponse)

---

## 변경 이력

| 날짜 | 버전 | 변경 내용 |
|------|------|----------|
| 2024-12-22 | 1.0 | 초안 작성 |
| 2024-12-22 | 1.1 | 4단계 Chain으로 변경 (reward를 Chain에 포함) |
| 2024-12-22 | 1.2 | Celery Task가 동기 함수(def)여야 하는 이유 섹션 추가 |
