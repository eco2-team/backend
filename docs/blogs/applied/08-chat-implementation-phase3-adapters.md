# Chat 서비스 구현 Phase 3: Infrastructure Adapters

> Port 인터페이스의 실제 구현, 왜 이렇게 설계했는가

---

## 1. Phase 3의 목표

Phase 2에서 정의한 6개 Port의 구현체(Adapter)를 작성합니다:

```
Port                   → Adapter
────────────────────────────────────────────
LLMPort                → OpenAILLMClient
                       → AnthropicLLMClient
                       → (GeminiLLMClient - 추후)
ToolCallerPort         → OpenAIToolCaller
                       → AnthropicToolCaller
TokenCounterPort       → TiktokenCounter
RetrieverPort          → LocalJSONRetriever
EventPublisherPort     → RedisEventPublisher
```

---

## 2. LLM Client 설계: 비동기 + 스트리밍

### 2.1 scan_worker와의 차이점

```python
# scan_worker (동기)
class GPTLLMAdapter(LLMPort):
    def generate_answer(self, ...) -> dict:
        response = self._client.chat.completions.parse(...)
        return response.choices[0].message.parsed

# chat (비동기 + 스트리밍)
class OpenAILLMClient(LLMPort):
    async def generate_answer_stream(self, ...) -> AsyncIterator[str]:
        stream = await self._client.chat.completions.create(
            ..., stream=True
        )
        async for chunk in stream:
            yield chunk.choices[0].delta.content
```

**비동기를 선택한 이유:**

| 항목 | scan_worker | chat |
|------|-------------|------|
| 실행 환경 | Celery Worker | Taskiq Worker |
| 이벤트 루프 | 없음 (gevent) | asyncio 네이티브 |
| API 호출 | 1회/요청 | N회/요청 (Tool) |
| 동시성 | 프로세스 기반 | 코루틴 기반 |

**스트리밍의 UX 효과:**

```
┌──────────────────────────────────────┐
│ 🤖 이코                             │
│                                      │
│ 페트병은 ▌                           │  ← 즉시 표시 시작
│                                      │
│ ● ● ●                               │
└──────────────────────────────────────┘

전체 응답 대기 시: 2~5초
스트리밍 시작까지: <100ms
```

---

### 2.2 OpenAI vs Anthropic 클라이언트 구현

**OpenAI (AsyncOpenAI):**

```python
async def generate_stream(self, prompt, ...) -> AsyncIterator[str]:
    stream = await self._client.chat.completions.create(
        model=self._model,
        messages=messages,
        stream=True,
    )
    async for chunk in stream:
        if chunk.choices and chunk.choices[0].delta.content:
            yield chunk.choices[0].delta.content
```

**Anthropic (AsyncAnthropic):**

```python
async def generate_stream(self, prompt, ...) -> AsyncIterator[str]:
    async with self._client.messages.stream(
        model=self._model,
        max_tokens=4096,
        system=system_prompt,
        messages=messages,
    ) as stream:
        async for text in stream.text_stream:
            yield text
```

**API 차이점:**

| 항목 | OpenAI | Anthropic |
|------|--------|-----------|
| 스트리밍 방식 | `stream=True` 파라미터 | `.stream()` 컨텍스트 매니저 |
| 청크 접근 | `chunk.choices[0].delta.content` | `stream.text_stream` |
| 시스템 프롬프트 | `messages[0]` | 별도 `system` 파라미터 |

**Port/Adapter로 추상화:**

```python
# 사용하는 측 (Application Layer)
async def process_message(llm: LLMPort, message: str):
    async for token in llm.generate_stream(message):
        await event_publisher.publish_token_event(job_id, token)
    
# Provider 차이를 모름
```

---

## 3. Tool Calling: 두 가지 패러다임

### 3.1 OpenAI Function Calling

```
┌─────────┐     ┌───────────┐     ┌─────────┐
│  User   │────▶│    LLM    │────▶│  개발자  │
│ Request │     │  (제안)   │     │  (실행)  │
└─────────┘     └───────────┘     └────┬────┘
                                        │
┌─────────┐     ┌───────────┐           │
│ Response│◀────│    LLM    │◀──────────┘
│         │     │  (최종)   │    (결과 전달)
└─────────┘     └───────────┘
```

