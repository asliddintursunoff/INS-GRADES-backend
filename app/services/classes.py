from fastapi import HTTPException,UploadFile
from psycopg2 import IntegrityError
from pydantic_core import ValidationError

from sqlalchemy import delete, select
from app.database.models import Class, Enrollment,Weeks,Subject,Group,Professor,ClassTime
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
            rows = [ClassBase(**row) for row in data_lst]

            # ✅ Full reset in correct FK order:
            # Enrollment -> ClassTime -> Class
            await self.session.execute(delete(Enrollment))
            await self.session.execute(delete(ClassTime))
            await self.session.execute(delete(Class))
            await self.session.commit()

            # ✅ Caches (speed)
            subject_cache: dict[str, Subject] = {}
            group_cache: dict[str, Group] = {}
            prof_cache: dict[str, Professor] = {}
            class_cache: dict[tuple[str, str], Class] = {}  # (group_name, subject_name) -> Class

            for r in rows:
                # -------------------------
                # Subject
                # -------------------------
                subject = subject_cache.get(r.subject)
                if not subject:
                    res = await self.session.execute(select(Subject).where(Subject.name == r.subject))
                    subject = res.scalar_one_or_none()
                    if not subject:
                        raise HTTPException(status_code=404, detail=f"Subject not found: {r.subject}")
                    subject_cache[r.subject] = subject

                # -------------------------
                # Group
                # -------------------------
                group = group_cache.get(r.group_name)
                if not group:
                    res = await self.session.execute(select(Group).where(Group.group_name == r.group_name))
                    group = res.scalar_one_or_none()
                    if not group:
                        raise HTTPException(status_code=404, detail=f"Group not found: {r.group_name}")
                    group_cache[r.group_name] = group

                # -------------------------
                # Professor
                # -------------------------
                prof = prof_cache.get(r.professor)
                if not prof:
                    res = await self.session.execute(select(Professor).where(Professor.name == r.professor))
                    prof = res.scalar_one_or_none()
                    if not prof:
                        raise HTTPException(status_code=404, detail=f"Professor not found: {r.professor}")
                    prof_cache[r.professor] = prof

                # -------------------------
                # Class (unique by group_id + subject_id)
                # -------------------------
                cache_key = (r.group_name, r.subject)
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
                        klass = Class(
                            group_id=group.id,
                            subject_id=subject.id,
                            professor_id=prof.id
                        )
                        self.session.add(klass)
                        await self.session.flush()  # get klass.id
                    else:
                        # optional: update professor
                        if klass.professor_id != prof.id:
                            klass.professor_id = prof.id
                            self.session.add(klass)

                    class_cache[cache_key] = klass

                # -------------------------
                # ClassTime (schedule row)
                # -------------------------
                # ✅ Hard validation so you immediately see bad CSV values
                if r.week_day is None or r.start_time is None:
                    raise HTTPException(
                        status_code=422,
                        detail=f"Invalid ClassTime row (week_day/start_time missing): {r.model_dump()}"
                    )

                # ✅ Insert (no exists-check; avoids NULL comparison issues)
                self.session.add(
                    ClassTime(
                        class_id=klass.id,
                        room=r.room,
                        week_day=r.week_day,
                        start_time=r.start_time,
                        end_time=r.end_time,
                    )
                )

            try:
                await self.session.commit()
            except IntegrityError as e:
                await self.session.rollback()
                raise HTTPException(
                    status_code=409,
                    detail=f"DB integrity error (maybe duplicate ClassTime rows). Add UNIQUE constraint or clean CSV. {str(e)}"
                )

            return "successfully updated whole database"

        except ValidationError as e:
            raise HTTPException(status_code=422, detail=str(e))
        except HTTPException:
            raise
        except Exception as e:
            await self.session.rollback()
            raise HTTPException(status_code=500, detail=str(e))



    

    async def update_existing_classtimes_by_csv(self, file: UploadFile) -> dict:
        """
        Updates ONLY existing ClassTime rows for existing classes.
        - No deletes
        - No creates (no new Class/ClassTime/Subject/Group/Professor)
        Matching rules:
          Class: (group_name + subject)
          ClassTime: (week_day + start_time) within that class
        Updates:
          room, end_time (optionally professor_id if you enable it below)
        """
        if file.content_type not in ALLOWED_CONTENT_TYPES:
            raise HTTPException(status_code=400, detail="File type not allowed. Allowed only for .csv!")
        if file.filename.split(".")[-1].lower() not in ALLOWED_EXTENSIONS:
            raise HTTPException(status_code=400, detail="File type not allowed. Allowed only for .csv!")

        df = pd.read_csv(file.file)
        data_lst = df.to_dict(orient="records")

        try:
            rows = [ClassBase(**row) for row in data_lst]

            # caches
            subject_cache: dict[str, Subject] = {}
            group_cache: dict[str, Group] = {}
            prof_cache: dict[str, Professor] = {}
            class_cache: dict[tuple[str, str], Class] = {}  # (group_name, subject_name) -> Class

            updated_count = 0

            for r in rows:
                # -------------------------
                # Subject (must exist)
                # -------------------------
                subject = subject_cache.get(r.subject)
                if not subject:
                    res = await self.session.execute(select(Subject).where(Subject.name == r.subject))
                    subject = res.scalar_one_or_none()
                    if not subject:
                        raise HTTPException(status_code=404, detail=f"Subject not found: {r.subject}")
                    subject_cache[r.subject] = subject

                # -------------------------
                # Group (must exist)
                # -------------------------
                group = group_cache.get(r.group_name)
                if not group:
                    res = await self.session.execute(select(Group).where(Group.group_name == r.group_name))
                    group = res.scalar_one_or_none()
                    if not group:
                        raise HTTPException(status_code=404, detail=f"Group not found: {r.group_name}")
                    group_cache[r.group_name] = group

                # -------------------------
                # Professor (must exist) - optional update
                # -------------------------
                prof = prof_cache.get(r.professor)
                if not prof:
                    res = await self.session.execute(select(Professor).where(Professor.name == r.professor))
                    prof = res.scalar_one_or_none()
                    if not prof:
                        raise HTTPException(status_code=404, detail=f"Professor not found: {r.professor}")
                    prof_cache[r.professor] = prof

                # -------------------------
                # Class MUST exist (no create)
                # -------------------------
                cache_key = (r.group_name, r.subject)
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
                        raise HTTPException(
                            status_code=404,
                            detail=f"Class not found for group={r.group_name}, subject={r.subject}"
                        )
                    class_cache[cache_key] = klass

                # OPTIONAL: update professor for existing class
                # (comment out if you want to NEVER touch professor)
                if klass.professor_id != prof.id:
                    klass.professor_id = prof.id
                    self.session.add(klass)

                # -------------------------
                # ClassTime MUST exist (no create)
                # Identify by (class_id + week_day + start_time)
                # -------------------------
                if r.week_day is None or r.start_time is None:
                    raise HTTPException(
                        status_code=422,
                        detail=f"Invalid CSV row (week_day/start_time missing): {r.model_dump()}"
                    )

                res = await self.session.execute(
                    select(ClassTime).where(
                        ClassTime.class_id == klass.id,
                        ClassTime.week_day == r.week_day,
                        ClassTime.start_time == r.start_time,
                    )
                )
                ct = res.scalar_one_or_none()
                if not ct:
                    raise HTTPException(
                        status_code=404,
                        detail=(
                            "ClassTime not found for "
                            f"group={r.group_name}, subject={r.subject}, week_day={r.week_day}, start_time={r.start_time}"
                        )
                    )

                # update fields
                ct.room = r.room
                ct.end_time = r.end_time
                self.session.add(ct)
                updated_count += 1

            try:
                await self.session.commit()
            except IntegrityError as e:
                await self.session.rollback()
                raise HTTPException(
                    status_code=409,
                    detail=f"DB integrity error while updating (maybe conflicts with UNIQUE constraints). {str(e)}"
                )

            return {"status": "ok", "updated_rows": updated_count}

        except ValidationError as e:
            raise HTTPException(status_code=422, detail=str(e))
        except HTTPException:
            raise
        except Exception as e:
            await self.session.rollback()
            raise HTTPException(status_code=500, detail=str(e))
