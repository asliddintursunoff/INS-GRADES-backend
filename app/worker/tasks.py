from app.config import db_settings

import os
from celery import Celery
from kombu import Queue

from app.database.session_sync import get_sync_session
from app.services.scraping import ScrapService

# -------------------------
# Celery app (single instance)
# -------------------------
redis=db_settings.REDIS_DB(10)
celery = Celery(
    "notification_tasks",
    broker= redis,   # Railway env
    backend=redis
)

celery.conf.timezone = "Asia/Tashkent"
celery.conf.enable_utc = True



# Queues
celery.conf.task_queues = (
    Queue("bulk"),
    Queue("realtime"),
)



# Route tasks
celery.conf.task_routes = {
    "app.worker.tasks.take_info_from_eclass": {"queue": "bulk"},
    "app.worker.tasks.take_info_from_eclass_one_user": {"queue": "realtime"},
}




# -------------------------
# Tasks
# -------------------------
@celery.task(name="app.worker.tasks.take_info_from_eclass")
def take_info_from_eclass():
    with get_sync_session() as session:
        service = ScrapService(session)
        service.scrape_e_class_for_all()
        session.commit()

@celery.task(name="app.worker.tasks.take_info_from_eclass_one_user")
def take_info_from_eclass_one_user(user_id):
    with get_sync_session() as session:
        service = ScrapService(session, is_send=False)
        service.scrape_e_class_for_one_user(user_id)
        session.commit()
