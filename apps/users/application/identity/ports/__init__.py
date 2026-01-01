"""Identity domain ports.

소셜 계정 연결 관련 포트입니다.
"""

from apps.users.application.identity.ports.social_account_gateway import (
    SocialAccountInfo,
    SocialAccountQueryGateway,
)

__all__ = [
    "SocialAccountInfo",
    "SocialAccountQueryGateway",
]
