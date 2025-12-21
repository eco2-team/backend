# AI Pipeline MQ Integration Plan

## 1. 개요 (Overview)

Scan API의 AI 파이프라인을 RabbitMQ + Celery 기반 비동기 아키텍처로 전환하여:
1. **단계별 진행 상황 추적**: 프론트엔드 UI와 연동된 실시간 프로그레스 표시
2. **리워드 실패 복구**: Circuit Breaker Open 시 보상 지급 큐잉 및 재처리
3. **응답 시간 개선**: 즉시 응답 (202 Accepted) + 비동기 처리

**기술 스택**: RabbitMQ + Celery (Kafka CDC 불필요, Task Queue 패턴으로 충분)

---

## 2. 현재 구조 (AS-IS)

### 2.1 동기식 파이프라인

```
POST /classify
     │
     ▼
┌─────────────────────────────────────────────────────────────┐
│              process_waste_classification (동기, 블로킹)     │
├─────────────────┬─────────────────┬─────────────────────────┤
│   STEP 1        │   STEP 2        │   STEP 3                │
│   Vision        │   RAG           │   Answer                │
│   (GPT-5.1)     │   (Rule-based)  │   (GPT-5.1)             │
│   ~3.5s         │   ~0.6ms        │   ~3.8s                 │
└─────────────────┴─────────────────┴─────────────────────────┘
     │
     ▼ (추가 동기 호출)
┌─────────────────────────────────────────────────────────────┐
│   Character Reward API (gRPC)                               │
│   - Circuit Breaker 적용                                    │
│   - Open 시 reward=None 반환 → 영구 손실                    │
└─────────────────────────────────────────────────────────────┘
     │
     ▼
200 OK (총 ~7.5초 후 응답)
```

### 2.2 문제점

| 문제 | 영향 |
|------|------|
| **긴 응답 시간** | 7.5초간 블로킹, 사용자 이탈 |
| **단계별 추적 불가** | 프론트엔드에서 진행 상황 표시 불가 |
| **리워드 손실** | Circuit Breaker Open 시 보상 영구 소실 |
| **부분 결과 노출 불가** | 전체 완료 전까지 아무것도 표시 안됨 |

---

## 3. 목표 구조 (TO-BE)

### 3.1 비동기 파이프라인 + 단계별 추적

```
┌──────────────────────────────────────────────────────────────────────────┐
│                          Frontend (React)                                 │
├──────────────────────────────────────────────────────────────────────────┤
│  1. POST /classify    →    task_id 즉시 반환 (202 Accepted)              │
│  2. GET /task/{id}    ←    Polling 또는 SSE 구독                         │
│  3. UI Progress       :    확인 → 분석 → 배출방법                         │
└──────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌──────────────────────────────────────────────────────────────────────────┐
│                         Scan API (FastAPI)                               │
├──────────────────────────────────────────────────────────────────────────┤
│  - task_id 생성 (UUID)                                                   │
│  - Redis에 초기 상태: { status: "queued", step: "pending" }              │
│  - Celery Task 발행 → 즉시 202 응답                                      │
└──────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌──────────────────────────────────────────────────────────────────────────┐
│                        RabbitMQ + Celery Workers                         │
├──────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  ┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐       │
│  │   Task 1:       │    │   Task 2:       │    │   Task 3:       │       │
│  │   vision_scan   │───▶│   rule_match    │───▶│   answer_gen    │       │
│  │                 │    │                 │    │                 │       │
│  │  step: "scan"   │    │  step: "analyze"│    │  step: "answer" │       │
│  │  ~3.5s (GPT)   │    │  ~1ms (local)  │    │  ~3.8s (GPT)   │       │
│  └────────┬────────┘    └────────┬────────┘    └────────┬────────┘       │
│           │                      │                      │                │
│           ▼                      ▼                      ▼                │
│  ┌─────────────────────────────────────────────────────────────┐        │
│  │                     Redis (상태 저장소)                      │        │
│  │  task:{id} → { status, step, progress, partial_result }     │        │
│  └─────────────────────────────────────────────────────────────┘        │
│                                                                          │
│  ┌─────────────────────────────────────────────────────────────┐        │
│  │   Task 4: reward_grant (독립 큐)                            │        │
│  │   - 분류 완료 후 자동 발행                                   │        │
│  │   - 실패 시 DLQ → 재시도 또는 수동 복구                      │        │
│  └─────────────────────────────────────────────────────────────┘        │
│                                                                          │
└──────────────────────────────────────────────────────────────────────────┘
```

### 3.2 UI 매핑

