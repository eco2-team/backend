# ADR: Multi-Intent Detection 고도화

> **상태**: Accepted  
> **일자**: 2026-01-14  
> **관련 Foundations**:  
> - [25-multi-intent-icl-2023.md](../foundations/25-multi-intent-icl-2023.md)  
> - [26-chain-of-intent-cikm2025.md](../foundations/26-chain-of-intent-cikm2025.md)

---

## 1. Context (현재 상황)

### 1.1 구현 완료 사항

Two-Stage Multi-Intent Detection이 구현되어 있습니다:

```
┌─────────────────────────────────────────────────────────────┐
│                 현재: Two-Stage Detection                    │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  Stage 1: Fast Filter (Rule-based)                          │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ - 짧은 메시지 (≤12자) → 단일 Intent                  │   │
│  │ - 후보 키워드 없음 → 단일 Intent                     │   │
│  │ - 후보 키워드 있음 → Stage 2로                       │   │
│  └─────────────────────────────────────────────────────┘   │
│                          │                                   │
│                          ▼                                   │
│  Stage 2: LLM-based Discrimination                          │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ - LLM이 Multi-Intent 여부 판별                       │   │
│  │ - Query Decomposition (DialogUSR 패턴)               │   │
│  │ - 각 하위 쿼리별 Intent 분류                         │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

### 1.2 관련 파일

| 파일 | 역할 |
|------|------|
| `intent_classifier.py` | IntentClassifier, MultiIntentClassifier |
| `multi_intent_detect.txt` | Multi-Intent 감지 프롬프트 |
| `decompose.txt` | Query Decomposition 프롬프트 |

### 1.3 테스트 현황

- 단위 테스트: 40개 통과
- 전체 테스트: 184개 통과

---

## 2. Problem Statement (문제점)

### 2.1 JSON 파싱 불안정

현재 LLM 응답을 정규식으로 파싱하고 있어 실패 가능성이 있습니다:

```python
# 현재 방식
json_match = re.search(r"```json\s*(.*?)\s*```", response, re.DOTALL)
if json_match:
    json_str = json_match.group(1)
else:
    json_str = response.strip()  # fallback

try:
    return json.loads(json_str)
except json.JSONDecodeError:
    logger.warning(f"Failed to parse: {response[:100]}")
    return {"is_multi": False, ...}  # 보수적 fallback
```

**문제점**:
- LLM이 마크다운 없이 JSON만 출력하면 파싱 실패
- 잘못된 JSON 형식 출력 시 fallback 의존
- 타입 안전성 없음

### 2.2 Few-shot 예시 부족

현재 프롬프트의 예시가 제한적입니다:

| 유형 | 현재 예시 수 | 권장 예시 수 |
|------|-------------|-------------|
| Single Intent (명확) | 2개 | 3-4개 |
| Single Intent (함정) | 1개 | 3-4개 |
| Multi Intent | 2개 | 3-4개 |

**문제점**:
- 같은 카테고리 품목을 Multi로 오인
- 조사/접속사 함정 케이스 미흡
- 다양한 Intent 조합 예시 부족

### 2.3 Intent 전환 패턴 미활용

Chain-of-Intent 논문의 핵심 인사이트인 **Intent 전이 확률**이 활용되지 않고 있습니다:

```python
# 현재: 맥락은 있지만 전이 확률 미활용
context = {"previous_intents": ["waste"]}
result = await classifier.classify(message, context=context)
# → previous_intents가 분류에 미치는 영향 제한적
```

---

## 3. Decision (결정)

### 3.1 Structured JSON Output 도입

OpenAI/Gemini의 Structured Output API를 활용하여 파싱 안정성을 보장합니다.

```python
from pydantic import BaseModel, Field

class MultiIntentDetectionSchema(BaseModel):
    """Multi-Intent 감지 결과 스키마."""
    is_multi: bool = Field(description="복수 의도 여부")
    reason: str = Field(description="판단 근거")
    detected_categories: list[str] = Field(description="감지된 카테고리")
    confidence: float = Field(ge=0.0, le=1.0, description="신뢰도")

