# 이코에코(Eco²) Agent #17: 동적 컨텍스트 압축 (OpenCode 스타일)

> OpenCode/Claude Code 기반 Production-Ready 컨텍스트 압축 전략

| 항목 | 값 |
|-----|-----|
| **작성일** | 2026-01-16 |
| **버전** | v2.0 |
| **시리즈** | Eco² Agent 시리즈 |
| **이전 포스팅** | [#16 컨텍스트 압축 v1.0](./30-chat-context-compression.md) |
| **참조** | OpenCode compaction.ts, Claude Code compaction |

---

## 1. 배경: v1.0의 한계

### 1.1 기존 구현 (v1.0)

```python
# v1.0 - 고정 임계값 방식
DEFAULT_MAX_TOKENS_BEFORE_SUMMARY = 3072  # 고정 3K
DEFAULT_MAX_SUMMARY_TOKENS = 512          # 고정 512
DEFAULT_KEEP_RECENT_MESSAGES = 4          # 고정 4개
```

| 문제 | 설명 |
|------|------|
| **고정 임계값** | GPT-5.2 (400K)와 Gemini-3 (1M)에 동일한 3K 적용 |
| **요약 토큰 부족** | 512 토큰으로는 구조화된 요약 불가능 |
| **컨텍스트 손실** | 4개 메시지만 유지 → 작업 연속성 저하 |
| **모델 무관** | 모델별 컨텍스트 윈도우 미고려 |

### 1.2 Production 환경 요구사항

| 요구사항 | 설명 |
|----------|------|
| **동적 임계값** | 모델별 컨텍스트 윈도우에 비례 |
| **충분한 요약** | 구조화된 5개 섹션 요약 (20K+ 토큰) |
| **작업 보호** | 최근 작업 컨텍스트 보호 (40K 토큰) |
| **표준 준수** | OpenCode/Claude Code 검증된 전략 적용 |

---

## 2. OpenCode 압축 전략 분석

### 2.1 OpenCode 소스 코드

> **Reference**: [sst/opencode/compaction.ts](https://github.com/sst/opencode/blob/dev/packages/opencode/src/session/compaction.ts)

```typescript
// OpenCode compaction.ts (2025)
const PRUNE_MINIMUM = 20_000   // 최소 정리 임계값
const PRUNE_PROTECT = 40_000   // 보호 토큰 (최근 메시지)

function isOverflow(messages: Message[], context: ContextLimit): boolean {
  const tokens = countTokens(messages)
  // 트리거 조건: tokens > (context_limit - output_limit)
  return tokens > (context.contextLimit - context.outputLimit)
}
```

### 2.2 Claude Code 압축 전략

> **Reference**: [Claude Code Compaction](https://stevekinney.com/courses/ai-development/claude-code-compaction)

| 항목 | Claude Code |
|------|-------------|
| **버퍼** | 40-45K 토큰 |
| **토큰 회복률** | ~50% |
| **예약 공간** | 20% |

### 2.3 전략 비교

| 도구 | 트리거 조건 | 요약 크기 | 최근 보호 |
|------|------------|----------|----------|
| **OpenCode** | context - output | 동적 | 40K (PRUNE_PROTECT) |
| **Claude Code** | 80% threshold | 동적 | 40-45K |
| **Cursor** | ~80% | ~20% | 가변 |
| **v1.0 (이전)** | 고정 3072 | 512 | 4개 메시지 |
| **v2.0 (신규)** | context - output | 15% (min 20K) | 40K |

---

## 3. 구현: ModelContextConfig

### 3.1 OpenCode 상수 정의

```python
# infrastructure/orchestration/langgraph/summarization.py

# OpenCode 기준 상수 (sst/opencode compaction.ts 참조)
# https://github.com/sst/opencode/blob/dev/packages/opencode/src/session/compaction.ts
PRUNE_MINIMUM = 20_000  # 최소 정리 임계값 (토큰)
PRUNE_PROTECT = 40_000  # 보호된 토큰 기준 (최근 도구 출력 보호)
```

### 3.2 ModelContextConfig 데이터 클래스

```python
@dataclass(frozen=True)
class ModelContextConfig:
    """모델별 컨텍스트 윈도우 설정.

    압축 전략 (OpenCode 기준):
    - 트리거: context_window - max_output 초과 시 (OpenCode isOverflow)
    - 요약 토큰: 컨텍스트의 15% 할당 (충분한 구조화된 요약용)
    - 최근 보호: PRUNE_PROTECT = 40K 토큰 (OpenCode 동일)

    Sources:
    - OpenCode: https://github.com/sst/opencode/blob/dev/packages/opencode/src/session/compaction.ts
    - Claude Code: https://stevekinney.com/courses/ai-development/claude-code-compaction
    """

    context_window: int  # 전체 컨텍스트 윈도우 (토큰)
    max_output: int      # 최대 출력 토큰

    @property
    def trigger_threshold(self) -> int:
        """OpenCode 스타일: context_window - max_output 초과 시 트리거.

        isOverflow 조건: tokens > (context_limit - output_limit)
        """
        return self.context_window - self.max_output

    @property
    def summary_tokens(self) -> int:
        """컨텍스트 윈도우의 15%를 요약에 할당.

        구조화된 5개 섹션 요약:
        - 사용자 요청 원문
        - 목표 및 기대 결과
        - 완료된 작업
        - 진행 중/남은 작업
        - 중요 컨텍스트

        최소 PRUNE_MINIMUM (20K), 최대 65536.
        """
        calculated = int(self.context_window * 0.15)
        return max(PRUNE_MINIMUM, min(65536, calculated))

    @property
    def keep_recent_tokens(self) -> int:
        """OpenCode PRUNE_PROTECT 기준: 40K 토큰 보호."""
        return PRUNE_PROTECT
```

### 3.3 모델 레지스트리

```python
# 모델별 컨텍스트 윈도우 레지스트리
# Sources:
# - GPT-5.2: https://openai.com/index/introducing-gpt-5-2/
# - Gemini-3.0: https://ai.google.dev/gemini-api/docs/models#gemini-3
MODEL_CONTEXT_REGISTRY: dict[str, ModelContextConfig] = {
    # OpenAI GPT-5.x 시리즈 (Production)
    "gpt-5.2": ModelContextConfig(context_window=400_000, max_output=128_000),
    "gpt-5.2-thinking": ModelContextConfig(context_window=400_000, max_output=128_000),
    "gpt-5.1": ModelContextConfig(context_window=400_000, max_output=128_000),
    "gpt-5": ModelContextConfig(context_window=400_000, max_output=128_000),
    # Google Gemini 3.x 시리즈 (Preview Only - 2026-01 기준)
    "gemini-3-flash-preview": ModelContextConfig(context_window=1_000_000, max_output=64_000),
    "gemini-3-pro-preview": ModelContextConfig(context_window=1_000_000, max_output=64_000),
}

# 기본값 (알 수 없는 모델용 - GPT-5.2 기준)
DEFAULT_MODEL_CONFIG = ModelContextConfig(context_window=400_000, max_output=128_000)
```

---

## 4. 동적 설정 계산

### 4.1 모델별 계산 결과

| 모델 | Context | Output | Trigger | Summary (15%) | Keep Recent |
|------|---------|--------|---------|---------------|-------------|
| **gpt-5.2** | 400K | 128K | **272K** | **60K** | 40K |
| **gemini-3-flash-preview** | 1M | 64K | **936K** | **65K** (max) | 40K |

### 4.2 v1.0 vs v2.0 비교

```
┌─────────────────────────────────────────────────────────────────┐
│                    v1.0 (고정) vs v2.0 (동적)                     │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  v1.0 (GPT-5.2 기준)                                            │
│  ├── Trigger: 3,072 tokens (0.77% of context!)                  │
│  ├── Summary: 512 tokens                                        │
│  └── Keep: 4 messages (~2K tokens)                              │
│                                                                  │
│  v2.0 (GPT-5.2 기준)                                            │
│  ├── Trigger: 272,000 tokens (68% of context)                   │
│  ├── Summary: 60,000 tokens                                     │
│  └── Keep: 40,000 tokens (~80 messages)                         │
│                                                                  │
│  개선율: Trigger 88x, Summary 117x, Keep 20x                    │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## 5. 구조화된 요약 프롬프트

### 5.1 oh-my-opencode 스타일 5개 섹션

> **Reference**: [oh-my-opencode/compaction-context-injector](https://github.com/code-yeongyu/oh-my-opencode)

```python
DEFAULT_SUMMARIZATION_PROMPT = """다음 대화 내용을 구조화된 형식으로 요약해주세요.
{max_summary_tokens} 토큰 이내로 작성하되, 아래 5개 섹션을 반드시 포함하세요.

## 요약 형식

### 1. 사용자 요청 (원문)
- 사용자가 요청한 내용을 원문 그대로 기록
- 여러 요청이 있었다면 모두 나열

### 2. 목표 및 기대 결과
- 최종적으로 달성하려는 목표
- 사용자가 기대하는 결과물

### 3. 완료된 작업
- 이미 수행 완료된 작업 목록
- 생성/수정된 파일, 구현된 기능 등

### 4. 진행 중/남은 작업
- 현재 진행 중인 작업
- 아직 수행하지 않은 남은 작업

### 5. 중요 컨텍스트
- 실패한 접근법 (다시 시도하지 말 것)
- 사용자가 명시한 제약사항
- 핵심 기술적 결정사항

{existing_summary_section}

## 대화 내용
{messages_text}

## 구조화된 요약"""
```

### 5.2 섹션별 목적

| 섹션 | 목적 | 중요도 |
|------|------|--------|
| **사용자 요청 원문** | 원래 의도 보존 | Critical |
| **목표/기대 결과** | 방향성 유지 | High |
| **완료된 작업** | 중복 방지 | High |
| **진행 중/남은 작업** | 연속성 유지 | Critical |
| **중요 컨텍스트** | 실패 재발 방지 | High |

---

## 6. SummarizationNode 동적 설정

### 6.1 초기화 로직

```python
class SummarizationNode:
    def __init__(
        self,
        llm: "LLMClientPort",
        model_name: str | None = None,  # 신규: 동적 설정용
        token_counter: Callable = count_tokens_approximately,
        max_tokens_before_summary: int | None = None,
        max_summary_tokens: int | None = None,
        keep_recent_messages: int | None = None,
        prompt_loader: "PromptLoaderPort | None" = None,
    ):
        # 동적 설정 계산
        if model_name:
            config = get_model_config(model_name)
            self.max_tokens_before_summary = (
                max_tokens_before_summary or config.trigger_threshold
            )
            self.max_summary_tokens = (
                max_summary_tokens or config.summary_tokens
            )
            # keep_recent_messages: 토큰 기반 계산
            # 대략 1 메시지 = 500 토큰 가정
            keep_recent_tokens = config.keep_recent_tokens
            self.keep_recent_messages = (
                keep_recent_messages or max(10, keep_recent_tokens // 500)
            )

            logger.info(
                "SummarizationNode initialized with dynamic config",
                extra={
                    "model": model_name,
                    "context_window": config.context_window,
                    "trigger_threshold": self.max_tokens_before_summary,
                    "summary_tokens": self.max_summary_tokens,
                    "keep_recent_messages": self.keep_recent_messages,
                },
            )
        else:
            # 레거시: 수동 설정 또는 기본값
            self.max_tokens_before_summary = (
                max_tokens_before_summary or DEFAULT_MAX_TOKENS_BEFORE_SUMMARY
            )
            # ...
```

### 6.2 Factory 통합

```python
# infrastructure/orchestration/langgraph/factory.py

def create_chat_graph(
    # ...
    enable_summarization: bool = False,
    summarization_model: str | None = None,  # 동적 설정용 모델명
    max_tokens_before_summary: int | None = None,
    max_summary_tokens: int | None = None,
    keep_recent_messages: int | None = None,
) -> StateGraph:
    if enable_summarization:
        summarization_node = SummarizationNode(
            llm=llm,
            model_name=summarization_model,  # 동적 설정
            max_tokens_before_summary=max_tokens_before_summary,
            max_summary_tokens=max_summary_tokens,
            keep_recent_messages=keep_recent_messages,
            prompt_loader=prompt_loader,
        )
```

---

## 7. 설정 가이드

### 7.1 Config (권장: None으로 동적 계산)

```python
# setup/config.py

class Settings(BaseSettings):
    # Multi-turn 대화 컨텍스트 압축 (OpenCode 스타일)
    # 동적 설정: context_window - max_output 초과 시 압축 트리거
    enable_summarization: bool = True  # 기본 활성화

    # None이면 모델 기반 동적 계산 (권장)
    # - GPT-5.2: 400K - 128K = 272K 트리거, 400K * 15% = 60K 요약
    # - gemini-3-flash-preview: 1M - 64K = 936K 트리거, 65K 요약 (max)
    max_tokens_before_summary: int | None = None
    max_summary_tokens: int | None = None
    keep_recent_messages: int | None = None
```

### 7.2 환경변수 오버라이드

```bash
# 동적 계산 사용 (권장)
CHAT_WORKER_ENABLE_SUMMARIZATION=true
# max_tokens_before_summary, max_summary_tokens, keep_recent_messages 설정 안함

# 수동 오버라이드 (특수 케이스)
CHAT_WORKER_MAX_TOKENS_BEFORE_SUMMARY=200000
CHAT_WORKER_MAX_SUMMARY_TOKENS=50000
CHAT_WORKER_KEEP_RECENT_MESSAGES=100
```

---

## 8. 변경 파일 목록

| 파일 | 변경 내용 |
|------|----------|
| `infrastructure/orchestration/langgraph/summarization.py` | ModelContextConfig, MODEL_CONTEXT_REGISTRY, 동적 설정 |
| `infrastructure/orchestration/langgraph/factory.py` | summarization_model 파라미터 추가 |
| `setup/config.py` | enable_summarization, 동적 설정 필드 |
| `setup/dependencies.py` | summarization_model 전달 |

---

## 9. 참고 문헌

### 9.1 Primary Sources (구현 기준)

| Source | URL | 참조 내용 |
|--------|-----|----------|
| **OpenCode compaction.ts** | [github.com/sst/opencode/.../compaction.ts](https://github.com/sst/opencode/blob/dev/packages/opencode/src/session/compaction.ts) | PRUNE_MINIMUM, PRUNE_PROTECT, isOverflow |
| **Claude Code Compaction** | [stevekinney.com/.../claude-code-compaction](https://stevekinney.com/courses/ai-development/claude-code-compaction) | 40-45K 버퍼, 50% 토큰 회복률 |
| **oh-my-opencode** | [github.com/code-yeongyu/oh-my-opencode](https://github.com/code-yeongyu/oh-my-opencode) | 5섹션 구조화 요약, Preemptive Compaction |

### 9.2 Model Documentation

| Model | Context | Output | Source |
|-------|---------|--------|--------|
| **GPT-5.2** | 400K | 128K | [openai.com/index/introducing-gpt-5-2](https://openai.com/index/introducing-gpt-5-2/) |
| **Gemini 3 Flash Preview** | 1M | 64K | [ai.google.dev/gemini-api/docs/models#gemini-3](https://ai.google.dev/gemini-api/docs/models#gemini-3) |

### 9.3 LangGraph Documentation

- [How to manage conversation history](https://langchain-ai.github.io/langgraph/how-tos/memory/manage-conversation-history/)
- [LangGraph Checkpointers](https://langchain-ai.github.io/langgraph/concepts/persistence/)
- [langmem: SummarizationNode](https://github.com/langchain-ai/langmem)

---

## 10. 결론

### 10.1 v1.0 → v2.0 개선 요약

| 항목 | v1.0 | v2.0 | 개선율 |
|------|------|------|--------|
| **Trigger** | 3,072 (고정) | 272,000 (GPT-5.2) | 88x |
| **Summary** | 512 | 60,000 | 117x |
| **Keep Recent** | ~2K (4 msg) | 40,000 | 20x |
| **모델 인식** | X | O | - |
| **구조화 요약** | X | 5섹션 | - |

### 10.2 Production Readiness

- OpenCode/Claude Code 검증된 전략 적용
- 모델별 동적 설정으로 확장성 확보
- 하위 호환성 유지 (레거시 기본값)
- 구조화된 요약으로 컨텍스트 보존 극대화

---

*문서 버전: v2.0*
*최종 수정: 2026-01-16*
