from fastapi import APIRouter,Depends

from app.api.schema.user import CreateUser,UserBase
from app.api.dependencies import user_session

router = APIRouter(tags=["User"],
                   prefix="/user")


@router.post("/register-user")
async def register_user(request:CreateUser,session:user_session):
    return await session.register_by_student_id(request.student_id,request.telegram_id)


@router.get("/is-exist")
async def is_exists_user(session:user_session,request:UserBase = Depends())->bool:
    return await session.is_user_exist(request.telegram_id)
