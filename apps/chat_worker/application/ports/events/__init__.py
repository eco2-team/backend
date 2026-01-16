"""Event Ports - 이벤트 관련 인터페이스.

분리 이유:
- ProgressNotifier: SSE/UI 진행률 (사용자 피드백용)
- DomainEventBus: 상태 변경 이벤트 (시스템 연동용)

Note:
    Event-First Architecture 적용으로 MessageSavePublisher 제거.
    done 이벤트에 persistence 데이터를 포함하여
    별도 Consumer Group(chat-persistence)이 PostgreSQL에 저장.
"""

from .domain_event_bus import DomainEventBusPort
from .progress_notifier import ProgressNotifierPort

__all__ = [
    "ProgressNotifierPort",
    "DomainEventBusPort",
]
