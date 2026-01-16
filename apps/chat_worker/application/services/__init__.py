"""Application Services (Layer-first).

순수 비즈니스 로직. Port 의존 없이 순수 로직만 담당.
Command(UseCase)에서 Port와 Service를 조립하여 사용.

Clean Architecture 원칙:
- Service: 순수 비즈니스 로직 (Port 의존 없음)
- Command: Port 호출, Service 호출, 오케스트레이션

Layer-first 구조:
- services/: 이 폴더 (비즈니스 로직)
- commands/: UseCase (정책/흐름, Port 호출)
- ports/: 추상화 (인터페이스)
- dto/: Data Transfer Objects
"""

# Intent 분류 (순수 로직)
# 답변 생성
from chat_worker.application.services.answer_generator import (
    AnswerGeneratorService,
)
from chat_worker.application.services.category_extractor import (
    CategoryExtractorService,
)

# Character 서비스
from chat_worker.application.services.character_service import (
    CharacterService,
)

# Fallback 오케스트레이션
from chat_worker.application.services.fallback_orchestrator import (
    FallbackOrchestrator,
)

# Feedback 평가
from chat_worker.application.services.feedback_evaluator import (
    FeedbackEvaluatorService,
)

# Human Interaction 서비스
from chat_worker.application.services.human_interaction_service import (
    HumanInteractionService,
)

# 하위 호환성
from chat_worker.application.services.intent_classifier import (
    IntentClassifier,  # alias for IntentClassifierService
    MultiIntentClassifier,  # alias for IntentClassifierService
)
from chat_worker.application.services.intent_classifier_service import (
    IntentClassificationResult,
    IntentClassifierService,
)

# Location 서비스
from chat_worker.application.services.location_service import (
    LocationService,
)

# RAG 검색
from chat_worker.application.services.rag_searcher import RAGSearcherService

# Vision 서비스
from chat_worker.application.services.vision_service import (
    VisionService,
)

# Web Search 서비스
from chat_worker.application.services.web_search_service import (
    WebSearchService,
)

# Bulk Waste 서비스
from chat_worker.application.services.bulk_waste_service import (
    BulkWasteService,
)

# Recyclable Price 서비스
from chat_worker.application.services.recyclable_price_service import (
    RecyclablePriceService,
)

# Progress Tracker (동적 라우팅용)
from chat_worker.application.services.progress_tracker import (
    DynamicProgressTracker,
    PHASE_PROGRESS,
    SUBAGENT_NODES,
)

__all__ = [
    # Intent (순수 로직)
    "IntentClassifierService",
    "IntentClassificationResult",
    # Intent (하위 호환)
    "IntentClassifier",
    "MultiIntentClassifier",
    # RAG
    "RAGSearcherService",
    # Answer
    "AnswerGeneratorService",
    # Feedback
    "FeedbackEvaluatorService",
    # Fallback
    "FallbackOrchestrator",
    # Character
    "CharacterService",
    "CategoryExtractorService",
    # Location
    "LocationService",
    # Vision
    "VisionService",
    # WebSearch
    "WebSearchService",
    # Interaction
    "HumanInteractionService",
    # BulkWaste
    "BulkWasteService",
    # RecyclablePrice
    "RecyclablePriceService",
    # Progress Tracker
    "DynamicProgressTracker",
    "PHASE_PROGRESS",
    "SUBAGENT_NODES",
]
