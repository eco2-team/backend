"""Dependency Injection - Clean Architecture.

Port/Adapter 패턴 기반 DI Factory.
Celery Task에서 Step, Pipeline을 조립하여 사용.
"""

from __future__ import annotations

from functools import lru_cache
from typing import TYPE_CHECKING

from scan_worker.application.classify.commands.execute_pipeline import (
    CheckpointingStepRunner,
    ClassifyPipeline,
    SingleStepRunner,
)
from scan_worker.application.classify.dto.classify_context import ClassifyContext
from scan_worker.application.classify.ports.context_store import ContextStorePort
from scan_worker.application.classify.ports.event_publisher import (
    EventPublisherPort,
)
from scan_worker.application.classify.ports.llm_model import LLMPort
from scan_worker.application.classify.ports.prompt_repository import (
    PromptRepositoryPort,
)
from scan_worker.application.classify.ports.result_cache import ResultCachePort
from scan_worker.application.classify.ports.retriever import RetrieverPort
from scan_worker.application.classify.ports.vision_model import VisionModelPort
from scan_worker.application.classify.steps.answer_step import AnswerStep
from scan_worker.application.classify.steps.reward_step import RewardStep
from scan_worker.application.classify.steps.rule_step import RuleStep
from scan_worker.application.classify.steps.vision_step import VisionStep
from scan_worker.infrastructure.asset_loader.prompt_repository_impl import (
    FilePromptRepository,
)
from scan_worker.infrastructure.llm import (
    GeminiLLMAdapter,
    GeminiVisionAdapter,
    GPTLLMAdapter,
    GPTVisionAdapter,
)
from scan_worker.infrastructure.event_bus import RedisEventPublisher
from scan_worker.infrastructure.persistence_redis import RedisResultCache
from scan_worker.infrastructure.retrievers.json_regulation import (
    JsonRegulationRetriever,
)
from scan_worker.setup.config import get_settings

if TYPE_CHECKING:
    from celery import Celery


# ============================================================
# Singleton Port Instances
# ============================================================


@lru_cache
def get_prompt_repository() -> PromptRepositoryPort:
    """PromptRepository 싱글톤."""
    settings = get_settings()
    return FilePromptRepository(assets_path=settings.assets_path)


@lru_cache
def get_retriever() -> RetrieverPort:
    """Retriever 싱글톤."""
    settings = get_settings()
    return JsonRegulationRetriever(data_path=settings.assets_path + "/data")


@lru_cache
def get_event_publisher() -> EventPublisherPort:
    """EventPublisher 싱글톤."""
    settings = get_settings()
    return RedisEventPublisher(
        redis_url=settings.redis_streams_url,
        shard_count=settings.sse_shard_count,
    )


@lru_cache
def get_result_cache() -> ResultCachePort:
    """ResultCache 싱글톤."""
    settings = get_settings()
    return RedisResultCache(
        redis_url=settings.redis_cache_url,
        default_ttl=settings.result_cache_ttl,
    )


@lru_cache
def get_context_store() -> ContextStorePort:
    """ContextStore 싱글톤 (체크포인팅)."""
    from scan_worker.infrastructure.persistence_redis.context_store_impl import (
        RedisContextStore,
    )

    settings = get_settings()
    return RedisContextStore(
        redis_url=settings.redis_cache_url,
        ttl=settings.checkpoint_ttl,
    )


# ============================================================
# Factory Functions (per-request)
# ============================================================


class UnsupportedModelError(ValueError):
    """지원하지 않는 모델 에러."""

    def __init__(self, model: str, supported: list[str]):
        self.model = model
        self.supported = supported
        models_str = ", ".join(supported[:5])
        super().__init__(f"Unsupported model: '{model}'. Supported: {models_str}...")


def get_vision_model(model: str | None = None) -> VisionModelPort:
    """VisionModel 생성 (per-request).

    Args:
        model: 모델명 (None이면 기본값 사용)

    Returns:
        VisionModelPort 구현체

    Raises:
        UnsupportedModelError: 지원하지 않는 모델인 경우
    """
    settings = get_settings()
    if model is None:
        model = settings.llm_default_model

    # 가드레일: 지원 모델 검증
    if not settings.validate_model(model):
        raise UnsupportedModelError(model, settings.get_supported_models())

    provider = settings.resolve_provider(model)
    api_key = settings.get_api_key(provider)

    if provider == "gemini":
        return GeminiVisionAdapter(model=model, api_key=api_key)
    # 기본: GPT
    return GPTVisionAdapter(model=model, api_key=api_key)


