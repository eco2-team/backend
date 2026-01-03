"""Messaging Infrastructure."""

from apps.users.infrastructure.messaging.default_character_publisher_celery import (
    CeleryDefaultCharacterPublisher,
)

__all__ = ["CeleryDefaultCharacterPublisher"]
