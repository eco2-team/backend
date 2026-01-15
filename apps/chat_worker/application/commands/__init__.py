"""Application Commands (CQRS UseCase).

Command: 상태를 변경하는 UseCase.
Node(LangGraph 어댑터)에서 호출.

구조:
- ProcessChatCommand: 최상위 파이프라인 실행
- ClassifyIntentCommand: 의도 분류
- SearchRAGCommand: 분리수거 규정 검색
- GenerateAnswerCommand: 답변 생성
- GetCharacterCommand: 캐릭터 정보 조회
- GetLocationCommand: 주변 위치 검색
- AnalyzeImageCommand: 이미지 분석
- SearchWebCommand: 웹 검색
- EvaluateFeedbackCommand: 피드백 평가
- SearchBulkWasteCommand: 대형폐기물 정보 조회
- SearchRecyclablePriceCommand: 재활용자원 시세 조회

Clean Architecture:
- Command(UseCase): 정책/흐름, Port 조립
- Service: 순수 비즈니스 로직
- Node(Adapter): state 변환 + Command 호출
"""

# AnalyzeImage
from chat_worker.application.commands.analyze_image_command import (
    AnalyzeImageCommand,
    AnalyzeImageInput,
    AnalyzeImageOutput,
)

# ClassifyIntent
from chat_worker.application.commands.classify_intent_command import (
    ClassifyIntentCommand,
    ClassifyIntentInput,
    ClassifyIntentOutput,
)

# EvaluateFeedback
from chat_worker.application.commands.evaluate_feedback_command import (
    EvaluateFeedbackCommand,
    EvaluateFeedbackInput,
    EvaluateFeedbackOutput,
)

# GenerateAnswer
from chat_worker.application.commands.generate_answer_command import (
    GenerateAnswerCommand,
    GenerateAnswerInput,
    GenerateAnswerOutput,
)

# GetCharacter
from chat_worker.application.commands.get_character_command import (
    GetCharacterCommand,
    GetCharacterInput,
    GetCharacterOutput,
)

# GetLocation
from chat_worker.application.commands.get_location_command import (
    GetLocationCommand,
    GetLocationInput,
    GetLocationOutput,
)

# ProcessChat
from chat_worker.application.commands.process_chat import (
    ChatPipelinePort,
    ProcessChatCommand,
    ProcessChatRequest,
    ProcessChatResponse,
)

# SearchRAG
from chat_worker.application.commands.search_rag_command import (
    SearchRAGCommand,
    SearchRAGInput,
    SearchRAGOutput,
)

# SearchWeb
from chat_worker.application.commands.search_web_command import (
    SearchWebCommand,
    SearchWebInput,
    SearchWebOutput,
)

# SearchBulkWaste
from chat_worker.application.commands.search_bulk_waste_command import (
    SearchBulkWasteCommand,
    SearchBulkWasteInput,
    SearchBulkWasteOutput,
)

# SearchRecyclablePrice
from chat_worker.application.commands.search_recyclable_price_command import (
    SearchRecyclablePriceCommand,
    SearchRecyclablePriceInput,
    SearchRecyclablePriceOutput,
)

__all__ = [
    # ProcessChat
    "ChatPipelinePort",
    "ProcessChatCommand",
    "ProcessChatRequest",
    "ProcessChatResponse",
    # ClassifyIntent
    "ClassifyIntentCommand",
    "ClassifyIntentInput",
    "ClassifyIntentOutput",
    # SearchRAG
    "SearchRAGCommand",
    "SearchRAGInput",
    "SearchRAGOutput",
    # GetCharacter
    "GetCharacterCommand",
    "GetCharacterInput",
    "GetCharacterOutput",
    # GetLocation
    "GetLocationCommand",
    "GetLocationInput",
    "GetLocationOutput",
    # AnalyzeImage
    "AnalyzeImageCommand",
    "AnalyzeImageInput",
    "AnalyzeImageOutput",
    # SearchWeb
    "SearchWebCommand",
    "SearchWebInput",
    "SearchWebOutput",
    # GenerateAnswer
    "GenerateAnswerCommand",
    "GenerateAnswerInput",
    "GenerateAnswerOutput",
    # EvaluateFeedback
    "EvaluateFeedbackCommand",
    "EvaluateFeedbackInput",
    "EvaluateFeedbackOutput",
    # SearchBulkWaste
    "SearchBulkWasteCommand",
    "SearchBulkWasteInput",
    "SearchBulkWasteOutput",
    # SearchRecyclablePrice
    "SearchRecyclablePriceCommand",
    "SearchRecyclablePriceInput",
    "SearchRecyclablePriceOutput",
]
