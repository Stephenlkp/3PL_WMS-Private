import logging

from app.core.config import settings

logger = logging.getLogger(__name__)


def redis_client():
    if not settings.REDIS_URL:
        return None
    try:
        from redis import Redis

        return Redis.from_url(settings.REDIS_URL, socket_connect_timeout=0.4, socket_timeout=0.4)
    except Exception:
        logger.warning("Redis client could not be created", exc_info=True)
        return None
