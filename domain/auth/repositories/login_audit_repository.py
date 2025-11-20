import uuid
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from domain.auth.models.login_audit import LoginAudit


class LoginAuditRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def add(
        self,
        *,
        user_id: uuid.UUID,
        provider: str,
        jti: str,
        login_ip: Optional[str],
        user_agent: Optional[str],
    ) -> None:
        record = LoginAudit(
            user_id=user_id,
            provider=provider,
            jti=jti,
            login_ip=login_ip,
            user_agent=user_agent,
        )
        self.session.add(record)
        await self.session.flush()
