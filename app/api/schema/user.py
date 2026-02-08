from pydantic import BaseModel


class UserBase(BaseModel):
    telegram_id:str
    
class CreateUser(UserBase):
    student_id:str