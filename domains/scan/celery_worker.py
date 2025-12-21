"""Celery worker entry point for Scan domain.

Usage:
    # Development (single worker)
    celery -A domains.scan.celery_worker worker --loglevel=info

    # Production (with concurrency)
    celery -A domains.scan.celery_worker worker \
        --loglevel=info \
        --concurrency=4 \
        --queues=scan.classification,scan.reward
"""

from domains._shared.taskqueue import celery_app

# Import tasks to register them with Celery
from domains.scan.tasks import (  # noqa: F401
    answer_gen,
    reward_grant,
    rule_match,
    vision_scan,
)

# Re-export celery app for CLI
app = celery_app

if __name__ == "__main__":
    app.start()
