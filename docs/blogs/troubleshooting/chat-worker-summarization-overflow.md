# Chat Worker Summarization Overflow 해결 리포트

## 1. 문제 발견

### 에러 로그

```
openai.BadRequestError: Error code: 400
Input tokens exceed the configured limit of 272000 tokens.
Your messages resulted in 915611 tokens.
```

`SummarizationNode`가 압축을 시도할 때, `summarize_messages()`에 전달된 `older_messages`가
모델 입력 한도(272K tokens)를 초과하여 크래시 발생.

### 기존 구조

```
User Message (Turn N)
       │
       ▼
  ┌─────────┐
  │  intent  │
  └────┬─────┘
       │
       ▼
  ┌─────────┐
  │  router  │ ← Send API (병렬 실행)
  └────┬─────┘
       │
       ├──────────────┬──────────────┬────────────┐
       ▼              ▼              ▼            ▼
 ┌──────────┐  ┌────────────┐  ┌────────┐  ┌────────┐
 │waste_rag │  │ web_search │  │location│  │ others │
 └────┬─────┘  └─────┬──────┘  └────┬───┘  └────┬───┘
      │               │              │            │
      │          결과 무제한           │            │
      │          (수백KB 가능)         │            │
      └───────────────┴──────────────┴────────────┘
                      │
                      ▼
              ┌──────────────┐
              │  aggregator   │
              └──────┬───────┘
                     │
                     ▼
         ┌───────────────────────┐
         │     summarize         │
         │                       │
         │  현재 tokens > 272K?  │
         │  → YES: 압축 시도     │
         │                       │
         │  older = msgs[:-80]   │
         │  (~900K tokens)       │
         │        ↓              │
         │  summarize_messages() │
         │  messages_text =      │
         │  전체 concat           │
         │        ↓              │
         │  llm.generate(prompt) │ ← 💥 915K > 272K limit
         └───────────────────────┘
                  ❌ 크래시
```

### 메시지 누적 메커니즘

```
┌─────────────────────────────────────────────────────────────────────────┐
│  ChatState 정의:                                                         │
│    messages: Annotated[list[AnyMessage], add_messages]                   │
│                                                                         │
│  커스텀 add_messages reducer:                                             │
│    def add_messages(existing, new):                                      │
│        return existing + new    ← 항상 append만, 삭제 불가                 │
│                                                                         │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  Turn 1:  messages = [H1, A1]                              ~2K tokens  │
│  Turn 2:  messages = [H1, A1, H2, A2]                     ~4K tokens  │
│  Turn 3:  messages = [..., H3, A3(웹검색 답변)]            ~60K tokens  │
│  Turn 4:  messages = [..., H4, A4(웹검색 답변)]           ~150K tokens  │
│  ...                                                                    │
│  Turn N:  messages = [H1, A1, ..., HN-1, AN-1, HN]      ~915K tokens  │
│                                                                         │
│  → messages는 절대 줄어들지 않음                                           │
│  → 매 턴마다 checkpoint에 전체 히스토리 저장                                │
│  → Redis 메모리 + 직렬화 비용도 무한 증가                                   │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

### SummarizationNode의 한계

블로그 글([rooftopsnow.tistory.com/200](https://rooftopsnow.tistory.com/200))의
OpenCode 기반 동적 설정은 적용되어 있으나, **요약 결과가 messages를 교체하지 않음**:

```python
# 현재 SummarizationNode 출력:
return {
    "llm_input_messages": [SystemMessage(요약), ...recent],  # ← answer 노드용 "뷰"
    "summary": new_summary,                                   # ← state에 저장
}
# "messages" 필드 미수정 → checkpoint에 전체 히스토리 그대로 유지
```

| 적용됨 (블로그 글)               | 누락됨                               |
|-------------------------------|--------------------------------------|
| 동적 트리거 (272K for GPT-5.2) | 요약 입력 크기 제한                     |
| 모델 레지스트리                  | messages 리스트 실제 삭제 (trim)        |
| PRUNE_PROTECT (40K tokens)    | RemoveMessage 패턴                    |
| 구조화 5섹션 요약                | checkpoint 크기 bounded 보장           |
| 요약 토큰 15% (60K)            |                                      |

---

## 2. 해결 방안 모색

### 방안 A: 입력 Truncation (band-aid)

`summarize_messages()`의 입력을 모델 한도 내로 잘라서 crash만 방지.

```python
# web_search 결과 제한
if len(result) > 50_000:
    result = result[:50_000]

# summarize_messages 입력 제한
if len(messages_text) > 800_000:
    messages_text = messages_text[-800_000:]  # tail 보존
```

- 장점: 변경 최소, crash 즉시 해결
- 단점: messages 무한 누적은 그대로. checkpoint/Redis 크기 증가 지속

### 방안 B: trimMessages (뷰 레벨)

LLM 호출 전에 최근 N개만 잘라서 전달 (LangGraph docs의 "Trimming" 패턴):

```python
from langchain_core.messages import trim_messages

