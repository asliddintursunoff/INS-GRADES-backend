from datetime import datetime
import math
from pydantic import BaseModel, field_validator


class UserBase(BaseModel):
    telegram_id:str
    
class CreateUser(UserBase):
    student_id:str



class CreateFullUserByCsv(BaseModel):
    telegram_id:str|None
    student_id:str
    group_name:str
    first_name:str|None
    last_name:str|None
    password:str|None = None
    is_subscribed: bool = False
    subscribtion_started:datetime|None
    subscribtion_end:datetime | None
    is_started:bool = False
    started_date:datetime|None = None


    @field_validator("password", mode="before")
    @classmethod
    def clean_password(cls, v):
        if v is None:
            return None
        if isinstance(v, float) and math.isnan(v):
            return None
        return str(v).strip() if str(v).strip() else None
    
    @field_validator("telegram_id", mode="before")
    @classmethod
    def telegram_to_str(cls, v):
        if v is None:
            return None
        if isinstance(v, float):
            if math.isnan(v):
                return None
            return str(int(v))  # 1220127328.0 -> "1220127328"
        return str(v).strip() if str(v).strip() else None

    @field_validator("subscribtion_started", "subscribtion_end", "started_date", mode="before")
    @classmethod
    def nan_datetime_to_none(cls, v):
        if v is None:
            return None
        if isinstance(v, float) and math.isnan(v):
            return None
        return v