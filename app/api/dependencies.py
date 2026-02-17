from uuid import UUID
from sqlalchemy import select
from app.database.models import User
from app.database.session import get_session,AsyncSession


from fastapi import Depends, HTTPException,Query
from typing import Annotated

from app.services.time_table import TimeTableService
from app.services.users import UserService
from app.services.subjects import SubjectService
from app.services.professors import ProfessorService
from app.services.groups import GroupService
from app.services.classes import ClassService
from app.services.eclass import EClassService
from app.services.superuser import SuperUser,SuperUserService



db_session = Annotated[AsyncSession,Depends(get_session)]

def get_user_dependency(session:db_session):
    return UserService(session=session)

user_session = Annotated[UserService,Depends(get_user_dependency)]

def get_time_table_session(session:db_session):

    return TimeTableService(session)

time_table_session = Annotated[TimeTableService,Depends(get_time_table_session)]



async def get_current_user_with_password(session:db_session,telegram_id:str = Query(...)):
    session =  await UserService(session).get_current_user_with_password(telegram_id)
    return session

current_user_with_password = Annotated[User,Depends(get_current_user_with_password)]

async def get_current_user(session:db_session,telegram_id:str = Query(...)):
    session =  await UserService(session).get_current_user(telegram_id)
    return session

current_user = Annotated[User,Depends(get_current_user)]


async def get_subject_session(session:db_session):
    return SubjectService(session)
subject_session = Annotated[SubjectService,Depends(get_subject_session)]



async def get_proff_session(session:db_session):
    return ProfessorService(session)
proff_session = Annotated[ProfessorService,Depends(get_proff_session)]


async def get_group_session(session:db_session):
    return GroupService(session)
group_session = Annotated[GroupService,Depends(get_group_session)]



async def get_class_session(session:db_session):
    return ClassService(session)
class_session = Annotated[ClassService,Depends(get_class_session)]


async def get_eclass_session(session:db_session):
    return EClassService(session)
eclass_session = Annotated[EClassService,Depends(get_eclass_session)]




#Super User


from fastapi.security import OAuth2PasswordBearer
from app.core.securty import decode_token

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/superuser/login")
async def get_is_root(session:db_session,
                      token:str = Depends(oauth2_scheme)):
    payload = decode_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid token")
    
    super_user_id = payload.get("sub")
    if not super_user_id:
        raise HTTPException(status_code=401, detail="Invalid token payload")
    stmt = await session.execute(select(SuperUser).where(SuperUser.id == UUID(super_user_id)))
    super_user = stmt.scalar_one_or_none()

    if not super_user:
        raise HTTPException(detail="Super user not found",status_code=404)
    if super_user.is_root ==False:
        raise  HTTPException(detail="Root super user required",status_code=403)
    
    return super_user

is_root = Annotated[None,Depends(get_is_root)]


async def get_super_user_session(session:db_session):
    return SuperUserService(session)

super_user_session = Annotated[SuperUserService,Depends(get_super_user_session)]



async def get_current_super_user(
        session:db_session,
        token:str = Depends(oauth2_scheme)):
    payload = decode_token(token)

    if not payload:
        raise HTTPException(status_code=401, detail="Invalid token")
    
    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token payload")
    
    result = await session.execute(select(SuperUser).where(SuperUser.id == UUID(user_id)))
    re = result.scalar_one_or_none()
    if not re:
        raise  HTTPException(status_code=401, detail="User not found")
    
    return re

current_super_user = Annotated[User,Depends(get_current_super_user)]