"""Scan Setup - Config, Dependencies, Celery App."""

from scan.setup.celery_app import celery_app
from scan.setup.config import Settings, get_settings

__all__ = ["Settings", "get_settings", "celery_app"]
