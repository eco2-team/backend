"""LoginAuditService - 로그인 감사 기록 서비스.

"연주자" 역할: 로그인 감사 엔티티 생성을 담당합니다.
UseCase(지휘자)가 이 서비스를 호출하여 엔티티를 생성하고,
Port(Gateway)는 UseCase가 직접 호출합니다.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from uuid import UUID, uuid4

from apps.auth.domain.entities.login_audit import LoginAudit

logger = logging.getLogger(__name__)


class LoginAuditService:
    """로그인 감사 기록 서비스 (순수 엔티티 팩토리).

    Responsibilities:
        - 로그인 감사 엔티티 생성
        - ID, timestamp 등 기본값 설정

    Note:
        Port(Gateway) 호출은 UseCase가 직접 담당합니다.
    """

    def create_login_audit(
        self,
        *,
        user_id: UUID,
        provider: str,
        access_jti: str,
        login_ip: str | None = None,
        user_agent: str | None = None,
    ) -> LoginAudit:
        """로그인 감사 엔티티를 생성합니다.

        Args:
            user_id: 사용자 ID
            provider: OAuth 프로바이더
            access_jti: 액세스 토큰 JTI
            login_ip: 로그인 IP 주소 (선택)
            user_agent: User-Agent (선택)

        Returns:
            생성된 LoginAudit 엔티티
        """
        login_audit = LoginAudit(
            id=uuid4(),
            user_id=user_id,
            provider=provider,
            jti=access_jti,
            login_ip=login_ip,
            user_agent=user_agent,
            issued_at=datetime.now(timezone.utc),
        )

        logger.debug(
            "Login audit entity created",
            extra={
                "user_id": str(user_id),
                "provider": provider,
                "audit_id": str(login_audit.id),
            },
        )

        return login_audit
