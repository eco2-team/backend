"""LangGraph Context Compression / Summarization.

멀티턴 대화에서 컨텍스트 압축을 수행합니다.
LangGraph 1.0+ pre_model_hook 패턴 지원.

전략 (OpenCode 스타일):
1. Dynamic Threshold: context_window - max_output 초과 시 압축 트리거
2. Structured Summary: 5개 섹션으로 구조화된 요약
3. Dynamic Token Limit: 컨텍스트 윈도우의 15% 요약 토큰 (min 20K, max 65K)
4. Context Preservation: 원문 요청 + 목표 + 작업 상태 보존

모델별 컨텍스트 윈도우:
- gpt-5.2: 400,000 context / 128,000 output (OpenAI)
- gemini-3-flash-preview: 1,000,000 context / 64,000 output (Google)

참조:
- OpenCode: https://github.com/sst/opencode/blob/dev/packages/opencode/src/session/compaction.ts
- oh-my-opencode: Preemptive Compaction
- LangGraph How-to: Manage Message History
- langmem: SummarizationNode
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Callable

from langchain_core.messages import SystemMessage

if TYPE_CHECKING:
    from langchain_core.messages import AnyMessage

    from chat_worker.application.ports.llm import LLMClientPort
    from chat_worker.application.ports.prompt_loader import PromptLoaderPort

logger = logging.getLogger(__name__)


# ============================================================
# Model Context Window Registry
# ============================================================

# ============================================================
# OpenCode 기준 상수 (sst/opencode compaction.ts 참조)
# https://github.com/sst/opencode/blob/dev/packages/opencode/src/session/compaction.ts
# ============================================================

PRUNE_MINIMUM = 20_000  # 최소 정리 임계값 (토큰)
PRUNE_PROTECT = 40_000  # 보호된 토큰 기준 (최근 도구 출력 보호)


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
    max_output: int  # 최대 출력 토큰

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
        """OpenCode PRUNE_PROTECT 기준: 40K 토큰 보호.

        최근 도구 출력/메시지를 보호하여 작업 연속성 유지.
        """
        return PRUNE_PROTECT


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
    # Stable 버전 미출시, Preview 버전만 사용 가능
    "gemini-3-flash-preview": ModelContextConfig(context_window=1_000_000, max_output=64_000),
    "gemini-3-pro-preview": ModelContextConfig(context_window=1_000_000, max_output=64_000),
}

# 기본값 (알 수 없는 모델용 - GPT-5.2 기준)
DEFAULT_MODEL_CONFIG = ModelContextConfig(context_window=400_000, max_output=128_000)


def get_model_config(model_name: str) -> ModelContextConfig:
    """모델명으로 컨텍스트 설정 조회.

    Args:
        model_name: 모델명 (예: "gpt-5.2", "gemini-3-flash-preview")

    Returns:
        ModelContextConfig 인스턴스
    """
    # 정확한 매칭
    if model_name in MODEL_CONTEXT_REGISTRY:
        return MODEL_CONTEXT_REGISTRY[model_name]

    # 부분 매칭 (예: "gpt-5.2-2025-12-11" → "gpt-5.2")
    model_lower = model_name.lower()
    for key, config in MODEL_CONTEXT_REGISTRY.items():
        if model_lower.startswith(key):
            return config

    logger.warning(
        "Unknown model, using default config",
        extra={"model": model_name, "default_context": DEFAULT_MODEL_CONFIG.context_window},
    )
    return DEFAULT_MODEL_CONFIG


# ============================================================
# Legacy Defaults (하위 호환성)
# ============================================================

DEFAULT_MAX_TOKENS = 4096
DEFAULT_MAX_TOKENS_BEFORE_SUMMARY = 3072  # 동적 계산으로 대체됨
DEFAULT_MAX_SUMMARY_TOKENS = 1024  # 동적 계산으로 대체됨
DEFAULT_KEEP_RECENT_MESSAGES = 6  # 동적 계산으로 대체됨


def count_tokens_approximately(messages: list["AnyMessage"]) -> int:
    """대략적인 토큰 수 계산.

    정확한 토큰 계산은 tiktoken 필요.
    여기서는 문자 수 기반 근사치 사용 (~4자 = 1토큰).

    Args:
        messages: 메시지 리스트

    Returns:
        대략적인 토큰 수
    """
    total_chars = 0
    for msg in messages:
        if hasattr(msg, "content"):
            content = msg.content
            if isinstance(content, str):
                total_chars += len(content)
            elif isinstance(content, list):
                for item in content:
                    if isinstance(item, dict) and "text" in item:
                        total_chars += len(item["text"])
    return total_chars // 4  # 대략 4자당 1토큰


# 기본 프롬프트 (PromptLoader가 없을 때 사용)
# oh-my-opencode 스타일 구조화된 요약
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


async def summarize_messages(
    messages: list["AnyMessage"],
    llm: "LLMClientPort",
    existing_summary: str | None = None,
    max_summary_tokens: int = DEFAULT_MAX_SUMMARY_TOKENS,
    prompt_loader: "PromptLoaderPort | None" = None,
    max_input_chars: int = 800_000,
) -> str:
    """메시지 히스토리 요약.

    Args:
        messages: 요약할 메시지 리스트
        llm: LLM 클라이언트
        existing_summary: 기존 요약 (있으면 병합)
        max_summary_tokens: 요약 최대 토큰
        prompt_loader: 프롬프트 로더 (선택)
        max_input_chars: messages_text 최대 문자 수 (기본 800K ≈ 200K tokens)

    Returns:
        요약된 텍스트
    """
    if not messages:
        return existing_summary or ""

    # 요약 프롬프트 로드 (PromptLoader 또는 기본값)
    if prompt_loader is not None:
        template = prompt_loader.load_or_default(
            category="summarization",
            name="context_compress",
            default=DEFAULT_SUMMARIZATION_PROMPT,
        )
    else:
        template = DEFAULT_SUMMARIZATION_PROMPT

    # 메시지 텍스트 구성
    messages_text = "\n".join(
        f"{msg.__class__.__name__}: {msg.content}" for msg in messages if hasattr(msg, "content")
    )

    # 입력 크기 제한: 모델 context window 초과 방지
    # 초과 시 가장 최근 메시지 위주로 유지 (tail 보존)
    if len(messages_text) > max_input_chars:
        logger.warning(
            "summarize_messages input truncated",
            extra={
                "original_chars": len(messages_text),
                "truncated_to": max_input_chars,
                "message_count": len(messages),
            },
        )
        messages_text = messages_text[-max_input_chars:]

    # 프롬프트 포맷팅
    existing_summary_section = f"이전 요약:\n{existing_summary}\n\n" if existing_summary else ""
    summary_prompt = template.format(
        max_summary_tokens=max_summary_tokens,
        existing_summary_section=existing_summary_section,
        messages_text=messages_text,
    )

    try:
        summary = await llm.generate(summary_prompt)
        logger.info(
            "conversation_summarized",
            extra={
                "input_messages": len(messages),
                "summary_length": len(summary),
            },
        )
        return summary
    except (ValueError, RuntimeError) as e:
        logger.error(
            "summarization_failed",
            extra={"error": str(e), "error_type": type(e).__name__},
        )
        # Fallback: 기존 요약 반환 또는 빈 문자열
        return existing_summary or ""


def create_summarization_hook(
    llm: "LLMClientPort",
    token_counter: Callable[[list["AnyMessage"]], int] = count_tokens_approximately,
    max_tokens_before_summary: int = DEFAULT_MAX_TOKENS_BEFORE_SUMMARY,
    max_summary_tokens: int = DEFAULT_MAX_SUMMARY_TOKENS,
    keep_recent_messages: int = DEFAULT_KEEP_RECENT_MESSAGES,
    prompt_loader: "PromptLoaderPort | None" = None,
) -> Callable[[dict[str, Any]], dict[str, Any]]:
    """pre_model_hook용 요약 함수 생성.

    LangGraph 1.0+ create_react_agent의 pre_model_hook으로 사용.

    Args:
        llm: 요약용 LLM 클라이언트
        token_counter: 토큰 카운터 함수
        max_tokens_before_summary: 요약 트리거 임계값
        max_summary_tokens: 요약 최대 토큰
        keep_recent_messages: 유지할 최근 메시지 수
        prompt_loader: 프롬프트 로더 (선택)

    Returns:
        pre_model_hook 함수

    Example:
        ```python
        hook = create_summarization_hook(llm)
        graph = create_react_agent(
            model,
            tools,
            pre_model_hook=hook,
        )
        ```
    """

    async def summarization_hook(state: dict[str, Any]) -> dict[str, Any]:
        """메시지 히스토리 압축 hook.

        1. 토큰 수 확인
        2. 임계값 초과 시 요약 생성
        3. summary + recent_messages로 context 갱신
        """
        messages = state.get("messages", [])

        if not messages:
            return {"llm_input_messages": messages}

        current_tokens = token_counter(messages)

        # 임계값 미만이면 그대로 반환
        if current_tokens <= max_tokens_before_summary:
            logger.debug(
                "context_within_limit",
                extra={
                    "current_tokens": current_tokens,
                    "threshold": max_tokens_before_summary,
                },
            )
            return {"llm_input_messages": messages}

        # 압축 필요
        logger.info(
            "context_compression_triggered",
            extra={
                "current_tokens": current_tokens,
                "threshold": max_tokens_before_summary,
            },
        )

        # 최근 메시지와 이전 메시지 분리
        recent_messages = messages[-keep_recent_messages:]
        older_messages = messages[:-keep_recent_messages]

        # 기존 요약 가져오기
        existing_summary = state.get("summary", "")

        # 이전 메시지 요약
        if older_messages:
            new_summary = await summarize_messages(
                older_messages,
                llm,
                existing_summary=existing_summary,
                max_summary_tokens=max_summary_tokens,
                prompt_loader=prompt_loader,
            )
        else:
            new_summary = existing_summary

        # 요약을 SystemMessage로 변환
        summarized_messages = []
        if new_summary:
            summarized_messages.append(SystemMessage(content=f"[이전 대화 요약]\n{new_summary}"))
        summarized_messages.extend(recent_messages)

        # 압축 후 토큰 확인
        compressed_tokens = token_counter(summarized_messages)
        logger.info(
            "context_compressed",
            extra={
                "original_tokens": current_tokens,
                "compressed_tokens": compressed_tokens,
                "compression_ratio": f"{(1 - compressed_tokens / current_tokens) * 100:.1f}%",
            },
        )

        return {
            "llm_input_messages": summarized_messages,
            "summary": new_summary,
        }

    return summarization_hook


class SummarizationNode:
    """LangGraph 노드용 요약 클래스 (동적 설정 지원).

    OpenCode 스타일 동적 컨텍스트 압축:
    - 모델별 컨텍스트 윈도우 자동 감지
    - context_window - max_output 초과 시 압축 트리거
    - 구조화된 5개 섹션 요약

    Example:
        ```python
        # 동적 설정 (권장)
        summarization = SummarizationNode(
            llm=llm,
            model_name="gpt-5.2",  # 자동으로 400K 윈도우 감지
        )

        # 수동 설정 (레거시)
        summarization = SummarizationNode(
            llm=llm,
            max_tokens_before_summary=3072,
        )

        graph.add_node("summarize", summarization)
        ```
    """

    def __init__(
        self,
        llm: "LLMClientPort",
        model_name: str | None = None,  # 신규: 동적 설정용
        token_counter: Callable[[list["AnyMessage"]], int] = count_tokens_approximately,
        max_tokens_before_summary: int | None = None,  # None이면 동적 계산
        max_summary_tokens: int | None = None,  # None이면 동적 계산
        keep_recent_messages: int | None = None,  # None이면 동적 계산
        prompt_loader: "PromptLoaderPort | None" = None,
    ):
        """초기화.

        Args:
            llm: 요약용 LLM 클라이언트
            model_name: 모델명 (동적 설정용, 예: "gpt-5.2")
            token_counter: 토큰 카운터 함수
            max_tokens_before_summary: 요약 트리거 임계값 (None이면 context-output 동적 계산)
            max_summary_tokens: 요약 최대 토큰 (None이면 15% 동적 계산)
            keep_recent_messages: 유지할 최근 메시지 수 (None이면 PRUNE_PROTECT 기반 계산)
            prompt_loader: 프롬프트 로더 (선택)
        """
        self.llm = llm
        self.token_counter = token_counter
        self.prompt_loader = prompt_loader

        # 동적 설정 계산
        if model_name:
            config = get_model_config(model_name)
            self.max_tokens_before_summary = max_tokens_before_summary or config.trigger_threshold
            self.max_summary_tokens = max_summary_tokens or config.summary_tokens
            # keep_recent_messages: 토큰 기반 계산
            # OpenCode PRUNE_PROTECT = 40K, Claude Code 버퍼 = 40-45K
            # 대략 1 메시지 = 500 토큰 가정 (코드 포함 시 더 길어짐)
            keep_recent_tokens = config.keep_recent_tokens
            self.keep_recent_messages = keep_recent_messages or max(10, keep_recent_tokens // 500)

            logger.info(
                "SummarizationNode initialized with dynamic config",
                extra={
                    "model": model_name,
                    "context_window": config.context_window,
                    "trigger_threshold": self.max_tokens_before_summary,
                    "summary_tokens": self.max_summary_tokens,
                    "keep_recent_tokens": keep_recent_tokens,
                    "keep_recent_messages": self.keep_recent_messages,
                },
            )
        else:
            # 레거시: 수동 설정 또는 기본값
            self.max_tokens_before_summary = (
                max_tokens_before_summary or DEFAULT_MAX_TOKENS_BEFORE_SUMMARY
            )
            self.max_summary_tokens = max_summary_tokens or DEFAULT_MAX_SUMMARY_TOKENS
            self.keep_recent_messages = keep_recent_messages or DEFAULT_KEEP_RECENT_MESSAGES

            logger.info(
                "SummarizationNode initialized with static config",
                extra={
                    "trigger_threshold": self.max_tokens_before_summary,
                    "summary_tokens": self.max_summary_tokens,
                    "keep_recent": self.keep_recent_messages,
                },
            )

        self._hook = create_summarization_hook(
            llm=llm,
            token_counter=token_counter,
            max_tokens_before_summary=self.max_tokens_before_summary,
            max_summary_tokens=self.max_summary_tokens,
            keep_recent_messages=self.keep_recent_messages,
            prompt_loader=prompt_loader,
        )

    async def __call__(self, state: dict[str, Any]) -> dict[str, Any]:
        """노드 또는 hook으로 호출."""
        return await self._hook(state)
