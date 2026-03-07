# Token Streaming 버그 수정 리포트

**날짜**: 2026-01-19
**작성자**: Claude Opus 4.5
**PR**: #448 (fix/token-duplication → develop)

---

## 1. 문제 요약

### 1.1 토큰 중복 (Token Duplication)
- **증상**: 웹 검색 사용 시 토큰이 두 번 발행됨
- **예시**: "요요즘즘 맛맛집집..." (정상: "요즘 맛집...")
- **영향**: 클라이언트 UI에서 중복 텍스트 표시

### 1.2 Intent 토큰 누출 (Intent Token Leak)
- **증상**: Intent 분류 결과("general")가 토큰 스트림 첫 번째에 노출
- **예시**:
  ```
  event: token
  data: {"content": "general", "node": "intent", "seq": 1001}
  ```
- **영향**: 클라이언트에서 "general요즘 맛집..." 형태로 표시

---

## 2. 근본 원인 분석

### 2.1 토큰 중복 원인
```
┌─────────────────────┐
│   answer_node.py    │ ─── notify_token_v2() ───┐
└─────────────────────┘                          │
         │                                        ▼
    LangGraph                              Redis Streams
    astream()                                    │
         │                                        │
         ▼                                        │
┌─────────────────────┐                          │
│ ProcessChatCommand  │ ─── notify_token_v2() ───┤  (중복!)
│ _handle_message_    │                          │
│       chunk()       │                          ▼
└─────────────────────┘                    SSE Gateway
```

**문제**:
- `answer_node.py`가 직접 `notify_token_v2()`로 토큰 발행
- `ProcessChatCommand`도 LangGraph `stream_mode="messages"`로 캡처된 토큰을 발행
- 결과: 동일 토큰이 두 번 발행됨

### 2.2 Intent 토큰 누출 원인
```
┌─────────────────────┐
│    intent_node.py   │
│  llm.generate()     │ ← LangChainLLMAdapter.ainvoke()
└─────────────────────┘
         │
         ▼
┌─────────────────────┐
│     LangGraph       │
│ stream_mode=        │ ← ainvoke() 응답도 "messages"로 캡처
│   ["messages"]      │
└─────────────────────┘
         │
         ▼
┌─────────────────────┐
│ ProcessChatCommand  │
│ _handle_message_    │ ← "answer" 노드만 건너뛰고 "intent" 노드는 발행
│       chunk()       │
└─────────────────────┘
         │
         ▼
    "general" 토큰 발행 (버그!)
```

**문제**:
- `LangChainLLMAdapter.generate()`가 내부적으로 `ainvoke()` 사용
- LangGraph가 `ainvoke()` 응답도 "messages" 이벤트로 캡처
- `_handle_message_chunk()`가 "answer" 노드만 건너뛰고 "intent" 노드 응답은 토큰으로 발행

---

## 3. 해결 방안

### 3.1 수정 파일

#### `apps/chat_worker/application/commands/process_chat.py`
```python
async def _handle_message_chunk(
    self,
    data: tuple[Any, dict[str, Any]],
    job_id: str,
) -> None:
    """messages 모드 청크 처리.

    Note:
        현재 아키텍처에서는 모든 토큰 발행을 개별 노드에서 직접 처리합니다:
        - answer_node: notify_token_v2로 직접 토큰 발행 (웹 검색/LangChain 모두)
        - intent_node: 분류 결과만 반환 (토큰 스트리밍 불필요)
        - 기타 노드: 컨텍스트 수집만 수행 (토큰 스트리밍 불필요)

        따라서 ProcessChatCommand는 stream_mode="messages"에서 캡처되는
        LLM 응답을 토큰으로 발행하지 않습니다. 이를 통해:
        1. answer_node와의 토큰 중복 방지
        2. intent_node 분류 결과가 토큰으로 노출되는 것 방지
    """
    # 모든 토큰 발행은 개별 노드에서 직접 처리하므로 여기서는 건너뜀
    # answer_node가 notify_token_v2로 직접 토큰을 발행함
    return
```

