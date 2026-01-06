"""Common Application Components.

공통 인터페이스 및 유틸리티:
- Step: 파이프라인 단계 인터페이스 (Stateless Reducer 패턴)
"""

from scan_worker.application.common.step_interface import Step

__all__ = ["Step"]
