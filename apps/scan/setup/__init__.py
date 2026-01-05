"""Scan Setup - Config, Dependencies, Celery App."""

from apps.scan.setup.celery_app import celery_app
from apps.scan.setup.config import Settings, get_settings

__all__ = ["Settings", "get_settings", "celery_app"]
