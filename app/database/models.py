from sqlmodel import SQLModel,Field,Column
from sqlalchemy.dialects import postgresql

from datetime import datetime,time
from uuid import UUID,uuid4
from enum import Enum

class Weeks(str,Enum):
    monday = "monday"
    tuesday = "tuesday"
    wednesday = "wednesday"
    thursday = "thursday"
    friday = "friday"
    saturday = "saturday"
    sunday = "sunday"


class Users(SQLModel,table = True):
    id:UUID = Field(
        sa_column=Column(
            postgresql.UUID,
            default=uuid4,
            primary_key=True
        ),
        
    )

    telegram_id:str|None = Field(unique=True,index=True,default=None)
    student_id:str
    group_name:str|None = Field(max_length=50,default=None)
    first_name:str|None = Field(max_length=50)
    last_name:str|None = Field(max_length=50)
    password:str|None
    is_subscribed: bool = Field(default=False)
    subscribtion_started:datetime|None= None
    subscribtion_end:datetime | None= None
    contact_number:str|None = None
    is_started :bool = False


class TimeTable(SQLModel,table=True):
    class_id:UUID = Field(
        sa_column=Column(
            postgresql.UUID,
            default=uuid4,
            primary_key=True
        ),
        
    )

    subject:str = Field(max_length=100)
    group_name:str = Field(max_length=50)
    professor:str = Field(max_length=50)
    room:str|None = None
    week_day:Weeks 
    start_time:time
    end_time:time
