# Multi-Turn 현재 아키텍처 상세 분석

> Date: 2026-01-25
> Scope: 멀티턴 대화의 전체 데이터 흐름 (입력 → 저장 → 로딩 → LLM 전달)

---

## 전체 흐름 요약

```
User Message
    │
    ▼
ProcessChatCommand.execute()
    │  initial_state["messages"] = [HumanMessage(content=msg)]
    │  config["configurable"]["thread_id"] = session_id
    │
    ▼
LangGraph astream() / ainvoke()
    │  ┌─── Checkpoint Load (thread_id) ───┐
    │  │  ReadThroughCheckpointer            │
    │  │    Redis hit → 즉시 반환            │
    │  │    Redis miss → PG read → promote  │
    │  └───────────────────────────────────┘
    │  add_messages reducer: 기존 messages + new HumanMessage
    │
    ├──▶ intent_node
    │      messages[-6:] → dict list → text flatten
    │      "사용자: {content[:100]}\n어시스턴트: {content[:100]}"
    │
    ├──▶ [subagent nodes: waste_rag, location, weather, ...]
    │      (conversation_history 미사용)
    │
    └──▶ answer_node
           messages[-10:] → dict list
           AnswerContext.to_prompt_context()
             "## Recent Conversation\n- User: ...\n- Assistant: ..."
           PromptBuilder → system_prompt + user_prompt
           LangChain: [SystemMessage, HumanMessage(with flattened history)]
           LLM API 호출
           return {"messages": [AIMessage(content=answer)]}
               │
               ▼
         Checkpoint Save (add_messages reducer)
           SyncableRedisSaver → Redis + sync queue
           checkpoint_syncer → PostgreSQL
```

---

## 계층별 상세

### 1. Entry Point — `process_chat.py:270-299`

```python
initial_state = {
    "messages": [HumanMessage(content=request.message)],  # 현재 턴만
    ...
}
config = {"configurable": {"thread_id": request.session_id}}
```

- `session_id`가 LangGraph의 `thread_id`로 매핑
- 현재 턴의 메시지만 initial state에 포함
- 이전 메시지는 checkpoint에서 자동 로딩 (add_messages reducer)

### 2. Checkpoint Loading — `read_through_checkpointer.py`

| 경로 | 조건 | Latency |
|------|------|---------|
| Redis hit | TTL 24h 이내 | ~1ms |
| PG fallback | Redis miss (TTL 만료) | ~10-50ms |
| Cold miss | Redis + PG 모두 없음 | ~10-50ms |

로딩된 checkpoint의 `messages` 필드 + initial state의 `HumanMessage`가 `add_messages` reducer로 병합.

### 3. Intent Node — `intent_node.py:93-111`

```python
messages = state.get("messages", [])
for msg in messages[-6:]:  # 최근 6개 = 3턴
    role = "user" if msg.type == "human" else "assistant"
    content = msg.content if isinstance(msg.content, str) else str(msg.content)
    conversation_history.append({"role": role, "content": content})
```

Intent Classifier Service (`intent_classifier_service.py:254-278`)에서 최종 포맷:

```python
recent_history = conversation_history[-3:]  # 3개만
for turn in recent_history:
    content = turn.get("content", "")[:100]  # 100자 제한
    history_lines.append(f"사용자: {content}")
```

**결과**: `[최근 대화]\n사용자: ...\n어시스턴트: ...` 형태의 **단일 텍스트**로 프롬프트에 주입.

### 4. Answer Node — `answer_node.py:116-211`

**Step 1**: Messages 추출

```python
messages = state.get("messages", [])
recent_messages = messages[-10:] if len(messages) > 10 else messages
conversation_history = [
    {"role": getattr(msg, "type", "user"), "content": getattr(msg, "content", str(msg))}
    for msg in recent_messages
]
```

**Step 2**: AnswerContext 포맷 (`answer_context.py:48-60`)

```python
# conversation_summary (압축 요약)
parts.append(f"## Previous Conversation Summary\n{self.conversation_summary}")

# conversation_history (최근 대화)
for msg in self.conversation_history:
    role_label = "User" if role == "user" else "Assistant"
    history_lines.append(f"- {role_label}: {content}")
parts.append("## Recent Conversation\n" + "\n".join(history_lines))
```

**Step 3**: LLM 호출 (`answer_node.py:160-178`)

```python
# LangChain 방식
langchain_messages = []
if prepared.system_prompt:
    langchain_messages.append(SystemMessage(content=prepared.system_prompt))
langchain_messages.append(HumanMessage(content=prepared.prompt))
#                                        ▲
#                            여기에 flattened history 포함

async for chunk in langchain_llm.astream(langchain_messages):
    ...
```

**Step 4**: 결과 저장

```python
return {"answer": answer, "messages": [AIMessage(content=answer)]}
```

### 5. LLM 클라이언트 — `openai_client.py` / `gemini_client.py`

**OpenAI** (`openai_client.py:75-106`):
```python
messages = []
if system_prompt:
    messages.append({"role": "system", "content": system_prompt})
messages.append({"role": "user", "content": user_content})
# user_content에 이미 flatten된 history 포함
response = await self._client.chat.completions.create(messages=messages)
```

**Gemini** (`gemini_client.py:60-89`):
```python
full_prompt = f"{system_prompt}\n\n## Context\n{context_str}\n\n## Question\n{prompt}"
# 전부 단일 문자열
response = await self._client.aio.models.generate_content(contents=full_prompt)
```

