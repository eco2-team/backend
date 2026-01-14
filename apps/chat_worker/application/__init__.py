"""Chat Worker Application Layer.

유스케이스와 비즈니스 로직을 담당.

구조:
```
application/
├── commands/          # 최상위 유스케이스 엔트리 (메인 커맨드)
│   └── process_chat   # queued → running → [waiting_human] → completed
│
├── intent/            # 의도 분류
│   └── services/
│       └── IntentClassifier
│
├── answer/            # 답변 생성
│   └── services/
│       └── AnswerGenerator
│
├── integrations/      # 외부 서비스 연동 (Tool Calling)
│   ├── character/     # Character API (gRPC)
│   └── location/      # Location API (gRPC)
│
├── interaction/       # Human-in-the-Loop (이벤트 발행만, 대기 X)
│   └── services/
│       └── HumanInputService
│
└── ports/             # 공용 포트
    ├── llm/           # LLM (순수 호출 + 정책)
    ├── events/        # 이벤트 (진행률 + 도메인)
    └── retriever      # RAG 검색
```

상태 모델:
- queued: 작업 대기
- running: 파이프라인 실행 중
- waiting_human: Human-in-the-Loop 대기
- completed: 완료
- failed: 실패
"""

# Commands (최상위 유스케이스)
from .commands import (
    ChatPipelinePort,
    ProcessChatCommand,
    ProcessChatRequest,
    ProcessChatResponse,
)

# Intent
from .intent import IntentClassifier

# Answer
from .answer import AnswerContext, AnswerGeneratorService

# Integrations (외부 서비스)
from .integrations import (
    CharacterClientPort,
    CharacterDTO,
    CharacterService,
    LocationClientPort,
    LocationDTO,
    LocationService,
)

# Interaction (Human-in-the-Loop)
from .interaction import HumanInteractionService, InputRequesterPort

# Ports (공용)
from .ports import (
    DomainEventBusPort,
    LLMClientPort,
    LLMPolicyPort,
    ProgressNotifierPort,
    RetrieverPort,
)

__all__ = [
    # Commands
    "ChatPipelinePort",
    "ProcessChatCommand",
    "ProcessChatRequest",
    "ProcessChatResponse",
    # Intent
    "IntentClassifier",
    # Answer
    "AnswerContext",
    "AnswerGeneratorService",
    # Integrations
    "CharacterClientPort",
    "CharacterDTO",
    "CharacterService",
    "LocationClientPort",
    "LocationDTO",
    "LocationService",
    # Interaction
    "HumanInteractionService",
    "InputRequesterPort",
    # Ports
    "DomainEventBusPort",
    "LLMClientPort",
    "LLMPolicyPort",
    "ProgressNotifierPort",
    "RetrieverPort",
]
