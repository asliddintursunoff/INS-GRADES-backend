from fastapi import UploadFile,HTTPException

import pandas as pd
from pydantic_core import ValidationError

from app.database.models import Subject
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import delete

from pydantic import BaseModel, field_validator, model_validator

class SubjectBase(BaseModel):
    name: str
    short_name: str | None = None

    @model_validator(mode="after")
    def generate_short_name(self):
        if not self.short_name:
            words = self.name.replace("&"," ")
            initials = "".join(word[0] for word in words.split() if word)
            self.short_name = initials
        return self
    
ALLOWED_CONTENT_TYPES = [
    "text/csv",
    
]
ALLOWED_EXTENSIONS = ["csv",]


class SubjectService:
    def __init__(self,session:AsyncSession):
        self.session = session

    async def adding_subjects_by_csv(self,file:UploadFile)->str:
        if file.content_type not in ALLOWED_CONTENT_TYPES:
            raise HTTPException(detail="File type not allowed. Allowed only for .csv!",status_code=400)
    
        if file.filename.split('.')[-1].lower() not in ALLOWED_EXTENSIONS:
            raise HTTPException(detail="File type not allowed. Allowed only for .csv!",status_code=400)
        
        df = pd.read_csv(file.file)
        data_lst =  df.to_dict(orient="records")
        
        
        try:
            data = [SubjectBase(**row)  for row in data_lst]
            
            stmp = delete(Subject)
            await self.session.execute(stmp)
            
            self.session.add_all(
                [Subject(**i.model_dump()) for i in data]
            )
            
            await self.session.commit()

            return "successfully updated whole database"

        except ValidationError as e:
            raise HTTPException(detail=str(e),status_code=422)
        except Exception as e:
            raise HTTPException(detail = str(e),status_code=500)
        