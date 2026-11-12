from celery import Celery

from app.core.config import settings
from app.tasks.jobs import refresh_low_stock_snapshot

broker = settings.REDIS_URL or "redis://localhost:6379/0"
celery_app = Celery("wms", broker=broker, backend=broker)
celery_app.conf.update(
    task_default_queue="wms",
    timezone="UTC",
    enable_utc=True,
    beat_schedule={"refresh-low-stock": {"task": "wms.refresh_low_stock", "schedule": 3600.0}},
)


@celery_app.task(name="wms.refresh_low_stock")
def refresh_low_stock() -> int:
    return refresh_low_stock_snapshot()