```python
# 1단계: Tool 제안 요청
response = await client.chat.completions.create(
    model=model,
    messages=messages,
    tools=openai_tools,
    tool_choice="auto",
)

# 2단계: 개발자가 실행
for tc in response.choices[0].message.tool_calls:
    result = await executors[tc.function.name](**args)
    
# 3단계: 결과 전달하여 최종 응답
```

### 3.2 Anthropic Programmatic Tool Calling

```
┌─────────┐     ┌─────────────────────┐     ┌─────────┐
│  User   │────▶│        LLM          │────▶│ Response│
│ Request │     │ (분석 → 실행 → 요약) │     │ (요약)  │
└─────────┘     └─────────────────────┘     └─────────┘
```

```python
response = await client.messages.create(
    model=model,
    tools=anthropic_tools,
    messages=messages,
)

# Claude가 직접 실행 계획을 세우고 결과를 요약
for block in response.content:
    if block.type == "tool_use":
        # 실행 요청
    elif block.type == "text":
        # 요약 텍스트
```

**Programmatic의 장점:**

| 측면 | Function Calling | Programmatic |
|------|------------------|--------------|
| API 호출 | 2회+ | 1회 |
| 컨텍스트 증가 | Tool 결과 전체 | 요약만 |
| 복잡한 시나리오 | 개발자가 조율 | LLM이 조율 |

**Chat 서비스에서의 선택:**

```
단순 질문 (1 Tool):
  → OpenAI Function Calling (효율적)

복잡한 질문 (N Tools):
  → Anthropic Programmatic (컨텍스트 절약)
```

---

## 4. Token Counter: 로컬 vs API

### 4.1 OpenAI (tiktoken)

```python
class TiktokenCounter(TokenCounterPort):
    def __init__(self, model, encoding_name="cl100k_base"):
        self._encoding = tiktoken.get_encoding(encoding_name)
        
    def count(self, text: str) -> int:
        return len(self._encoding.encode(text))
```

**tiktoken 선택 이유:**

```
API 호출 방식:
  - 네트워크 지연: ~50ms
  - 비용: API 호출당 과금
  - 장점: 정확함

tiktoken 로컬:
  - 지연: <1ms
  - 비용: 0
  - 정확도: 99%+ (동일 인코딩)
```

### 4.2 메시지 오버헤드 계산

```python
def count_messages(self, messages: list[dict]) -> int:
    tokens_per_message = 4  # role, content 구분자
    total = 0
    
    for message in messages:
        total += tokens_per_message
        for key, value in message.items():
            if isinstance(value, str):
                total += self.count(value)
    
    total += 3  # 프라이밍 오버헤드
    return total
```

---

## 5. Event Publisher: Redis Streams

### 5.1 이벤트 타입별 발행

```python
async def publish_stage_event(self, task_id, stage, status, ...):
    """파이프라인 진행 이벤트"""
    event_data = {
        "event_type": "stage",
        "stage": stage,      # intent, vision, rag, answer
        "status": status,    # started, completed, failed
        "message": message,  # "🔍 이미지 분류 중..."
    }

async def publish_token_event(self, task_id, content):
    """LLM 스트리밍 토큰"""
    event_data = {
        "event_type": "token",
        "content": content,  # "페트" | "병은" | ...
    }

async def publish_tool_event(self, task_id, action, tool_name, ...):
    """Tool 실행 이벤트"""
    event_data = {
        "event_type": "tool",
        "action": action,    # start, progress, done
        "tool_name": name,   # search_centers
    }

async def publish_context_usage(self, task_id, ...):
    """컨텍스트 사용량"""
    event_data = {
        "event_type": "context_usage",
        "percentage": 45.2,
    }
```

### 5.2 scan_worker와의 인프라 공유

