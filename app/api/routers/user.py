from io import TextIOWrapper
from fastapi import APIRouter,Depends, UploadFile

from app.api.schema.user import CreateUser,UserBase
from app.api.dependencies import user_session,db_session,current_user

router = APIRouter(tags=["user"],
                   prefix="/user")



@router.post("/rebase-with-csv")
async def rebase_subjects(session:user_session,file:UploadFile):
    return await session.adding_subjects_by_csv(file)





@router.post("/register-user")
async def register_user(request:CreateUser,session:user_session):
    return await session.register_by_student_id(request.student_id,request.telegram_id)




@router.get("/is-exist")
async def is_exists_user(session:user_session,request:UserBase = Depends())->bool:
    return await session.is_user_exist(request.telegram_id)


@router.get("/register-user-eclass-and-load-data")
async def check_password(student_id,session:user_session,password:str,telegram_id:str)->bool:
    if await session.register_with_password(student_id,password,telegram_id):
        return 






