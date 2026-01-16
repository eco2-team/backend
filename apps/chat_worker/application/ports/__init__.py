"""Application Ports (Layer-first).

모든 Port(추상화/인터페이스)를 한 곳에서 관리.
Infrastructure에서 Adapter로 구현.

Layer-first 구조:
- ports/: 이 폴더 (추상화)
- services/: 비즈니스 로직
- commands/: UseCase (정책/흐름)
- dto/: Data Transfer Objects

카테고리:
- LLM: LLMClientPort, LLMPolicyPort
- Vision: VisionModelPort
- Events: ProgressNotifierPort, DomainEventBusPort
- Retrieval: RetrieverPort
- Cache: CachePort
- Metrics: MetricsPort
- WebSearch: WebSearchPort
- Integrations: CharacterClientPort, LocationClientPort
- Feedback: LLMFeedbackEvaluatorPort
- Interaction: InputRequesterPort, InteractionStateStorePort
- Prompt: PromptBuilderPort
"""

# LLM
# Cache
from chat_worker.application.ports.cache import CachePort

# Circuit Breaker
from chat_worker.application.ports.circuit_breaker import (
    CircuitBreakerPort,
    CircuitBreakerRegistryPort,
)

# Integrations - Bulk Waste
from chat_worker.application.ports.bulk_waste_client import (
    BulkWasteClientPort,
    BulkWasteCollectionDTO,
    BulkWasteItemDTO,
    WasteDisposalInfoDTO,
    WasteInfoSearchResponse,
)

# Integrations - Recyclable Price
from chat_worker.application.ports.recyclable_price_client import (
    RecyclableCategory,
    RecyclablePriceClientPort,
    RecyclablePriceDTO,
    RecyclablePriceSearchResponse,
    RecyclableRegion,
)

# Integrations - Character
from chat_worker.application.ports.character_client import (
    CharacterClientPort,
    CharacterDTO,
)

# Events
from chat_worker.application.ports.events import (
    DomainEventBusPort,
    ProgressNotifierPort,
)

# Interaction - HITL
from chat_worker.application.ports.input_requester import (
    InputRequesterPort,
)
from chat_worker.application.ports.interaction_state_store import (
    InteractionStateStorePort,
)
from chat_worker.application.ports.llm import LLMClientPort, LLMPolicyPort

# Feedback - LLM 평가기
from chat_worker.application.ports.llm_evaluator import (
    LLMFeedbackEvaluatorPort,
)

# Integrations - Location
from chat_worker.application.ports.location_client import (
    LocationClientPort,
    LocationDTO,
)

# Metrics
from chat_worker.application.ports.metrics import MetricsPort

# Prompt Builder
from chat_worker.application.ports.prompt_builder import (
    PromptBuilderPort,
)

# Prompt Loader
from chat_worker.application.ports.prompt_loader import (
    PromptLoaderPort,
)

# Retrieval
from chat_worker.application.ports.retrieval import RetrieverPort

# Vision
from chat_worker.application.ports.vision import VisionModelPort

# Image Generator
from chat_worker.application.ports.image_generator import (
    ImageGenerationError,
    ImageGenerationResult,
    ImageGeneratorPort,
)

# Web Search
from chat_worker.application.ports.web_search import WebSearchPort

__all__ = [
    # LLM
    "LLMClientPort",
    "LLMPolicyPort",
    # Vision
    "VisionModelPort",
    # Image Generator
    "ImageGeneratorPort",
    "ImageGenerationResult",
    "ImageGenerationError",
    # Events
    "ProgressNotifierPort",
    "DomainEventBusPort",
    # Retrieval
    "RetrieverPort",
    # Cache
    "CachePort",
    # Circuit Breaker
    "CircuitBreakerPort",
    "CircuitBreakerRegistryPort",
    # Metrics
    "MetricsPort",
    # Web Search
    "WebSearchPort",
    # Integrations - Bulk Waste
    "BulkWasteClientPort",
    "BulkWasteCollectionDTO",
    "BulkWasteItemDTO",
    "WasteDisposalInfoDTO",
    "WasteInfoSearchResponse",
    # Integrations - Recyclable Price
    "RecyclableCategory",
    "RecyclablePriceClientPort",
    "RecyclablePriceDTO",
    "RecyclablePriceSearchResponse",
    "RecyclableRegion",
    # Integrations - Character/Location
    "CharacterClientPort",
    "CharacterDTO",
    "LocationClientPort",
    "LocationDTO",
    # Feedback
    "LLMFeedbackEvaluatorPort",
    # Interaction
    "InputRequesterPort",
    "InteractionStateStorePort",
    # Prompt
    "PromptBuilderPort",
    "PromptLoaderPort",
]
