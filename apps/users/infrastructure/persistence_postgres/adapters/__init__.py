"""Infrastructure adapters implementing application ports."""

from apps.users.infrastructure.persistence_postgres.adapters.identity_gateway_sqla import (
    SqlaIdentityCommandGateway,
    SqlaIdentityQueryGateway,
)
from apps.users.infrastructure.persistence_postgres.adapters.social_account_gateway_sqla import (
    SqlaSocialAccountQueryGateway,
)
from apps.users.infrastructure.persistence_postgres.adapters.transaction_manager_sqla import (
    SqlaTransactionManager,
)
from apps.users.infrastructure.persistence_postgres.adapters.user_character_gateway_sqla import (
    SqlaUserCharacterQueryGateway,
)
from apps.users.infrastructure.persistence_postgres.adapters.user_gateway_sqla import (
    SqlaUserCommandGateway,
    SqlaUserQueryGateway,
)

__all__ = [
    "SqlaUserQueryGateway",
    "SqlaUserCommandGateway",
    "SqlaUserCharacterQueryGateway",
    "SqlaTransactionManager",
    "SqlaSocialAccountQueryGateway",
    "SqlaIdentityQueryGateway",
    "SqlaIdentityCommandGateway",
]
