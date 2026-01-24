# SDK Version Compatibility Check

OpenAI Python SDK 버전 호환성을 검증합니다.

## 수행 작업

1. **requirements.txt 파싱**: `openai` 패키지 버전 constraint 확인
2. **코드베이스 스캔**: 사용 중인 API 패턴 탐지
   - `client.chat.completions.create` → Chat Completions API
   - `client.responses.create` → Responses API (>=1.66.0 필요)
   - `openai-agents` import → Agents SDK (openai>=2.9.0 필요)
3. **호환성 매트릭스 대조**: 사용 기능 vs 요구 버전 비교
4. **Built-in Tools 검증**: tool type 값이 올바른지 확인
   - `web_search_preview` (O) vs `web_search` (X - 잘못된 값)
   - `file_search`, `code_interpreter`, `computer_use_preview`
5. **Breaking Changes 확인**: v2.0.0 breaking change 영향도 분석
6. **Fallback 패턴 감지**: `except AttributeError` 등 silent degradation 경고

## 검증 기준

| 사용 기능 | 필요 최소 버전 |
|-----------|---------------|
| Chat Completions | `>=1.0.0` |
| Responses API | `>=1.66.0` |
| Built-in Tools (web_search_preview) | `>=1.66.0` |
| GPT-5.x 모델 | `>=2.8.0` |
| Agents SDK 호환 | `>=2.9.0,<3` |

## 참조 문서

- `docs/blogs/applied/openai-sdk-version-compatibility.md` — 전체 호환성 매트릭스
- `docs/blogs/troubleshooting/chat-worker-web-search-agent.md` — 버전 불일치 장애 사례

## 출력 형식

```
=== SDK Version Compatibility Report ===

[requirements.txt]
  openai constraint: >=2.9.0,<3

[사용 중인 API]
  - Chat Completions API: ✓ (intent_node, answer_node)
  - Responses API: ✓ (web_search_node)
  - Agents SDK: ✗ (미사용)

[Tool Type 검증]
  - web_search_preview: ✓ (openai_client.py:247)

[호환성 결과]
  최소 필요 버전: >=2.9.0
  현재 constraint: >=2.9.0,<3
  상태: ✓ 호환

[경고]
  - (없음)
```