trimmed = trim_messages(state["messages"], max_tokens=200_000, strategy="last")
response = await model.invoke(trimmed)
```

- 장점: answer 노드만 수정
- 단점: checkpoint에는 전체 히스토리 유지. Redis 메모리 계속 증가

### 방안 C: RemoveMessage (근본 해결)

LangGraph 공식 패턴으로 실제 messages를 삭제:

```python
from langchain_core.messages import RemoveMessage

return {
    "messages": [RemoveMessage(id=m.id) for m in older] + [SystemMessage(요약)],
    "summary": new_summary,
}
```

- 장점: checkpoint 자체가 bounded. Redis 메모리 안정
- 단점: reducer 교체 필요 (커스텀 → LangGraph 내장)

---

## 3. 채택안: RemoveMessage 패턴

### LangGraph 공식 레퍼런스

[LangGraph - Add Memory (Summarization)](https://docs.langchain.com/oss/javascript/langgraph/add-memory)

```typescript
// 공식 패턴: 요약 후 older messages를 RemoveMessage로 삭제
const summarizeConversation = async (state) => {
  const summary = state.summary || "";
  const summaryMsg = summary
    ? `Extend this summary: ${summary}`
    : "Create a summary:";

  const messages = [...state.messages, new HumanMessage(summaryMsg)];
  const response = await model.invoke(messages);

  return {
    summary: response.content,
    messages: state.messages.slice(0, -2)
      .map(m => new RemoveMessage({ id: m.id }))  // ← 실제 삭제
  };
};
```

핵심: 노드가 `RemoveMessage`를 반환하면, `add_messages` reducer가 해당 ID의 메시지를
기존 리스트에서 **제거**. checkpoint에도 제거된 상태로 저장됨.

---

## 4. 채택안 이유: Reducer 구조와 RemoveMessage의 필요성

### LangGraph State = Reducer 기반

LangGraph의 state 필드는 **reducer 함수**를 통해서만 업데이트됩니다.
노드가 값을 반환하면 reducer가 `기존값`과 `새값`을 병합합니다:

```
노드 반환: {"messages": [new_msg]}
                   │
                   ▼
         reducer(existing, new)
         = existing + new        ← 결과가 checkpoint에 저장
```

이 구조에서는 노드가 **직접 messages를 교체할 수 없습니다**.
항상 append만 가능하므로, messages는 단조증가합니다:

```
Turn 1 → reducer([], [H1, A1])           = [H1, A1]
Turn 2 → reducer([H1,A1], [H2, A2])      = [H1, A1, H2, A2]
Turn 3 → reducer([...], [H3, A3])        = [H1, A1, ..., H3, A3]
  ...
Turn N → reducer([...], [HN, AN])        = [전체 누적]  ← unbounded!
```

### RemoveMessage = Reducer에게 보내는 "삭제 시그널"

`RemoveMessage`는 일반 메시지가 아닌 **제어 메시지**입니다.
LangGraph 내장 `add_messages` reducer는 이를 감지하여 삭제를 수행합니다:

```
노드 반환: {"messages": [RemoveMessage(id="H1"), SystemMessage("요약")]}
                   │
                   ▼
         add_messages(existing, new):
           for msg in new:
             if isinstance(msg, RemoveMessage):
               existing.remove(id=msg.id)   ← 삭제!
             else:
               existing.append(msg)          ← 추가
```

이 메커니즘이 없으면 reducer 기반 state에서 **값을 줄이는 것이 구조적으로 불가능**합니다.

### 왜 직접 교체하면 안 되는가?

```python
# ❌ 이렇게 하면?
return {"messages": [SystemMessage("요약"), H_recent, A_recent]}

# reducer 동작:
# existing = [H1, A1, H2, A2, ..., HN]  (915K tokens)
# new = [SystemMessage, H_recent, A_recent]
# result = existing + new = [H1, ..., HN, SystemMessage, ...]  ← 더 커짐!
```

Reducer를 우회하려면 LangGraph의 state 관리 체계를 벗어나야 하며,
checkpoint 일관성이 깨집니다. `RemoveMessage`는 이 제약 내에서
유일하게 messages를 줄이는 공식 메커니즘입니다.

---

## 5. 구현 방안

### 수정 대상 파일

| # | 파일 | 변경 내용 |
|---|------|-----------|
| 1 | `state.py` | 커스텀 `add_messages` → LangGraph 내장으로 교체 |
| 2 | `summarization.py` | `RemoveMessage` 반환하도록 수정 |
| 3 | `web_search_node.py` | 결과 크기 제한 유지 (방어적) |
| 4 | `summarization.py` | 입력 truncation 유지 (방어적) |

### Step 1: Reducer 교체 (state.py)

```python
# Before (커스텀 — RemoveMessage 미지원):
def add_messages(
    existing: list[AnyMessage] | None,
    new: list[AnyMessage] | AnyMessage,
) -> list[AnyMessage]:
    if existing is None:
        existing = []
    if isinstance(new, list):
        return existing + new
    return existing + [new]

# After (LangGraph 내장 — RemoveMessage 지원):
from langgraph.graph.message import add_messages
```

LangGraph 내장 `add_messages`는:
- `RemoveMessage` 감지하여 ID 기반 삭제
- 동일 ID 메시지 업데이트 (upsert)
- 기본 append 동작 유지

### Step 2: SummarizationNode 출력 변경 (summarization.py)

```python
# Before:
return {
    "llm_input_messages": summarized_messages,  # ← 임시 뷰 (state에 무의미)
    "summary": new_summary,
}

