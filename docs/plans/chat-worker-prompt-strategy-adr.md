# Chat Worker Prompt Strategy Architecture Decision Report

> **작성일**: 2026-01-14  
> **상태**: Proposed 📋  
> **관련 서비스**: chat_worker  
> **관련 문서**: 
> - [21-chat-vision-processing.md](../blogs/applied/21-chat-vision-processing.md)
> - [24-multi-agent-prompt-patterns.md](../foundations/24-multi-agent-prompt-patterns.md)

---

## 📋 Executive Summary

본 ADR은 Eco² 챗봇 `chat_worker`의 Answer 노드 프롬프트 전략에 대한 아키텍처 의사결정을 문서화합니다.

**핵심 결정사항:**
1. **프롬프트 구조**: 단일 통합 프롬프트 → **하이브리드 (Global + Local) 프롬프트**
2. **Intent별 지침**: 코드 내장 → **외부 파일 분리 + 동적 로딩**
3. **Answer 합성**: 단일 템플릿 → **컨텍스트 인젝션 기반 동적 합성**

---

## 1. 배경

### 1.1 현재 구조

```python
# 현재: 단일 시스템 프롬프트 (answer_node.py)
ANSWER_SYSTEM_PROMPT = """너는 "이코"야, Eco² 앱의 친절한 분리배출 도우미.
## 성격
- 친절하고 귀여운 말투
- 환경 보호에 열정적
## 답변 규칙
...
"""
```

### 1.2 문제점

| 문제 | 설명 |
|------|------|
| **Intent 최적화 부재** | waste/character/location/general 모두 동일 프롬프트 |
| **토큰 낭비** | 불필요한 지침이 항상 포함 |
| **유지보수 어려움** | Intent 추가 시 프롬프트 전체 수정 필요 |
| **A/B 테스트 어려움** | 프롬프트 실험이 코드 배포 필요 |

### 1.3 서브에이전트 구조

```
chat_worker 파이프라인:

    ┌─────────┐
    │  Vision │ (이미지 입력 시)
    └────┬────┘
         │
         ▼
    ┌─────────┐
    │  Router │ Intent 분류
    └────┬────┘
         │
    ┌────┴────┬─────────────┬──────────────┐
    ▼         ▼             ▼              ▼
┌────────┐ ┌────────┐ ┌──────────┐ ┌─────────┐
│waste_  │ │char    │ │location  │ │general  │
│rag     │ │acter   │ │          │ │         │
└────┬───┘ └────┬───┘ └────┬─────┘ └────┬────┘
     │          │          │            │
     └──────────┴──────────┴────────────┘
                     │
                     ▼
              ┌───────────┐
              │  Answer   │ ← 프롬프트 전략 적용 지점
              └───────────┘
```

---

## 2. 선택지 분석

### 2.1 Option A: 단일 통합 프롬프트 (현재)

```python
SYSTEM_PROMPT = """
너는 이코야...
## 분리배출 규칙
## 캐릭터 규칙
## 위치 규칙
## 일반 규칙
"""
```

| 장점 | 단점 |
|------|------|
| 구현 단순 | Intent별 최적화 불가 |
| 일관된 캐릭터 유지 | 토큰 낭비 |
| | 프롬프트 길이 증가 |

**판정**: ❌ 확장성 부족

### 2.2 Option B: Intent별 완전 분리 프롬프트

```python
INTENT_PROMPTS = {
    "waste": "분리배출 전문가로서...",
    "character": "캐릭터 안내자로서...",
    "location": "위치 서비스로서...",
    "general": "환경 도우미로서...",
}
```

| 장점 | 단점 |
|------|------|
| Intent별 최적화 가능 | 캐릭터 일관성 깨짐 |
| 토큰 효율 | 프롬프트 파일 관리 부담 |
| | 중복 지침 발생 |

**판정**: ❌ 캐릭터 일관성 문제

### 2.3 Option C: 하이브리드 (Global + Local) ✅ 선택

