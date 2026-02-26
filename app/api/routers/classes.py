from fastapi import APIRouter, UploadFile
from app.api.dependencies import class_session

router = APIRouter(
    tags=["class"],
    prefix="/class"
)



@router.post("/rebase-with-csv")
async def rebase_subjects(session:class_session,file:UploadFile):
    return await session.adding_classes_by_csv(file)

@router.post("/update-classes-with-csv")
async def update_classes(session:class_session,file:UploadFile):
    return await session.replace_classtimes_by_csv(file)
