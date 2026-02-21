from fastapi import HTTPException,UploadFile
from pydantic_core import ValidationError
from sqlalchemy import delete
from app.database.models import Group
from sqlalchemy.ext.asyncio import AsyncSession
import pandas as pd
from pydantic import BaseModel

class GroupBase(BaseModel):
    group_name: str
    

    
    
ALLOWED_CONTENT_TYPES = [
    "text/csv",
    
]
ALLOWED_EXTENSIONS = ["csv",]


class GroupService():
    def __init__(self,session:AsyncSession):
        self.session = session

    async def adding_proffs_by_csv(self,file:UploadFile)->str:
        if file.content_type not in ALLOWED_CONTENT_TYPES:
            raise HTTPException(detail="File type not allowed. Allowed only for .csv!",status_code=400)
    
        if file.filename.split('.')[-1].lower() not in ALLOWED_EXTENSIONS:
            raise HTTPException(detail="File type not allowed. Allowed only for .csv!",status_code=400)
        
        df = pd.read_csv(file.file)
        data_lst =  df.to_dict(orient="records")
        
        
        try:
            data = [GroupBase(**row)  for row in data_lst]
            
            stmp = delete(Group)
            await self.session.execute(stmp)
            
            self.session.add_all(
                [Group(**i.model_dump()) for i in data]
            )
            
            await self.session.commit()

            return "successfully updated whole database"

        except ValidationError as e:
            raise HTTPException(detail=str(e),status_code=422)
        except Exception as e:
            raise HTTPException(detail = str(e),status_code=500)
        
        