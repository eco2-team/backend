# 이코에코(Eco²) Agent #16: 컨텍스트 압축 (LangGraph 1.0.6)

> LangGraph 1.0+ Message History Management & SummarizationNode 패턴

| 항목 | 값 |
|-----|-----|
| **작성일** | 2026-01-16 |
| **버전** | v1.0 |
| **시리즈** | Eco² Agent 시리즈 |
| **이전 포스팅** | [#15 Eval Agent 고도화](./29-chat-eval-agent-enhancement.md) |
| **참조** | LangGraph How-to: Manage Message History, langmem |

---

## 1. 배경: 멀티턴 대화의 토큰 한계

### 1.1 문제 상황

```
[Turn 1] 사용자: 페트병 어떻게 버려?
         AI: 페트병은 내용물을 비우고...

[Turn 2] 사용자: 라벨은요?
         AI: 라벨은 분리해서...

[Turn 3] 사용자: 뚜껑은 어떻게?
         AI: 뚜껑은...

...

[Turn 20] 컨텍스트 초과! 🔥
```

| 문제 | 설명 |
|------|------|
| **토큰 폭발** | 멀티턴 대화에서 메시지 누적 → LLM 입력 한계 초과 |
| **비용 증가** | 매 턴마다 전체 히스토리 전송 → 토큰 비용 급증 |
| **응답 지연** | 긴 컨텍스트 → 응답 생성 시간 증가 |
| **컨텍스트 손실** | 단순 truncation → 중요 정보 유실 |

### 1.2 LangGraph 1.0+ 솔루션

```
┌─────────────────────────────────────────────────────────────────┐
│                    Context Compression Strategy                   │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  [messages] ──▶ token_count > threshold? ──▶ [summarize]        │
│                      │ no                        │               │
│                      ▼                           ▼               │
│              [pass-through]            [summary + recent_msgs]   │
│                      │                           │               │
│                      └───────────────────────────┘               │
│                                  │                               │
│                                  ▼                               │
│                             [LLM input]                          │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## 2. 아키텍처 설계

### 2.1 개선된 파이프라인

```
START → intent → [vision?] → router
                              │
                   ┌──────────┼──────────┬───────────┬───────────┐
                   ▼          ▼          ▼           ▼           ▼
                waste    character   location   web_search   general
                (RAG)    (gRPC)      (gRPC)    (DuckDuckGo)  (passthrough)
                   │          │          │           │           │
                   ▼          │          │           │           │
              [feedback]      │          │           │           │
                   │          │          │           │           │
                   └──────────┴──────────┴───────────┴───────────┘
                                         │
                                         ▼
                                   [summarize?] ← NEW: Context Compression
                                         │
                                         ▼
                                      answer → END
```

### 2.2 ChatState TypedDict

```python
# infrastructure/orchestration/langgraph/state.py

class ChatState(TypedDict, total=False):
    """Chat 파이프라인 상태 - LangGraph 1.0+ 컨텍스트 압축 지원."""

    # 대화 히스토리 (Reducer로 누적)
    messages: Annotated[list[AnyMessage], add_messages]

    # 컨텍스트 압축
    summary: str  # 이전 대화 요약
    context: dict[str, Any]  # LLM 입력용 컨텍스트

    # 현재 턴 입력
    query: str
    image_url: str | None

    # 파이프라인 중간 결과
    intent: str
    evidence: list[dict[str, Any]]
    character: dict[str, Any] | None
    location: dict[str, Any] | None
    web_results: list[dict[str, Any]]
    classification_result: str | None

    # 품질 평가
    feedback: dict[str, Any]
    fallback_reason: str | None

    # 최종 출력
    answer: str

    # 메타데이터
    job_id: str
    user_id: str
    thread_id: str
```

### 2.3 메시지 Reducer

```python
def add_messages(
    existing: list[AnyMessage] | None,
    new: list[AnyMessage] | AnyMessage,
) -> list[AnyMessage]:
    """메시지 리스트 병합 Reducer.

    LangGraph 1.0+ Annotated 패턴 사용.
    매 턴마다 메시지가 자동으로 누적됨.
    """
    if existing is None:
        existing = []

    if isinstance(new, list):
        return existing + new
    return existing + [new]
```

---

## 3. SummarizationNode 구현

### 3.1 토큰 카운팅

```python
# infrastructure/orchestration/langgraph/summarization.py

DEFAULT_MAX_TOKENS_BEFORE_SUMMARY = 3072  # 요약 트리거 임계값
DEFAULT_MAX_SUMMARY_TOKENS = 512  # 요약 최대 토큰
DEFAULT_KEEP_RECENT_MESSAGES = 4  # 최근 N개 메시지 유지


def count_tokens_approximately(messages: list["AnyMessage"]) -> int:
    """대략적인 토큰 수 계산.

    정확한 계산은 tiktoken 필요.
    여기서는 문자 수 기반 근사치 사용 (~4자 = 1토큰).
    """
    total_chars = 0
    for msg in messages:
        if hasattr(msg, "content"):
            content = msg.content
            if isinstance(content, str):
                total_chars += len(content)
            elif isinstance(content, list):
                for item in content:
                    if isinstance(item, dict) and "text" in item:
                        total_chars += len(item["text"])
    return total_chars // 4
```

### 3.2 요약 프롬프트 (PromptLoaderPort 활용)

```
# infrastructure/assets/prompts/summarization/context_compress.txt

다음 대화 내용을 간결하게 요약해주세요.
핵심 정보와 맥락만 유지하고, {max_summary_tokens} 토큰 이내로 작성하세요.

{existing_summary_section}새로운 대화:
{messages_text}

요약:
```

### 3.3 summarize_messages 함수

```python
async def summarize_messages(
    messages: list["AnyMessage"],
    llm: "LLMClientPort",
    existing_summary: str | None = None,
    max_summary_tokens: int = DEFAULT_MAX_SUMMARY_TOKENS,
    prompt_loader: "PromptLoaderPort | None" = None,
) -> str:
    """메시지 히스토리 요약.

    Clean Architecture 준수:
    - LLMClientPort: Application Layer Port
    - PromptLoaderPort: Application Layer Port
    """
    if not messages:
        return existing_summary or ""

    # 프롬프트 로드 (PromptLoader 또는 기본값)
    if prompt_loader is not None:
        template = prompt_loader.load_or_default(
            category="summarization",
            name="context_compress",
            default=DEFAULT_SUMMARIZATION_PROMPT,
        )
    else:
        template = DEFAULT_SUMMARIZATION_PROMPT

    # 메시지 텍스트 구성
    messages_text = "\n".join(
        f"{msg.__class__.__name__}: {msg.content}"
        for msg in messages
        if hasattr(msg, "content")
    )

    # 프롬프트 포맷팅
    existing_summary_section = (
        f"이전 요약:\n{existing_summary}\n\n" if existing_summary else ""
    )
    summary_prompt = template.format(
        max_summary_tokens=max_summary_tokens,
        existing_summary_section=existing_summary_section,
        messages_text=messages_text,
    )

    try:
        summary = await llm.generate(summary_prompt)
        logger.info(
            "conversation_summarized",
            extra={
                "input_messages": len(messages),
                "summary_length": len(summary),
            },
        )
        return summary
    except (ValueError, RuntimeError) as e:
        logger.error(
            "summarization_failed",
            extra={"error": str(e), "error_type": type(e).__name__},
        )
        return existing_summary or ""
```

### 3.4 SummarizationNode 클래스

```python
class SummarizationNode:
    """LangGraph 노드용 요약 클래스.

    langmem의 SummarizationNode와 유사한 인터페이스.
    독립 노드로 사용하거나 pre_model_hook으로 사용 가능.
    """

    def __init__(
        self,
        llm: "LLMClientPort",
        token_counter: Callable[[list["AnyMessage"]], int] = count_tokens_approximately,
        max_tokens_before_summary: int = DEFAULT_MAX_TOKENS_BEFORE_SUMMARY,
        max_summary_tokens: int = DEFAULT_MAX_SUMMARY_TOKENS,
        keep_recent_messages: int = DEFAULT_KEEP_RECENT_MESSAGES,
        prompt_loader: "PromptLoaderPort | None" = None,
    ):
        self.llm = llm
        self.token_counter = token_counter
        self.max_tokens_before_summary = max_tokens_before_summary
        self.max_summary_tokens = max_summary_tokens
        self.keep_recent_messages = keep_recent_messages
        self.prompt_loader = prompt_loader

        self._hook = create_summarization_hook(
            llm=llm,
            token_counter=token_counter,
            max_tokens_before_summary=max_tokens_before_summary,
            max_summary_tokens=max_summary_tokens,
            keep_recent_messages=keep_recent_messages,
            prompt_loader=prompt_loader,
        )

    async def __call__(self, state: dict[str, Any]) -> dict[str, Any]:
        """노드 또는 hook으로 호출."""
        return await self._hook(state)
```

---

## 4. Factory 통합

### 4.1 create_chat_graph 파라미터

```python
def create_chat_graph(
    llm: "LLMClientPort",
    retriever: "RetrieverPort",
    event_publisher: "ProgressNotifierPort",
    prompt_loader: "PromptLoaderPort",
    # ... 기존 파라미터 ...
    enable_summarization: bool = False,  # LangGraph 1.0+ 컨텍스트 압축
    max_tokens_before_summary: int = 3072,  # 요약 트리거 임계값
) -> StateGraph:
```

### 4.2 노드 등록 및 엣지 연결

```python
# 컨텍스트 압축 노드 (선택)
if enable_summarization:
    summarization_node = SummarizationNode(
        llm=llm,
        max_tokens_before_summary=max_tokens_before_summary,
        prompt_loader=prompt_loader,
    )
    logger.info(
        "Summarization enabled (threshold=%d tokens)",
        max_tokens_before_summary,
    )
else:
    summarization_node = None

# ...

# Summarization 노드 등록 (선택)
if summarization_node is not None:
    graph.add_node("summarize", summarization_node)
    logger.info("Summarization node registered")

# 최종 목적지 결정
final_target = "summarize" if summarization_node is not None else "answer"

# 엣지 연결
for node_name in ["character", "location", "web_search", "general"]:
    graph.add_edge(node_name, final_target)

if summarization_node is not None:
    graph.add_edge("summarize", "answer")

graph.add_edge("answer", END)
```

---

## 5. 압축 알고리즘

### 5.1 압축 흐름

```
┌─────────────────────────────────────────────────────────────────┐
│                    Context Compression Flow                       │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  [messages: 20개, ~5000 tokens]                                  │
│              │                                                   │
│              ▼                                                   │
│  ┌─────────────────────────────────────────────────────┐        │
│  │  token_count(messages) > threshold (3072)?          │        │
│  │              │ YES                                   │        │
│  └──────────────┼───────────────────────────────────────┘        │
│                 ▼                                                │
│  ┌─────────────────────────────────────────────────────┐        │
│  │  Split messages                                      │        │
│  │  ├── recent_messages: messages[-4:]  (최근 4개)     │        │
│  │  └── older_messages: messages[:-4]   (나머지 16개)  │        │
│  └─────────────────────────────────────────────────────┘        │
│                 │                                                │
│                 ▼                                                │
│  ┌─────────────────────────────────────────────────────┐        │
│  │  LLM.generate(summarize_prompt)                      │        │
│  │  └── older_messages → summary (~512 tokens)          │        │
│  └─────────────────────────────────────────────────────┘        │
│                 │                                                │
│                 ▼                                                │
│  ┌─────────────────────────────────────────────────────┐        │
│  │  Result: [SystemMessage(summary)] + recent_messages  │        │
│  │  └── ~1500 tokens (70% 압축)                         │        │
│  └─────────────────────────────────────────────────────┘        │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### 5.2 요약 형식

```python
# 요약을 SystemMessage로 변환
summarized_messages = []
if new_summary:
    summarized_messages.append(
        SystemMessage(content=f"[이전 대화 요약]\n{new_summary}")
    )
summarized_messages.extend(recent_messages)
```

### 5.3 로깅 (Observability)

```python
logger.info(
    "context_compressed",
    extra={
        "original_tokens": current_tokens,
        "compressed_tokens": compressed_tokens,
        "compression_ratio": f"{(1 - compressed_tokens / current_tokens) * 100:.1f}%",
    },
)
```

---

## 6. 사용 예시

### 6.1 Factory 호출

```python
# setup/dependencies.py

def get_chat_graph() -> StateGraph:
    return create_chat_graph(
        llm=get_llm_client(),
        retriever=get_retriever(),
        event_publisher=get_progress_notifier(),
        prompt_loader=get_prompt_loader(),
        checkpointer=get_postgres_checkpointer(),  # 멀티턴 필수
        enable_summarization=True,  # 컨텍스트 압축 활성화
        max_tokens_before_summary=3072,
    )
```

### 6.2 체크포인터와 조합

```python
# 멀티턴 대화에서 체크포인터 + 압축 조합
graph = create_chat_graph(
    llm=llm,
    retriever=retriever,
    event_publisher=event_publisher,
    prompt_loader=prompt_loader,
    checkpointer=create_postgres_checkpointer(conn_string),  # 세션 유지
    enable_summarization=True,  # 토큰 최적화
    max_tokens_before_summary=3072,
)

# thread_id로 세션 유지
config = {"configurable": {"thread_id": user_session_id}}
result = await graph.ainvoke(state, config=config)
```

---

## 7. Clean Architecture 준수

### 7.1 의존성 방향

```
┌─────────────────────────────────────────────────────────────────┐
│                    Dependency Direction                          │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│   Application Layer                                              │
│   ├── ports/llm/llm_client.py      → LLMClientPort (ABC)        │
│   └── ports/prompt_loader.py       → PromptLoaderPort (ABC)     │
│                                                                  │
│                           ▲                                      │
│                           │ implements                           │
│                           │                                      │
│   Infrastructure Layer                                           │
│   ├── orchestration/langgraph/summarization.py                  │
│   │   └── SummarizationNode (uses Ports)                        │
│   └── assets/prompt_loader.py                                   │
│       └── FilePromptLoader (implements PromptLoaderPort)        │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### 7.2 Port 사용 패턴

| Component | Port | Adapter |
|-----------|------|---------|
| LLM 호출 | `LLMClientPort` | `GeminiClient`, `OpenAIClient` |
| 프롬프트 로딩 | `PromptLoaderPort` | `FilePromptLoader` |
| 토큰 카운팅 | 함수 파라미터 (DI) | `count_tokens_approximately` |

---

## 8. 변경 파일 목록

| 파일 | 변경 내용 |
|------|----------|
| `infrastructure/orchestration/langgraph/state.py` | ChatState TypedDict, add_messages Reducer |
| `infrastructure/orchestration/langgraph/summarization.py` | SummarizationNode, create_summarization_hook |
| `infrastructure/orchestration/langgraph/factory.py` | enable_summarization 파라미터, 노드 통합 |
| `infrastructure/orchestration/langgraph/__init__.py` | docstring 업데이트 |
| `infrastructure/assets/prompts/summarization/context_compress.txt` | 요약 프롬프트 |
| `requirements.txt` | langgraph>=1.0.6, langgraph-checkpoint-redis |

---

## 9. 참고 문헌

### LangGraph 공식 문서
- [How to manage conversation history](https://langchain-ai.github.io/langgraph/how-tos/memory/manage-conversation-history/) (2025)
- [LangGraph Message History](https://langchain-ai.github.io/langgraph/concepts/memory/#message-history)
- [Checkpointers](https://langchain-ai.github.io/langgraph/concepts/persistence/)

### 관련 라이브러리
- [langmem: SummarizationNode](https://github.com/langchain-ai/langmem)
- [LangGraph Checkpoint Postgres](https://github.com/langchain-ai/langgraph-checkpoint-postgres)

### Anthropic 기술 문서
- [Effective context engineering for AI agents](https://www.anthropic.com/engineering/effective-context-engineering) (2025)

---

*문서 버전: v1.0*
*최종 수정: 2026-01-16*
