# Location 노드 수정 및 이미지 생성 프롬프트 강화 리포트

## Executive Summary

Location 노드(카카오 장소 검색)가 정상 동작하지 않았던 3가지 근본 원인을 분석하고 수정하였습니다. OpenAI provider 사용 시 Function Calling 미구현, state 필드명 불일치로 인한 Aggregator fallback 트리거, 그리고 이미지 생성 시 캐릭터 원본 보존 부족 문제를 해결하였습니다.

**관련 PR**: #489, #490, #491, #495

---

## 1. 아키텍처 개요

```
┌──────────────────────────────────────────────────────────────────────┐
│                    Location 검색 파이프라인                            │
├──────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  User Message                                                        │
│       │                                                              │
│       ▼                                                              │
│  ┌─────────┐    ┌──────────────────┐    ┌────────────────┐          │
│  │ Intent  │───▶│  Dynamic Router  │───▶│ kakao_place_node│          │
│  │  Node   │    │  (location)      │    │  (Function Call)│          │
│  └─────────┘    └──────────────────┘    └───────┬────────┘          │
│                                                  │                   │
│                         ┌────────────────────────┘                   │
│                         ▼                                            │
│  ┌──────────────────────────────────────┐                            │
│  │        LLMClientPort                  │                            │
│  │  .generate_function_call()            │                            │
│  │                                       │                            │
│  │  ┌─────────────────────────────────┐ │                            │
│  │  │ OpenAI: LangChainLLMAdapter     │ │  ← 수정 대상 ①             │
│  │  │ Google: GeminiLLMClient         │ │                            │
│  │  └─────────────────────────────────┘ │                            │
│  └──────────────────────────────────────┘                            │
│                         │                                            │
│                         ▼                                            │
│  ┌──────────────────────────────────────┐                            │
│  │  SearchKakaoPlaceCommand             │                            │
│  │  → KakaoLocalClientPort              │                            │
│  │  → 검색 결과 반환                     │                            │
│  └──────────────────────────────────────┘                            │
│                         │                                            │
│                         ▼                                            │
│  ┌──────────────────────────────────────┐                            │
│  │  State: "location_context"           │  ← 수정 대상 ②             │
│  │  (AS-IS: "kakao_place_context")      │                            │
│  └──────────────────────────────────────┘                            │
│                         │                                            │
│                         ▼                                            │
│  ┌──────────────────────────────────────┐                            │
│  │  Aggregator Node                      │                            │
│  │  contracts.py: location_context 필수  │                            │
│  │  → needs_fallback 판단                │                            │
│  └──────────────────────────────────────┘                            │
│                         │                                            │
│                         ▼                                            │
│  ┌──────────────────────────────────────┐                            │
│  │  Answer Node                          │                            │
│  │  → 검색 결과 기반 응답 생성            │                            │
│  └──────────────────────────────────────┘                            │
│                                                                      │
└──────────────────────────────────────────────────────────────────────┘
```

Location 검색 파이프라인은 Intent 분류 후 Dynamic Router가 `kakao_place_node`로 라우팅하며, LLM Function Calling으로 검색 파라미터를 추출한 뒤 Kakao Local API를 호출합니다. 결과는 Aggregator를 거쳐 Answer Node에 전달됩니다.

---

## 2. Bugs (수정 완료)

### 2.1 [P0 Critical] LangChainLLMAdapter Function Calling 미구현 ✅ Fixed

**위치**: `apps/chat_worker/infrastructure/llm/clients/langchain_adapter.py`

| 항목 | 내용 |
|------|------|
| **증상** | "주변 재활용센터" 등 장소 검색 요청 시 `generate_function_call() is not implemented` 에러 발생 |
| **영향** | OpenAI provider 사용 시 Location 노드, Weather 노드 등 Function Calling 기반 노드 전체 동작 불능 |
| **원인** | `default_provider="openai"`일 때 `LangChainLLMAdapter`가 주입되는데, 이 클래스에 `generate_function_call()` 메서드가 구현되어 있지 않아 기본 `LLMClientPort`의 `NotImplementedError` 발생 |

**AS-IS**:
```python
# LangChainLLMAdapter에 generate_function_call() 없음
# → 기본 LLMClientPort.generate_function_call() 호출
# → NotImplementedError 발생
class LangChainLLMAdapter(LLMClientPort):
    async def generate(self, ...): ...
    async def generate_stream(self, ...): ...
    async def generate_structured(self, ...): ...
    # generate_function_call() 미구현!
```

**TO-BE**:
```python
class LangChainLLMAdapter(LLMClientPort):
    ...
    async def generate_function_call(
        self,
        prompt: str,
        functions: list[dict[str, Any]],
        system_prompt: str | None = None,
        function_call: str | dict[str, str] = "auto",
    ) -> tuple[str | None, dict[str, Any] | None]:
        # LangChainOpenAIRunnable의 내부 AsyncOpenAI 클라이언트 활용
        client = self._llm._client
        tools = [{"type": "function", "function": func} for func in functions]
        response = await client.chat.completions.create(
            model=model, messages=messages, tools=tools, tool_choice=tool_choice,
        )
        # tool_calls에서 함수명과 인자 추출
        ...
```

**커밋**: `7a17e748` fix: add generate_function_call to LangChainLLMAdapter

---

### 2.2 [P0 Critical] State 필드명 불일치로 Aggregator Fallback 트리거 ✅ Fixed

