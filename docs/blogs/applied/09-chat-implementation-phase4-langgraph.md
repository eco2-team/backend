# Chat 서비스 구현 Phase 4: LangGraph 파이프라인

> 왜 LangGraph인가, 그리고 Intent-Routed Workflow의 실제 구현

---

## 1. Celery Chain vs LangGraph

### 1.1 scan_worker의 Celery Chain

```python
# scan_worker: 순차적 파이프라인
pipeline = chain(
    vision_task.s(image_url),
    rule_task.s(),
    answer_task.s(),
    reward_task.s(),
)
```

**특징:**
- 항상 동일한 순서로 실행
- 분기 로직은 Task 내부에서 처리
- 디버깅이 어려움 (중간 상태 확인 불가)

### 1.2 chat의 LangGraph

```python
# chat: 조건부 분기 파이프라인
graph = StateGraph(ChatState)
graph.add_conditional_edges(
    "intent",
    route_by_intent,
    {
        "waste": "waste_rag",
        "character": "character",
        "location": "location",
        "general": "general",
    },
)
```

**특징:**
- 상태 기반 분기
- 시각화 가능 (Mermaid 다이어그램)
- 중간 상태 검사/수정 용이

### 1.3 선택 이유

| 요구사항 | Celery | LangGraph |
|----------|--------|-----------|
| 조건부 분기 | △ Task 내부 | ✓ 명시적 |
| 상태 추적 | △ Redis 별도 | ✓ 내장 |
| 스트리밍 | △ 별도 구현 | ✓ 네이티브 |
| asyncio | ✗ gevent | ✓ 네이티브 |
| Subagent | △ 복잡 | ✓ 자연스러움 |

---

## 2. Intent-Routed Workflow 설계

### 2.1 전체 플로우

```
┌───────────┐
│   START   │
└─────┬─────┘
      ▼
┌───────────┐
│  intent   │  "🧠 의도 파악 중..."
└─────┬─────┘
      ▼
 ┌────┴────┐
 │ router  │  의도별 분기
 └────┬────┘
      │
┌─────┼─────┬─────────┬────────────┐
▼     ▼     ▼         ▼            ▼
waste char preview location    general
│     │     │         │            │
└─────┴─────┴─────────┴────────────┘
      │
      ▼
┌───────────┐
│  answer   │  "💭 답변 고민 중..."
└─────┬─────┘
      ▼
┌───────────┐
│    END    │
└───────────┘
```

### 2.2 노드 + 서비스 분리 패턴

> **핵심 변경**: 노드는 오케스트레이션만, 비즈니스 로직은 서비스로 분리

```python
# application/services/intent_classifier.py (순수 비즈니스 로직)
class IntentClassifier:
    def __init__(self, llm: LLMPort):
        self._llm = llm
    
    async def classify(self, message: str) -> IntentResult:
        intent_str = await self._llm.classify_intent(
            message=message,
            system_prompt=INTENT_CLASSIFIER_PROMPT,
        )
        return IntentResult(intent=intent_str, is_complex=...)

# infrastructure/langgraph/nodes/intent.py (오케스트레이션)
def create_intent_node(
    llm: LLMPort,
    event_publisher: EventPublisherPort,
):
    """의도 분류 노드 팩토리."""
    classifier = IntentClassifier(llm)  # 서비스 주입
    
    async def intent_node(state: ChatState) -> ChatState:
        # 1. 이벤트 발행 (시작)
        await event_publisher.publish_stage_event(...)
        
        # 2. 서비스 호출 (비즈니스 로직 위임)
        result = await classifier.classify(state["message"])
        
        # 3. 이벤트 발행 (완료)
        await event_publisher.publish_stage_event(...)
        
        # 4. state 업데이트
        return {**state, "intent": result.intent}
    
    return intent_node
```

**노드 vs 서비스 분리의 장점:**

```
노드에 로직 포함:
  ✗ infrastructure가 application을 먹음
  ✗ 테스트 시 LangGraph 필요
  ✗ 로직 재사용 불가
  
노드 + 서비스 분리:
  ✓ 노드는 orchestration만 (thin wrapper)
  ✓ 서비스는 순수 함수 (프레임워크 무관)
  ✓ 서비스 단독 테스트 가능
  ✓ 다른 파이프라인에서 서비스 재사용
```

**면접 질문:**
> "LangGraph 노드에 로직이 많으면 infrastructure가 application을 먹지 않나요?"

