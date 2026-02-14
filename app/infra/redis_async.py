from redis.asyncio import Redis
from app.config import db_settings


redis_user_info_cache_async = Redis.from_url(
    url = db_settings.REDIS_DB(3),
    
)

redis_registered_users = Redis.from_url(
    url = db_settings.REDIS_DB(4),
    
)