# After:
from langchain_core.messages import RemoveMessage

# older_messages를 삭제하고 요약 SystemMessage로 대체
delete_msgs = [RemoveMessage(id=m.id) for m in older_messages if hasattr(m, 'id')]
summary_msg = SystemMessage(content=f"[이전 대화 요약]\n{new_summary}")

return {
    "messages": delete_msgs + [summary_msg],  # ← reducer가 실제 삭제+추가 수행
    "summary": new_summary,
}
```

### Step 3: Answer 노드 수정 (answer_node.py)

`llm_input_messages` 의존 제거. `messages`를 직접 사용:

```python
# Before:
messages = state.get("llm_input_messages", state.get("messages", []))

# After:
messages = state.get("messages", [])
# → summarize 노드에서 이미 messages가 trim되어 있음
```

### 수정 후 구조

```
Turn N: messages = [H1, A1, ..., HN-1, AN-1, HN]   ~300K tokens
         │
         ▼
   ┌─────────────────────────────────────────────────────────┐
   │  SummarizationNode                                      │
   │                                                         │
   │  current_tokens = 300K > 272K → 트리거!                  │
   │                                                         │
   │  recent  = messages[-80:]           ~40K tokens         │
   │  older   = messages[:-80]           ~260K tokens        │
   │                                                         │
   │  ┌─────────────────────────────────────────────┐        │
   │  │ summarize_messages(older)                    │        │
   │  │   messages_text = concat (max 800K chars)   │        │
   │  │   → llm.generate(prompt)                    │        │
   │  │   → "구조화된 5섹션 요약" (≤ 60K tokens)      │        │
   │  └─────────────────────────────────────────────┘        │
   │                                                         │
   │  Return: {                                              │
   │    "messages": [                                        │
   │       RemoveMessage(H1.id),  ← older 삭제               │
   │       RemoveMessage(A1.id),                             │
   │       ...                                               │
   │       SystemMessage("요약"),  ← 요약으로 대체             │
   │    ],                                                   │
   │    "summary": new_summary,                              │
   │  }                                                      │
   └────────────────────┬────────────────────────────────────┘
                        │
                        ▼ add_messages reducer 처리
   ┌─────────────────────────────────────────────────────────┐
   │  messages = [SystemMessage("요약"), ...recent_80개]       │
   │             ~100K tokens (bounded!)                      │
   └────────────────────┬────────────────────────────────────┘
                        │
                        ▼
                ┌──────────────┐
                │    answer     │ ← messages에서 직접 읽음
                │              │
                │  messages += │
                │  [AIMessage] │
                └──────┬───────┘
                       │
                       ▼
                checkpoint 저장: messages ≈ ~100K tokens (bounded!)
```

### 크기 비교

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    Before vs After                                       │
├────────────────────┬─────────────────────┬──────────────────────────────┤
│                    │ Before              │ After                         │
├────────────────────┼─────────────────────┼──────────────────────────────┤
│ messages 크기       │ 무한 누적            │ ~100K tokens (bounded)        │
│ checkpoint 크기     │ 무한 증가            │ 안정적                         │
│ Redis 메모리        │ 세션당 수MB 가능      │ 세션당 ~400KB 이하             │
│ 요약 trigger 후     │ messages 그대로      │ older 삭제 + 요약 교체         │
│ 다음 Turn           │ 이전 전체 + 새 메시지 │ 요약 + recent + 새 메시지      │
│ 장기 대화 안정성     │ ❌ 언젠간 crash       │ ✅ 항상 bounded                │
└────────────────────┴─────────────────────┴──────────────────────────────┘
```

### 방어적 truncation 유지

`RemoveMessage` 적용 후에도, 첫 trigger 전 messages가 272K를 넘는 edge case
(예: 단일 턴에서 거대한 웹검색 결과)를 대비하여 기존 truncation fix도 유지:

```python
# web_search_node.py — 결과 50K chars 제한
if len(result) > max_result_chars:
    result = result[:max_result_chars]

# summarization.py — 요약 입력 800K chars 제한
if len(messages_text) > max_input_chars:
    messages_text = messages_text[-max_input_chars:]
```

이 두 단계 방어로 crash는 방지하되, `RemoveMessage`로 근본적 크기 제어를 달성합니다.

---

## 참조

- [LangGraph - Add Memory (Summarization, Trimming, Deletion)](https://docs.langchain.com/oss/javascript/langgraph/add-memory)
- [OpenCode 동적 컨텍스트 압축 전략](https://rooftopsnow.tistory.com/200)
- [LangGraph How-to: Manage Message History](https://langchain-ai.github.io/langgraph/how-tos/manage-conversation-history/)
- Error: `openai.BadRequestError: 915611 tokens > 272000 limit`
- Branch: `fix/web-search-result-truncation`
- PR: TBD (방어적 truncation은 커밋 완료, RemoveMessage는 별도 작업)
