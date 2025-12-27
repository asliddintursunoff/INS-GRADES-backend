from pydantic import BaseModel

class User(BaseModel):
    student_id:str 
    password:str

    
