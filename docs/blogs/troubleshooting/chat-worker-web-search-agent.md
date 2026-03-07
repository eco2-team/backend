# Web Search Agent Troubleshooting

## 증상

사용자가 실시간 검색을 요청하면 봇이 **"웹을 직접 검색할 수 없습니다"** 라고 응답.
로그상 `web_search_node`는 정상 실행 완료로 표시됨.

```
[03:30:34,602] web_search_node    INFO  Executing web search
[03:30:35,469] httpx              INFO  POST https://api.openai.com/v1/chat/completions 200 OK
[03:30:39,961] web_search_node    INFO  Web search completed
[03:30:39,962] node_executor      INFO  Node execution succeeded
```

---

## 기존 구조 및 장애 지점

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         LangGraph Pipeline                              │
│                                                                         │
│  ┌──────────┐    ┌───────────┐    ┌──────────────┐    ┌─────────────┐  │
│  │  Intent  │───▶│  Dynamic  │───▶│  Web Search  │───▶│ Aggregator  │  │
│  │   Node   │    │  Router   │    │     Node     │    │    Node     │  │
│  └──────────┘    └───────────┘    └──────┬───────┘    └──────┬──────┘  │
│                                          │                    │         │
│                                          ▼                    ▼         │
│                                  ┌──────────────┐    ┌─────────────┐   │
│                                  │  OpenAI LLM  │    │   Answer    │   │
│                                  │    Client    │    │    Node     │   │
│                                  └──────┬───────┘    └─────────────┘   │
│                                          │                              │
└──────────────────────────────────────────┼──────────────────────────────┘
                                           │
                              ┌─────────────┴─────────────┐
                              │    generate_with_tools()   │
                              │                            │
                              │  ❌ FAILURE POINT 1        │
                              │  openai SDK < 1.66         │
                              │  → client.responses 없음   │
                              │  → AttributeError 발생     │
                              │                            │
                              ├────────────────────────────┤
                              │                            │
                              │  except AttributeError:    │
                              │  ❌ FAILURE POINT 2        │
                              │  Silent fallback →         │
                              │  generate_stream()         │
                              │  (Chat Completions API)    │
                              │  → web search 도구 없음    │
                              │                            │
                              ├────────────────────────────┤
                              │                            │
                              │  ❌ FAILURE POINT 3        │
                              │  tool type: "web_search"   │
                              │  (올바른 값:               │
                              │   "web_search_preview")    │
                              │                            │
                              └─────────────┬──────────────┘
                                            │
                                            ▼
                              ┌────────────────────────────┐
                              │  모델 응답 (도구 미호출):   │
                              │  "웹 검색을 할 수 없습니다" │
                              └─────────────┬──────────────┘
                                            │
                                            ▼
                              ┌────────────────────────────┐
                              │  web_search_node:          │
                              │  이 텍스트를 "검색 결과"로  │
                              │  반환 → success: true      │
                              └─────────────┬──────────────┘
                                            │
                                            ▼
                              ┌────────────────────────────┐
                              │  answer_node:              │
                              │  context에 "검색 불가"      │
                              │  텍스트가 들어있으므로       │
                              │  그대로 사용자에게 전달      │
                              └────────────────────────────┘
```

### 장애 전파 경로 요약

```
SDK 버전 부족 → AttributeError → Silent Fallback → Chat Completions (도구 없음)
→ 모델이 "검색 불가" 텍스트 생성 → 이것이 "검색 결과"로 취급됨
→ answer_node가 이 context를 신뢰 → 사용자에게 "검색 안 됨" 답변
```

---

## 근본 원인 분석

### Flaw 1: openai SDK 버전 요구사항 부족

**파일:** `requirements.txt`

```python
# BEFORE:
openai>=1.58.0

# Responses API (client.responses.create)는 v1.66.0에서 도입
# Agents SDK 호환은 v2.0.0+
```

프로덕션에 1.58~1.65 사이 버전이 설치되어 `client.responses` 속성이 존재하지 않았음.

### Flaw 2: Silent Fallback (자동 성능 저하)

**파일:** `openai_client.py:280-288`

```python
except AttributeError:
    # Responses API가 지원되지 않는 경우 fallback
    logger.warning("Responses API not available, falling back to chat completions")
    async for chunk in self.generate_stream(prompt=prompt, ...):
        yield chunk
```

- `WARNING` 레벨이라 로그에서 놓치기 쉬움
- Chat Completions API로 fallback하면 web search 도구가 없으므로 모델이 자체 지식으로만 응답
- 노드는 "성공"으로 보고 → 장애 감지 불가

### Flaw 3: 잘못된 Tool Type

**파일:** `openai_client.py:247`

```python
# BEFORE (잘못된 값 — API는 에러 안 반환, 모델이 도구를 무시):
{"type": "web_search", "search_context_size": "medium"}