class QueryDecompositionSchema(BaseModel):
    """Query Decomposition 결과 스키마."""
    is_compound: bool = Field(description="복합 질문 여부")
    queries: list[str] = Field(description="분해된 쿼리 목록")
```

**장점**:
- 파싱 실패 0%
- 타입 안전성 보장
- 스키마 검증 자동화

### 3.2 Few-shot 프롬프트 강화

ICL 논문의 가이드라인에 따라 예시를 확장합니다:

```markdown
## Examples (확장)

### Single Intent - 명확한 케이스 (3개)
- "페트병 어떻게 버려?" → waste
- "캐릭터 뭐야?" → character  
- "근처 재활용센터 어디야?" → location

### Single Intent - 같은 카테고리 (3개)
- "페트병, 캔, 유리병 어떻게 버려?" → waste (단일)
- "플라스틱이랑 비닐 같이 버려도 돼?" → waste (단일)
- "종이랑 종이컵 분리?" → waste (단일)

### Single Intent - 조사/접속사 함정 (3개)
- "페트병도 재활용 되나요?" → waste (단일)
- "근처 센터랑 거리도 알려줘" → location (단일)
- "캐릭터도 포인트 있어?" → character (단일)

### Multi Intent - 명확한 케이스 (3개)
- "페트병 버리고 캐릭터도 알려줘" → [waste, character]
- "재활용센터 어디야, 그리고 유리병은?" → [location, waste]
- "최신 정책 알려주고 내 캐릭터도" → [web_search, character]
```

### 3.3 Intent Transition Boost 추가

Chain-of-Intent 논문의 HMM 전이 확률 개념을 적용합니다:

```python
INTENT_TRANSITION_BOOST = {
    Intent.WASTE: {
        Intent.LOCATION: 0.15,    # waste 후 location 자주
        Intent.CHARACTER: 0.05,
    },
    Intent.GENERAL: {
        Intent.WASTE: 0.10,       # 인사 후 본론
    },
    Intent.LOCATION: {
        Intent.WASTE: 0.10,
    },
}
```

---

## 4. Implementation Plan (구현 계획)

### P0: Structured Output (High Priority)

**목표**: JSON 파싱 안정성 100% 보장

**수정 파일**:
1. `application/ports/llm/llm_client.py` - `generate_structured` 메서드 추가
2. `infrastructure/llm/clients/openai_client.py` - Structured Output 구현
3. `infrastructure/llm/clients/gemini_client.py` - Structured Output 구현

**구현**:
```python
# LLMClientPort 확장
class LLMClientPort(ABC):
    @abstractmethod
    async def generate_structured(
        self,
        prompt: str,
        response_schema: type[BaseModel],
        system_prompt: str | None = None,
    ) -> BaseModel:
        """구조화된 응답 생성."""
        pass
```

### P1: Few-shot 예시 확장 (High Priority)

**목표**: 함정 케이스 커버리지 향상

**수정 파일**:
1. `prompts/classification/multi_intent_detect.txt`
2. `prompts/classification/decompose.txt`

**추가 예시**:
- 같은 카테고리 품목 3개
- 조사/접속사 함정 3개
- 명확한 Multi-Intent 3개

### P2: Intent Transition Boost (Medium Priority)

**목표**: 대화 맥락 활용 강화

**수정 파일**:
1. `application/intent/services/intent_classifier.py`

**구현**:
```python
def _adjust_confidence_by_transition(
    self,
    intent: Intent,
    previous_intents: list[str],
) -> float:
    """이전 Intent 기반 신뢰도 보정."""
    if not previous_intents:
        return 0.0
    
    last_intent = Intent.from_string(previous_intents[-1])
    transitions = INTENT_TRANSITION_BOOST.get(last_intent, {})
    
    return transitions.get(intent, 0.0)
