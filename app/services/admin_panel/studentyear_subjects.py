from typing import List
from uuid import UUID
from app.api.schema.styear import MajorBase, Professors, SubjectOUT
from app.database.models import StudentYear,Major,Subject

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

class StYearService():
    def __init__(self,session:AsyncSession):
        self.session = session

    async def get_studentyear(self):
        stmt = await self.session.execute(
            select(StudentYear)
        )
        result = stmt.scalars().all()

        return result
    
    async def get_subjects_by_styear_id(self, sty_id: UUID) -> List[SubjectOUT]:
        stmt = await self.session.execute(
            select(Subject)
            .where(Subject.student_year_id == sty_id)
        )

        subjects = stmt.scalars().all()

        if not subjects:
            raise HTTPException(detail="Subjects not found",status_code=404)

        # Convert to Pydantic models
        result = []
        for subj in subjects:
            # Convert majors
            majors_out = [
                MajorBase(id=major.id, major_name=major.major_name)
                for major in getattr(subj, "majors", [])
            ]
            # Convert professors from classes (unique)
            professors_set = set()
            professors_out = []
            for klass in getattr(subj, "classes", []):
                if klass.professor and klass.professor.name not in professors_set:
                    professors_set.add(klass.professor.name)
                    professors_out.append(Professors(name=klass.professor.name))

            result.append(
                SubjectOUT(
                    id=subj.id,
                    short_name=subj.short_name,
                    name=subj.name,
                    majors=majors_out,
                    professors=professors_out,
                )
            )

        return result


    async def add_styear(self,year_name,starting_year,graduation_year):
        existing_stmt = await self.session.execute(
        select(StudentYear).where(StudentYear.year_name == year_name)
    )
        existing = existing_stmt.scalar_one_or_none()

        if existing:
            raise HTTPException(detail="Student year already exists")

        new_year = StudentYear(
          
            year_name=year_name,
            starting_year=starting_year,
            graduation_year=graduation_year,
        )

        self.session.add(new_year)
        await self.session.commit()
        await self.session.refresh(new_year)

        return new_year
    

    