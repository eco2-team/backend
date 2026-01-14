"""Application Commands - 최상위 유스케이스 엔트리.

CQRS의 Command 부분.
메인 유스케이스는 최상위, 나머지는 서브 유스케이스/도메인 서비스.

호출 순서:
```
ProcessChatCommand
    │
    ├── 1. Intent (의도 분류)
    │       └── IntentClassifier
    │
    ├── 2. Route by Intent
    │       ├── waste → RAG
    │       ├── character → integrations/character
    │       └── location → integrations/location + interaction
    │
    └── 3. Answer (답변 생성)
            └── AnswerGenerator
```

상태 모델:
- queued: 작업 대기
- running: 파이프라인 실행 중
- waiting_human: Human-in-the-Loop 대기
- completed: 완료
- failed: 실패
"""

from .process_chat import (
    ChatPipelinePort,
    ProcessChatCommand,
    ProcessChatRequest,
    ProcessChatResponse,
)

__all__ = [
    "ChatPipelinePort",
    "ProcessChatCommand",
    "ProcessChatRequest",
    "ProcessChatResponse",
]
