from fastapi import APIRouter,UploadFile,File,HTTPException
from sqlalchemy import delete

from typing import List
import pandas as pd
from pydantic import ValidationError

from app.api.schema.time_table import TimeTableBase
from app.api.dependencies import db_session,time_table_session,user_session,current_user
from app.database.models import TimeTable,Weeks



router = APIRouter()



@router.post("/change-time-table")
async def change_time_table(session:time_table_session,file:UploadFile = File(...),):
    return await session.update_whole_time_time(file = file)


# @router.get("/test")
# async def test(session:time_table_session,todays:Weeks):
#     return await session.send_todays_time_table_everymorning(todays)

@router.get("/my-timetable")
async def get_my_timetable(current_user:current_user,session:time_table_session):
    result  = await session.get_user_full_time_table(current_user)
    return result