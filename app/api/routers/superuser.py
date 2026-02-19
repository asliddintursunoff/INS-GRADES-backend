import enum
from fastapi import APIRouter, Depends
from fastapi.security import OAuth2PasswordRequestForm
from fastapi.responses import StreamingResponse
from io import BytesIO
from typing import List

from uuid import UUID

from app.api.dependencies import is_root,super_user_session,current_super_user





from pydantic import BaseModel, ConfigDict

class SuperUserBase(BaseModel):
    username:str
    first_name:str
    last_name:str
    
class SuperUserCreate(SuperUserBase):
    password:str
    telegram_id:str|None = None
    is_root:bool = False

class LoginSuperUser(BaseModel):
    username:str
    password:str

class SuperUserOut(SuperUserBase):
    model_config = ConfigDict(from_attributes=True)
    id:UUID
    telegram_id:str|None
    is_root:bool


class Token(BaseModel):
    access_token:str
    token_type:str
router = APIRouter(
    prefix="/superuser",
    tags=["ADMIN PANEL - Super User"]
)


#ENUM
import enum

class AcademicYear(str, enum.Enum):
    freshman = "freshman"
    sophomore = "sophomore"
    junior = "junior"
    senior = "senior"

YEAR_TO_COHORT = {
    AcademicYear.freshman: 25,
    AcademicYear.sophomore: 24,
    AcademicYear.junior: 23,
    AcademicYear.senior: 22,
}


class GroupType(str, enum.Enum):
    BM = "BM"
    BUS = "BUS"
    CIE = "CIE"
    CSE = "CSE"
    EMBA = "EMBA"
    ICE = "ICE"
    IT = "IT"
    LOG = "LOG"
    MBA = "MBA"



@router.post("/register",status_code=201)
async def register(data:SuperUserCreate,session:super_user_session,root_required:is_root):
    await session.create_super_user(
        **data.model_dump()
    )
    return {"ok": True}


@router.post("/login",response_model=Token)
async def login(session:super_user_session,form:OAuth2PasswordRequestForm = Depends()):
    return await session.authenticate_user(username=form.username,password=form.password)


@router.get("/me",response_model=SuperUserOut)
async def me(me:current_super_user):
    return me


@router.get('/super-users',response_model=List[SuperUserOut])
async def get_super_users_all(session:super_user_session,root_user:is_root):
    return await session.get_super_users()

@router.get('/super-user',response_model=SuperUserOut)
async def get_super_super_user(user_id:str,session:super_user_session,root_user:is_root):
    return await session.get_user_by_id(user_id)

@router.delete('/super-user')
async def delete_super_user(user_id:str,session:super_user_session,root_user:is_root):
    return await session.delete_super_user(user_id,root_user)


@router.get("/matrix")
async def matrix(
    program: GroupType,
    year: AcademicYear,
    session: super_user_session,
    current_user:current_super_user
):
    cohort = YEAR_TO_COHORT[year]
    return await session.get_attendance_matrix_by_program_cohort(program, cohort)



@router.get("/matrix/excel")
async def download_matrix_excel(
    program: GroupType,
    year: AcademicYear,
    session: super_user_session,
    current_user:current_super_user
):
    cohort = YEAR_TO_COHORT[year]
    xlsx_bytes, filename = await session.export_attendance_matrix_excel_professional(program, cohort)

    return StreamingResponse(
        BytesIO(xlsx_bytes),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'}
    )