from app.database.models import Users


from typing import List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select


from fastapi import HTTPException
class UserService():
    def __init__(self,session:AsyncSession):
        self.session = session

    async def get_all_users_by_group_name(self,group_name:str)->List[Users]:
        stmt = select(Users).where(Users.group_name==group_name,Users.telegram_id is not None)
        query = await self.session.execute(stmt)
        return query.scalars().all()


    async def get_user_by_telegram_id(self,telegram_id:str)->Users|None:
        query = await self.session.execute(select(Users).where(Users.telegram_id == telegram_id))
        user = query.scalar()
        if not user:
            raise HTTPException(detail="User not found",status_code=404)
        return user
    
    async def register_by_student_id(self,student_id:str,telegram_id)->Users:
        
        query = await self.session.execute(select(Users).where(Users.student_id == student_id))
        user = query.scalar_one_or_none()

        if not user:
            raise HTTPException(detail="Incorrect student_id",status_code=403)
        
        user.telegram_id = telegram_id

        await self.session.commit()
        return user
    
    async def is_user_exist(self,telegram_id:str)->bool:
        stmt = await self.session.execute(select(Users).where(Users.telegram_id ==telegram_id))
        user = stmt.scalar_one_or_none()
        if user:
            return True
        else:
            return False
        