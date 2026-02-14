from fastapi import APIRouter, UploadFile
from app.api.dependencies import subject_session


router = APIRouter(tags=["subjects"],prefix="/subjects")


@router.post("/rebase-with-csv")
async def rebase_subjects(session:subject_session,file:UploadFile):
    return await session.adding_subjects_by_csv(file)