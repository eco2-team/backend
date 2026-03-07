# Chat 아키텍처 면접 답변 가이드

> **목적**: chat/chat_worker 아키텍처에 대한 면접 질문 대응
>
> **핵심 메시지**: "API는 작업 제출만, Worker가 상태 변경의 source of truth"

---

## 1. 아키텍처 한 장 요약

```
┌─────────────────────────────────────────────────────────────┐
│                        Client                                │
└────────────────────┬────────────────────────────────────────┘
                     │ POST /chat
                     │ (message, session_id)
                     v
┌─────────────────────────────────────────────────────────────┐
│                    chat (API)                                │
│  ┌─────────────────────────────────────────────────────┐    │
│  │ presentation/http/controllers/chat.py               │    │
│  │   └── submit_chat()                                 │    │
│  └────────────────────────┬────────────────────────────┘    │
│                           │                                  │
│  ┌────────────────────────v────────────────────────────┐    │
│  │ application/commands/submit_chat.py                 │    │
│  │   └── SubmitChatCommand                             │    │
│  │       └── job_id 생성                               │    │
│  │       └── JobSubmitter.submit()                     │    │
│  └────────────────────────┬────────────────────────────┘    │
│                           │                                  │
│  ┌────────────────────────v────────────────────────────┐    │
│  │ infrastructure/messaging/job_submitter.py           │    │
│  │   └── TaskiqJobSubmitter (enqueue만)                │    │
│  └────────────────────────┬────────────────────────────┘    │
└───────────────────────────┼─────────────────────────────────┘
                            │ RabbitMQ
                            v
┌─────────────────────────────────────────────────────────────┐
│                   chat_worker                                │
│  ┌─────────────────────────────────────────────────────┐    │
│  │ presentation/tasks/process_task.py                  │    │
│  │   └── @broker.task("chat.process")                  │    │
│  │       └── queued 이벤트 발행 ◄── 여기서부터 상태 관리 │    │
│  │       └── graph.ainvoke()                           │    │
│  └────────────────────────┬────────────────────────────┘    │
│                           │                                  │
│  ┌────────────────────────v────────────────────────────┐    │
│  │ infrastructure/langgraph/ (Orchestration)           │    │
│  │   └── nodes/intent.py                               │    │
│  │       └── IntentClassifier 서비스 호출              │    │
│  │   └── nodes/rag.py                                  │    │
│  │   └── nodes/answer.py                               │    │
│  └────────────────────────┬────────────────────────────┘    │
│                           │                                  │
│  ┌────────────────────────v────────────────────────────┐    │
│  │ application/services/ (비즈니스 로직)               │    │
│  │   └── IntentClassifier                              │    │
│  │   └── (향후) AnswerGenerator, RAGSearcher 등       │    │
│  └─────────────────────────────────────────────────────┘    │
│                                                              │
│  ┌─────────────────────────────────────────────────────┐    │
│  │ infrastructure/datasources/event_publisher.py       │    │
│  │   └── Redis Streams 이벤트 발행                     │    │
│  └────────────────────────┬────────────────────────────┘    │
└───────────────────────────┼─────────────────────────────────┘
                            │ Redis Streams
                            v
┌─────────────────────────────────────────────────────────────┐
│              event_router → sse_gateway                      │
│                        │                                     │
│                        v                                     │
│                     Client SSE                               │
└─────────────────────────────────────────────────────────────┘
```

---

## 2. 핵심 설계 원칙

| 원칙 | 설명 |
|------|------|
| **API는 얇게** | 요청 검증 + 작업 제출만. 비즈니스 로직 없음 |
| **Worker가 상태 주체** | queued/running/done 이벤트는 모두 Worker가 발행 |
| **노드는 오케스트레이션만** | LangGraph 노드 → 서비스 호출 → state 업데이트 |
| **서비스는 순수 로직** | 프레임워크 의존성 없는 비즈니스 로직 |
| **Port로 경계 설정** | 테스트 시 mock 교체 용이 |

---

## 3. 면접 질문 & 답변 (8개)

