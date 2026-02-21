from fastapi import APIRouter, UploadFile, File, Depends
from app.api.dependencies import subject_session

router = APIRouter(tags=["subjects"], prefix="/subjects")


@router.post("/rebase-with-csv")
async def rebase_subjects(
    service:subject_session,
    file: UploadFile = File(...),
):
    """
    FULL RESET:
    - deletes SubjectMajorLink + Subject
    - re-inserts everything from file
    """
    return await service.replace_subjects_by_csv(file)


@router.post("/update-with-csv")
async def update_subjects(
    service:subject_session,
    file: UploadFile = File(...),
):
    """
    UPDATE/UPSERT:
    - creates subject if missing
    - updates year if changed
    - syncs majors to match the row (adds missing, removes extra)
    """
    return await service.update_subjects_by_csv(file)
