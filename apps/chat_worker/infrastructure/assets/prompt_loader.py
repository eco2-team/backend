"""Local Prompt Optimization Loader.

Global + Local 프롬프트를 로드하고 조합하는 모듈.

Architecture:
    assets/prompts/
    ├── global/              # 캐릭터 정의 (모든 Intent 공통)
    │   └── eco_character.txt
    ├── local/               # Intent별 Answer 지침
    │   ├── waste_instruction.txt
    │   ├── character_instruction.txt
    │   ├── location_instruction.txt
    │   ├── web_instruction.txt
    │   └── general_instruction.txt
    ├── classification/      # 분류 프롬프트
    │   ├── intent.txt
    │   ├── text.txt
    │   └── vision.txt
    └── subagent/            # 서브에이전트 프롬프트
        ├── character.txt
        └── location.txt

Pattern: Local Prompt Optimization (arxiv:2504.20355)
- Global: 캐릭터/톤 고정 (변하지 않음)
- Local: Intent별 지침 동적 주입 (개별 최적화 가능)

References:
- docs/plans/chat-worker-prompt-strategy-adr.md
"""

from __future__ import annotations

import logging
from functools import lru_cache
from pathlib import Path
from typing import Literal

from chat_worker.application.ports.prompt_builder import PromptBuilderPort
from chat_worker.application.ports.prompt_loader import PromptLoaderPort

logger = logging.getLogger(__name__)

# 프롬프트 파일 경로 (assets/prompts/)
PROMPTS_DIR = Path(__file__).parent / "prompts"

# Intent 타입
IntentType = Literal["waste", "character", "location", "web_search", "general"]

# Intent -> 파일명 매핑
INTENT_FILE_MAP: dict[IntentType, str] = {
    "waste": "waste_instruction",
    "character": "character_instruction",
    "location": "location_instruction",
    "web_search": "web_instruction",
    "general": "general_instruction",
}


@lru_cache(maxsize=10)
def load_prompt_file(category: str, name: str) -> str:
    """프롬프트 파일 로드 (LRU 캐싱).

    Args:
        category: 카테고리 (global/local)
        name: 파일명 (확장자 제외)

    Returns:
        프롬프트 내용

    Raises:
        FileNotFoundError: 파일이 없는 경우
    """
    path = PROMPTS_DIR / category / f"{name}.txt"

    if not path.exists():
        logger.error(f"Prompt file not found: {path}")
        raise FileNotFoundError(f"Prompt file not found: {path}")

    content = path.read_text(encoding="utf-8")
    logger.debug(f"Loaded prompt: {category}/{name} ({len(content)} chars)")

    return content


class PromptLoader(PromptLoaderPort):
    """프롬프트 로더 구현체.

    PromptLoaderPort의 구현체로, 파일 시스템에서 프롬프트를 로드합니다.
    Application Layer에서 DI를 통해 주입받아 사용합니다.
    """

    def load(self, category: str, name: str) -> str:
        """프롬프트 파일 로드.

        Args:
            category: 프롬프트 카테고리 (classification, extraction 등)
            name: 프롬프트 이름 (확장자 제외)

        Returns:
            프롬프트 내용

        Raises:
            FileNotFoundError: 파일이 없을 경우
        """
        return load_prompt_file(category, name)


# 싱글톤 인스턴스 (DI에서 사용)
_prompt_loader_instance: PromptLoader | None = None


def get_prompt_loader() -> PromptLoader:
    """PromptLoader 싱글톤 반환."""
    global _prompt_loader_instance
    if _prompt_loader_instance is None:
        _prompt_loader_instance = PromptLoader()
    return _prompt_loader_instance