```
┌─────────────────────────────────────────┐
│            Redis Cluster                 │
│  ┌─────────────────────────────────┐    │
│  │  rfr-streams-redis              │    │
│  │  (Event Broadcasting)           │    │
│  │                                 │    │
│  │  scan:events:{task_id}  ───────┼───▶ SSE Gateway
│  │  chat:events:{task_id}  ───────┼───▶ SSE Gateway
│  └─────────────────────────────────┘    │
│  ┌─────────────────────────────────┐    │
│  │  rfr-cache-redis                │    │
│  │  (Checkpointing)                │    │
│  │                                 │    │
│  │  scan:context:{task_id} ────────────▶ Scan Context
│  │  chat:session:{session_id} ─────────▶ RedisSaver
│  └─────────────────────────────────┘    │
└─────────────────────────────────────────┘
```

---

## 6. Retriever: JSON 파일 기반

### 6.1 Assets 복제

```bash
# scan_worker의 assets를 chat_worker에 복제
cp -r apps/scan_worker/infrastructure/assets/data/* \
      apps/chat_worker/infrastructure/assets/data/

cp -r apps/scan_worker/infrastructure/assets/prompts/* \
      apps/chat_worker/infrastructure/assets/prompts/
```

**복제 이유:**

```
공유 (심볼릭 링크):
  ✗ 독립 배포 불가
  ✗ 버전 불일치 위험
  
복제:
  ✓ 독립 배포
  ✓ Chat 전용 프롬프트 추가 가능
  ✓ 데이터 동기화는 CI/CD에서 관리
```

### 6.2 검색 전략

```python
def search(self, category, subcategory):
    # 1. 정확히 일치
    for key, data in self._data.items():
        if category in key:
            return {"key": key, "data": data}
    
    # 2. 매핑 기반 fallback
    category_map = {
        "재활용": "재활용폐기물",
        "일반": "일반종량제폐기물",
    }
    # ...
```

---

## 7. 디렉토리 구조

> **핵심 변경**: `persistence/` → `datasources/` (네이밍 개선)

```
apps/chat/infrastructure/        # API (얇게)
├── __init__.py
└── messaging/
    ├── __init__.py
    ├── job_submitter.py         # JobSubmitterPort 구현 (Taskiq)
    └── redis_client.py          # Redis 연결

apps/chat_worker/infrastructure/ # Worker (비즈니스 로직)
├── __init__.py
├── llm/
│   ├── __init__.py
│   ├── config.py                # 공통 설정
│   ├── openai/
│   │   ├── __init__.py
│   │   ├── client.py            # LLMPort 구현
│   │   ├── token_counter.py     # TokenCounterPort 구현
│   │   └── tool_caller.py       # ToolCallerPort 구현
│   ├── anthropic/
│   │   ├── __init__.py
│   │   ├── client.py
│   │   └── tool_caller.py
│   └── gemini/
│       ├── __init__.py
│       └── client.py
├── datasources/                 # ← persistence가 아닌 datasources
│   ├── __init__.py
│   ├── event_publisher.py       # EventPublisherPort 구현
│   └── retriever.py             # RetrieverPort 구현
├── langgraph/                   # 오케스트레이션
│   ├── __init__.py
│   ├── factory.py
│   └── nodes/
│       ├── __init__.py
│       ├── intent.py
│       ├── rag.py
│       └── answer.py
└── assets/
    ├── data/
    │   ├── item_class_list.yaml
    │   └── source/
    │       ├── 재활용폐기물_*.json
    │       └── ...
    └── prompts/
        ├── system_prompt.txt
        └── intent_classifier.txt
```

**왜 `datasources`인가?**

```
persistence:
  - DB, 트랜잭션, 일관성 연상
  - CRUD 작업 암시
  
datasources:
  - 읽기 전용 데이터 소스
  - Knowledge Base, External API 포함
  - Local JSON은 "저장"이 아닌 "조회"
```

---

## 8. 다음 단계

Phase 4에서는:

1. **Presentation Layer** - FastAPI 라우터, SSE 엔드포인트
2. **LangGraph Nodes** - 의도 분류, RAG, 답변 생성 노드
3. **Graph Factory** - StateGraph 조립
4. **Taskiq Task** - `chat.process` 비동기 작업

---

**작성일**: 2026-01-13  
**Phase**: 3/6 (Infrastructure Adapters)

