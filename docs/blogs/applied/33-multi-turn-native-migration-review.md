# Multi-Turn Native Migration 검토

> Status: **검토 완료 / 구현 대기**
> Date: 2026-01-25

## 배경

현재 멀티턴 대화를 자체 리소스(Redis + PostgreSQL checkpoint)로 관리 중.
LLM 네이티브 멀티턴 API로 마이그레이션 가능 여부 검토.

## 참조 API

- [OpenAI Agents SDK - AgentHookContext.turn_input](https://openai.github.io/openai-agents-python/ref/run_context/#agents.run_context.AgentHookContext.turn_input)
- [Google Gemini - Text Generation (Multi-turn)](https://ai.google.dev/gemini-api/docs/text-generation?hl=ko)

## 현재 아키텍처

| 계층 | 구현 | 리소스 비용 |
|------|------|------------|
| Persistence | Redis (hot, TTL 24h) + PostgreSQL (cold) | Redis 메모리, PG 커넥션 풀 |
| Sync | `SyncableRedisSaver` → BRPOP 비동기 큐 → PG | 별도 syncer 프로세스 |
| Read-Through | Redis miss → PG read → Redis promote | LRU 캐시 로직 |
| History 주입 | `answer_node.py`에서 recent 10 msgs → markdown flatten → 단일 user prompt | 토큰 낭비 (role 구분 상실) |

### 핵심 문제

LLM에 히스토리를 markdown 텍스트로 flatten해서 전달 → 모델이 대화 구조를 인식하지 못함.

```python
# answer_context.py (line 47-60)
parts.append("## Recent Conversation\n" + "\n".join(
    f"- {role_label}: {content}" for msg in history
))
# → 전부 하나의 user 메시지 안에 들어감
```

## 네이티브 API 비교

### OpenAI Chat Completions

```python
# 네이티브: messages array로 role 분리
response = client.chat.completions.create(
    messages=[
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": "종이 어떻게 버려?"},
        {"role": "assistant", "content": "종이는..."},
        {"role": "user", "content": "그럼 플라스틱은?"},
    ]
)
```

### Gemini chats.create()

```python
chat = client.chats.create(
    model="gemini-3-flash-preview",
    history=[...prior messages...]
)
response = chat.send_message("그럼 플라스틱은?")
```

### OpenAI Agents SDK turn_input

- `AgentHookContext.turn_input`: per-turn 입력 아이템 리스트
- Runner가 멀티턴 루프 관리 (tool call → response 순환)
- 우리 구조에서는 LangGraph가 orchestration 담당 → 불필요

## 마이그레이션 판단

### 가능 (LLM 호출 계층)

| 항목 | 현재 | 네이티브 전환 | 효과 |
|------|------|--------------|------|
| History 포맷 | markdown flatten → 1 user msg | messages array (role 분리) | 모델 이해도 향상, 토큰 절약 |
| OpenAI client | `generate(prompt: str)` | `generate(messages: list[dict])` | 직접 적용 가능 |
| Gemini client | `generate_content(prompt)` | `contents` list with role parts | 직접 적용 가능 |

### 불가 (Persistence 계층)

| 항목 | 이유 |
|------|------|
| Redis/PG 체크포인터 | 네이티브 API는 in-memory/per-session — 프로세스 재시작 시 유실 |
| Cross-request 연속성 | 사용자가 수 시간 후 복귀 시 SDK 세션 종료됨 |
| Non-message state | intent, context channels, summary 등 메시지 외 상태 보존 필요 |
| Summarization | RemoveMessage + summary 교체는 LangGraph state에서만 가능 |
| 멀티 워커 | Stateless 워커 — 세션 상태를 외부 저장소에 의존 |

## 권장안

1. LLM 클라이언트의 `generate()` 인터페이스를 `messages: list[dict]` 기반으로 확장
2. `answer_node`에서 히스토리를 markdown이 아닌 native messages array로 전달
3. Redis/PG 체크포인터는 그대로 유지

## 변경 대상 파일

- `apps/chat_worker/infrastructure/llm/clients/openai_client.py`
- `apps/chat_worker/infrastructure/llm/clients/gemini_client.py`
- `apps/chat_worker/infrastructure/orchestration/langgraph/nodes/answer_node.py`
- `apps/chat_worker/application/dto/answer_context.py`

## 기대 효과

- 토큰 효율: role-separated messages는 동일 내용 대비 ~20-30% 토큰 절약
- 대화 이해도: 모델이 user/assistant 턴을 구조적으로 인식
- Coreference resolution 정확도 향상 (대명사 참조 등)