**위치**: `apps/chat_worker/infrastructure/orchestration/langgraph/nodes/kakao_place_node.py`

| 항목 | 내용 |
|------|------|
| **증상** | Kakao API 검색이 성공했음에도 "위치 정보가 없어서 찾기 어렵다"는 fallback 응답 생성 |
| **영향** | Location 검색 결과가 Answer Node에 전달되지 않아 사용자에게 항상 실패 응답 전달 |
| **원인** | `contracts.py`와 `aggregator_node`는 `location_context` 필드를 기대하지만, `kakao_place_node`는 `kakao_place_context`를 반환하여 Aggregator가 "required context missing"으로 판단 |

**AS-IS**:
```python
# kakao_place_node.py - 잘못된 필드명 반환
return {
    **state,
    "kakao_place_context": output.places_context,  # ← Aggregator가 인식 못함
}

# contracts.py - location_context를 필수로 요구
INTENT_REQUIRED_FIELDS = {
    "location": frozenset({"location_context"}),  # ← 불일치!
}
```

**TO-BE**:
```python
# kakao_place_node.py - contracts.py와 일치하는 필드명
return {
    **state,
    "location_context": output.places_context,  # ← Aggregator 정상 인식
}
```

**커밋**: `d884ee1d` fix: rename kakao_place_context to location_context

---

### 2.3 [P1 Major] 이미지 생성 시 캐릭터 원본 미보존 ✅ Fixed

**위치**: `apps/chat_worker/infrastructure/assets/prompts/image_generation/`

| 항목 | 내용 |
|------|------|
| **증상** | 캐릭터 참조 이미지를 제공해도 생성된 이미지에서 캐릭터 디자인이 변형됨 |
| **영향** | 브랜드 캐릭터 일관성 훼손, 사용자 경험 저하 |
| **원인** | 기존 프롬프트가 "유지해주세요" 수준의 약한 지시로 모델이 캐릭터를 재해석 |

**AS-IS** (`character_reference.txt`):
```text
이 캐릭터의 다음 요소를 정확하게 유지해주세요:
- 캐릭터의 전체적인 형태와 실루엣
- 색상 팔레트와 색조
```

**TO-BE** (`character_reference.txt`):
```text
## CRITICAL: Character Preservation (HIGHEST PRIORITY)
You MUST preserve the EXACT appearance of this character:

### REQUIRED - Copy Exactly From Reference:
- **Body shape**: Exact proportions, silhouette, and body structure
- **Colors**: IDENTICAL color palette - do not shift or adjust any colors

### FORBIDDEN - Do Not Change:
- DO NOT redesign or reinterpret the character
- DO NOT change the character's proportions
```

추가로 `system.txt`에 "NON-NEGOTIABLE character consistency" 규칙을 추가하고, `generate_image_command.py`에서 시스템 프롬프트를 로드하여 모든 생성 요청에 적용하도록 수정하였습니다.

**커밋**: `e96cf17c` feat: enhance image generation prompts for character preservation

---

## 3. 검증 결과

### 3.1 Location 검색 정상 동작 확인

```
[18:36:28] HTTP Request: POST https://api.openai.com/v1/chat/completions "200 OK"
[18:36:28] Function calling completed
[18:36:28] Kakao place search input (query="제로웨이스트샵", radius=5000)
[18:36:28] HTTP Request: GET https://dapi.kakao.com/v2/local/search/keyword.json "200 OK"
[18:36:28] Kakao keyword search completed
[18:36:28] Kakao place search output (success=True)
```

Function Calling → Kakao API 호출 → 검색 결과 반환까지의 전체 파이프라인이 정상 동작함을 확인하였습니다.

### 3.2 관련 CI 상태

| PR | 내용 | CI 상태 |
|----|------|---------|
| #489 | Gemini Function Calling 구현 | ✅ Merged |
| #490 | Location 노드 로깅 강화 | ✅ Merged |
| #491 | 멀티턴 대화 컨텍스트 지원 | ✅ Merged |
| #495 | Location 수정 + 이미지 프롬프트 강화 | ✅ Merged |

---

## 4. 변경 파일 목록

| 파일 | 변경 내용 |
|------|-----------|
| `infrastructure/llm/clients/langchain_adapter.py` | `generate_function_call()` 메서드 추가 (86줄) |
| `infrastructure/orchestration/langgraph/nodes/kakao_place_node.py` | `kakao_place_context` → `location_context` 필드명 변경 |
| `infrastructure/assets/prompts/image_generation/character_reference.txt` | 캐릭터 보존 규칙 강화 |
| `infrastructure/assets/prompts/image_generation/system.txt` | 시스템 레벨 캐릭터 일관성 규칙 |
| `application/commands/generate_image_command.py` | 시스템 프롬프트 로드 및 적용 |
| `tests/unit/.../test_kakao_place_function_calling.py` | 필드명 변경 반영 |
| `tests/unit/application/intent/test_intent_classifier.py` | 프롬프트 포맷 변경 반영 |

---

## 5. 향후 과제

| 항목 | 우선순위 | 상태 |
|------|----------|------|
| 멀티턴 대화에서 Location 재요청 시 이전 검색 결과 참조 | P2 | 미적용 |
| 위치 권한 미허용 시 지역명 기반 검색 fallback | P2 | 미적용 |
| 이미지 생성 품질 A/B 테스트 (프롬프트 효과 측정) | P3 | 미적용 |
