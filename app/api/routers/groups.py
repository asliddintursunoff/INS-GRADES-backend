from fastapi import APIRouter, UploadFile
from app.api.dependencies import group_session

router = APIRouter(
    tags=["group"],
    prefix="/group"
)



@router.post("/rebase-with-csv")
async def rebase_subjects(session:group_session,file:UploadFile):
    return await session.adding_proffs_by_csv(file)