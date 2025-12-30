"""Application Ports (Interfaces).

This module contains interfaces that define the contracts
between the application layer and external systems.

Following Clean Architecture / Hexagonal Architecture:
- Ports are defined in the Application layer
- Adapters implement these ports in the Infrastructure layer
"""

from domains.auth.application.ports.outbox import OutboxRepository

__all__ = ["OutboxRepository"]
