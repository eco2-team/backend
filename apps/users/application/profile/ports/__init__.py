"""Profile domain ports.

사용자 프로필 CRUD 관련 포트입니다.
"""

from apps.users.application.profile.ports.profile_gateway import (
    ProfileCommandGateway,
    ProfileQueryGateway,
)

__all__ = [
    "ProfileCommandGateway",
    "ProfileQueryGateway",
]