```python
# Global: 캐릭터/톤 고정
GLOBAL_PROMPT = """너는 "이코"야...
## 성격
- 친절하고 귀여운 말투
"""

# Local: Intent별 지침 동적 주입
LOCAL_INSTRUCTIONS = {
    "waste": "## 분리배출 답변 지침\n1. RAG 컨텍스트 기반...",
    "character": "## 캐릭터 답변 지침\n1. 캐릭터 정보 자연스럽게...",
    ...
}

def build_prompt(intent: str) -> str:
    return f"{GLOBAL_PROMPT}\n{LOCAL_INSTRUCTIONS[intent]}"
```

| 장점 | 단점 |
|------|------|
| 캐릭터 일관성 유지 | 약간의 복잡도 증가 |
| Intent별 최적화 | 지침 섹션 관리 필요 |
| 토큰 효율 | |
| 확장성 (새 Intent 추가 용이) | |

**판정**: ✅ 채택

---

## 3. 이론적 근거

### 3.1 관련 연구

2025년 AI Agent 논문에서 확인된 주요 패턴:

| 논문 | 핵심 패턴 | 적용 |
|------|----------|------|
| **Local Prompt Optimization** | Global + Local 프롬프트 조합 | ✅ 하이브리드 구조 |
| **Multi-Agent Collaboration via Evolving Orchestration** | 상황별 동적 프롬프트 선택 | ✅ Intent 기반 선택 |
| **Mem0** | 단기 컨텍스트 + 장기 메모리 분리 | ✅ Checkpointer 연동 |
| **SEW: Self-Evolving Agentic Workflows** | 워크플로우 기반 프롬프트 진화 | 🔜 향후 적용 |

**참고**: [24-multi-agent-prompt-patterns.md](../foundations/24-multi-agent-prompt-patterns.md)

### 3.2 선행 사례 (중국 연구진)

| 프로젝트 | 기관 | 프롬프트 전략 |
|----------|------|---------------|
| **ChatDev** | 청화대 OpenBMB | 역할별 완전 분리 |
| **MetaGPT** | DeepWisdom | SOP + 역할 특화 |
| **AgentCoder** | - | 역할별 분리 + 반복 개선 |

**차이점**: 위 사례들은 **다른 페르소나**의 에이전트 협업이지만,  
우리는 **동일 캐릭터(이코)**가 다양한 질문에 답하는 구조 → **하이브리드** 적합

---

## 4. 최종 아키텍처

### 4.1 프롬프트 구조

```
┌─────────────────────────────────────────────────────────────────┐
│                    Hybrid Prompt Architecture                    │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │                    GLOBAL PROMPT                         │   │
│  │  (캐릭터 정의, 톤, 공통 규칙 - 모든 Intent에서 사용)     │   │
│  └─────────────────────────────────────────────────────────┘   │
│                              │                                   │
│                              ▼                                   │
│  ┌──────────┬──────────┬──────────┬──────────┐                 │
│  │  WASTE   │  CHAR    │ LOCATION │ GENERAL  │  LOCAL          │
│  │ INSTRUCT │ INSTRUCT │ INSTRUCT │ INSTRUCT │  INSTRUCTIONS   │
│  └──────────┴──────────┴──────────┴──────────┘                 │
│                              │                                   │
│                              ▼                                   │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │                    FINAL PROMPT                          │   │
│  │  = GLOBAL + LOCAL[intent]                                │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### 4.2 파일 구조

```
apps/chat_worker/infrastructure/assets/prompts/
├── global/
│   └── eco_character.txt        # 이코 캐릭터 정의
├── local/
│   ├── waste_instruction.txt    # 분리배출 지침
│   ├── character_instruction.txt # 캐릭터 지침
│   ├── location_instruction.txt  # 위치 지침
│   └── general_instruction.txt   # 일반 지침
└── __init__.py                   # 프롬프트 로더
```

### 4.3 구현 코드

```python
# apps/chat_worker/infrastructure/orchestration/prompts/loader.py
from pathlib import Path
from functools import lru_cache