| 프론트 UI | 파이프라인 단계 | Celery Task | Redis step | progress |
|-----------|----------------|-------------|------------|----------|
| **확인** | Vision (GPT) | `vision_scan` | `scan` | 0-33% |
| **분석** | Rule-based RAG | `rule_match` | `analyze` | 33-66% |
| **배출방법** | Answer (GPT) | `answer_gen` | `answer` | 66-99% |
| **완료** | - | - | `complete` | 100% |

---

## 4. 리워드 큐잉 아키텍처

### 4.1 현재 문제

```python
# scan/services/scan.py
async def _call_character_reward_api(self, ...):
    client = get_character_client()
    result = await client.get_character_reward(...)  # Circuit Breaker
    
    if result is None:  # CB Open or 실패
        return None  # ❌ 리워드 영구 손실!
```

### 4.2 MQ 기반 리워드 큐잉

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        Reward Queue Architecture                         │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  ┌──────────────────┐                                                   │
│  │  answer_gen      │                                                   │
│  │  (분류 완료)      │                                                   │
│  └────────┬─────────┘                                                   │
│           │                                                              │
│           ▼ (성공 시 이벤트 발행)                                        │
│  ┌──────────────────────────────────────────────────────────────────┐   │
│  │                    reward.queue (RabbitMQ)                       │   │
│  │  Message: { task_id, user_id, category, amount, timestamp }      │   │
│  └──────────────────────────────────────────────────────────────────┘   │
│           │                                                              │
│           ▼                                                              │
│  ┌──────────────────┐                                                   │
│  │  reward_worker   │                                                   │
│  │  (Celery)        │                                                   │
│  │                  │                                                   │
│  │  1. gRPC 호출    │                                                   │
│  │  2. 실패 시 재시도│ ←── Exponential Backoff (3회)                    │
│  │  3. 최종 실패    │ ───▶ DLQ (Dead Letter Queue)                     │
│  └──────────────────┘                                                   │
│                                                                          │
│  ┌──────────────────────────────────────────────────────────────────┐   │
│  │                    reward.dlq (Dead Letter Queue)                │   │
│  │  - 수동 검토 후 재처리                                            │   │
│  │  - 관리자 알림 (Slack/PagerDuty)                                  │   │
│  │  - 주기적 재처리 스케줄러                                         │   │
│  └──────────────────────────────────────────────────────────────────┘   │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

### 4.3 리워드 메시지 스키마

```python
@dataclass
class RewardMessage:
    task_id: str           # 분류 작업 ID
    user_id: str           # 사용자 UUID
    category: str          # 분류 카테고리 (major_category)
    amount: int            # 보상 포인트
    classification_id: str # 분류 결과 참조 ID
    timestamp: datetime    # 발행 시각
    retry_count: int = 0   # 재시도 횟수
```

### 4.4 장점

| 항목 | 현재 (동기) | MQ 도입 후 |
|------|------------|-----------|
| **리워드 손실** | CB Open 시 영구 손실 | DLQ 보관, 복구 가능 |
| **사용자 피드백** | `reward: null` | `reward_status: "pending"` |
| **추적성** | 로그만 존재 | task_id로 전체 추적 |
| **재처리** | 수동 DB 조작 필요 | 자동 재시도 + DLQ |

---

## 5. Redis 상태 스키마

```python
# task:{task_id}
{
    "task_id": "550e8400-e29b-41d4-a716-446655440000",
    "user_id": "user-uuid",
    "image_url": "https://images.dev.growbin.app/scan/...",
    
    # 상태 정보
    "status": "processing",     # queued | processing | completed | failed
    "step": "analyze",          # pending | scan | analyze | answer | complete
    "progress": 66,             # 0-100 (UI 프로그레스 바)
    
    # 단계별 부분 결과 (점진적 노출)
    "partial_result": {
        "classification": {
            "major_category": "재활용폐기물",
            "middle_category": "무색페트병",
            "minor_category": "찌그러진 무색 페트병"
        },
        "situation_tags": ["내용물_없음", "찌그러짐"]
    },
    
    # 최종 결과 (완료 후)
    "result": {
        "classification_result": {...},
        "disposal_rules": {...},
        "final_answer": {...}
    },
    
    # 리워드 상태 (분리 추적)
    "reward_status": "pending",  # pending | granted | failed | queued
    "reward_task_id": "celery-task-id",
    
    # 타이밍
    "created_at": "2025-12-21T02:30:00Z",
    "updated_at": "2025-12-21T02:30:05Z",
    "metadata": {
        "duration_scan": 3.52,
        "duration_analyze": 0.001,
        "duration_answer": 3.81
    },
    
    # TTL: 24시간 후 자동 삭제
    "expires_at": "2025-12-22T02:30:00Z"
}
```

