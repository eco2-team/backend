"""LoginAuditGateway Port.

로그인 감사 기록 Gateway 인터페이스입니다.
"""

from typing import Protocol

from apps.auth.domain.entities.login_audit import LoginAudit


class LoginAuditGateway(Protocol):
    """로그인 감사 Gateway.

    구현체:
        - SqlaLoginAuditMapper (infrastructure/adapters/)
    """

    def add(self, login_audit: LoginAudit) -> None:
        """로그인 감사 기록 추가.

        Args:
            login_audit: 추가할 감사 기록 엔티티
        """
        ...