PROMPTS_DIR = Path(__file__).parent.parent / "assets" / "prompts"


@lru_cache(maxsize=10)
def load_prompt(category: str, name: str) -> str:
    """프롬프트 파일 로드 (캐싱)."""
    path = PROMPTS_DIR / category / f"{name}.txt"
    return path.read_text(encoding="utf-8")


class PromptBuilder:
    """하이브리드 프롬프트 빌더."""
    
    def __init__(self):
        self._global = load_prompt("global", "eco_character")
        self._local = {
            "waste": load_prompt("local", "waste_instruction"),
            "character": load_prompt("local", "character_instruction"),
            "location": load_prompt("local", "location_instruction"),
            "general": load_prompt("local", "general_instruction"),
        }
    
    def build(self, intent: str) -> str:
        """Intent에 따른 최종 프롬프트 생성."""
        local = self._local.get(intent, self._local["general"])
        return f"{self._global}\n\n{local}"
```

```python
# apps/chat_worker/infrastructure/orchestration/langgraph/nodes/answer_node.py
from chat_worker.infrastructure.orchestration.prompts.loader import PromptBuilder

prompt_builder = PromptBuilder()

async def answer_node(state: dict[str, Any]) -> dict[str, Any]:
    intent = state.get("intent", "general")
    
    # 동적 프롬프트 생성
    system_prompt = prompt_builder.build(intent)
    
    # AnswerContext 구성
    context = AnswerContext(
        classification=state.get("classification_result"),
        disposal_rules=state.get("disposal_rules", {}).get("data"),
        character_context=state.get("character_context"),
        location_context=state.get("location_context"),
        user_input=state.get("message"),
    )
    
    # LLM 호출 (스트리밍)
    async for token in answer_service.generate_stream(
        context=context,
        system_prompt=system_prompt,  # 동적 프롬프트
    ):
        await event_publisher.notify_token(task_id=job_id, content=token)
        ...
```

---

## 5. 프롬프트 템플릿

### 5.1 Global Prompt (`eco_character.txt`)

```
# Identity
너는 "이코"야, Eco² 앱의 친절한 분리배출 도우미.

# Personality
- 친근하고 따뜻한 말투
- 환경 보호에 열정적
- 사용자를 격려하고 응원

# Common Rules
1. 자연어로 답변 (JSON 금지)
2. 3~5문장 내외로 간결하게
3. 잘못된 정보보다 모른다고 솔직히
4. Markdown 서식 사용 가능
```

### 5.2 Local Prompts

#### waste_instruction.txt
```
# Waste Disposal Instructions

## 컨텍스트 활용
1. disposal_rules (RAG 결과) 기반으로 답변
2. classification (분류 결과) 있으면 언급
3. situation_tags 기반 개선점 안내

## 답변 구조
1. 핵심 답변 (1~2문장)
2. 구체적 배출 방법
3. 상태 개선 팁 (있는 경우)

## 예시
Input: "페트병 어떻게 버려요?"
Output: 페트병은 **투명 페트병 전용 수거함**에 버리면 돼요!
라벨을 떼고, 내용물을 비운 뒤 납작하게 압착해서 배출해주세요.
```

#### character_instruction.txt
```
# Character Instructions

## 컨텍스트 활용
1. character_context에서 캐릭터 정보 추출
2. 친근한 대화체로 소개

## 답변 구조
1. 캐릭터 이름/특징 소개
2. 획득 방법 안내 (필요시)

## 예시
Input: "내 캐릭터 뭐야?"
Output: 지금 함께하고 있는 친구는 **푸른숲 다람쥐**예요!
재활용을 잘하면 더 다양한 친구들을 만날 수 있어요.
```

#### location_instruction.txt
```
# Location Instructions

## 컨텍스트 활용
1. location_context에서 수거함/센터 정보 추출
2. 운영 시간, 위치 정보 포함

