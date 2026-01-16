"""Info Worker Entry Point.

Celery app export for worker startup.

Usage:
    celery -A info_worker.main worker --loglevel=info -Q info.collect_news
    celery -A info_worker.main beat --loglevel=info
"""

from info_worker.setup.celery import celery_app

__all__ = ["celery_app"]
