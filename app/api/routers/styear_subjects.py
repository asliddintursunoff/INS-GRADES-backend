from typing import List
from uuid import UUID
from app.api.dependencies import st_year_session,is_root,current_super_user
from app.api.schema.styear import StYearBase,StYearOUT,SubjectOUT

from fastapi import APIRouter, Query

router = APIRouter(
    tags=["ADMIN PANEL"],
    prefix="/adminpanel"
)


@router.get("/student-year",response_model=List[StYearOUT])
async def get_student_years(session:st_year_session,super_user_required :current_super_user):
    return await session.get_studentyear()

@router.post("/student-year")
async def add_student_year(data:StYearBase,session:st_year_session,super_user_required:current_super_user):
    return await session.add_styear(**data.model_dump())




@router.get("/subjects-by-st-year",response_model=List[SubjectOUT])
async def get_subjects_by_st_year(session:st_year_session,super_user_required:current_super_user,student_year_id:UUID = Query(...)):
    return await session.get_subjects_by_styear_id(student_year_id)