"""Ports (Interfaces).

Infrastructure와의 계약을 정의하는 인터페이스입니다.

블로그 참고: https://rooftopsnow.tistory.com/126
Port의 파라미터 타입: primitive 타입 사용 (UUID, str, datetime)
- Infrastructure가 Application DTO를 import하지 않음
- 의존성 방향 엄격하게 유지
"""

from apps.auth_worker.application.common.ports.blacklist_store import BlacklistStore

__all__ = ["BlacklistStore"]
