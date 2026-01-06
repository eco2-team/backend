"""Scan Worker Entry Point.

Clean Architecture 기반 Celery Worker.

Usage:
    celery -A apps.scan_worker.main worker \\
        --pool=gevent --concurrency=100 \\
        -Q scan.vision,scan.rule,scan.answer,scan.reward \\
        --loglevel=INFO
"""

from scan_worker.setup.celery import celery_app

# Celery app export for worker startup
app = celery_app

if __name__ == "__main__":
    celery_app.start()
