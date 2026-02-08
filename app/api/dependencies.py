from app.database.session import get_session,AsyncSession


from fastapi import Depends,Query
from typing import Annotated

from app.services.time_table import TimeTableService
from app.services.users import UserService,Users

db_session = Annotated[AsyncSession,Depends(get_session)]

def get_user_dependency(session:db_session):
    return UserService(session=session)

user_session = Annotated[UserService,Depends(get_user_dependency)]

def get_time_table_session(session:db_session,user_session:user_session):

    return TimeTableService(session,user_session)

time_table_session = Annotated[TimeTableService,Depends(get_time_table_session)]



async def get_current_user(session:db_session,telegram_id:str = Query(...)):
    session =  await UserService(session).get_user_by_telegram_id(telegram_id)
    return session

current_user = Annotated[Users,Depends(get_current_user)]