**답변:**
> "노드는 orchestration만 담당합니다:
> 1. 이벤트 발행 (시작)
> 2. 서비스 호출 (비즈니스 로직 위임)
> 3. state 업데이트
> 4. 이벤트 발행 (완료)
> 실제 로직은 application/services에 있어서 테스트와 재사용이 용이합니다."

---

## 3. 핵심 노드 구현

### 3.1 Intent Node

```python
INTENT_CLASSIFIER_PROMPT = """
## 가능한 의도:
- waste: 분리배출, 폐기물 처리 방법 질문
- character: 캐릭터 정보, 획득 조건 질문
- character_preview: 특정 쓰레기로 얻을 수 있는 캐릭터
- location: 주변 재활용 센터, 제로웨이스트샵 검색
- general: 기타 일반적인 대화

## 규칙:
1. 반드시 위 5가지 중 하나만 출력
2. 소문자로 출력
3. 추가 설명 없이 의도 단어만 출력
"""
```

**왜 Few-shot이 아닌 Zero-shot인가:**

```
Few-shot:
  - 토큰 증가 (예시 N개 × 문장 길이)
  - 5개 의도에 비해 과잉

Zero-shot (GPT-5.2):
  - 충분한 이해력
  - 빠른 응답
  - 비용 절감
```

### 3.2 RAG Node

```python
async def rag_node(state: ChatState) -> ChatState:
    classification = state.get("classification_result")
    
    # 1. 분류 기반 검색 (Vision 결과 있을 때)
    if classification:
        disposal_rules = retriever.search(
            category=classification["major_category"],
            subcategory=classification["minor_category"],
        )
    
    # 2. 키워드 검색 (텍스트 질문)
    else:
        keywords = _extract_keywords(state["message"])
        disposal_rules = retriever.search_by_keyword(keywords[0])
    
    return {**state, "disposal_rules": disposal_rules}
```

**두 가지 검색 경로:**

```
이미지 입력:
  Vision → classification → search(분류)
  
텍스트 입력:
  message → keywords → search_by_keyword(키워드)
```

### 3.3 Answer Node (스트리밍)

```python
async def answer_node(state: ChatState) -> ChatState:
    answer_parts = []
    
    # 스트리밍 생성
    async for token in llm.generate_answer_stream(
        classification=state.get("classification_result"),
        disposal_rules=state.get("disposal_rules"),
        user_input=state["message"],
        system_prompt=ANSWER_SYSTEM_PROMPT,
    ):
        # 토큰 이벤트 발행 (실시간)
        await event_publisher.publish_token_event(
            task_id=state["job_id"],
            content=token,
        )
        answer_parts.append(token)
    
    return {**state, "answer": "".join(answer_parts)}
```

**스트리밍의 UX 효과:**

```
┌──────────────────────────────────────┐
│ 🤖 이코                              │
│                                      │
│ 페트병은 라벨을 제거하고 내용물을 비운 │
│ 후 압착하여 배출하면 돼요! ✨▌        │  ← 실시간 표시
│                                      │
│ ● ● ●                                │
└──────────────────────────────────────┘
```

---

## 4. 라우팅 함수

### 4.1 의도 기반 라우팅

```python
def route_by_intent(state: ChatState) -> str:
    """의도에 따른 라우팅."""
    return state.get("intent", "general")
```

**단순하게 유지하는 이유:**

```
복잡한 라우팅:
  def route(state):
      if state["intent"] == "waste" and state["image"]:
          return "vision_waste"
      elif state["intent"] == "waste":
          return "text_waste"
      ...

단순한 라우팅:
  def route(state):
      return state["intent"]  # 노드에서 분기 처리
```

LangGraph의 장점은 **그래프 수준의 분기**입니다.
세부 로직은 노드 내부에서 처리하는 것이 유지보수에 유리.

### 4.2 복잡도 기반 라우팅

```python
def route_by_complexity(state: ChatState) -> str:
    """복잡도에 따른 라우팅."""
    return "complex" if state.get("is_complex") else "simple"

def _is_complex_query(message: str, intent: Intent) -> bool:
    """복잡한 질문인지 판단."""
    complex_keywords = ["그리고", "또한", "차이", "비교", "여러"]
    
    for keyword in complex_keywords:
        if keyword in message:
            return True
    
    if len(message) > 100:
        return True
    
    return False
```

**복잡도 판단의 목적:**

