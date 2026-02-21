from redis import Redis
from app.config import db_settings


    
class_notification_cache = Redis.from_url(
    db_settings.REDIS_DB(0),
    decode_responses=True
)