---

## 6. Celery Task 정의

### 6.1 Queue 구조

```python
# celery_config.py
CELERY_TASK_ROUTES = {
    'scan.tasks.vision_scan': {'queue': 'scan.vision'},
    'scan.tasks.rule_match': {'queue': 'scan.rule'},
    'scan.tasks.answer_gen': {'queue': 'scan.answer'},
    'scan.tasks.reward_grant': {'queue': 'reward'},
}

CELERY_TASK_DEFAULT_QUEUE = 'default'
```

### 6.2 Task Chain (파이프라인)

```python
from celery import chain

@app.post("/classify", status_code=202)
async def classify(payload: ClassificationRequest, user: CurrentUser):
    task_id = str(uuid4())
    
    # Redis 초기 상태 저장
    await redis.hset(f"task:{task_id}", mapping={
        "status": "queued",
        "step": "pending",
        "progress": 0,
        "user_id": str(user.user_id),
        "image_url": str(payload.image_url),
    })
    
    # Celery Chain 발행
    workflow = chain(
        vision_scan.s(task_id, str(payload.image_url)),
        rule_match.s(task_id),
        answer_gen.s(task_id),
    )
    workflow.apply_async()
    
    return {"task_id": task_id, "status": "queued"}


@celery_app.task(bind=True, max_retries=3)
def vision_scan(self, task_id: str, image_url: str):
    """Step 1: GPT Vision 분석"""
    redis.hset(f"task:{task_id}", mapping={
        "status": "processing",
        "step": "scan",
        "progress": 10,
    })
    
    try:
        result = analyze_images("", image_url)
        
        redis.hset(f"task:{task_id}", mapping={
            "progress": 33,
            "partial_result": json.dumps({
                "classification": result.get("classification", {}),
                "situation_tags": result.get("situation_tags", []),
            }),
        })
        
        return result
    except Exception as exc:
        redis.hset(f"task:{task_id}", mapping={
            "status": "failed",
            "error": str(exc),
        })
        raise self.retry(exc=exc, countdown=2 ** self.request.retries)


@celery_app.task
def rule_match(vision_result: dict, task_id: str):
    """Step 2: Rule-based RAG 매칭"""
    redis.hset(f"task:{task_id}", mapping={
        "step": "analyze",
        "progress": 50,
    })
    
    disposal_rules = get_disposal_rules(vision_result)
    
    redis.hset(f"task:{task_id}", mapping={"progress": 66})
    
    return {"vision_result": vision_result, "disposal_rules": disposal_rules}


@celery_app.task
def answer_gen(prev_result: dict, task_id: str):
    """Step 3: GPT Answer 생성"""
    redis.hset(f"task:{task_id}", mapping={
        "step": "answer",
        "progress": 75,
    })
    
    final_answer = generate_answer(
        prev_result["vision_result"],
        prev_result["disposal_rules"],
    )
    
    # 완료 상태 저장
    redis.hset(f"task:{task_id}", mapping={
        "status": "completed",
        "step": "complete",
        "progress": 100,
        "result": json.dumps({
            "classification_result": prev_result["vision_result"],
            "disposal_rules": prev_result["disposal_rules"],
            "final_answer": final_answer,
        }),
    })
    
    # 리워드 Task 발행 (비동기)
    reward_grant.delay(
        task_id=task_id,
        user_id=redis.hget(f"task:{task_id}", "user_id"),
        category=prev_result["vision_result"]["classification"]["major_category"],
    )
    
    return final_answer


@celery_app.task(bind=True, max_retries=3, default_retry_delay=60)
def reward_grant(self, task_id: str, user_id: str, category: str):
    """리워드 지급 (독립 재시도)"""
    redis.hset(f"task:{task_id}", "reward_status", "processing")
    
    try:
        # gRPC 호출 (Circuit Breaker 없이, MQ가 재시도 담당)
        client = CharacterGrpcClient()
        result = client.grant_reward(user_id, category)
        
        redis.hset(f"task:{task_id}", "reward_status", "granted")
        return result
        
    except Exception as exc:
        redis.hset(f"task:{task_id}", "reward_status", "queued")
        
        if self.request.retries >= self.max_retries:
            # DLQ로 이동 (자동)
            redis.hset(f"task:{task_id}", "reward_status", "failed")
            logger.error(f"Reward failed permanently: {task_id}")
            raise
        
        raise self.retry(exc=exc)
```

---

## 7. 프론트엔드 연동

### 7.1 Polling 방식 (Phase 1)

