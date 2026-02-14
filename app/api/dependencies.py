from app.database.models import User
from app.database.session import get_session,AsyncSession


from fastapi import Depends,Query
from typing import Annotated

from app.services.time_table import TimeTableService
from app.services.users import UserService
from app.services.subjects import SubjectService
from app.services.professors import ProfessorService
from app.services.groups import GroupService
from app.services.classes import ClassService
from app.services.eclass import EClassService

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
