from slowapi import Limiter
from slowapi.util import get_remote_address

from app.core.config import settings

_kwargs: dict = {
    "key_func": get_remote_address,
    "enabled": settings.RATE_LIMIT_ENABLED,
    "storage_uri": settings.RATE_LIMIT_STORAGE,
    "headers_enabled": True,
}
if settings.RATE_LIMIT_ENABLED:
    _kwargs["default_limits"] = ["240/minute"]

limiter = Limiter(**_kwargs)