## 답변 구조
1. 근처 시설 안내
2. 위치/운영시간 정보
3. 추가 팁 (있는 경우)

## 예시
Input: "근처 재활용 센터 알려줘"
Output: 가장 가까운 곳은 **강남구 재활용센터**예요!
주소: 서울시 강남구 테헤란로 123
운영시간: 평일 09:00~18:00
```

#### general_instruction.txt
```
# General Instructions

## 답변 범위
1. 분리배출, 재활용 일반 상식
2. 탄소중립, 제로웨이스트 트렌드
3. 인사, 감사 등 일반 대화

## 답변 구조
1. 질문에 대한 직접 답변
2. 환경 주제로 자연스럽게 연결

## 예시
Input: "안녕!"
Output: 안녕하세요! 저는 분리배출 도우미 **이코**예요.
오늘도 지구를 위한 작은 실천을 함께해요!
```

---

## 6. 기대 효과

| 측면 | Before | After |
|------|--------|-------|
| **토큰 효율** | 모든 지침 포함 (~500 tokens) | Intent별 (~200 tokens) |
| **캐릭터 일관성** | ✅ 유지 | ✅ 유지 |
| **Intent 최적화** | ❌ 불가 | ✅ 가능 |
| **유지보수** | 코드 수정 필요 | 텍스트 파일만 수정 |
| **A/B 테스트** | 코드 배포 필요 | ConfigMap 교체로 가능 |

---

## 7. 향후 계획

### 7.1 Phase 1: 하이브리드 프롬프트 구현 ✅
- Global/Local 프롬프트 파일 분리
- PromptBuilder 클래스 구현
- answer_node 수정

### 7.2 Phase 2: 프롬프트 최적화
- A/B 테스트 프레임워크 도입
- 프롬프트 성능 메트릭 수집
- Local Prompt Optimization 논문 기반 자동 최적화 검토

### 7.3 Phase 3: Self-Evolving Prompts (장기)
- SEW 논문 기반 자기 진화 프롬프트 검토
- 사용자 피드백 기반 프롬프트 개선

---

## 8. 결론

### 8.1 핵심 의사결정

| 항목 | 초기 방안 | 최종 결정 | 변경 이유 |
|------|----------|----------|----------|
| 프롬프트 구조 | 단일 통합 | **하이브리드** | Intent별 최적화 + 캐릭터 일관성 |
| 저장 방식 | 코드 내장 | **외부 파일** | 유지보수, A/B 테스트 용이 |
| 로딩 방식 | 매번 로드 | **LRU 캐싱** | 성능 최적화 |

### 8.2 적용 범위

- `chat_worker` Answer 노드
- 향후 `scan_worker` Answer 노드 통합 검토

---

## 참고 자료

- [ai-agent-papers (GitHub)](https://github.com/masamasa59/ai-agent-papers) - 2025 AI Agent 논문 모음
- [Local Prompt Optimization (arxiv:2504.20355)](https://arxiv.org/abs/2504.20355) - Global + Local 프롬프트 패턴
- [Multi-Agent Collaboration via Evolving Orchestration (arxiv:2505.19591)](https://arxiv.org/abs/2505.19591) - 동적 오케스트레이션
- [Mem0 (arxiv:2504.19413)](https://arxiv.org/abs/2504.19413) - 프로덕션 레벨 에이전트 메모리
- [SEW (arxiv:2505.18646)](https://arxiv.org/abs/2505.18646) - Self-Evolving 워크플로우
- [FlowReasoner (arxiv:2504.15257)](https://arxiv.org/abs/2504.15257) - 메타 에이전트 프롬프트 선택
- [ChatDev (arxiv:2307.07924)](https://arxiv.org/abs/2307.07924) - 역할 기반 멀티 에이전트
- [MetaGPT (arxiv:2308.00352)](https://arxiv.org/abs/2308.00352) - SOP 기반 멀티 에이전트

