import dramatiq
from dramatiq.brokers.redis import RedisBroker
from dramatiq.middleware import Retries, TimeLimit

from app.config import get_settings

settings = get_settings()

redis_broker = RedisBroker(url=settings.redis_url)

# Avoid double-adding default middlewares on re-import
_existing = {type(m) for m in redis_broker.middleware}
if TimeLimit not in _existing:
    redis_broker.add_middleware(TimeLimit())
if Retries not in _existing:
    redis_broker.add_middleware(Retries(max_retries=3))

dramatiq.set_broker(redis_broker)
