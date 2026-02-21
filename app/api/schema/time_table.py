from pydantic import BaseModel,field_validator
from datetime import time

from app.database.models import Weeks

class TimeTableBase(BaseModel):
    subject:str
    group_name:str
    professor:str
    room:str
    week_day:Weeks
    start_time:time
    end_time:time

    @field_validator("week_day",mode="before")
    @classmethod
    def week_day_validator(cls,value:str)->str:
        return Weeks(value.lower())