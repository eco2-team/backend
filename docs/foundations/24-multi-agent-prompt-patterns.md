# Multi-Agent Prompt Patterns: 2025년 최신 연구 동향

> 멀티 에이전트 시스템에서의 프롬프트 설계 패턴을 최신 논문 기반으로 분석합니다.
> 
> **참고**: [ai-agent-papers (GitHub)](https://github.com/masamasa59/ai-agent-papers)
> **관련 ADR**: [chat-worker-prompt-strategy-adr.md](../plans/chat-worker-prompt-strategy-adr.md)

---

## 목차

1. [개요](#1-개요)
2. [프롬프트 패턴 분류](#2-프롬프트-패턴-분류)
3. [2025년 주요 논문 분석](#3-2025년-주요-논문-분석)
4. [선행 연구 (2023-2024)](#4-선행-연구-2023-2024)
5. [패턴 비교 및 선택 가이드](#5-패턴-비교-및-선택-가이드)
6. [적용 사례: Eco² chat_worker](#6-적용-사례-eco²-chat_worker)

---

## 1. 개요

### 1.1 멀티 에이전트 시스템의 프롬프트 도전과제

멀티 에이전트 LLM 시스템에서 프롬프트 설계는 다음 도전과제를 해결해야 합니다:

| 도전과제 | 설명 |
|----------|------|
| **일관성** | 여러 에이전트가 동일한 "성격"이나 "브랜드"를 유지 |
| **특화** | 각 에이전트/태스크에 맞는 전문 지침 제공 |
| **효율성** | 불필요한 토큰 낭비 방지 |
| **확장성** | 새로운 에이전트/태스크 추가 용이 |
| **유지보수** | 프롬프트 수정이 코드 변경 없이 가능 |

### 1.2 프롬프트 계층 구조

```
┌─────────────────────────────────────────────────────────────┐
│                    Prompt Hierarchy                          │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  Level 1: System Identity (고정)                            │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ "너는 이코야, Eco² 앱의 친절한 분리배출 도우미"      │   │
│  └─────────────────────────────────────────────────────┘   │
│                          │                                   │
│  Level 2: Task Instructions (동적)                          │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ "분리배출 질문에는 RAG 컨텍스트 기반으로 답변..."    │   │
│  └─────────────────────────────────────────────────────┘   │
│                          │                                   │
│  Level 3: Context Data (런타임)                             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ disposal_rules, classification, location_context    │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

---

## 2. 프롬프트 패턴 분류

### 2.1 Pattern A: 단일 통합 프롬프트 (Unified Prompt)

```python
SYSTEM_PROMPT = """
너는 이코야, 분리배출 도우미.

## 분리배출 질문 시
- RAG 컨텍스트 기반 답변
- 분류 결과 언급

## 캐릭터 질문 시
- 캐릭터 정보 자연스럽게 소개

## 위치 질문 시
- 근처 수거함/센터 안내

## 일반 질문 시
- 환경 관련 상식 답변
"""
```

| 장점 | 단점 |
|------|------|
| 구현 단순 | 토큰 낭비 |
| 단일 파일 관리 | Intent별 최적화 어려움 |
| | 프롬프트 길이 증가 |

**적합한 경우**: Intent가 2-3개인 간단한 시스템

### 2.2 Pattern B: 역할별 완전 분리 (Role-Based Separation)

```python
ROLE_PROMPTS = {
    "waste_expert": "분리배출 전문가로서 정확한 정보를 제공...",
    "character_guide": "캐릭터 안내자로서 친근하게 소개...",
    "location_service": "위치 서비스로서 정확한 좌표 기반...",
}
```

| 장점 | 단점 |
|------|------|
| 역할별 최적화 | 캐릭터 일관성 깨짐 |
| 토큰 효율 | 중복 지침 발생 |
| | 프롬프트 파일 관리 부담 |

**적합한 경우**: 완전히 다른 페르소나의 에이전트 협업 (ChatDev, MetaGPT)

### 2.3 Pattern C: 하이브리드 (Global + Local) ⭐ 권장

```python
# Global: 모든 에이전트에 공통
GLOBAL_PROMPT = """너는 이코야, 분리배출 도우미.
## 성격
- 친절하고 귀여운 말투
"""

# Local: 태스크별 지침
LOCAL_INSTRUCTIONS = {
    "waste": "## 분리배출 답변\n1. RAG 기반...",
    "character": "## 캐릭터 답변\n1. 친근하게...",
}

def build_prompt(intent: str) -> str:
    return f"{GLOBAL_PROMPT}\n{LOCAL_INSTRUCTIONS[intent]}"
```

| 장점 | 단점 |
|------|------|
| 캐릭터 일관성 유지 | 약간의 복잡도 |
| 태스크별 최적화 | 지침 섹션 관리 필요 |
| 토큰 효율 | |
| 확장성 | |

**적합한 경우**: 동일 캐릭터가 다양한 태스크 수행 (Eco² chat_worker)

---

## 3. 2025년 주요 논문 분석

### 3.1 Local Prompt Optimization

> **출처**: [arxiv:2504.20355](https://arxiv.org/abs/2504.20355) - April 2025

**핵심 아이디어**: 전역(Global) 프롬프트와 지역(Local) 프롬프트를 분리하여,
각 태스크/노드에서 Local 프롬프트만 최적화

```
┌─────────────────────────────────────────────────────────────┐
│                Local Prompt Optimization                     │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌─────────────────────────────────────────────────────┐   │
│  │           GLOBAL PROMPT (고정)                       │   │
│  │   - 시스템 Identity                                  │   │
│  │   - 공통 규칙                                        │   │
│  └─────────────────────────────────────────────────────┘   │
│                          │                                   │
│           ┌──────────────┼──────────────┐                   │
│           ▼              ▼              ▼                    │
│  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐           │
│  │ Local A     │ │ Local B     │ │ Local C     │           │
│  │ (최적화 ↻) │ │ (최적화 ↻) │ │ (최적화 ↻) │           │
│  └─────────────┘ └─────────────┘ └─────────────┘           │
│                                                              │
│  최적화: RL 또는 자동 프롬프트 튜닝으로 Local만 개선        │
└─────────────────────────────────────────────────────────────┘
```

**적용 포인트**:
- Global = 캐릭터 정의 (이코)
- Local = Intent별 지침 (waste/character/location/general)

---

### 3.2 Multi-Agent Collaboration via Evolving Orchestration

> **출처**: [arxiv:2505.19591](https://arxiv.org/abs/2505.19591) - May 2025

**핵심 아이디어**: Orchestrator가 상황에 따라 동적으로 에이전트와 프롬프트를 선택

```
┌─────────────────────────────────────────────────────────────┐
│            Evolving Orchestration Architecture               │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌─────────────────────────────────────────────────────┐   │
│  │               ORCHESTRATOR                           │   │
│  │   - 입력 분석                                        │   │
│  │   - 에이전트/프롬프트 동적 선택                      │   │
│  │   - 결과 합성                                        │   │
│  └─────────────────────────────────────────────────────┘   │
│                          │                                   │
│       Query Analysis     │   Dynamic Selection               │
│                          ▼                                   │
│  ┌───────────┬───────────┬───────────┬───────────┐         │
│  │ Agent A   │ Agent B   │ Agent C   │ Agent D   │         │
│  │ + PromptA │ + PromptB │ + PromptC │ + PromptD │         │
│  └───────────┴───────────┴───────────┴───────────┘         │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

**적용 포인트**:
- Router 노드 = Orchestrator 역할
- Intent 분류 결과에 따른 프롬프트 동적 선택

---

### 3.3 Mem0: Building Production-Ready AI Agents with Scalable Long-Term Memory

> **출처**: [arxiv:2504.19413](https://arxiv.org/abs/2504.19413) - April 2025

**핵심 아이디어**: 단기 컨텍스트(현재 요청)와 장기 메모리(대화 이력, 사용자 선호)를 분리

```
┌─────────────────────────────────────────────────────────────┐
│                    Mem0 Memory Architecture                  │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌─────────────────────────────────────────────────────┐   │
│  │              SHORT-TERM CONTEXT                      │   │
│  │   - 현재 요청 (message, image_url)                   │   │
│  │   - 서브에이전트 결과 (classification, rules)        │   │
│  └─────────────────────────────────────────────────────┘   │
│                          │                                   │
│                          ▼                                   │
│  ┌─────────────────────────────────────────────────────┐   │
│  │               LLM + PROMPT                           │   │
│  └─────────────────────────────────────────────────────┘   │
│                          ▲                                   │
│                          │                                   │
│  ┌─────────────────────────────────────────────────────┐   │
│  │              LONG-TERM MEMORY                        │   │
│  │   - 대화 이력 (Checkpointer)                         │   │
│  │   - 사용자 선호 (learned preferences)                │   │
│  │   - 자주 묻는 질문 패턴                              │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

**적용 포인트**:
- Short-term = AnswerContext (classification, disposal_rules, etc.)
- Long-term = Checkpointer (Redis L1 + PostgreSQL L2)

---

### 3.4 SEW: Self-Evolving Agentic Workflows for Automated Code Generation

> **출처**: [arxiv:2505.18646](https://arxiv.org/abs/2505.18646) - May 2025

**핵심 아이디어**: 워크플로우와 프롬프트가 자동으로 진화

```
┌─────────────────────────────────────────────────────────────┐
│              Self-Evolving Workflows (SEW)                   │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌───────────────────────────────────────────────────┐     │
│  │                WORKFLOW v1                         │     │
│  │   Node A → Node B → Node C                        │     │
│  │   Prompt A  Prompt B  Prompt C                    │     │
│  └───────────────────────────────────────────────────┘     │
│                          │                                   │
│                   Performance                                │
│                    Feedback                                  │
│                          ▼                                   │
│  ┌───────────────────────────────────────────────────┐     │
│  │              EVOLUTION ENGINE                      │     │
│  │   - 실패 분석                                      │     │
│  │   - 프롬프트 수정 제안                             │     │
│  │   - 워크플로우 구조 변경                           │     │
│  └───────────────────────────────────────────────────┘     │
│                          │                                   │
│                          ▼                                   │
│  ┌───────────────────────────────────────────────────┐     │
│  │                WORKFLOW v2                         │     │
│  │   Node A → Node B' → Node D → Node C              │     │
│  │   Prompt A  Prompt B'  Prompt D  Prompt C         │     │
│  └───────────────────────────────────────────────────┘     │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

**적용 포인트** (향후):
- 사용자 피드백 기반 프롬프트 자동 개선
- LLM 기반 프롬프트 리라이팅

---

### 3.5 FlowReasoner: Reinforcing Query-Level Meta-Agents

> **출처**: [arxiv:2504.15257](https://arxiv.org/abs/2504.15257) - April 2025

**핵심 아이디어**: 쿼리 레벨에서 메타 에이전트가 최적의 워크플로우/프롬프트 선택

```
User Query
    │
    ▼
┌───────────────────────────────────────────────────────────┐
│                    META AGENT                              │
│   - Query 분석                                             │
│   - 최적 워크플로우 선택                                   │
│   - 최적 프롬프트 조합 선택                                │
└───────────────────────────────────────────────────────────┘
    │
    ├── Query Type A → Workflow 1 + Prompts {A1, A2}
    ├── Query Type B → Workflow 2 + Prompts {B1, B2, B3}
    └── Query Type C → Workflow 3 + Prompts {C1}
```

**적용 포인트**:
- Router 노드가 Meta Agent 역할
- Intent에 따른 워크플로우 + 프롬프트 조합 선택

---

## 4. 선행 연구 (2023-2024)

### 4.1 ChatDev (청화대학교 OpenBMB, 2023)

> **논문**: "Communicative Agents for Software Development"  
> **arxiv**: 2307.07924

**프롬프트 전략**: 역할별 완전 분리

```
CEO     → "회사의 전략적 방향을 결정하는 역할..."
CTO     → "기술적 결정을 내리는 역할..."
Programmer → "코드를 작성하는 역할..."
Tester  → "테스트를 수행하는 역할..."
```

**특징**:
- 각 역할이 **완전히 다른 페르소나**
- 순차적 대화를 통한 협업
- 역할 전환 시 컨텍스트 전달

**우리와의 차이**:
- ChatDev: 다른 페르소나의 에이전트들
- chat_worker: **동일 캐릭터(이코)**가 다양한 태스크 수행

---

### 4.2 MetaGPT (DeepWisdom, 2023)

> **논문**: "Meta Programming for A Multi-Agent Collaborative Framework"  
> **arxiv**: 2308.00352

**프롬프트 전략**: SOP (Standard Operating Procedures) + 역할 특화

```
Product Manager → "PRD 문서 작성 SOP를 따르는 역할..."
Architect       → "설계 문서 작성 SOP를 따르는 역할..."
Engineer        → "코드 작성 SOP를 따르는 역할..."
QA Engineer     → "테스트 작성 SOP를 따르는 역할..."
```

**특징**:
- **구조화된 출력 포맷** (JSON, Markdown 등)
- SOP 기반 프로세스 준수
- 역할별 Artifact 생성

**우리와의 차이**:
- MetaGPT: 구조화된 문서/코드 생성
- chat_worker: **자연어 스트리밍 답변** 생성

---

### 4.3 AgentCoder (2024)

> **논문**: "AgentCoder: Multi-Agent-based Code Generation with Iterative Testing and Optimisation"

**프롬프트 전략**: 역할별 분리 + 반복 개선

```
Programmer → "코드 작성..."
Tester     → "테스트 케이스 생성..."
Debugger   → "실패 분석 및 수정 제안..."
```

**특징**:
- 반복적 개선 루프
- 실패 피드백 기반 프롬프트 조정

---

## 5. 패턴 비교 및 선택 가이드

### 5.1 패턴 비교표

| 패턴 | 캐릭터 일관성 | 태스크 최적화 | 토큰 효율 | 확장성 | 복잡도 |
|------|---------------|---------------|----------|--------|--------|
| **통합 (A)** | ✅ 높음 | ❌ 낮음 | ❌ 낮음 | ⚠️ 중간 | ✅ 낮음 |
| **분리 (B)** | ❌ 낮음 | ✅ 높음 | ✅ 높음 | ⚠️ 중간 | ⚠️ 중간 |
| **하이브리드 (C)** | ✅ 높음 | ✅ 높음 | ✅ 높음 | ✅ 높음 | ⚠️ 중간 |

### 5.2 선택 가이드

```
                          ┌─────────────────────────┐
                          │  에이전트들이 다른      │
                          │  페르소나를 가지는가?   │
                          └───────────┬─────────────┘
                                      │
                     ┌────────────────┼────────────────┐
                     │ YES            │                │ NO
                     ▼                │                ▼
          ┌─────────────────┐        │     ┌─────────────────┐
          │  Pattern B      │        │     │  태스크가       │
          │  역할별 완전 분리│        │     │  3개 이상인가?  │
          │  (ChatDev 스타일)│        │     └────────┬────────┘
          └─────────────────┘        │              │
                                     │    ┌────────┼────────┐
                                     │    │ YES    │        │ NO
                                     │    ▼        │        ▼
                                     │ ┌─────────────┐  ┌─────────────┐
                                     │ │ Pattern C   │  │ Pattern A   │
                                     │ │ 하이브리드  │  │ 단일 통합   │
                                     │ └─────────────┘  └─────────────┘
                                     │
                                     └─────────────────────────────────
```

---

## 6. 적용 사례: Eco² chat_worker

### 6.1 현황 분석

| 항목 | 현재 | 권장 |
|------|------|------|
| 캐릭터 | 동일 (이코) | 유지 |
| 태스크 수 | 4개 (waste/char/loc/general) | 확장 가능 |
| 프롬프트 | 단일 통합 | 하이브리드 |

### 6.2 권장 패턴: Pattern C (하이브리드)

**이유**:
1. **동일 캐릭터** 유지 필요 → Global Prompt
2. **4개 이상의 태스크** → Local Instructions
3. **자연어 스트리밍** 답변 → 구조화 강제 불필요
4. **향후 확장** 예상 (Vision, Multi-turn 등)

### 6.3 구현 아키텍처

```
┌─────────────────────────────────────────────────────────────────────┐
│                    chat_worker Prompt Architecture                   │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  assets/prompts/                                                     │
│  ├── global/                                                         │
│  │   └── eco_character.txt    ─────┐                                │
│  └── local/                         │                                │
│      ├── waste_instruction.txt  ────┼───┐                           │
│      ├── character_instruction.txt ─┼───┤                           │
│      ├── location_instruction.txt ──┼───┤                           │
│      └── general_instruction.txt ───┼───┤                           │
│                                     │   │                            │
│                                     ▼   ▼                            │
│                            ┌─────────────────┐                      │
│                            │  PromptBuilder  │                      │
│                            │  .build(intent) │                      │
│                            └────────┬────────┘                      │
│                                     │                                │
│                                     ▼                                │
│                            ┌─────────────────┐                      │
│                            │  answer_node    │                      │
│                            │  + AnswerContext│                      │
│                            └────────┬────────┘                      │
│                                     │                                │
│                                     ▼                                │
│                              Streaming Answer                        │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 참고 자료

### 2025년 논문
- [ai-agent-papers (GitHub)](https://github.com/masamasa59/ai-agent-papers) - AI Agent 논문 모음 (격주 업데이트)
- [Local Prompt Optimization (arxiv:2504.20355)](https://arxiv.org/abs/2504.20355)
- [Multi-Agent Collaboration via Evolving Orchestration (arxiv:2505.19591)](https://arxiv.org/abs/2505.19591)
- [Mem0: Building Production-Ready AI Agents with Scalable Long-Term Memory (arxiv:2504.19413)](https://arxiv.org/abs/2504.19413)
- [SEW: Self-Evolving Agentic Workflows for Automated Code Generation (arxiv:2505.18646)](https://arxiv.org/abs/2505.18646)
- [FlowReasoner: Reinforcing Query-Level Meta-Agents (arxiv:2504.15257)](https://arxiv.org/abs/2504.15257)
- [SkillWeaver: Web Agents can Self-Improve by Discovering and Honing Skills (arxiv:2504.07079)](https://arxiv.org/abs/2504.07079)

### 2023-2024년 논문
- [ChatDev (arxiv:2307.07924)](https://arxiv.org/abs/2307.07924) - 청화대 OpenBMB
- [MetaGPT (arxiv:2308.00352)](https://arxiv.org/abs/2308.00352) - DeepWisdom
- AgentCoder - Multi-Agent-based Code Generation

### 서베이 논문
- [A Survey of Frontiers in LLM Reasoning: Inference Scaling, Learning to Reason, and Agentic Systems](https://openreview.net/forum?id=SlsZZ25InC)
- [Creativity in LLM-based Multi-Agent Systems: A Survey (arxiv:2505.21116)](https://arxiv.org/abs/2505.21116)
- [A Survey of AI Agent Protocols (arxiv:2504.16736)](https://arxiv.org/abs/2504.16736)
- [Rethinking Memory in AI: Taxonomy, Operations, Topics, and Future Directions (arxiv:2505.00675)](https://arxiv.org/abs/2505.00675)

---

## TODO: 논문 상세 분석

> 아래 논문들은 실제로 읽고 상세 내용을 추가해야 합니다.

- [ ] [Local Prompt Optimization (arxiv:2504.20355)](https://arxiv.org/abs/2504.20355) - 상세 분석
- [ ] [Multi-Agent Collaboration via Evolving Orchestration (arxiv:2505.19591)](https://arxiv.org/abs/2505.19591) - 상세 분석
- [ ] [Mem0 (arxiv:2504.19413)](https://arxiv.org/abs/2504.19413) - 구현 방식 상세 분석
- [ ] [SEW (arxiv:2505.18646)](https://arxiv.org/abs/2505.18646) - Self-Evolution 메커니즘 분석
- [ ] [FlowReasoner (arxiv:2504.15257)](https://arxiv.org/abs/2504.15257) - Meta Agent 구현 방식 분석

