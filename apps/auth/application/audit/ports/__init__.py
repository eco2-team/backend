"""Audit domain ports.

감사 로그 관련 포트입니다.
"""

from apps.auth.application.audit.ports.login_audit_gateway import LoginAuditGateway

__all__ = [
    "LoginAuditGateway",
]