### Q1: 왜 API/Worker 둘 다 event_publisher가 있나요?

**A**: ~~없습니다.~~ (리팩토링 후)

- **API**: `JobSubmitterPort` (enqueue 전용)
- **Worker**: `EventPublisherPort` (상태 이벤트 발행)

**설계 이유**:
```
API가 queued 이벤트를 발행하면:
- Worker가 아직 작업을 수신하지 않았는데
- 클라이언트는 이미 "작업 시작"으로 착각

Worker가 queued 발행하면:
- 실제로 작업을 수신한 시점에 발행
- 상태의 일관성 보장
```

---

### Q2: Job 상태(queued/running/done)의 source of truth는 어디?

**A**: **Worker**

```
┌─────────────────────────────────────────┐
│              chat_worker                 │
│  ┌─────────────────────────────────┐    │
│  │ process_task.py                 │    │
│  │   1. queued 이벤트 발행         │    │
│  │   2. graph.ainvoke()            │    │
│  │   3. 각 노드에서 progress 발행  │    │
│  │   4. done 이벤트 발행           │    │
│  └─────────────────────────────────┘    │
│                 │                        │
│                 v                        │
│          Redis Streams                   │
│    (이벤트 소싱 + 상태 저장)              │
└─────────────────────────────────────────┘
```

**이점**:
- 상태 변경과 이벤트 발행이 한 곳에서 발생
- Redis Streams가 이벤트 히스토리 보존
- 클라이언트 재연결 시 히스토리 조회 가능

---

### Q3: 중복 작업 제출 시 멱등성 키는 어디서 잡나요?

**A**: **API** (scan 패턴 참고)

```python
# chat/presentation/http/controllers/chat.py
@router.post("")
async def submit_chat(
    payload: ChatRequest,
    x_idempotency_key: str | None = Header(None),
    ...
):
    # 1. 캐시에서 기존 job_id 조회
    if x_idempotency_key:
        cached = await idempotency_cache.get(x_idempotency_key)
        if cached:
            return cached  # 기존 응답 반환

    # 2. 새 작업 생성
    response = await command.execute(request)

    # 3. 캐시에 저장 (TTL: 1시간)
    if x_idempotency_key:
        await idempotency_cache.set(x_idempotency_key, response)

    return response
```

**미구현 사유**: MVP 단계에서 클라이언트 재시도 빈도가 낮아 후순위

---

### Q4: LangGraph 노드가 실패하면 재시도 단위는?

**A**: **Task 단위** (전체 재시작)

```python
@broker.task(
    task_name="chat.process",
    retry_on_error=True,
    max_retries=2,  # 최대 2회 재시도
    timeout=120,
)
async def process_chat(...):
    ...
```

**설계 결정 이유**:
1. **LLM 호출 비용**: 노드 단위 재시도 시 중간 상태 저장 필요 → 복잡도 증가
2. **사용자 경험**: 실패 시 전체 재시도가 더 예측 가능
3. **향후 개선**: LangGraph Checkpointing으로 노드 단위 재시도 가능

---

### Q5: 프롬프트/JSON 자주 바뀌면 배포를 매번 해야 하나요?

**A**: **현재는 의도적으로 버전 고정**

```
장점:
- 빌드 아티팩트만으로 재현 가능
- 프롬프트 변경 = 코드 변경 → PR 리뷰 필수
- 운영 환경에서 예기치 않은 변경 방지

단점:
- 핫픽스가 느림 (배포 필요)

향후 옵션:
1. ConfigMap: K8s 환경에서 런타임 교체
2. S3/GCS: 외부 저장소에서 로딩
3. Feature Flag: 프롬프트 버전 A/B 테스트
```

**면접 답변**:
> "현재는 프롬프트 품질 관리를 위해 의도적으로 코드와 함께 배포합니다.
> 프롬프트 변경이 서비스 품질에 직접 영향을 주므로
> PR 리뷰를 통한 검증이 중요하다고 판단했습니다.
> 튜닝이 잦아지면 ConfigMap이나 S3로 외부화할 계획입니다."

---