```typescript
// React Hook
const useClassificationTask = (taskId: string) => {
  const [task, setTask] = useState<TaskState | null>(null);
  
  useEffect(() => {
    if (!taskId) return;
    
    const poll = async () => {
      const response = await fetch(`/api/v1/scan/task/${taskId}`);
      const data = await response.json();
      
      setTask(data);
      
      if (data.status !== 'completed' && data.status !== 'failed') {
        setTimeout(poll, 500);  // 0.5초 간격
      }
    };
    
    poll();
  }, [taskId]);
  
  return task;
};

// UI 컴포넌트
const ClassificationProgress = ({ taskId }) => {
  const task = useClassificationTask(taskId);
  
  const steps = [
    { key: 'scan', label: '확인', icon: '📷' },
    { key: 'analyze', label: '분석', icon: '🔍' },
    { key: 'answer', label: '배출방법', icon: '📋' },
  ];
  
  return (
    <div>
      <ProgressBar value={task?.progress || 0} />
      
      <StepIndicator 
        steps={steps}
        currentStep={task?.step}
      />
      
      {task?.partial_result?.classification && (
        <PartialResult 
          classification={task.partial_result.classification}
        />
      )}
    </div>
  );
};
```

### 7.2 SSE 방식 (Phase 2)

```python
# FastAPI SSE Endpoint
@router.get("/task/{task_id}/stream")
async def task_stream(task_id: str):
    async def event_generator():
        while True:
            data = await redis.hgetall(f"task:{task_id}")
            
            yield {
                "event": "update",
                "data": json.dumps(data),
            }
            
            if data.get("status") in ("completed", "failed"):
                break
            
            await asyncio.sleep(0.3)
    
    return EventSourceResponse(event_generator())
```

---

## 8. 구현 로드맵

### Phase 1: Redis 상태 관리 (1주)
- [ ] Redis 상태 스키마 구현
- [ ] `/task/{id}` API 확장 (부분 결과 반환)
- [ ] 프론트엔드 Polling 연동

### Phase 2: Celery + RabbitMQ 도입 (2주)
- [ ] RabbitMQ Helm Chart 배포
- [ ] Celery Worker 구현 (scan, reward 큐)
- [ ] Task Chain 구현
- [ ] DLQ 설정

### Phase 3: 리워드 큐잉 (1주)
- [ ] `reward_grant` Task 구현
- [ ] Circuit Breaker 제거 (MQ 재시도로 대체)
- [ ] DLQ 모니터링 대시보드

### Phase 4: SSE 실시간 (선택)
- [ ] EventSource 엔드포인트 구현
- [ ] 프론트엔드 SSE 연동

---

## 9. Celery + RabbitMQ 충분성 검토

### 9.1 왜 Kafka가 필요 없는가?

| 요구사항 | RabbitMQ + Celery | Kafka |
|----------|-------------------|-------|
| **Task Queue** | ✅ 네이티브 지원 | ❌ Consumer Group 복잡 |
| **재시도 + DLQ** | ✅ 내장 기능 | ⚠️ 수동 구현 필요 |
| **Task Chain** | ✅ Celery Canvas | ❌ Stream 조합 복잡 |
| **짧은 TTL** | ✅ 24시간 후 삭제 | ⚠️ Log Retention 과다 |
| **운영 복잡도** | 낮음 | 높음 (ZK/KRaft) |

### 9.2 현재 요구사항에 Celery + RabbitMQ가 적합한 이유

1. **Command 패턴**: "이 이미지를 분류해줘" → Task Queue
2. **짧은 수명**: 24시간 후 결과 삭제 → Log Compaction 불필요
3. **재시도 중심**: 실패 시 재처리 → DLQ + Retry
4. **순서 보장 불필요**: 사용자별 독립 작업 → Partition 불필요

### 9.3 Kafka가 필요한 시점 (미래)

- **Event Sourcing**: 모든 분류 이벤트 영구 보관
- **CDC**: DB 변경 스트리밍
- **분석 파이프라인**: 실시간 집계/ML 학습 데이터

---

## 10. 참고 자료

- [docs/blogs/async/00-rabbitmq-celery-architecture.md](../blogs/async/00-rabbitmq-celery-architecture.md)
- [docs/blogs/async/01-mq-optimization-opportunities.md](../blogs/async/01-mq-optimization-opportunities.md)
- [Celery Best Practices](https://docs.celeryq.dev/en/stable/userguide/tasks.html)
- [RabbitMQ DLQ Pattern](https://www.rabbitmq.com/dlx.html)

---

## 변경 이력

| 날짜 | 버전 | 변경 내용 |
|------|------|----------|
| 2025-12-21 | 1.0 | 초안 작성 (단계별 추적 + 리워드 큐잉) |
