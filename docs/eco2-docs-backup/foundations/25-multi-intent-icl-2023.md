# Multi-Intent Comment Generation via In-Context Learning

> **논문**: "Large Language Models are Few-Shot Summarizers: Multi-Intent Comment Generation via In-Context Learning"  
> **출처**: [arxiv:2304.11384](https://arxiv.org/abs/2304.11384) - April 2023  
> **키워드**: Multi-Intent, In-Context Learning, Few-shot, Code Comment Generation

---

## 목차

1. [논문 개요](#1-논문-개요)
2. [Multi-Intent의 정의](#2-multi-intent의-정의)
3. [In-Context Learning 활용](#3-in-context-learning-활용)
4. [Few-shot 프롬프트 전략](#4-few-shot-프롬프트-전략)
5. [실험 결과 및 인사이트](#5-실험-결과-및-인사이트)
6. [Eco2 chat_worker 적용점](#6-eco2-chat_worker-적용점)

---

## 1. 논문 개요

### 1.1 연구 배경

코드 주석(Comment) 생성은 소프트웨어 유지보수의 핵심 요소입니다. 기존 접근법은 단일 관점(예: "무엇을 하는가")에서만 주석을 생성했으나, 실제 개발자들은 다양한 관점의 정보를 필요로 합니다.

### 1.2 핵심 가설

> LLM은 사전학습 과정에서 코드와 자연어 주석 간의 **의미적 연결(Semantic Association)**을 학습했으며, 이를 통해 **다중 의도(Multi-Intent)**를 가진 주석을 생성할 수 있다.

### 1.3 연구 질문

| RQ | 질문 |
|----|------|
| RQ1 | LLM이 다중 의도 주석을 생성할 수 있는가? |
| RQ2 | Few-shot 예시가 생성 품질에 어떤 영향을 미치는가? |
| RQ3 | 프롬프트 구성 전략이 성능에 어떤 영향을 미치는가? |
| RQ4 | 후처리가 결과 품질을 향상시킬 수 있는가? |

---

## 2. Multi-Intent의 정의

### 2.1 Intent 카테고리

논문에서 정의한 코드 주석의 Multi-Intent 카테고리:

| Intent | 설명 | 예시 |
|--------|------|------|
| **What** | 기능/동작 설명 | "이 함수는 리스트를 정렬한다" |
| **Why** | 목적/이유 | "성능 최적화를 위해" |
| **How** | 구현 방식 | "퀵소트 알고리즘을 사용하여" |
| **Property** | 속성/제약 | "입력은 정수 리스트여야 한다" |
| **Usage** | 사용 예시 | "sort([3,1,2]) → [1,2,3]" |

### 2.2 Multi-Intent 주석 예시

```python
# What: 주어진 리스트에서 중복을 제거합니다.
# Why: 데이터 정제 파이프라인의 전처리 단계로 사용됩니다.
# How: set을 사용하여 O(n) 시간복잡도로 처리합니다.
# Usage: remove_duplicates([1,2,2,3]) → [1,2,3]
def remove_duplicates(items: list) -> list:
    return list(set(items))
```

### 2.3 대화 시스템에서의 Multi-Intent

논문의 개념을 대화 시스템에 적용하면:

```
┌─────────────────────────────────────────────────────────────┐
│            Multi-Intent in Dialogue Systems                  │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  코드 주석 도메인              대화 시스템 도메인             │
│  ─────────────────           ─────────────────              │
│  What (기능)          →      waste (분리배출 방법)          │
│  Why (목적)           →      general (이유/배경 설명)       │
│  How (방식)           →      location (어디서/어떻게)       │
│  Property (속성)      →      character (캐릭터 정보)        │
│  Usage (사용)         →      web_search (최신 정보)         │
│                                                              │
│  Multi-Intent 예시:                                          │
│  "페트병 버리고(waste) 캐릭터도 알려줘(character)"          │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

---

## 3. In-Context Learning 활용

### 3.1 ICL의 핵심 원리

```
┌─────────────────────────────────────────────────────────────┐
│              In-Context Learning (ICL) 원리                  │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  Prompt 구조:                                                │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  [Task Description]                                  │   │
│  │  "다음 코드에 대해 What, Why, How 관점의 주석 생성"  │   │
│  │                                                      │   │
│  │  [Example 1]                                         │   │
│  │  Input: def add(a, b): return a + b                 │   │
│  │  Output: What: 두 수를 더함, Why: 산술연산, How: +   │   │
│  │                                                      │   │
│  │  [Example 2]                                         │   │
│  │  Input: def sort(lst): ...                          │   │
│  │  Output: What: 정렬, Why: 순서화, How: 퀵소트       │   │
│  │                                                      │   │
│  │  [Query]                                             │   │
│  │  Input: def remove_duplicates(items): ...           │   │
│  │  Output: ???                                         │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                              │
│  LLM은 예시 패턴을 학습하여 새로운 입력에 적용              │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

### 3.2 ICL이 Multi-Intent에 효과적인 이유

| 요인 | 설명 |
|------|------|
| **패턴 인식** | 예시에서 다중 Intent 출력 패턴을 학습 |
| **의미적 연결** | 사전학습에서 획득한 코드-언어 연결 활용 |
| **구조 유지** | 예시의 출력 구조를 새 입력에도 적용 |
| **암묵적 지식** | 명시적 규칙 없이 예시만으로 학습 |

### 3.3 Zero-shot vs Few-shot 비교

```
Zero-shot (예시 없음):
┌─────────────────────────────────────────┐
│ Prompt: "다음 질문의 의도를 분류하세요" │
│ Input: "페트병 버리고 캐릭터도 알려줘"  │
│ Output: waste (단일 Intent만 감지)      │
└─────────────────────────────────────────┘

Few-shot (예시 포함):
┌─────────────────────────────────────────┐
│ Prompt: "다음 질문의 의도를 분류하세요" │
│                                         │
│ 예시 1: "플라스틱 버려" → [waste]       │
│ 예시 2: "버리고 센터도" → [waste, loc]  │
│ 예시 3: "캐릭터 뭐야" → [character]     │
│                                         │
│ Input: "페트병 버리고 캐릭터도 알려줘"  │
│ Output: [waste, character] ✓            │
└─────────────────────────────────────────┘
```

---

## 4. Few-shot 프롬프트 전략

### 4.1 예시 선택 전략

| 전략 | 설명 | 효과 |
|------|------|------|
| **다양성** | 다양한 Intent 조합 포함 | 커버리지 향상 |
| **대표성** | 자주 발생하는 패턴 우선 | 정확도 향상 |
| **균형** | Single/Multi Intent 균형 | 편향 방지 |
| **난이도** | 쉬운 것 → 어려운 것 순서 | 학습 효율 |

### 4.2 프롬프트 구성 요소

```markdown
# Multi-Intent Detection Prompt

## Task Description (역할 정의)
당신은 사용자 질문의 의도를 분류하는 전문가입니다.
하나의 질문에 여러 의도가 포함될 수 있습니다.

## Intent Categories (카테고리 정의)
- waste: 분리배출/재활용 방법
- character: 캐릭터 정보
- location: 위치/센터 정보
- general: 일반 대화
- web_search: 최신 정보 검색

## Examples (Few-shot 예시)
### Single Intent
- "페트병 어떻게 버려?" → [waste]
- "캐릭터 뭐야?" → [character]

### Multi Intent  
- "페트병 버리고 캐릭터도 알려줘" → [waste, character]
- "재활용센터 어디야, 유리병도 버려야 해" → [location, waste]

### Tricky Cases (함정 케이스)
- "페트병도 재활용 되나요?" → [waste] (단일)
- "페트병, 캔, 유리병 버려" → [waste] (같은 카테고리)

## Output Format
JSON 형식으로 출력
```

### 4.3 예시 수에 따른 성능 변화

```
성능
 │
 │                    ●────────● (수렴)
 │               ●────┘
 │          ●────┘
 │     ●────┘
 │●────┘
 └────────────────────────────────── 예시 수
   0    2    4    6    8    10

- 0-shot: 기본 성능
- 2-shot: 급격한 성능 향상
- 4-shot: 안정적 성능
- 6+ shot: 수렴 (추가 효과 감소)
```

---

## 5. 실험 결과 및 인사이트

### 5.1 주요 발견

| 발견 | 설명 |
|------|------|
| **Few-shot 효과** | 2-4개 예시만으로 Multi-Intent 생성 가능 |
| **예시 순서** | 쉬운 예시 → 어려운 예시 순서가 효과적 |
| **구조화** | 출력 형식 명시 시 일관성 향상 |
| **후처리** | 생성 후 검증/필터링으로 품질 향상 |

### 5.2 실패 케이스 분석

| 실패 유형 | 원인 | 해결 방안 |
|-----------|------|-----------|
| **과잉 감지** | 연결 조사를 Multi로 오인 | 함정 예시 추가 |
| **누락** | 암묵적 Intent 미감지 | 맥락 정보 추가 |
| **혼동** | 유사 카테고리 구분 실패 | 카테고리 정의 명확화 |

### 5.3 프롬프트 최적화 가이드라인

```
┌─────────────────────────────────────────────────────────────┐
│            Prompt Optimization Guidelines                    │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  1. Task Description                                         │
│     - 명확하고 구체적인 역할 정의                            │
│     - Multi-Intent 가능성 명시                               │
│                                                              │
│  2. Category Definition                                      │
│     - 각 카테고리의 범위 명확화                              │
│     - 경계 케이스 설명                                       │
│                                                              │
│  3. Example Selection                                        │
│     - Single Intent 2-3개                                    │
│     - Multi Intent 2-3개                                     │
│     - Tricky Cases 2-3개                                     │
│                                                              │
│  4. Output Format                                            │
│     - 구조화된 형식 (JSON)                                   │
│     - 필수 필드 명시                                         │
│                                                              │
│  5. Post-processing                                          │
│     - 출력 검증                                              │
│     - 신뢰도 기반 필터링                                     │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

---

## 6. Eco2 chat_worker 적용점

### 6.1 현재 구현과의 연결

| 논문 개념 | chat_worker 적용 |
|-----------|------------------|
| Multi-Intent | `MultiIntentClassifier` |
| Few-shot | `multi_intent_detect.txt` 프롬프트 |
| Post-processing | `_parse_multi_detect_response()` |

### 6.2 개선 방향

#### A. Few-shot 예시 강화

현재 프롬프트의 예시를 논문 가이드라인에 맞게 확장:

```markdown
## Examples (확장)

### Single Intent - 명확한 케이스
- "페트병 어떻게 버려?" → {"is_multi": false, "categories": ["waste"]}
- "캐릭터 뭐야?" → {"is_multi": false, "categories": ["character"]}
- "근처 재활용센터 어디야?" → {"is_multi": false, "categories": ["location"]}

### Single Intent - 함정 케이스 (같은 카테고리)
- "페트병, 캔, 유리병 어떻게 버려?" → {"is_multi": false, "categories": ["waste"]}
- "플라스틱이랑 비닐 같이 버려도 돼?" → {"is_multi": false, "categories": ["waste"]}

### Single Intent - 함정 케이스 (조사/접속사)
- "페트병도 재활용 되나요?" → {"is_multi": false, "categories": ["waste"]}
- "근처 센터랑 거리도 알려줘" → {"is_multi": false, "categories": ["location"]}

### Multi Intent - 명확한 케이스
- "페트병 버리고 캐릭터도 알려줘" → {"is_multi": true, "categories": ["waste", "character"]}
- "재활용센터 어디야, 그리고 유리병은?" → {"is_multi": true, "categories": ["location", "waste"]}
- "최신 정책 알려주고 내 캐릭터도" → {"is_multi": true, "categories": ["web_search", "character"]}
```

#### B. Structured Output 도입

논문의 "구조화된 출력" 권장사항을 적용:

```python
from pydantic import BaseModel

class MultiIntentDetection(BaseModel):
    is_multi: bool
    reason: str
    detected_categories: list[str]
    confidence: float

# LLM API의 Structured Output 기능 활용
# → 파싱 실패 0%, 타입 안전성 보장
```

#### C. 신뢰도 기반 후처리

```python
def _post_process_detection(self, result: MultiIntentDetection) -> MultiIntentDetection:
    """논문의 후처리 가이드라인 적용."""
    
    # 1. 신뢰도 낮으면 Single로 보수적 판단
    if result.confidence < 0.7 and result.is_multi:
        return MultiIntentDetection(
            is_multi=False,
            reason="Low confidence, conservative fallback",
            detected_categories=[result.detected_categories[0]],
            confidence=result.confidence,
        )
    
    # 2. 같은 카테고리 중복 제거
    unique_categories = list(dict.fromkeys(result.detected_categories))
    if len(unique_categories) == 1:
        result.is_multi = False
    
    return result
```

---

## 참고 자료

- [arxiv:2304.11384](https://arxiv.org/abs/2304.11384) - 원본 논문
- [OpenAI Structured Outputs](https://platform.openai.com/docs/guides/structured-outputs)
- [Gemini Structured Output](https://ai.google.dev/gemini-api/docs/structured-output)

