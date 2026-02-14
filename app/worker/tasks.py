from app.worker.notification_scheduler import celery
from app.database.session_sync import get_sync_session
from app.services.scraping import ScrapService


@celery.task(name = "app.worker.tasks.take_info_from_eclass")
def take_info_from_eclass():
    with get_sync_session() as session:
        service = ScrapService(session)
        service.scrape_e_class_for_all()
        session.commit()
        

@celery.task(name = "app.worker.tasks.take_info_from_eclass_one_user")
def take_info_from_eclass_one_user(user_id):
    with get_sync_session() as session:
        service = ScrapService(session,is_send=False)
        service.scrape_e_class_for_one_user(user_id)
        session.commit()
        
