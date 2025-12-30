"""Outbox Repository Port (Interface).

This module defines the interface for outbox storage,
following the Dependency Inversion Principle (DIP).

Location: Application Layer
    - Ports belong to the Application layer because they define
      what the application NEEDS from external systems.
    - The application layer owns the interface contract.

Architecture (Hexagonal / Ports & Adapters):
    Application Layer:
        ├── Services (BlacklistEventPublisher)
        │       │
        │       └── uses ─► OutboxRepository (Port/Interface) ◄── THIS FILE
        │
    Infrastructure Layer:
        └── Adapters
                └── RedisOutboxRepository (implements Port)

Reference: https://github.com/ivan-borovets/fastapi-clean-example
"""

from __future__ import annotations

from typing import Protocol


class OutboxRepository(Protocol):
    """Interface for outbox storage operations.

    This port defines what the application needs for outbox functionality.
    Concrete implementations (adapters) are in the infrastructure layer.

    Implementations:
        - RedisOutboxRepository: Production Redis-based implementation
        - InMemoryOutboxRepository: For testing (optional)
    """

    def push(self, key: str, data: str) -> bool:
        """Push data to the outbox queue (FIFO - LPUSH).

        Args:
            key: The outbox queue key
            data: JSON-serialized event data

        Returns:
            True if successful, False otherwise
        """
        ...

    def pop(self, key: str) -> str | None:
        """Pop data from the outbox queue (FIFO - RPOP).

        Args:
            key: The outbox queue key

        Returns:
            JSON-serialized event data, or None if empty
        """
        ...