def get_llm(model: str | None = None) -> LLMPort:
    """LLM 생성 (per-request).

    Args:
        model: 모델명 (None이면 기본값 사용)

    Returns:
        LLMPort 구현체

    Raises:
        UnsupportedModelError: 지원하지 않는 모델인 경우
    """
    settings = get_settings()
    if model is None:
        model = settings.llm_default_model

    # 가드레일: 지원 모델 검증
    if not settings.validate_model(model):
        raise UnsupportedModelError(model, settings.get_supported_models())

    provider = settings.resolve_provider(model)
    api_key = settings.get_api_key(provider)

    if provider == "gemini":
        return GeminiLLMAdapter(model=model, api_key=api_key)
    # 기본: GPT
    return GPTLLMAdapter(model=model, api_key=api_key)


# ============================================================
# Step Factories (per-request, Port 주입)
# ============================================================


def get_vision_step(model: str | None = None) -> VisionStep:
    """VisionStep 생성.

    Args:
        model: 모델명 (None이면 기본값 사용)

    Returns:
        VisionStep 인스턴스
    """
    return VisionStep(
        vision_model=get_vision_model(model),
        prompt_repository=get_prompt_repository(),
    )


def get_rule_step() -> RuleStep:
    """RuleStep 생성."""
    return RuleStep(retriever=get_retriever())


def get_answer_step(model: str | None = None) -> AnswerStep:
    """AnswerStep 생성.

    Args:
        model: 모델명 (None이면 기본값 사용)

    Returns:
        AnswerStep 인스턴스
    """
    return AnswerStep(
        llm=get_llm(model),
        prompt_repository=get_prompt_repository(),
    )


def get_reward_step(celery_app: "Celery") -> RewardStep:
    """RewardStep 생성.

    Args:
        celery_app: Celery 앱 인스턴스

    Returns:
        RewardStep 인스턴스
    """
    return RewardStep(
        celery_app=celery_app,
        event_publisher=get_event_publisher(),
        result_cache=get_result_cache(),
    )


# ============================================================
# Pipeline Factories
# ============================================================


def get_step_runner() -> SingleStepRunner:
    """SingleStepRunner 생성 (기존 Celery Chain 호환)."""
    return SingleStepRunner(event_publisher=get_event_publisher())


def get_checkpointing_step_runner(
    skip_completed: bool = True,
) -> CheckpointingStepRunner:
    """CheckpointingStepRunner 생성 (체크포인팅 기능 추가).

    Args:
        skip_completed: 이미 완료된 Step 건너뛰기 여부 (기본: True)

    Returns:
        CheckpointingStepRunner 인스턴스
    """
    return CheckpointingStepRunner(
        event_publisher=get_event_publisher(),
        context_store=get_context_store(),
        skip_completed=skip_completed,
    )


def create_classify_pipeline(
    celery_app: "Celery",
    model: str | None = None,
) -> ClassifyPipeline:
    """ClassifyPipeline 생성 - 전체 DI 조립.

    Args:
        celery_app: Celery 앱 인스턴스
        model: 모델명 (None이면 기본값 사용)

    Returns:
        ClassifyPipeline 인스턴스
    """
    steps = [
        ("vision", get_vision_step(model)),
        ("rule", get_rule_step()),
        ("answer", get_answer_step(model)),
        ("reward", get_reward_step(celery_app)),
    ]

    return ClassifyPipeline(
        steps=steps,
        event_publisher=get_event_publisher(),
    )


# ============================================================
# Context Helpers
# ============================================================


def create_context(
    task_id: str,
    user_id: str,
    image_url: str,
    user_input: str | None = None,
    model: str | None = None,
) -> ClassifyContext:
    """ClassifyContext 생성 헬퍼.

    Args:
        task_id: 작업 ID
        user_id: 사용자 ID
        image_url: 이미지 URL
        user_input: 사용자 입력
        model: 모델명 (None이면 기본값 사용)

    Returns:
        ClassifyContext 인스턴스
    """
    settings = get_settings()
    if model is None:
        model = settings.llm_default_model

    return ClassifyContext(
        task_id=task_id,
        user_id=user_id,
        image_url=image_url,
        user_input=user_input,
        llm_provider=settings.resolve_provider(model),
        llm_model=model,
    )
