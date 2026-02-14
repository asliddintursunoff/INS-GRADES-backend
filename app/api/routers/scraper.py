from fastapi import APIRouter

from app.database.session_sync import get_sync_session
from app.services.scraping import ScrapService
router = APIRouter()

@router.get("/prepre")
def test():
    with get_sync_session() as session:
        service = ScrapService(session)
        return service.scrape_e_class_for_all()
