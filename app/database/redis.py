from redis import Redis
from app.config import db_settings


    
class_notification_cache = Redis(host=db_settings.REDIS_HOST,
                                port=db_settings.REDIS_PORT,
                                db=0)
