


from datetime import  datetime
from typing import List
from zoneinfo import ZoneInfo
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select,delete
from fastapi import HTTPException,UploadFile
from pydantic_core import ValidationError
import pandas as pd


from app.database.models import Class,Group,User
from app.api.schema.user import CreateFullUserByCsv
from app.scraper.script import EclassClient


ALLOWED_CONTENT_TYPES = [
    "text/csv",
    
]
ALLOWED_EXTENSIONS = ["csv",]



class UserService():
    def __init__(self,session:AsyncSession):
        self.session = session

    async def get_current_user(self,telegram_id:str)->User:
        stmt = await self.session.execute(
            select(User).where(User.telegram_id ==telegram_id)
            )
        user = stmt.scalar_one_or_none()

        if not user:
            raise HTTPException(
                detail="User is not registered\Please Register first!",
                status_code=404
            )
        return user
    
    async def get_current_user_with_password(self,telegram_id:str)->User:
        user = await self.get_current_user(telegram_id)
        if not user.password:
            raise HTTPException(
                detail="User is not fully registered\Please Register first!",
                status_code=403
            ) 
        return user

    async def adding_subjects_by_csv(self,file:UploadFile)->str:
        if file.content_type not in ALLOWED_CONTENT_TYPES:
            raise HTTPException(detail="File type not allowed. Allowed only for .csv!",status_code=400)
    
        if file.filename.split('.')[-1].lower() not in ALLOWED_EXTENSIONS:
            raise HTTPException(detail="File type not allowed. Allowed only for .csv!",status_code=400)
        
        df = pd.read_csv(file.file)
        data_lst =  df.to_dict(orient="records")
        
        
        try:
            data = [CreateFullUserByCsv(**row)  for row in data_lst]
            
            stmp = delete(User)
            await self.session.execute(stmp)
            
            for i in data:
                
                user_data = i.model_dump()
                group_name = user_data.pop("group_name")

                group_res = await self.session.execute(select(Group).where(Group.group_name == group_name))
                group = group_res.scalar_one_or_none()
                
                if not group:
                    raise HTTPException(422, detail=f"Group not found: {group_name}")

                stmt = await self.session.execute(
                    select(Class).where(Class.group_id == group.id))
                classes = stmt.scalars().all()
                
                user =User(**user_data)
                user.classes = classes
                user.group_id = group.id
                self.session.add(user)
                
            await self.session.commit()

            return "successfully updated whole database"

        except ValidationError as e:
            raise HTTPException(detail=str(e),status_code=422)
        except Exception as e:
            raise HTTPException(detail = str(e),status_code=500)
        

    async def is_user_exist(self,telegram_id:str)->bool:
        stmt = await self.session.execute(select(User).where(User.telegram_id ==telegram_id))
        user = stmt.scalar_one_or_none()

        
        if user:
            if user.eclass_registered == None:
                user.eclass_registered = datetime.now(ZoneInfo("Asia/Tashkent"))
            return True
        
        else:
            return False



    async def register_by_student_id(self,student_id:str,telegram_id:str)->User:
        
        query = await self.session.execute(select(User).where(User.student_id == student_id))

        
        user = query.scalar_one_or_none()

        if not user:
            raise HTTPException(detail="Incorrect student id\nIf any trouble please contact with admin!",status_code=403)
        
        if user.password:
            raise HTTPException(detail="user must register with password",status_code=300)
        
        user.telegram_id = telegram_id

        await self.session.commit()
        return user
    

    async def register_with_password(self,student_id:str,password:str,session:AsyncSession)->bool:
        c = EclassClient()
        query = await self.session.execute(select(User).where(User.student_id == student_id))
        user = query.scalar_one_or_none()
        result,err = await c.check_credentials(user.student_id,password)

        if result:
            user
            user.password == password
            await self.session.commit()
            return True
        else:
            return False

        

