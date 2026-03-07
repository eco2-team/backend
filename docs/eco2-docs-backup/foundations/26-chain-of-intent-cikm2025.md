# Chain-of-Intent: Intent-Driven Multi-Turn Classification

> **논문**: "From Intents to Conversations: Generating Intent-Driven Dialogues with Contrastive Learning for Multi-Turn Classification"  
> **출처**: [arxiv:2411.14252](https://arxiv.org/abs/2411.14252) - CIKM '25 (November 2025, Seoul)  
> **키워드**: Multi-Turn Intent Classification, HMM, LLM, Contrastive Learning, MINT-CL

---

## 목차

1. [논문 개요](#1-논문-개요)
2. [Chain-of-Intent 프레임워크](#2-chain-of-intent-프레임워크)
3. [MINT-CL: Multi-Task Contrastive Learning](#3-mint-cl-multi-task-contrastive-learning)
4. [MINT-E 데이터셋](#4-mint-e-데이터셋)
5. [실험 결과](#5-실험-결과)
6. [Eco2 chat_worker 적용점](#6-eco2-chat_worker-적용점)

---

## 1. 논문 개요

### 1.1 연구 배경

e-커머스 플랫폼의 챗봇은 Multi-Turn 대화에서 각 턴의 사용자 의도를 정확히 파악해야 합니다. 그러나:

| 문제 | 설명 |
|------|------|
| **데이터 부족** | Multi-Turn Intent 데이터셋 구축 비용이 높음 |
| **다국어** | 여러 언어/시장에 대응해야 함 |
| **맥락 의존** | 이전 대화를 무시하면 정확도 하락 |
| **Intent 다양성** | 산업용 챗봇은 수백 개의 Intent 처리 |

### 1.2 핵심 기여

```
┌─────────────────────────────────────────────────────────────┐
│                    논문의 3가지 기여                          │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  1. Chain-of-Intent                                          │
│     - HMM + LLM 결합                                         │
│     - Intent 시퀀스 모델링                                   │
│     - Self-play 대화 생성                                    │
│                                                              │
│  2. MINT-CL                                                  │
│     - Multi-Task Contrastive Learning                        │
│     - Turn + Context 인코딩                                  │
│     - 적은 데이터로 높은 정확도                              │
│                                                              │
│  3. MINT-E Dataset                                           │
│     - 8개 언어/시장                                          │
│     - 다국어 Multi-Turn Intent 코퍼스                        │
│     - 연구 커뮤니티에 공개                                   │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

### 1.3 Multi-Turn Intent Classification (MTIC)

```
대화 예시:

Turn 1: User: "안녕하세요"           → Intent: Chitchat
Turn 2: Bot:  "안녕하세요! 무엇을..."
Turn 3: User: "페트병 어떻게 버려요?" → Intent: Waste_Disposal
Turn 4: Bot:  "페트병은 라벨을..."
Turn 5: User: "근처 수거함은?"        → Intent: Location_Search
Turn 6: Bot:  "가까운 수거함은..."

MTIC = 각 Turn의 Intent를 맥락을 고려하여 분류
```

---

## 2. Chain-of-Intent 프레임워크

### 2.1 아키텍처 개요

```
┌─────────────────────────────────────────────────────────────┐
│                  Chain-of-Intent Architecture                │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  Phase 1: Intent Transition Extraction                       │
│  ┌─────────────────────────────────────────────────────┐   │
│  │                                                      │   │
│  │   Historical Chat Logs                               │   │
│  │          │                                           │   │
│  │          ▼                                           │   │
│  │   ┌─────────────────────────────────────────┐       │   │
│  │   │      Intent Sequence Mining              │       │   │
│  │   │                                          │       │   │
│  │   │  [chitchat] → [waste] → [location]      │       │   │
│  │   │  [waste] → [waste] → [character]        │       │   │
│  │   │  [general] → [waste] → [location]       │       │   │
│  │   └─────────────────────────────────────────┘       │   │
│  │          │                                           │   │
│  │          ▼                                           │   │
│  │   ┌─────────────────────────────────────────┐       │   │
│  │   │      HMM Transition Matrix               │       │   │
│  │   │                                          │       │   │
│  │   │          To:  chitchat waste location   │       │   │
│  │   │  From:                                   │       │   │
│  │   │  chitchat    0.2     0.5    0.3         │       │   │
│  │   │  waste       0.1     0.4    0.5         │       │   │
│  │   │  location    0.3     0.3    0.4         │       │   │
│  │   └─────────────────────────────────────────┘       │   │
│  │                                                      │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                              │
│  Phase 2: Intent-Driven Dialogue Generation                  │
│  ┌─────────────────────────────────────────────────────┐   │
│  │                                                      │   │
│  │   HMM samples Intent Chain:                         │   │
│  │   [chitchat → waste → location]                     │   │
│  │          │                                           │   │
│  │          ▼                                           │   │
│  │   ┌─────────────────────────────────────────┐       │   │
│  │   │           LLM Self-Play                  │       │   │
│  │   │                                          │       │   │
│  │   │  Intent: chitchat                        │       │   │
│  │   │  → User: "안녕하세요"                    │       │   │
│  │   │  → Bot: "안녕하세요! 무엇을..."          │       │   │
│  │   │                                          │       │   │
│  │   │  Intent: waste                           │       │   │
│  │   │  → User: "페트병 어떻게 버려요?"         │       │   │
│  │   │  → Bot: "페트병은 라벨을..."             │       │   │
│  │   │                                          │       │   │
│  │   │  Intent: location                        │       │   │
│  │   │  → User: "근처 수거함은?"                │       │   │
│  │   │  → Bot: "가까운 수거함은..."             │       │   │
│  │   └─────────────────────────────────────────┘       │   │
│  │                                                      │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

### 2.2 Hidden Markov Model (HMM) 역할

HMM은 Intent 시퀀스의 **전이 패턴**을 모델링합니다:

| 구성요소 | 역할 | 예시 |
|----------|------|------|
| **States** | Intent 카테고리 | {chitchat, waste, location, ...} |
| **Transition** | Intent 전이 확률 | P(waste→location) = 0.5 |
| **Emission** | Intent→발화 생성 | LLM이 담당 |

```python
# Intent Transition Matrix 예시
INTENT_TRANSITIONS = {
    "chitchat": {"chitchat": 0.2, "waste": 0.5, "location": 0.3},
    "waste":    {"chitchat": 0.1, "waste": 0.4, "location": 0.5},
    "location": {"chitchat": 0.3, "waste": 0.3, "location": 0.4},
}

# 의미: waste 질문 후 location 질문이 올 확률 = 0.5
```

### 2.3 LLM의 Emission Probability 역할

LLM은 주어진 Intent에 맞는 **자연스러운 발화**를 생성합니다:

```
┌─────────────────────────────────────────────────────────────┐
│              LLM as Emission Model                           │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  Input:                                                      │
│  - Target Intent: waste                                      │
│  - Dialogue Context: [이전 대화 히스토리]                    │
│  - Domain Knowledge: [e-commerce / 분리배출]                 │
│                                                              │
│  LLM Generation:                                             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  System: "당신은 {intent}에 해당하는 질문을 생성"    │   │
│  │  Context: [이전 대화]                                │   │
│  │  Output: "페트병은 어떻게 분리배출 하나요?"          │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                              │
│  → Intent에 맞는 자연스러운 발화 생성                        │
│  → 맥락을 고려한 coherent 대화                               │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

---

## 3. MINT-CL: Multi-Task Contrastive Learning

### 3.1 프레임워크 개요

```
┌─────────────────────────────────────────────────────────────┐
│                    MINT-CL Architecture                      │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  Input: Multi-Turn Dialogue                                  │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  Turn 1: "안녕하세요"                                │   │
│  │  Turn 2: "페트병 어떻게 버려요?"                     │   │
│  │  Turn 3: "근처 수거함은?" ← Current Turn            │   │
│  └─────────────────────────────────────────────────────┘   │
│                          │                                   │
│           ┌──────────────┴──────────────┐                   │
│           ▼                              ▼                   │
│  ┌─────────────────┐          ┌─────────────────┐          │
│  │  Turn Encoder   │          │ Context Encoder │          │
│  │                 │          │                 │          │
│  │ "근처 수거함은?"│          │ Turn 1 + Turn 2 │          │
│  │      ↓          │          │      ↓          │          │
│  │  turn_emb       │          │  context_emb    │          │
│  └────────┬────────┘          └────────┬────────┘          │
│           │                              │                   │
│           └──────────────┬──────────────┘                   │
│                          ▼                                   │
│                  ┌─────────────────┐                        │
│                  │    Fusion       │                        │
│                  │  turn + context │                        │
│                  └────────┬────────┘                        │
│                          │                                   │
│           ┌──────────────┼──────────────┐                   │
│           ▼              ▼              ▼                    │
│  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐           │
│  │ Task 1:     │ │ Task 2:     │ │ Task 3:     │           │
│  │ Intent      │ │ Next Intent │ │ Contrastive │           │
│  │ Classification│ │ Prediction │ │ Learning    │           │
│  └─────────────┘ └─────────────┘ └─────────────┘           │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

### 3.2 Multi-Task Learning 구성

| Task | 목적 | Loss |
|------|------|------|
| **Task 1: Intent Classification** | 현재 턴의 Intent 분류 | Cross-Entropy |
| **Task 2: Next Intent Prediction** | 다음 턴의 Intent 예측 | Cross-Entropy |
| **Task 3: Contrastive Learning** | 같은 Intent 발화 유사하게 | InfoNCE Loss |

### 3.3 Contrastive Learning 상세

```
┌─────────────────────────────────────────────────────────────┐
│              Contrastive Learning in MINT-CL                 │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  목표: 같은 Intent의 발화는 가깝게, 다른 Intent는 멀게      │
│                                                              │
│  Embedding Space:                                            │
│                                                              │
│        waste Intent 클러스터                                 │
│        ┌─────────────────┐                                  │
│        │  ●"페트병 버려" │                                  │
│        │  ●"캔 분리배출" │                                  │
│        │  ●"유리병 처리" │                                  │
│        └─────────────────┘                                  │
│                                                              │
│        location Intent 클러스터                              │
│        ┌─────────────────┐                                  │
│        │  ○"센터 어디"   │                                  │
│        │  ○"가까운 곳"   │                                  │
│        │  ○"수거함 위치" │                                  │
│        └─────────────────┘                                  │
│                                                              │
│  InfoNCE Loss:                                               │
│  L = -log( exp(sim(q,k+)/τ) / Σ exp(sim(q,k)/τ) )          │
│                                                              │
│  q: query (현재 발화)                                        │
│  k+: positive (같은 Intent 발화)                             │
│  k: all (배치 내 모든 발화)                                  │
│  τ: temperature                                              │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

### 3.4 Context Encoding

이전 대화 맥락이 현재 Intent 분류에 미치는 영향:

```python
# Context가 없을 때
message = "그럼 근처는?"
# → Intent 불명확 (location? general?)

# Context가 있을 때
context = [
    {"role": "user", "content": "페트병 어떻게 버려요?", "intent": "waste"},
    {"role": "bot", "content": "페트병은 라벨을 제거하고..."},
]
message = "그럼 근처는?"
# → Intent: location (맥락상 재활용센터/수거함 질문)
```

---

## 4. MINT-E 데이터셋

### 4.1 데이터셋 특성

| 항목 | 값 |
|------|-----|
| **언어/시장** | 8개 (다국어) |
| **대화 유형** | FAQ + TOD + Chitchat 혼합 |
| **Intent 수** | 수백 개 (시장별 상이) |
| **턴 수** | Multi-turn (평균 4-6턴) |
| **도메인** | e-commerce |

### 4.2 Intent 유형 분류

```
┌─────────────────────────────────────────────────────────────┐
│                    Intent Types in MINT-E                    │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  1. FAQ (Frequently Asked Questions)                         │
│     - 정책 관련 질문                                         │
│     - 서비스 이용 방법                                       │
│     예: "반품은 어떻게 하나요?"                              │
│                                                              │
│  2. TOD (Task-Oriented Dialogue)                             │
│     - 특정 작업 수행 요청                                    │
│     - 정보 제공/수정                                         │
│     예: "주문 취소해 주세요"                                 │
│                                                              │
│  3. Chitchat                                                 │
│     - 일반 대화                                              │
│     - 인사/감사                                              │
│     예: "안녕하세요", "감사합니다"                           │
│                                                              │
│  실제 대화에서는 이 세 유형이 혼합되어 나타남                │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

### 4.3 데이터 생성 파이프라인

```
Historical Logs → Intent Mining → HMM Training → 
Chain-of-Intent Sampling → LLM Self-Play → MINT-E Dataset
```

---

## 5. 실험 결과

### 5.1 MTIC 성능 비교

| 모델 | Accuracy | F1-Score |
|------|----------|----------|
| BERT (baseline) | 78.2% | 0.76 |
| RoBERTa | 80.1% | 0.78 |
| **MINT-CL** | **84.7%** | **0.83** |

### 5.2 다국어 성능

| 시장 | 언어 | Accuracy |
|------|------|----------|
| US | English | 85.2% |
| KR | Korean | 84.1% |
| JP | Japanese | 83.8% |
| TW | Chinese | 84.5% |

### 5.3 Context의 중요성

```
┌─────────────────────────────────────────────────────────────┐
│           Context가 정확도에 미치는 영향                      │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  Accuracy (%)                                                │
│  │                                                           │
│  │  84.7 ●──────────────────────● MINT-CL (full context)   │
│  │       │                                                   │
│  │  80.3 │        ●──────────────● 2-turn context          │
│  │       │        │                                          │
│  │  76.8 │        │       ●──────● 1-turn context          │
│  │       │        │       │                                  │
│  │  72.4 │        │       │      ●── No context             │
│  │       │        │       │      │                           │
│  └───────┴────────┴───────┴──────┴───────────────────────── │
│          0        1       2      3+ (context turns)          │
│                                                              │
│  → Context가 많을수록 정확도 향상                             │
│  → 2-turn context만으로도 상당한 개선                        │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

### 5.4 핵심 인사이트

| 인사이트 | 설명 |
|----------|------|
| **맥락 필수** | 이전 Intent가 현재 분류에 큰 영향 |
| **전이 패턴** | Intent 간 전이 확률이 예측에 유용 |
| **Contrastive 효과** | 같은 Intent 발화 클러스터링 개선 |
| **다국어 일반화** | 한 언어로 학습해도 다른 언어에 적용 가능 |

---

## 6. Eco2 chat_worker 적용점

### 6.1 현재 구현과의 연결

| 논문 개념 | chat_worker 적용 |
|-----------|------------------|
| Intent Transition | `INTENT_TRANSITION_BOOST` (신규) |
| Context Encoding | `context` 파라미터 (기존) |
| Multi-Turn | Checkpointer 기반 (기존) |

### 6.2 Intent Transition Boost 구현

논문의 HMM 전이 확률 개념을 간소화하여 적용:

```python
# intent_classifier.py에 추가

# Intent 전이 확률 (실제 로그 기반으로 튜닝 필요)
INTENT_TRANSITION_BOOST = {
    # previous_intent → {next_intent: boost_score}
    Intent.WASTE: {
        Intent.LOCATION: 0.15,    # waste 후 location 질문 빈번
        Intent.CHARACTER: 0.05,   # waste 후 character 가끔
    },
    Intent.GENERAL: {
        Intent.WASTE: 0.10,       # 인사 후 본론으로
    },
    Intent.LOCATION: {
        Intent.WASTE: 0.10,       # 센터 질문 후 버리는 방법
    },
}

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

### 6.3 Context-Aware Classification

논문의 맥락 인코딩 개념 강화:

```python
def _build_prompt_with_context(
    self,
    message: str,
    context: dict | None,
) -> str:
    """MINT-CL 스타일의 맥락 포함 프롬프트."""
    if not context:
        return message
    
    parts = []
    
    # 1. 이전 Intent 히스토리 (전이 패턴 힌트)
    previous_intents = context.get("previous_intents", [])
    if previous_intents:
        recent = previous_intents[-2:]  # 최근 2개
        parts.append(f"[이전 의도: {' → '.join(recent)}]")
    
    # 2. 대화 히스토리 (맥락 이해)
    history = context.get("conversation_history", [])
    if history:
        for turn in history[-2:]:  # 최근 2턴
            role = turn.get("role", "user")
            content = turn.get("content", "")[:50]
            parts.append(f"[{role}: {content}...]")
    
    # 3. 현재 메시지
    parts.append(f"[현재: {message}]")
    
    return "\n".join(parts)
```

### 6.4 Contrastive Learning 아이디어 (향후)

임베딩 기반 유사도 캐싱으로 LLM 호출 감소:

```
┌─────────────────────────────────────────────────────────────┐
│            Intent Embedding Cache (향후 적용)                │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  1. 발화 임베딩 저장                                         │
│  ┌─────────────────────────────────────────────────────┐   │
│  │   "페트병 버려" → emb_1 → Intent.WASTE              │   │
│  │   "캔 분리배출" → emb_2 → Intent.WASTE              │   │
│  │   "캐릭터 뭐야" → emb_3 → Intent.CHARACTER          │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                              │
│  2. 새 쿼리 분류 시                                          │
│  ┌─────────────────────────────────────────────────────┐   │
│  │   "플라스틱 어떻게 버려요?"                          │   │
│  │          │                                           │   │
│  │          ▼ embedding                                │   │
│  │   cosine_sim(emb, emb_1) = 0.92                     │   │
│  │          │                                           │   │
│  │          ▼                                           │   │
│  │   → Intent.WASTE (LLM 호출 없이)                    │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                              │
│  효과: LLM 호출 50%+ 감소 예상                               │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

### 6.5 Next Intent Prediction 활용 (향후)

사용자의 다음 질문을 예측하여 선제적 정보 제공:

```python
# 예: waste 질문 후 location 질문이 올 확률이 높으면
if current_intent == Intent.WASTE:
    next_likely = Intent.LOCATION  # P=0.5
    
    # 선제적 정보 포함
    answer += "\n\n💡 가까운 재활용센터도 안내해 드릴까요?"
```

---

## 참고 자료

- [arxiv:2411.14252](https://arxiv.org/abs/2411.14252) - 원본 논문
- CIKM '25: 34th ACM International Conference on Information and Knowledge Management
- [Hidden Markov Model](https://en.wikipedia.org/wiki/Hidden_Markov_model)
- [Contrastive Learning](https://lilianweng.github.io/posts/2021-05-31-contrastive/)