### Q6: retriever가 local JSON인데 왜 datasources인가요?

**A**: **네이밍 의도** (리팩토링 완료)

```
기존: infrastructure/persistence/retriever.py
변경: infrastructure/datasources/retriever.py
```

**이유**:
- `persistence`는 DB/트랜잭션/일관성을 연상
- Local JSON은 "읽기 전용 데이터 소스"
- 향후 ES/Vector DB로 교체 시에도 `datasources/`에 위치

**마이그레이션 경로**:
```python
# 현재
class LocalJSONRetriever(RetrieverPort):
    ...

# 향후 (Port는 동일)
class ElasticsearchRetriever(RetrieverPort):
    ...
```

---

### Q7: 요청 하나의 trace-id가 API→Worker→노드까지 이어지나요?

**A**: **현재 부분 구현, 향후 OpenTelemetry 통합 예정**

```python
# 현재 구현
logger.info(
    "Chat task started",
    extra={
        "job_id": job_id,       # 추적 가능
        "session_id": session_id,
        "user_id": user_id,
    },
)

# 향후 계획
from opentelemetry import trace

tracer = trace.get_tracer(__name__)

with tracer.start_as_current_span("process_chat") as span:
    span.set_attribute("job_id", job_id)
    ...
```

**구현 계획**:
1. `job_id`를 모든 로그에 포함 (현재 완료)
2. OpenTelemetry SDK 통합
3. Jaeger/Tempo로 분산 추적

---

### Q8: LLM 호출 폭주 제어는 어디서 하나요?

**A**: **Worker Concurrency + 향후 Token Budget**

```python
# 현재: Taskiq Worker 동시성 제한
# Dockerfile
CMD ["taskiq", "worker", "...", "--workers", "2"]

# 향후: Token Budget (Rate Limiting)
class TokenBudget:
    def __init__(self, max_tokens_per_minute: int):
        self._budget = max_tokens_per_minute
        self._used = 0

    async def acquire(self, tokens: int) -> bool:
        if self._used + tokens > self._budget:
            return False  # 거부
        self._used += tokens
        return True
```

**다단계 방어**:
1. **API Gateway**: 요청 rate limiting
2. **Worker Concurrency**: 동시 처리 수 제한
3. **Token Budget**: LLM 호출당 비용 제어 (향후)

---

## 4. 디렉토리 구조 최종

```
apps/chat/                         # API (얇게)
├── application/chat/
│   ├── commands/
│   │   └── submit_chat.py         # job_id 생성 + enqueue
│   └── ports/
│       └── job_submitter.py       # enqueue 전용 Port
├── infrastructure/messaging/
│   └── job_submitter.py           # Taskiq Adapter
└── presentation/http/controllers/
    └── chat.py                    # POST /chat

apps/chat_worker/                  # Worker (비즈니스 로직)
├── application/chat/
│   ├── services/
│   │   └── intent_classifier.py   # 순수 비즈니스 로직
│   ├── dto/
│   │   └── chat_context.py
│   └── ports/
│       ├── llm_client.py
│       ├── retriever.py
│       └── event_publisher.py
├── infrastructure/
│   ├── langgraph/nodes/           # 오케스트레이션
│   │   ├── intent.py              # → IntentClassifier 호출
│   │   ├── rag.py
│   │   └── answer.py
│   ├── datasources/               # (persistence 아님)
│   │   ├── retriever.py           # Local JSON
│   │   └── event_publisher.py     # Redis Streams
│   ├── llm/
│   │   ├── openai/client.py
│   │   └── gemini/client.py
│   └── assets/                    # 버전 고정 (의도적)
│       ├── data/source/*.json
│       └── prompts/*.txt
└── presentation/tasks/
    └── process_task.py            # @broker.task
```

---

## 5. 한 줄 요약

> **"API는 job_id 발급과 enqueue만, 상태 관리와 이벤트 발행은 Worker가 책임진다."**

이 원칙으로 다음이 보장됩니다:
- 상태의 source of truth가 명확 (Worker)
- 테스트 용이 (Port/Adapter)
- 확장 용이 (서비스 분리)

