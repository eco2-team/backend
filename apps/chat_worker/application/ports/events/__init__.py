"""Event Ports - 이벤트 관련 인터페이스.

분리 이유:
- ProgressNotifier: SSE/UI 진행률 (사용자 피드백용)
- DomainEventBus: 상태 변경 이벤트 (시스템 연동용)

나중에 MQ 이벤트/감사 로그/메트릭과 섞여도 구분 가능.
"""

from .domain_event_bus import DomainEventBusPort
from .progress_notifier import ProgressNotifierPort

__all__ = [
    "ProgressNotifierPort",
    "DomainEventBusPort",
]
