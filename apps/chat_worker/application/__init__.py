"""Chat Worker Application Layer (Layer-first).

Clean Architecture의 Application Layer.
모든 UseCase, Service, Port, DTO를 중앙에서 관리.

구조:
├── commands/     # UseCase (CQRS Command)
├── services/     # 순수 비즈니스 로직
├── ports/        # 추상화 (인터페이스)
└── dto/          # Data Transfer Objects

사용 예시:
    from chat_worker.application.commands import ClassifyIntentCommand
    from chat_worker.application.services import IntentClassifier
    from chat_worker.application.ports import LLMClientPort
    from chat_worker.application.dto import AnswerContext
"""

# Commands (UseCase)
from chat_worker.application.commands import (
    # ProcessChat
    ChatPipelinePort,
    # ClassifyIntent
    ClassifyIntentCommand,
    ClassifyIntentInput,
    ClassifyIntentOutput,
    # EvaluateFeedback
    EvaluateFeedbackCommand,
    EvaluateFeedbackInput,
    EvaluateFeedbackOutput,
    # GenerateAnswer
    GenerateAnswerCommand,
    GenerateAnswerInput,
    GenerateAnswerOutput,
    # GetCharacter
    GetCharacterCommand,
    GetCharacterInput,
    GetCharacterOutput,
    ProcessChatCommand,
    ProcessChatRequest,
    ProcessChatResponse,
    # SearchRAG
    SearchRAGCommand,
    SearchRAGInput,
    SearchRAGOutput,
)

# DTOs
from chat_worker.application.dto import (
    AnswerContext,
    ChatIntent,
    FallbackResult,
    FeedbackResult,
)

# Ports
from chat_worker.application.ports import (
    CachePort,
    CharacterClientPort,
    DomainEventBusPort,
    InputRequesterPort,
    InteractionStateStorePort,
    LLMClientPort,
    LLMFeedbackEvaluatorPort,
    LLMPolicyPort,
    LocationClientPort,
    MetricsPort,
    ProgressNotifierPort,
    RetrieverPort,
    VisionModelPort,
    WebSearchPort,
)

# Services
from chat_worker.application.services import (
    AnswerGeneratorService,
    CategoryExtractorService,
    CharacterService,
    FallbackOrchestrator,
    FeedbackEvaluatorService,
    HumanInteractionService,
    IntentClassifier,
    LocationService,
    MultiIntentClassifier,
    RAGSearcherService,
)

__all__ = [
    # Commands
    "ChatPipelinePort",
    "ProcessChatCommand",
    "ProcessChatRequest",
    "ProcessChatResponse",
    "ClassifyIntentCommand",
    "ClassifyIntentInput",
    "ClassifyIntentOutput",
    "SearchRAGCommand",
    "SearchRAGInput",
    "SearchRAGOutput",
    "GetCharacterCommand",
    "GetCharacterInput",
    "GetCharacterOutput",
    "GenerateAnswerCommand",
    "GenerateAnswerInput",
    "GenerateAnswerOutput",
    "EvaluateFeedbackCommand",
    "EvaluateFeedbackInput",
    "EvaluateFeedbackOutput",
    # Services
    "IntentClassifier",
    "MultiIntentClassifier",
    "RAGSearcherService",
    "AnswerGeneratorService",
    "FeedbackEvaluatorService",
    "FallbackOrchestrator",
    "CharacterService",
    "CategoryExtractorService",
    "LocationService",
    "HumanInteractionService",
    # Ports
    "LLMClientPort",
    "LLMPolicyPort",
    "VisionModelPort",
    "ProgressNotifierPort",
    "DomainEventBusPort",
    "RetrieverPort",
    "CachePort",
    "MetricsPort",
    "WebSearchPort",
    "CharacterClientPort",
    "LocationClientPort",
    "LLMFeedbackEvaluatorPort",
    "InputRequesterPort",
    "InteractionStateStorePort",
    # DTOs
    "ChatIntent",
    "AnswerContext",
    "FeedbackResult",
    "FallbackResult",
]