# AFTER (올바른 값):
{"type": "web_search_preview", "search_context_size": "medium"}
```

OpenAI Responses API는 `"web_search_preview"`를 요구함.
`"web_search"`는 유효하지 않은 타입이지만 API가 에러를 반환하지 않고,
모델이 해당 도구를 invoke하지 않은 채 텍스트만 생성.

---

## 장애가 감지되지 않은 이유

| 계층 | 왜 통과했는가 |
|------|--------------|
| OpenAI API | 잘못된 tool type에도 200 OK 반환 (에러 아님) |
| `generate_with_tools` | `except AttributeError` → fallback으로 텍스트 생성 성공 |
| `web_search_node` | 비어있지 않은 텍스트를 받음 → `success: True` 반환 |
| `node_executor` | 예외 없음 → "Node execution succeeded" 로깅 |
| `answer_node` | context에 텍스트가 있으므로 정상 답변 생성 |
| 사용자 | 봇이 "검색 안 됨"이라고 답함 → 기능 장애 인지 |

**결론:** 모든 계층이 "성공"으로 보고했으나, 실제로는 도구가 한 번도 호출되지 않았음.

---

## 수정 사항

### 1. SDK 버전 범프

```diff
- openai>=1.58.0
+ openai>=2.0.0  # Responses API + Agents SDK compatibility
```

### 2. Tool Type 수정

```diff
- "type": "web_search",
+ "type": "web_search_preview",
```

### 3. Silent Fallback 제거

```diff
- except AttributeError:
-     logger.warning("Responses API not available, falling back to chat completions")
-     async for chunk in self.generate_stream(...):
-         yield chunk
- except Exception as e:
-     logger.error(f"generate_with_tools failed: {e}")
-     async for chunk in self.generate_stream(...):
-         yield chunk
+ except Exception as e:
+     logger.error(
+         "generate_with_tools failed (no fallback)",
+         extra={"error": str(e), "tools": tools},
+     )
+     raise
```

실패 시 예외를 그대로 raise하면 `web_search_node`의 try/except에서 잡아
`FAIL_OPEN` (error context 반환, 파이프라인 계속)으로 처리됨.

---

## 수정 후 구조

```
┌──────────────────────────────────────────────────────────────────┐
│                      LangGraph Pipeline                          │
│                                                                  │
│  Intent → Router → Web Search Node → Aggregator → Answer Node   │
│                         │                                        │
└─────────────────────────┼────────────────────────────────────────┘
                          │
                          ▼
              ┌───────────────────────┐
              │  generate_with_tools  │
              │                       │
              │  openai >= 2.0.0      │
              │  client.responses     │
              │    .create(           │
              │      tools=[{         │
              │        "type":        │
              │        "web_search_   │
              │         preview"      │
              │      }]               │
              │    )                  │
              └───────────┬───────────┘
                          │
                          ▼
              ┌───────────────────────┐
              │  POST /v1/responses   │  ← Chat Completions 아님!
              │  → 실제 웹 검색 수행   │
              │  → 검색 결과 + 출처    │
              └───────────┬───────────┘
                          │
                          ▼
              ┌───────────────────────┐
              │  실패 시: raise       │
              │  → node catch         │
              │  → FAIL_OPEN          │
              │  → error context 반환 │
              │  → 파이프라인 계속     │
              └───────────────────────┘
```

---

## Gemini 검증

Gemini client의 Google Search 구현은 정상:

```python
# gemini_client.py:134
types.Tool(google_search=types.GoogleSearch())
config = types.GenerateContentConfig(tools=tool_configs)
await self._client.aio.models.generate_content_stream(model=..., config=config)
```

공식 문서와 동일한 패턴. Gemini provider에서는 웹 검색이 정상 동작.

---

## 교훈

1. **Silent fallback은 장애를 숨긴다** — 성능 저하(degradation)를 선택하면 모니터링이 어려움
2. **API가 에러를 안 반환한다고 정상은 아님** — 잘못된 tool type에도 200 OK
3. **SDK 버전 constraint는 실제 사용 기능 기준으로 설정** — Responses API 쓰면서 1.58+ 요구는 불일치
4. **"성공" 로그만 보지 말고 실제 API endpoint 확인** — `/v1/chat/completions` vs `/v1/responses`

---

## 참조

- [OpenAI Web Search Tool 문서](https://platform.openai.com/docs/guides/tools-web-search)
- [Gemini Google Search 문서](https://ai.google.dev/gemini-api/docs/google-search?hl=ko)
- [OpenAI Agents SDK (PyPI)](https://pypi.org/project/openai-agents/)
- PR #526: `fix/openai-web-search-tool-type`
