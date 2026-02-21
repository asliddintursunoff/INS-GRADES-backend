from fastapi import APIRouter, UploadFile
from app.api.dependencies import proff_session
router = APIRouter(
    tags=["professor"],
    prefix="/proffs"
)



@router.post("/rebase-with-csv")
async def rebase_subjects(session:proff_session,file:UploadFile):
    return await session.adding_proffs_by_csv(file)