class PromptBuilder(PromptBuilderPort):
    """Local Prompt Optimization 빌더.

    PromptBuilderPort 구현체.
    Global + Local 프롬프트를 조합하여 최종 시스템 프롬프트 생성.
    arxiv:2504.20355 패턴 적용.

    Usage:
        builder = PromptBuilder()
        prompt = builder.build("waste")  # Global + Waste Local

    Architecture:
        ┌────────────────────────────────────────────────────────────┐
        │                   GLOBAL PROMPT (고정)                     │
        │    캐릭터 정의, 톤, 공통 규칙 - 모든 Intent에서 사용       │
        └────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
        ┌──────────┬──────────┬──────────┬──────────┬──────────┐
        │  WASTE   │  CHAR    │ LOCATION │   WEB    │ GENERAL  │ LOCAL
        │ INSTRUCT │ INSTRUCT │ INSTRUCT │ INSTRUCT │ INSTRUCT │
        └──────────┴──────────┴──────────┴──────────┴──────────┘
                                    │
                                    ▼
        ┌────────────────────────────────────────────────────────────┐
        │                      FINAL PROMPT                          │
        │               = GLOBAL + LOCAL[intent]                     │
        └────────────────────────────────────────────────────────────┘
    """

    def __init__(self):
        """프롬프트 빌더 초기화.

        Global 프롬프트와 모든 Local 프롬프트를 미리 로드.
        (LRU 캐시로 실제 파일 I/O는 한 번만 발생)
        """
        # Global 프롬프트 (캐릭터 정의)
        self._global = load_prompt_file("global", "eco_character")

        # Local 프롬프트 (Intent별 지침)
        self._local: dict[IntentType, str] = {}
        for intent, filename in INTENT_FILE_MAP.items():
            try:
                self._local[intent] = load_prompt_file("local", filename)
            except FileNotFoundError:
                logger.warning(f"Local prompt not found for {intent}, using general")
                self._local[intent] = self._local.get("general", "답변을 생성해주세요.")

        logger.info(f"PromptBuilder initialized with {len(self._local)} local prompts")

    def build(self, intent: str) -> str:
        """Intent에 따른 최종 프롬프트 생성.

        Args:
            intent: Intent 타입 (waste/character/location/general)

        Returns:
            Global + Local 조합된 최종 시스템 프롬프트
        """
        # Intent 정규화 (unknown -> general)
        normalized_intent = self._normalize_intent(intent)

        # Local 프롬프트 선택
        local = self._local.get(normalized_intent, self._local["general"])

        # Global + Local 조합
        final_prompt = f"{self._global}\n\n---\n\n{local}"

        logger.debug(
            f"Built prompt for intent={intent} "
            f"(normalized={normalized_intent}, length={len(final_prompt)})"
        )

        return final_prompt

    def build_multi(self, intents: list[str]) -> str:
        """Multi-Intent에 따른 조합 프롬프트 생성.

        여러 Intent의 Local 프롬프트를 조합하여 하나의 시스템 프롬프트 생성.
        DialogUSR 패턴: 분해된 쿼리에 맞는 Policy를 조합 주입.

        Args:
            intents: Intent 타입 리스트 (예: ["waste", "character"])

        Returns:
            Global + 조합된 Local 프롬프트

        Example:
            >>> builder.build_multi(["waste", "character"])
            # Global + Waste Instruction + Character Instruction
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

        logger.info(
            f"Built multi-intent prompt for intents={intents} "
            f"(unique={unique_intents}, length={len(final_prompt)})"
        )

        return final_prompt

    def _normalize_intent(self, intent: str) -> IntentType:
        """Intent 문자열을 정규화.

        Args:
            intent: 원본 Intent 문자열

        Returns:
            정규화된 IntentType
        """
        intent_lower = intent.lower().strip()

        # 매핑
        mapping = {
            "waste": "waste",
            "waste_query": "waste",
            "recycling": "waste",
            "disposal": "waste",
            "character": "character",
            "character_query": "character",
            "my_character": "character",
            "location": "location",
            "location_query": "location",
            "zerowaste": "location",
            "web_search": "web_search",
            "search": "web_search",
            "news": "web_search",
            "policy": "web_search",
            "general": "general",
            "greeting": "general",
            "unknown": "general",
        }

        return mapping.get(intent_lower, "general")

    @property
    def global_prompt(self) -> str:
        """Global 프롬프트 반환 (테스트용)."""
        return self._global

    def get_local_prompt(self, intent: str) -> str:
        """특정 Intent의 Local 프롬프트 반환 (테스트용).

        Args:
            intent: Intent 타입

        Returns:
            Local 프롬프트 내용
        """
        normalized = self._normalize_intent(intent)
        return self._local.get(normalized, self._local["general"])


# 싱글톤 인스턴스 (선택적 사용)
_prompt_builder: PromptBuilder | None = None


def get_prompt_builder() -> PromptBuilder:
    """PromptBuilder 싱글톤 인스턴스 반환.

    Returns:
        PromptBuilder 인스턴스
    """
    global _prompt_builder
    if _prompt_builder is None:
        _prompt_builder = PromptBuilder()
    return _prompt_builder