### 6. Checkpoint 저장 — `SyncableRedisSaver`

```
answer_node return → add_messages reducer (AIMessage 추가)
    → LangGraph checkpoint save
    → SyncableRedisSaver.aput()
        → Redis HSET (checkpoint data)
        → Redis LPUSH (sync queue)
    → [별도 프로세스] checkpoint_syncer
        → BRPOP sync queue
        → AsyncPostgresSaver.aput() → PostgreSQL
```

---

## 리소스 사용 현황

| 리소스 | 용도 | 비용 요인 |
|--------|------|-----------|
| **Redis** | Checkpoint hot storage | 메모리 (messages 전체 직렬화) |
| **PostgreSQL** | Checkpoint cold storage | 디스크 + 커넥션 풀 |
| **Sync Queue** | Redis → PG 비동기 동기화 | 별도 프로세스 (CPU/네트워크) |
| **LLM 토큰** | History를 텍스트로 flatten | 불필요한 role label 오버헤드 |

### 토큰 낭비 분석

한 턴의 대화 (user: 50자, assistant: 200자)가 10턴 누적 시:

| 방식 | 토큰 추정 | 비고 |
|------|-----------|------|
| **현재 (text flatten)** | ~1,800 | `- User: ...` 마크다운 오버헤드 |
| **Native messages array** | ~1,300 | role 메타데이터는 API 레벨 처리 |
| **차이** | ~500 (~28%) | 매 호출마다 낭비 |

---

## 문제점 정리

### P1. Conversation History가 단일 User Message에 Flatten

```
LLM이 보는 것:
  messages: [
    {"role": "system", "content": "...system prompt..."},
    {"role": "user", "content": "## Recent Conversation\n- User: 종이 버려?\n- Assistant: 종이는...\n\n## User Question\n그럼 플라스틱은?"}
  ]

LLM이 봐야 하는 것 (native):
  messages: [
    {"role": "system", "content": "...system prompt..."},
    {"role": "user", "content": "종이 어떻게 버려?"},
    {"role": "assistant", "content": "종이는..."},
    {"role": "user", "content": "그럼 플라스틱은?"}
  ]
```

**영향**:
- 모델이 대화 구조를 인식 못함
- Coreference resolution 저하 ("그럼", "그것" 등 대명사 참조 부정확)
- In-context learning 효율 저하

### P2. History 추출 불일치

| 노드 | 메시지 수 | Content 제한 | 용도 |
|------|-----------|-------------|------|
| intent_node | 6 (3턴) | 100자 | 의도 분류 |
| answer_node | 10 (5턴) | 없음 | 답변 생성 |

Intent는 truncated history로 판단하지만, Answer는 full history로 생성 → 의도 판단과 답변이 다른 컨텍스트 기반.

### P3. 이중 저장 구조

- `state.messages`: LangChain AnyMessage 리스트 (checkpoint에 직렬화)
- `AnswerContext.conversation_history`: dict 리스트 (prompt에 텍스트로 주입)
- `state.summary`: 압축 요약 (SummarizationNode 생성)

동일한 데이터가 3가지 형태로 존재 → 동기화 이슈 가능.

### P4. Summarization과의 상호작용

SummarizationNode가 `RemoveMessage`로 older messages를 삭제하면:
- `state.messages`에는 요약 SystemMessage + recent messages만 남음
- 하지만 answer_node는 `messages[-10:]`에서 요약 SystemMessage도 포함하여 추출
- 요약 메시지의 role이 `system` → conversation_history에 `{"role": "system", "content": "[이전 대화 요약]..."}`으로 들어감
- AnswerContext에서 role_label이 "Assistant"로 매핑됨 (user가 아닌 모든 것)

---

## 파일 참조

| 파일 | 라인 | 역할 |
|------|------|------|
| `application/commands/process_chat.py` | 270-299 | Entry point, initial state 구성 |
| `infrastructure/orchestration/langgraph/state.py` | 295 | `messages: Annotated[list[AnyMessage], add_messages]` |
| `infrastructure/orchestration/langgraph/nodes/intent_node.py` | 93-111 | Messages → intent history 추출 |
| `application/services/intent_classifier_service.py` | 254-278 | History text formatting (100자 제한) |
| `infrastructure/orchestration/langgraph/nodes/answer_node.py` | 116-211 | Messages → AnswerContext → LLM 호출 |
| `application/dto/answer_context.py` | 43-60 | History → markdown text flatten |
| `application/commands/generate_answer_command.py` | 161 | AnswerContext에 history 주입 |
| `infrastructure/llm/clients/langchain_adapter.py` | 94-112 | `_build_messages()` - 최종 LLM 메시지 구성 |
| `infrastructure/llm/clients/openai_client.py` | 75-106 | OpenAI API 호출 (single user msg) |
| `infrastructure/llm/clients/gemini_client.py` | 60-89 | Gemini API 호출 (single string) |
| `infrastructure/orchestration/langgraph/summarization.py` | 525-599 | RemoveMessage + 요약 생성 |
| `infrastructure/orchestration/langgraph/sync/read_through_checkpointer.py` | 60-117 | Redis → PG read-through |
| `infrastructure/orchestration/langgraph/checkpointer.py` | 39-184 | Checkpointer factory |
