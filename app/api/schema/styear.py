from typing import List
from uuid import UUID
from pydantic import BaseModel

class StYearBase(BaseModel):
    year_name:str
    starting_year:int
    graduation_year:int

class StYearOUT(StYearBase):
    id:UUID


class MajorBase(BaseModel):
    id:UUID
    major_name:str

class Professors(BaseModel):
    name:str


class SubjectOUT(BaseModel):
    id:UUID
    short_name:str
    name:str
    
    majors:List[MajorBase]
    professors:List[Professors]



class MajorOUT(BaseModel):
    id:UUID 
    major_name:str
    major_full_name:str|None = None
