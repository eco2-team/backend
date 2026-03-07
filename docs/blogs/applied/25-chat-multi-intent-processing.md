# Multi-Intent 처리 고도화 - Policy 조합 주입과 Answer 캐싱

> LangGraph 기반 Chat Agent의 Multi-Intent 처리를 고도화하여,
> 여러 의도가 포함된 질문에 대해 Policy를 조합 주입하고 비용 최적화를 위한 Answer 캐싱을 구현합니다.

## 목차

1. [문제 정의](#1-문제-정의)
2. [해결 방향](#2-해결-방향)
3. [P2: Multi-Intent Policy 조합 주입](#3-p2-multi-intent-policy-조합-주입)
4. [P3: Answer 캐싱](#4-p3-answer-캐싱)
5. [테스트 검증](#5-테스트-검증)
6. [결론](#6-결론)

---

## 1. 문제 정의

### 1.1 AS-IS: Multi-Intent는 감지만 하고 활용 안 됨

기존 시스템은 Multi-Intent를 **감지**는 하지만 **첫 번째 Intent로만 라우팅**했습니다.

```
┌─────────────────────────────────────────────────────────────┐
│                    기존: 첫 번째 Intent만 사용              │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  Input: "페트병 버리고 캐릭터 알려줘"                         │
│                                                              │
│  MultiIntentClassifier.classify_multi()                      │
│       ↓                                                      │
│  intents = [waste, character]                                │
│  decomposed_queries = ["페트병 버려", "캐릭터 알려줘"]        │
│       ↓                                                      │
│  intent_node: primary_intent = waste  ← 첫 번째만 사용!      │
│       ↓                                                      │
│  route_by_intent() → "waste"                                 │
│       ↓                                                      │
│  waste_rag → answer                                          │
│                                                              │
│  ❌ character는 무시됨!                                       │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

### 1.2 비용 인식 부재

모든 요청이 동일한 경로로 처리되어, 간단한 질문도 불필요한 LLM 호출 발생:

```
"안녕" (단순 인사)     ──┬──→ 매번 LLM 호출 (비용 동일)
"뭐해?" (일상 대화)    ──┤
"복잡한 질문"          ──┘
```

---

## 2. 해결 방향

### 2.1 개선 목표

| 구분 | AS-IS | TO-BE | 효과 |
|------|-------|-------|------|
| **P2** | 첫 번째 Intent로만 라우팅 | **Policy 조합 주입** | 복합 질문 완전 응답 |
| **P3** | 모든 요청 LLM 호출 | **간단한 건 캐싱** | 비용/지연 최적화 |

### 2.2 아키텍처 변경

```
┌─────────────────────────────────────────────────────────────┐
│                    TO-BE: Policy 조합 + 캐싱               │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  Input: "페트병 버리고 캐릭터 알려줘"                         │
│                                                              │
│  intent_node                                                 │
│       ↓                                                      │
│  intents = [waste, character]                                │
│  has_multi_intent = true                                     │
│  additional_intents = ["character"]                          │
│       ↓                                                      │
│  answer_node                                                 │
│       ↓                                                      │
│  PromptBuilder.build_multi(["waste", "character"])           │
│       ↓                                                      │
│  ┌──────────────────────────────────────────────────────┐   │
│  │ ## 다중 의도 처리 모드                                │   │
│  │ ### [1] WASTE 관련 지침                              │   │
│  │ (분리수거 Policy)                                    │   │
│  │ ---                                                  │   │
│  │ ### [2] CHARACTER 관련 지침                          │   │
│  │ (캐릭터 Policy)                                      │   │
│  └──────────────────────────────────────────────────────┘   │
│       ↓                                                      │
│  ✅ 두 주제 모두 포함된 답변 생성!                           │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

---

## 3. P2: Multi-Intent Policy 조합 주입

### 3.1 PromptBuilder 확장

`PromptBuilder`에 `build_multi()` 메서드를 추가하여 여러 Intent의 Local 프롬프트를 조합합니다.

```python
# infrastructure/orchestration/prompts/loader.py

class PromptBuilder:
    def build_multi(self, intents: list[str]) -> str:
        """Multi-Intent에 따른 조합 프롬프트 생성.

        여러 Intent의 Local 프롬프트를 조합하여 하나의 시스템 프롬프트 생성.
        DialogUSR 패턴: 분해된 쿼리에 맞는 Policy를 조합 주입.
        """
        if not intents:
            return self.build("general")

        if len(intents) == 1:
            return self.build(intents[0])

        # 중복 제거하면서 순서 유지
        seen: set[str] = set()
        unique_intents: list[IntentType] = []
        for intent in intents:
            normalized = self._normalize_intent(intent)
            if normalized not in seen:
                seen.add(normalized)
                unique_intents.append(normalized)

        # Local 프롬프트 조합
        local_parts = []
        for i, intent in enumerate(unique_intents, 1):
            local_prompt = self._local.get(intent, self._local["general"])
            local_parts.append(f"### [{i}] {intent.upper()} 관련 지침\n\n{local_prompt}")

        combined_local = "\n\n---\n\n".join(local_parts)

        # Multi-Intent 헤더 추가
        multi_header = (
            "## 다중 의도 처리 모드\n"
            "사용자의 질문에 여러 주제가 포함되어 있습니다. "
            "아래 각 지침을 참고하여 모든 주제에 대해 답변해주세요.\n"
            "각 주제별 답변을 자연스럽게 연결하여 하나의 응답으로 제공하세요."
        )

        final_prompt = f"{self._global}\n\n---\n\n{multi_header}\n\n{combined_local}"
        return final_prompt
```

### 3.2 Answer Node 수정

`answer_node`에서 Multi-Intent 여부를 확인하고 조합 프롬프트를 사용합니다.

```python
# infrastructure/orchestration/langgraph/nodes/answer_node.py

async def answer_node(state: dict[str, Any]) -> dict[str, Any]:
    intent = state.get("intent", "general")  # Primary Intent
    additional_intents = state.get("additional_intents", [])  # Multi-Intent
    has_multi_intent = state.get("has_multi_intent", False)

    # P2: Multi-Intent인 경우 여러 Policy 조합 주입
    if has_multi_intent and additional_intents:
        all_intents = [intent] + additional_intents
        system_prompt = prompt_builder.build_multi(all_intents)
    else:
        system_prompt = prompt_builder.build(intent)

    # LLM 호출...
```

### 3.3 프롬프트 구조 시각화

```
┌──────────────────────────────────────────────────────────────────┐
│                         GLOBAL PROMPT                             │
│              (이코 캐릭터 정의, 톤, 공통 규칙)                     │
├──────────────────────────────────────────────────────────────────┤
│                     ## 다중 의도 처리 모드                        │
│   사용자의 질문에 여러 주제가 포함되어 있습니다...                  │
├──────────────────────────────────────────────────────────────────┤
│   ### [1] WASTE 관련 지침                                        │
│   - 분류된 품목의 배출 정보를 disposal_rules에서 찾아 답변         │
│   - 지역별 규정이 다를 수 있음을 안내                             │
│   ---                                                            │
│   ### [2] CHARACTER 관련 지침                                    │
│   - 현재 캐릭터 성장 정보 안내                                    │
│   - 다음 레벨 달성 조건 안내                                      │
└──────────────────────────────────────────────────────────────────┘
```

---

## 4. P3: Answer 캐싱

### 4.1 캐시 전략

모든 답변을 캐싱하는 것은 비효율적입니다. 다음 조건을 충족하는 경우만 캐싱합니다:

| 조건 | 설명 | 이유 |
|------|------|------|
| **Intent** | `general`, `greeting`만 | 동적 데이터 없음 |
| **Context** | 없음 | RAG/Subagent 결과가 있으면 매번 다름 |

```python
# 캐시 가능한 Intent
CACHEABLE_INTENTS = frozenset({"general", "greeting"})
ANSWER_CACHE_TTL = 3600  # 1시간
```

### 4.2 캐시 로직 흐름

```
┌─────────────────────────────────────────────────────────────┐
│                    Answer Cache Flow                         │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  Input: "안녕" (intent=general, context=None)                │
│                                                              │
│  1. _is_cacheable() 확인                                    │
│     ├── intent in CACHEABLE_INTENTS? ✅                     │
│     └── context.has_context()? ❌ (없음)                    │
│     → 캐시 가능!                                            │
│                                                              │
│  2. Cache 조회                                               │
│     ├── HIT → 캐시된 답변 반환 (LLM 호출 ❌)                │
│     └── MISS → LLM 호출 → 캐시 저장                        │
│                                                              │
│  Input: "페트병 버려" (intent=waste)                         │
│     → _is_cacheable() = false                               │
│     → 캐시 안 함 (매번 RAG 결과 다름)                        │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

### 4.3 구현 코드

```python
# infrastructure/orchestration/langgraph/nodes/answer_node.py

def create_answer_node(
    llm: "LLMClientPort",
    event_publisher: "ProgressNotifierPort",
    cache: "CachePort | None" = None,  # P3: Answer 캐싱용
):
    def _generate_cache_key(message: str, intent: str) -> str:
        """Answer 캐시 키 생성."""
        content = f"answer:{intent}:{message.strip().lower()}"
        return f"answer:{hashlib.sha256(content.encode()).hexdigest()[:16]}"

    def _is_cacheable(intent: str, context: AnswerContext) -> bool:
        """캐시 가능 여부 판단."""
        if intent not in CACHEABLE_INTENTS:
            return False
        if context.has_context():
            return False
        return True

    async def answer_node(state: dict[str, Any]) -> dict[str, Any]:
        # ... 컨텍스트 구성 ...

        # P3: Answer 캐시 확인
        cache_key = _generate_cache_key(message, intent)
        is_cacheable = cache is not None and _is_cacheable(intent, context)

        if is_cacheable:
            cached_answer = await cache.get(cache_key)
            if cached_answer:
                logger.info("Answer cache hit")
                # 캐시된 답변 스트리밍
                for char in cached_answer:
                    await event_publisher.notify_token(task_id=job_id, content=char)
                return {**state, "answer": cached_answer, "cache_hit": True}

        # LLM 호출...
        answer = "".join(answer_parts)

        # P3: 캐시 저장
        if is_cacheable and answer:
            await cache.set(cache_key, answer, ttl=ANSWER_CACHE_TTL)

        return {**state, "answer": answer}
```

### 4.4 비용 최적화 효과

```
┌──────────────────────────────────────────────────────────────┐
│                    비용 최적화 시나리오                        │
├──────────────────────────────────────────────────────────────┤
│                                                               │
│  요청 1: "안녕" → Cache MISS → LLM 호출 → 캐시 저장           │
│  요청 2: "안녕" → Cache HIT  → LLM 호출 ❌ (비용 0)           │
│  요청 3: "안녕" → Cache HIT  → LLM 호출 ❌ (비용 0)           │
│                                                               │
│  ┌─────────────────────────────────────────────────────┐     │
│  │  일반 인사 요청 100건/일 가정                        │     │
│  │  - 기존: 100 x $0.01 = $1.00                        │     │
│  │  - 개선: 1 x $0.01 + 99 x $0 = $0.01                │     │
│  │  → 99% 비용 절감!                                   │     │
│  └─────────────────────────────────────────────────────┘     │
│                                                               │
└──────────────────────────────────────────────────────────────┘
```

---

## 5. 테스트 검증

### 5.1 Multi-Intent 테스트

```python
class TestMultiIntentPromptBuilder:
    def test_build_multi_two_intents(self, builder):
        """두 Intent의 Policy가 모두 포함."""
        prompt = builder.build_multi(["waste", "character"])

        assert "다중 의도 처리 모드" in prompt
        assert "[1] WASTE" in prompt
        assert "[2] CHARACTER" in prompt

    def test_build_multi_duplicate_removal(self, builder):
        """중복 Intent는 제거."""
        prompt = builder.build_multi(["waste", "waste", "character"])

        assert prompt.count("[1] WASTE") == 1
        assert "[2] CHARACTER" in prompt
        assert "[3]" not in prompt
```

### 5.2 Answer 캐시 테스트

```python
class TestAnswerCache:
    async def test_cache_hit_returns_cached(self, mock_llm, mock_cache):
        """캐시 히트 시 LLM 호출 없이 캐시된 답변 반환."""
        mock_cache.preset(cache_key, "캐시된 답변!")

        result = await node(state)

        assert result["answer"] == "캐시된 답변!"
        assert result.get("cache_hit") is True
        assert mock_llm.call_count == 0  # LLM 호출 안 됨

    async def test_non_cacheable_intent_not_cached(self, mock_llm, mock_cache):
        """캐시 불가능한 Intent는 캐시하지 않음."""
        state = {"intent": "waste", ...}

        await node(state)

        assert mock_llm.call_count == 1
        assert len(mock_cache.set_calls) == 0  # 캐시 저장 안 됨
```

### 5.3 테스트 결과

```bash
$ pytest apps/chat_worker/tests/ -q

215 passed in 0.47s
```

---

## 6. 결론

### 6.1 구현 완료 항목

| 항목 | 상태 | 설명 |
|------|------|------|
| **P2: Multi-Intent Policy 조합** | ✅ | `build_multi()` 메서드로 여러 Policy 조합 |
| **P3: Answer 캐싱** | ✅ | 간단한 질문 캐싱으로 비용 최적화 |
| **테스트 보강** | ✅ | 35개 테스트 추가 |

### 6.2 개선 효과

```
┌─────────────────────────────────────────────────────────────┐
│                    개선 효과 요약                            │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  Before:                                                     │
│  "페트병 버리고 캐릭터 알려줘"                                │
│  → "페트병은 일반 플라스틱으로..." (캐릭터 정보 누락)        │
│                                                              │
│  After:                                                      │
│  → "페트병은 일반 플라스틱으로 분리수거해요!                 │
│     그리고 현재 이코는 레벨 5이고..."                        │
│  (두 주제 모두 포함!)                                        │
│                                                              │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  Before:                                                     │
│  "안녕" x 100회 → LLM 호출 100회 ($1.00)                    │
│                                                              │
│  After:                                                      │
│  "안녕" x 100회 → LLM 호출 1회 + 캐시 99회 ($0.01)          │
│  (99% 비용 절감!)                                            │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

### 6.3 향후 과제

- **P2.2**: Multi-Intent 병렬 Subagent 호출 (현재는 순차)
- **P3.3**: 복잡도 기반 모델 선택 (쉬운 건 작은 모델)
- **Semantic Cache**: 유사 질문도 캐시 히트 (임베딩 기반)

---

## References

- [arxiv:2304.11384] Multi-Intent In-Context Learning for Intent Classification
- [arxiv:2411.14252] Chain-of-Intent for Multi-Turn Dialogue
- [docs/plans/multi-intent-enhancement-adr.md] Multi-Intent 고도화 ADR
- [docs/foundations/25-multi-intent-icl-2023.md] Multi-Intent ICL 논문 정리
- [docs/foundations/26-chain-of-intent-cikm2025.md] Chain-of-Intent 논문 정리