```

### P3: 임베딩 캐싱 (Low Priority - 향후)

**목표**: LLM 호출 50% 감소

**구현 아이디어**:
- 발화 임베딩 저장
- 유사도 기반 캐시 히트
- 임계값 이상이면 LLM 스킵

---

## 5. Architecture (아키텍처)

### 5.1 Structured Output 흐름

```
┌─────────────────────────────────────────────────────────────┐
│              Structured Output Flow                          │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  IntentClassifier                                            │
│        │                                                     │
│        ▼                                                     │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  _detect_multi_intent(message)                       │   │
│  │        │                                             │   │
│  │        ▼                                             │   │
│  │  llm.generate_structured(                            │   │
│  │      prompt=message,                                 │   │
│  │      response_schema=MultiIntentDetectionSchema,     │   │
│  │      system_prompt=self._multi_detect_prompt,        │   │
│  │  )                                                   │   │
│  │        │                                             │   │
│  │        ▼                                             │   │
│  │  MultiIntentDetectionSchema (Pydantic Model)         │   │
│  │  - is_multi: bool                                    │   │
│  │  - reason: str                                       │   │
│  │  - detected_categories: list[str]                    │   │
│  │  - confidence: float                                 │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                              │
│  → 파싱 로직 불필요                                          │
│  → 타입 안전성 보장                                          │
│  → 스키마 위반 시 API 레벨에서 재시도                        │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

### 5.2 Intent Transition Boost 흐름

```
┌─────────────────────────────────────────────────────────────┐
│              Intent Transition Boost Flow                    │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  Context: previous_intents = ["waste"]                       │
│  Current: message = "근처 센터는?"                           │
│                                                              │
│  1. LLM 기본 분류                                            │
│     intent = "location", confidence = 0.75                   │
│                                                              │
│  2. Transition Boost 적용                                    │
│     INTENT_TRANSITION_BOOST[waste][location] = 0.15          │
│     boosted_confidence = 0.75 + 0.15 = 0.90                  │
│                                                              │
│  3. 최종 결과                                                │
│     intent = "location", confidence = 0.90 ✓                 │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

---

## 6. Testing Strategy (테스트 전략)

### 6.1 단위 테스트 추가

| 테스트 케이스 | 검증 항목 |
|--------------|----------|
| `test_structured_output_parsing` | Pydantic 모델 반환 검증 |
| `test_transition_boost_waste_to_location` | 전이 부스트 적용 |
| `test_transition_boost_no_context` | 맥락 없을 때 부스트 0 |
| `test_few_shot_same_category` | 같은 카테고리 → Single |
| `test_few_shot_tricky_case` | 함정 케이스 → Single |

### 6.2 통합 테스트

```python
@pytest.mark.asyncio
async def test_multi_intent_structured_output():
    """Structured Output으로 Multi-Intent 감지."""
    classifier = MultiIntentClassifier(llm, cache)
    
    result = await classifier.classify_multi(
        "페트병 버리고 캐릭터도 알려줘"
    )
    
    assert result.is_multi
    assert len(result.intents) == 2
    assert Intent.WASTE in [i.intent for i in result.intents]
    assert Intent.CHARACTER in [i.intent for i in result.intents]
```

---

## 7. Risks & Mitigations (위험 및 대응)

| 위험 | 영향 | 대응 |
|------|------|------|
| Structured Output 미지원 모델 | 일부 모델에서 사용 불가 | Fallback to regex parsing |
| Transition Boost 과적합 | 특정 패턴에 편향 | 실제 로그 기반 튜닝 |
| 프롬프트 길이 증가 | 토큰 비용 증가 | 예시 수 최적화 (9-12개) |

---

## 8. Timeline (일정)

| Phase | 작업 | 예상 시간 |
|-------|------|----------|
| P0 | Structured Output 구현 | 2시간 |
| P1 | Few-shot 프롬프트 강화 | 1시간 |
| P2 | Intent Transition Boost | 1시간 |
| Test | 테스트 보강 및 실행 | 1시간 |
| **Total** | | **5시간** |

---

## 9. References (참고 자료)

- [OpenAI Structured Outputs](https://platform.openai.com/docs/guides/structured-outputs)
- [Gemini Structured Output](https://ai.google.dev/gemini-api/docs/structured-output)
- [arxiv:2304.11384](https://arxiv.org/abs/2304.11384) - Multi-Intent ICL
- [arxiv:2411.14252](https://arxiv.org/abs/2411.14252) - Chain-of-Intent