#### `apps/chat_worker/tests/unit/application/commands/test_process_chat.py`
```python
@pytest.mark.anyio
async def test_streaming_skips_all_message_tokens(
    self,
    streaming_command: ProcessChatCommand,
    mock_notifier: MockProgressNotifier,
    sample_request: ProcessChatRequest,
):
    """스트리밍에서 모든 메시지 토큰 건너뛰기."""
    await streaming_command.execute(sample_request)

    # ProcessChatCommand는 모든 메시지 토큰을 건너뜀
    assert len(mock_notifier.tokens) == 0
```

### 3.2 수정된 아키텍처

```
┌─────────────────────┐
│   answer_node.py    │ ─── notify_token_v2() ───┐
│                     │                          │
│ (웹 검색 경로)       │                          │
│ (LangChain 경로)    │                          ▼
└─────────────────────┘                    Redis Streams
                                                 │
┌─────────────────────┐                          │
│ ProcessChatCommand  │                          │
│ _handle_message_    │ ─── return (건너뜀) ───╳  │
│       chunk()       │                          │
└─────────────────────┘                          ▼
                                            SSE Gateway
                                                 │
                                                 ▼
                                            Client (토큰 1회만 수신)
```

---

## 4. 테스트 결과

### 4.1 단위 테스트
```
======================== 15 passed, 2 warnings in 0.14s ========================
```

### 4.2 E2E 테스트

**테스트 메시지**: "2026년 1월 19일 현재 가장 핫한 AI 소식은 뭐야?"

**수정 전**:
```
event: token
data: {"seq": 1001, "content": "general", "node": "intent"}  ← 버그!

event: token
data: {"seq": 1002, "content": "요", "node": "answer"}

event: token
data: {"seq": 1003, "content": "요", "node": "answer"}  ← 중복!
```

**수정 후**:
```
event: token
data: {"seq": 1001, "content": "음", "node": "answer"}  ← 정상!

event: token
data: {"seq": 1002, "content": "…", "node": "answer"}

event: token
data: {"seq": 1003, "content": " **", "node": "answer"}

event: token
data: {"seq": 1004, "content": """, "node": "answer"}

event: token
data: {"seq": 1005, "content": "202", "node": "answer"}
...
```

**검증 항목**:
- [x] "general" 토큰이 스트림에 노출되지 않음
- [x] 토큰 중복 없음 (seq 번호 연속적)
- [x] 모든 토큰이 "answer" 노드에서만 발행됨
- [x] 클라이언트에서 정상적인 텍스트 표시

---

## 5. 배포 정보

| 항목 | 값 |
|------|-----|
| PR 번호 | #448 |
| 브랜치 | fix/token-duplication → develop |
| 머지 시간 | 2026-01-19T11:00:58Z |
| 이미지 태그 | chat-worker-dev-latest |
| 이미지 SHA | sha256:3c12f51714f5a101fb6655c218a8e3749218f442fbd844fad7644f11aebc4a81 |

---

## 6. 향후 고려사항

### 6.1 잠재적 개선점
1. **노드별 토큰 발행 정책 명문화**: 어떤 노드가 토큰을 발행해야 하는지 문서화
2. **LangGraph stream_mode 활용 재검토**: 현재는 "messages" 모드를 사용하지 않음
3. **테스트 커버리지 강화**: 다양한 intent에 대한 E2E 테스트 추가

### 6.2 관련 코드 위치
- Token 발행: `answer_node.py:200-230`
- Token 건너뛰기: `process_chat.py:439-465`
- 테스트: `test_process_chat.py:443-465`

---

## 7. 커밋 이력

```
4c47288d fix(chat_worker): skip all message tokens in ProcessChatCommand
39da14ca merge: resolve conflicts with develop
```

**Co-Authored-By**: Claude Opus 4.5 <noreply@anthropic.com>