```
단순 질문: "페트병 어떻게 버려?"
  → waste_rag → answer (빠름)

복잡한 질문: "페트병이랑 캔 어떻게 버려? 근처 센터도"
  → decomposer → experts 병렬 → synthesizer (정확)
```

---

## 5. API 엔드포인트

### 5.1 Job 패턴

```python
@router.post("/messages", status_code=202)
async def submit_message(request: ChatMessageRequest):
    """
    1. job_id 생성
    2. Taskiq Worker에 위임
    3. 즉시 job_id 반환
    """
    job_id = f"chat_{uuid.uuid4().hex[:12]}"
    
    # Taskiq Task 호출 (비동기 위임)
    await process_chat.kiq(
        job_id=job_id,
        session_id=request.session_id,
        message=request.message,
    )
    
    return ChatJobResponse(job_id=job_id, ...)
```

**202 Accepted를 사용하는 이유:**

```
200 OK:
  - 요청 처리 완료
  - LLM 응답 대기 (2~10초)
  - 타임아웃 위험

202 Accepted:
  - 요청 접수 완료 (<100ms)
  - 비동기 처리
  - SSE로 결과 전달
```

### 5.2 SSE 스트림

```python
@router.get("/stream/{job_id}")
async def stream_events(job_id: str):
    """Redis Streams → SSE 변환."""
    
    async def event_generator():
        yield f"event: connected\ndata: ...\n\n"
        
        # Redis Streams에서 이벤트 소비
        async for event in redis_consumer.read(job_id):
            yield f"event: {event.type}\ndata: {event.data}\n\n"
    
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
    )
```

---

## 6. Taskiq Task

```python
@broker.task(
    task_name="chat.process",
    timeout=120,
    retry_on_error=True,
    max_retries=2,
)
async def process_chat(
    job_id: str,
    session_id: str,
    message: str,
    ...
) -> dict:
    """LangGraph 파이프라인 실행."""
    
    # 초기 상태
    initial_state = {
        "job_id": job_id,
        "session_id": session_id,
        "message": message,
    }
    
    # 그래프 실행
    graph = get_chat_graph()
    result = await graph.ainvoke(initial_state)
    
    return {
        "job_id": job_id,
        "status": "completed",
        "answer": result["answer"],
    }
```

**Taskiq를 선택한 이유:**

| 특성 | Celery | Taskiq |
|------|--------|--------|
| asyncio | △ gevent | ✓ 네이티브 |
| RabbitMQ | ✓ | ✓ |
| 재시도 | ✓ | ✓ |
| 타임아웃 | ✓ | ✓ |
| 복잡도 | 높음 | 낮음 |

---

## 7. 디렉토리 구조

> **핵심 변경**: presentation/tasks, application/services 분리

```
apps/chat/                       # API (얇게)
├── application/chat/
│   ├── commands/
│   │   └── submit_chat.py       # job_id 생성 + enqueue
│   └── ports/
│       └── job_submitter.py     # enqueue 전용
├── infrastructure/messaging/
│   └── job_submitter.py         # TaskiqJobSubmitter
└── presentation/http/controllers/
    └── chat.py                  # POST /messages, GET /stream

apps/chat_worker/                # Worker (비즈니스 로직)
├── application/chat/
│   ├── services/
│   │   └── intent_classifier.py # 순수 비즈니스 로직
│   ├── dto/
│   │   └── chat_context.py
│   └── ports/
│       ├── llm_client.py
│       ├── retriever.py
│       └── event_publisher.py
├── infrastructure/
│   ├── langgraph/
│   │   ├── factory.py           # create_chat_graph
│   │   └── nodes/
│   │       ├── intent.py        # create_intent_node → 서비스 호출
│   │       ├── rag.py
│   │       └── answer.py
│   └── datasources/
│       ├── retriever.py
│       └── event_publisher.py
└── presentation/tasks/
    └── process_task.py          # @broker.task("chat.process")
```

**왜 presentation/tasks인가?**

```
tasks/만 있을 때:
  ✗ 어떤 레이어인지 불명확
  
presentation/tasks/:
  ✓ "외부 진입점"임을 명시
  ✓ HTTP Controller와 동급
  ✓ 노드 로직과 분리
```

---

## 8. 다음 단계

Phase 5에서는:

1. **Setup** - Config, Dependencies, Broker 설정
2. **main.py** - FastAPI 앱 조립
3. **DI Container** - 의존성 컨테이너

---

**작성일**: 2026-01-13  
**Phase**: 4/6 (Presentation + LangGraph)

