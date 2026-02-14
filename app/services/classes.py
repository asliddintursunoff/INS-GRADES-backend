from fastapi import HTTPException,UploadFile
from pydantic_core import ValidationError

from sqlalchemy import delete, select
from app.database.models import Class,Weeks,Subject,Group,Professor,ClassTime
from datetime import time

from sqlalchemy.ext.asyncio import AsyncSession
import pandas as pd
from pydantic import BaseModel,field_validator

class ClassBase(BaseModel):
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


    
ALLOWED_CONTENT_TYPES = [
    "text/csv",
    
]
ALLOWED_EXTENSIONS = ["csv",]


class ClassService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def adding_classes_by_csv(self, file: UploadFile) -> str:
        if file.content_type not in ALLOWED_CONTENT_TYPES:
            raise HTTPException(status_code=400, detail="File type not allowed. Allowed only for .csv!")
        if file.filename.split(".")[-1].lower() not in ALLOWED_EXTENSIONS:
            raise HTTPException(status_code=400, detail="File type not allowed. Allowed only for .csv!")

        df = pd.read_csv(file.file)
        data_lst = df.to_dict(orient="records")

        try:
            data = [ClassBase(**row) for row in data_lst]

            # If you really want a full reset:
            # delete class_times first (FK), then classes
            await self.session.execute(delete(ClassTime))
            await self.session.execute(delete(Class))

            # Caches to reduce DB queries (big speedup)
            subject_cache: dict[str, Subject] = {}
            group_cache: dict[str, Group] = {}
            prof_cache: dict[str, Professor] = {}
            class_cache: dict[tuple[str, str], Class] = {}  # (group_name, subject_name) -> Class

            for i in data:
                # --- Subject ---
                subject = subject_cache.get(i.subject)
                if not subject:
                    res = await self.session.execute(select(Subject).where(Subject.name == i.subject))
                    subject = res.scalar_one_or_none()
                    if not subject:
                        raise HTTPException(status_code=404, detail=f"Subject not found: {i.subject}")
                    subject_cache[i.subject] = subject

                # --- Group ---
                group = group_cache.get(i.group_name)
                if not group:
                    res = await self.session.execute(select(Group).where(Group.group_name == i.group_name))
                    group = res.scalar_one_or_none()
                    if not group:
                        raise HTTPException(status_code=404, detail=f"Group not found: {i.group_name}")
                    group_cache[i.group_name] = group

                # --- Professor ---
                prof = prof_cache.get(i.professor)
                if not prof:
                    res = await self.session.execute(select(Professor).where(Professor.name == i.professor))
                    prof = res.scalar_one_or_none()
                    if not prof:
                        raise HTTPException(status_code=404, detail=f"Professor not found: {i.professor}")
                    prof_cache[i.professor] = prof

                # --- Class (unique by group_id + subject_id) ---
                cache_key = (i.group_name, i.subject)
                klass = class_cache.get(cache_key)

                if not klass:
                    res = await self.session.execute(
                        select(Class).where(
                            Class.group_id == group.id,
                            Class.subject_id == subject.id,
                        )
                    )
                    klass = res.scalar_one_or_none()

                    if not klass:
                        klass = Class(group_id=group.id, subject_id=subject.id, professor_id=prof.id)
                        self.session.add(klass)
                        # flush to get klass.id for ClassTime without committing
                        await self.session.flush()
                    else:
                        # ensure professor is updated (optional)
                        klass.professor_id = prof.id

                    class_cache[cache_key] = klass

                # --- ClassTime (schedule row) ---
                # optional: prevent duplicates by checking existing before insert
                # (recommended if you might re-upload same CSV)
                exists = await self.session.execute(
                    select(ClassTime).where(
                        ClassTime.class_id == klass.id,
                        ClassTime.week_day == i.week_day,
                        ClassTime.start_time == i.start_time,
                        ClassTime.end_time == i.end_time,
                        ClassTime.room == i.room,
                    )
                )
                if exists.scalar_one_or_none() is None:
                    self.session.add(
                        ClassTime(
                            class_id=klass.id,
                            room=i.room,
                            week_day=i.week_day,
                            start_time=i.start_time,
                            end_time=i.end_time,
                        )
                    )

            await self.session.commit()
            return "successfully updated whole database"

        except ValidationError as e:
            raise HTTPException(status_code=422, detail=str(e))
        except HTTPException:
            # re-raise cleanly
            raise
        except Exception as e:
            await self.session.rollback()
            raise HTTPException(status_code=500, detail=str(e))