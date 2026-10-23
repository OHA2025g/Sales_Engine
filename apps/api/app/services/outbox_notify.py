"""Ask the worker to drain the outbox after the capture transaction commits."""

from app.core.config import get_settings


def notify_outbox() -> None:
    settings = get_settings()
    if settings.environment.lower() == "test":
        return
    try:
        from app.workers.celery_app import celery_app

        celery_app.send_task("process_outbox")
    except Exception:
        return
