"""Intent Classifier - 하위 호환성 모듈.

이 파일은 하위 호환성을 위해 유지됩니다.
실제 구현은 intent_classifier_service.py로 이동했습니다.

Clean Architecture 리팩토링:
- 기존: IntentClassifier (Port 직접 의존)
- 신규: IntentClassifierService (순수 로직, Port 의존 없음)
- 신규: ClassifyIntentCommand (Port 호출, 오케스트레이션)

사용법:
    # 권장 (새 구조)
    from chat_worker.application.services.intent_classifier_service import (
        IntentClassifierService,
    )
    from chat_worker.application.commands.classify_intent_command import (
        ClassifyIntentCommand,
    )

    # 하위 호환 (deprecated)
    from chat_worker.application.services.intent_classifier import (
        IntentClassifier,  # → IntentClassifierService로 이전됨
        MultiIntentClassifier,  # → ClassifyIntentCommand로 통합됨
    )
"""

# Re-export from new module
from chat_worker.application.services.intent_classifier_service import (
    COMPLEX_KEYWORDS,
    CONFIDENCE_THRESHOLD,
    INTENT_CACHE_TTL,
    MULTI_INTENT_CANDIDATE_KEYWORDS,
    SINGLE_INTENT_PATTERNS,
    DecomposedQuery,
    IntentClassificationResult,
    IntentClassifierService,
    MultiIntentDetection,
    MultiIntentDetectionSchema,
    MultiIntentResult,
    QueryDecompositionSchema,
)

# Aliases for backward compatibility
IntentClassifier = IntentClassifierService
MultiIntentClassifier = IntentClassifierService  # 기능은 Command로 통합됨

__all__ = [
    # New names
    "IntentClassifierService",
    "IntentClassificationResult",
    # Backward compatible aliases
    "IntentClassifier",
    "MultiIntentClassifier",
    # DTOs
    "MultiIntentDetection",
    "DecomposedQuery",
    "MultiIntentResult",
    # Schemas
    "MultiIntentDetectionSchema",
    "QueryDecompositionSchema",
    # Constants
    "COMPLEX_KEYWORDS",
    "MULTI_INTENT_CANDIDATE_KEYWORDS",
    "SINGLE_INTENT_PATTERNS",
    "CONFIDENCE_THRESHOLD",
    "INTENT_CACHE_TTL",
]
