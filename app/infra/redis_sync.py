from app.config import db_settings
from redis import Redis


redis_scrape_cache = Redis.from_url(
    url=db_settings.REDIS_DB(2),
    decode_responses=True
)
redis_user_info_cache = Redis.from_url(
    url=db_settings.REDIS_DB(3),
    decode_responses=True
)

notification_cache = Redis.from_url(
    url=db_settings.REDIS_DB(9),
    decode_responses=True
)

redis_registered_users_sync = Redis.from_url(
    url = db_settings.REDIS_DB(4),
    
)