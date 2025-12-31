"""Application Ports (Gateway Interfaces).

CQRS 패턴에 따라 Command Gateway와 Query Gateway를 분리합니다.
"""

from apps.auth.application.common.ports.user_command_gateway import UserCommandGateway
from apps.auth.application.common.ports.user_query_gateway import UserQueryGateway
from apps.auth.application.common.ports.social_account_gateway import SocialAccountGateway
from apps.auth.application.common.ports.login_audit_gateway import LoginAuditGateway
from apps.auth.application.common.ports.token_service import TokenService
from apps.auth.application.common.ports.state_store import StateStore
from apps.auth.application.common.ports.token_blacklist import TokenBlacklist
from apps.auth.application.common.ports.user_token_store import UserTokenStore
from apps.auth.application.common.ports.outbox_gateway import OutboxGateway
from apps.auth.application.common.ports.flusher import Flusher
from apps.auth.application.common.ports.transaction_manager import TransactionManager
from apps.auth.application.common.ports.blacklist_event_publisher import (
    BlacklistEventPublisher,
)

__all__ = [
    "UserCommandGateway",
    "UserQueryGateway",
    "SocialAccountGateway",
    "LoginAuditGateway",
    "TokenService",
    "StateStore",
    "TokenBlacklist",
    "UserTokenStore",
    "OutboxGateway",
    "Flusher",
    "TransactionManager",
    "BlacklistEventPublisher",
]
