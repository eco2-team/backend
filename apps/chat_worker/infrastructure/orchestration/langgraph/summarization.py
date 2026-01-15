"""LangGraph Context Compression / Summarization.

멀티턴 대화에서 컨텍스트 압축을 수행합니다.
LangGraph 1.0+ pre_model_hook 패턴 지원.

전략:
1. Token Counting: 현재 컨텍스트 토큰 수 측정
2. Threshold Check: max_tokens_before_summary 초과 시 압축 트리거
3. Summarization: 이전 대화를 요약하고 최근 메시지만 유지
4. Context Update: summary + recent_messages로 context 갱신

참조:
- LangGraph How-to: Manage Message History
- langmem: SummarizationNode
- Anthropic: Context Engineering for Agents
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Callable

from langchain_core.messages import SystemMessage

if TYPE_CHECKING:
    from langchain_core.messages import AnyMessage

    from chat_worker.application.ports.llm import LLMClientPort
    from chat_worker.application.ports.prompt_loader import PromptLoaderPort

logger = logging.getLogger(__name__)

# 기본값
DEFAULT_MAX_TOKENS = 4096
DEFAULT_MAX_TOKENS_BEFORE_SUMMARY = 3072
DEFAULT_MAX_SUMMARY_TOKENS = 512
DEFAULT_KEEP_RECENT_MESSAGES = 4  # 최근 N개 메시지 유지


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
DEFAULT_SUMMARIZATION_PROMPT = """다음 대화 내용을 간결하게 요약해주세요.
핵심 정보와 맥락만 유지하고, {max_summary_tokens} 토큰 이내로 작성하세요.

{existing_summary_section}새로운 대화:
{messages_text}

요약:"""


async def summarize_messages(
    messages: list["AnyMessage"],
    llm: "LLMClientPort",
    existing_summary: str | None = None,
    max_summary_tokens: int = DEFAULT_MAX_SUMMARY_TOKENS,
    prompt_loader: "PromptLoaderPort | None" = None,
) -> str:
    """메시지 히스토리 요약.

    Args:
        messages: 요약할 메시지 리스트
        llm: LLM 클라이언트
        existing_summary: 기존 요약 (있으면 병합)
        max_summary_tokens: 요약 최대 토큰
        prompt_loader: 프롬프트 로더 (선택)

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
        f"{msg.__class__.__name__}: {msg.content}"
        for msg in messages
        if hasattr(msg, "content")
    )

    # 프롬프트 포맷팅
    existing_summary_section = (
        f"이전 요약:\n{existing_summary}\n\n" if existing_summary else ""
    )
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
            summarized_messages.append(
                SystemMessage(content=f"[이전 대화 요약]\n{new_summary}")
            )
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
    """LangGraph 노드용 요약 클래스.

    langmem의 SummarizationNode와 유사한 인터페이스.
    독립 노드로 사용하거나 pre_model_hook으로 사용 가능.

    Example:
        ```python
        summarization = SummarizationNode(
            llm=llm,
            max_tokens_before_summary=3072,
        )

        # 노드로 사용
        graph.add_node("summarize", summarization)

        # 또는 hook으로 사용
        graph = create_react_agent(
            model,
            tools,
            pre_model_hook=summarization,
        )
        ```
    """

    def __init__(
        self,
        llm: "LLMClientPort",
        token_counter: Callable[[list["AnyMessage"]], int] = count_tokens_approximately,
        max_tokens_before_summary: int = DEFAULT_MAX_TOKENS_BEFORE_SUMMARY,
        max_summary_tokens: int = DEFAULT_MAX_SUMMARY_TOKENS,
        keep_recent_messages: int = DEFAULT_KEEP_RECENT_MESSAGES,
        prompt_loader: "PromptLoaderPort | None" = None,
    ):
        """초기화.

        Args:
            llm: 요약용 LLM 클라이언트
            token_counter: 토큰 카운터 함수
            max_tokens_before_summary: 요약 트리거 임계값
            max_summary_tokens: 요약 최대 토큰
            keep_recent_messages: 유지할 최근 메시지 수
            prompt_loader: 프롬프트 로더 (선택)
        """
        self.llm = llm
        self.token_counter = token_counter
        self.max_tokens_before_summary = max_tokens_before_summary
        self.max_summary_tokens = max_summary_tokens
        self.keep_recent_messages = keep_recent_messages
        self.prompt_loader = prompt_loader

        self._hook = create_summarization_hook(
            llm=llm,
            token_counter=token_counter,
            max_tokens_before_summary=max_tokens_before_summary,
            max_summary_tokens=max_summary_tokens,
            keep_recent_messages=keep_recent_messages,
            prompt_loader=prompt_loader,
        )

    async def __call__(self, state: dict[str, Any]) -> dict[str, Any]:
        """노드 또는 hook으로 호출."""
        return await self._hook(state)
