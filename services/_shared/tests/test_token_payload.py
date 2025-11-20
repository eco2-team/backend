import sys
from pathlib import Path
from uuid import UUID, uuid4

SHARED_ROOT = Path(__file__).resolve().parents[2]
WORKSPACE_ROOT = Path(__file__).resolve().parents[3]
for path in (WORKSPACE_ROOT, SHARED_ROOT):
    if str(path) not in sys.path:
        sys.path.append(str(path))

from services._shared.security.jwt import TokenPayload, TokenType  # noqa: E402


def test_token_payload_exposes_uuid_property():
    identifier = uuid4()
    payload = TokenPayload(
        sub=str(identifier),
        jti="test-jti",
        type=TokenType.ACCESS,
        exp=999999,
        iat=123456,
        provider="test",
    )

    assert payload.user_id == UUID(payload.sub)
